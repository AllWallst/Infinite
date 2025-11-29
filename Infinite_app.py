import streamlit as st
import json
import random
import pandas as pd
import base64
import re
from openai import OpenAI

# ==========================================
# 1. CONFIGURATION & CSS
# ==========================================
st.set_page_config(
    page_title="Infinite Tabletop v4.4",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stChatMessage { border-radius: 15px; padding: 15px; background-color: #262730; border: 1px solid #444; }
    .stat-box { background-color: #333; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #555; margin-bottom: 5px; }
    .stat-val { font-size: 1.5em; font-weight: bold; }
    .stat-label { font-size: 0.8em; text-transform: uppercase; color: #aaa; }
    div.stButton > button { width: 100%; border-radius: 6px; font-weight: 600; transition: 0.2s; }
    div.stButton > button:hover { border-color: #FFD700; color: #FFD700; }
    .update-badge { background-color: #1e3a8a; color: #93c5fd; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; margin-top: 5px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. STATE & DATA SANITIZATION
# ==========================================
# --- URL DECODER ---
query_params = st.query_params
seed_payload = None
if "seed" in query_params:
    try:
        decoded_bytes = base64.b64decode(query_params["seed"])
        seed_payload = json.loads(decoded_bytes.decode('utf-8'))
    except Exception: pass

# --- DEFAULTS ---
RACES = ["Human", "Elf", "Dwarf", "Halfling", "Orc", "Tiefling", "Dragonborn", "Gnome", "Warforged"]
CLASSES = ["Fighter", "Wizard", "Rogue", "Cleric", "Bard", "Paladin", "Ranger", "Barbarian", "Druid", "Sorcerer", "Warlock"]
RANDOM_NAMES = ["Thorne", "Elara", "Grom", "Vex", "Lyra", "Kael", "Seraphina", "Durnik", "Zane"]

# Inventory Safety Loader
def load_inventory(payload=None):
    """Loads inventory and strictly enforces types to prevent crashes."""
    if payload and "inventory_data" in payload:
        df = pd.DataFrame(payload["inventory_data"])
    else:
        df = pd.DataFrame([
            {"Item": "Rations", "Value": "5sp", "Rarity": "Common"},
            {"Item": "Dagger", "Value": "2gp", "Rarity": "Common"}
        ])
    
    # CRITICAL FIX: Ensure columns exist and are string types to prevent 'join' errors
    required_cols = ["Item", "Value", "Rarity"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str)
    
    return df

DEFAULT_STATE = {
    "history": seed_payload.get("history", []) if seed_payload else [],
    "game_started": True if seed_payload else False,
    "api_key": "",
    "custom_model_id": "", 
    "char_name": seed_payload.get("char_name", "") if seed_payload else "",
    "char_race": seed_payload.get("char_race", "Human") if seed_payload else "Human",
    "char_class": seed_payload.get("char_class", "Fighter") if seed_payload else "Fighter",
    "hp_curr": seed_payload.get("hp_curr", 10) if seed_payload else 10,
    "hp_max": seed_payload.get("hp_max", 10) if seed_payload else 10,
    "gold": seed_payload.get("gold", 0) if seed_payload else 0,
    "silver": seed_payload.get("silver", 0) if seed_payload else 0,
    "inventory_df": load_inventory(seed_payload),
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ==========================================
# 3. LOGIC ENGINE
# ==========================================
def generate_image_url(prompt):
    clean_prompt = prompt.replace(" ", "%20")
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20fantasy%20art?nologo=true"

def parse_and_update_state(llm_response):
    """
    Robust Parser V2: Looks for JSON code blocks.
    Extracts delta updates and applies them to session_state.
    """
    # Regex for ```json ... ``` or just { ... } at the end
    json_match = re.search(r'```json\n(.*?)\n```', llm_response, re.DOTALL)
    if not json_match:
        # Fallback for lazy models that forget the markdown
        json_match = re.search(r'(\{\s*"hp_diff".*?\})', llm_response, re.DOTALL)

    updates_found = []

    if json_match:
        json_str = json_match.group(1)
        try:
            data = json.loads(json_str)
            
            # 1. HP Math
            if "hp_diff" in data and isinstance(data["hp_diff"], int):
                diff = data["hp_diff"]
                st.session_state.hp_curr = max(0, min(st.session_state.hp_max, st.session_state.hp_curr + diff))
                if diff != 0: updates_found.append(f"HP {'+' if diff > 0 else ''}{diff}")

            # 2. Currency Math
            if "gold_diff" in data and isinstance(data["gold_diff"], int):
                g_diff = data["gold_diff"]
                st.session_state.gold = max(0, st.session_state.gold + g_diff)
                if g_diff != 0: updates_found.append(f"{g_diff} GP")

            if "silver_diff" in data and isinstance(data["silver_diff"], int):
                s_diff = data["silver_diff"]
                st.session_state.silver = max(0, st.session_state.silver + s_diff)

            # 3. Inventory Logic
            if "loot_obtained" in data and isinstance(data["loot_obtained"], list):
                for item in data["loot_obtained"]:
                    # Sanitize input
                    if isinstance(item, str):
                        new_row = {"Item": item, "Value": "?", "Rarity": "Common"}
                    elif isinstance(item, dict):
                        new_row = {
                            "Item": str(item.get("Item", "Unknown")),
                            "Value": str(item.get("Value", "?")),
                            "Rarity": str(item.get("Rarity", "Common"))
                        }
                    else:
                        continue
                        
                    st.session_state.inventory_df = pd.concat([
                        st.session_state.inventory_df, 
                        pd.DataFrame([new_row])
                    ], ignore_index=True)
                    updates_found.append(f"+{new_row['Item']}")

            if "loot_removed" in data and isinstance(data["loot_removed"], list):
                for item_name in data["loot_removed"]:
                    # Robust Case-Insensitive Removal
                    item_str = str(item_name)
                    df = st.session_state.inventory_df
                    # Keep rows that do NOT match the item name
                    st.session_state.inventory_df = df[~df["Item"].str.contains(re.escape(item_str), case=False, na=False)]
                    updates_found.append(f"-{item_str}")

            # Return clean text (remove the JSON block)
            clean_text = llm_response.replace(json_match.group(0), "").replace("```json", "").replace("```", "").strip()
            
            # Append a small system note to the text so the user knows state updated
            if updates_found:
                sys_note = f"\n\n<div class='update-badge'>SYSTEM UPDATE: {', '.join(updates_found)}</div>"
                return clean_text + sys_note
            return clean_text

        except json.JSONDecodeError:
            return llm_response # If parse fails, just return raw text
        except Exception as e:
            return f"{llm_response}\n\n[System Error parsing update: {str(e)}]"
            
    return llm_response

def get_dm_response(user_input, dice_result=None):
    if not st.session_state.api_key or not st.session_state.custom_model_id:
        return "⚠️ **SYSTEM ERROR:** Credentials missing."

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=st.session_state.api_key)
    
    # CRITICAL FIX: Ensure clean string list for Prompt Injection
    # Drop NaNs, force to string, then list
    clean_items = st.session_state.inventory_df["Item"].dropna().astype(str).tolist()
    inv_str = ", ".join(clean_items) if clean_items else "Empty"
    
    # Prompt Engineering: Strict JSON Enforcement
    sys_prompt = f"""
    You are the Infinite Game Engine.
    
    PLAYER: {st.session_state.char_name} | HP: {st.session_state.hp_curr}/{st.session_state.hp_max}
    WEALTH: {st.session_state.gold} GP, {st.session_state.silver} SP
    INVENTORY: {inv_str}
    
    INSTRUCTIONS:
    1. Narrate the adventure dynamically.
    2. VISUALS: End scenes with [IMAGE: <description>].
    3. STATE UPDATES: You MUST output a JSON code block at the VERY END if HP, Gold, or Inventory changes.
    
    JSON SCHEMA (Do not include markdown notes outside the block):
    ```json
    {{
      "hp_diff": 0, // Integer (negative for damage, positive for healing)
      "gold_diff": 0, // Integer change in gold
      "silver_diff": 0, // Integer change in silver
      "loot_obtained": [{{"Item": "Name", "Value": "10gp", "Rarity": "Common"}}],
      "loot_removed": ["ItemName"]
    }}
    ```
    If no change, omit the JSON block.
    """

    messages = [{"role": "system", "content": sys_prompt}] + st.session_state.history
    
    if dice_result:
        messages.append({"role": "user", "content": f"[SYSTEM EVENT: Player rolled {dice_result}. Adjudicate result.]"})

    try:
        completion = client.chat.completions.create(
            model=st.session_state.custom_model_id,
            messages=messages,
            extra_headers={"HTTP-Referer": "https://infinite-tabletop.streamlit.app"},
            temperature=0.8
        )
        raw_content = completion.choices[0].message.content
        return parse_and_update_state(raw_content)
        
    except Exception as e:
        return f"⚠️ **Connection Failed:** {str(e)}"

def roll_dice(sides):
    res = random.randint(1, sides)
    st.toast(f"Rolled {res} (d{sides})")
    
    # Append user action
    st.session_state.history.append({"role": "user", "content": f"🎲 **I rolled a {res} on a d{sides}!**"})
    
    # Trigger DM response
    with st.spinner("Calculating fate..."):
        resp = get_dm_response(None, dice_result=f"{res} (d{sides})")
        st.session_state.history.append({"role": "assistant", "content": resp})
    
    # Rerun to update Sidebar/HUD immediately
    st.rerun()

# ==========================================
# 4. SIDEBAR
# ==========================================
with st.sidebar:
    st.title("Infinite Tabletop v4.4")
    
    # Gatekeeper
    if not st.session_state.api_key:
        with st.expander("⚙️ Neural Config", expanded=True):
            key = st.text_input("API Key", type="password")
            model = st.text_input("Model ID", value="meta-llama/llama-3.1-70b-instruct:free")
            if st.button("Connect"):
                st.session_state.api_key = key
                st.session_state.custom_model_id = model
                st.rerun()
        st.stop()

    # HUD
    col_hp, col_gp, col_sp = st.columns(3)
    col_hp.markdown(f"<div class='stat-box'><div class='stat-val'>{st.session_state.hp_curr}</div><div class='stat-label'>HP</div></div>", unsafe_allow_html=True)
    col_gp.markdown(f"<div class='stat-box'><div class='stat-val'>{st.session_state.gold}</div><div class='stat-label'>GP</div></div>", unsafe_allow_html=True)
    col_sp.markdown(f"<div class='stat-box'><div class='stat-val'>{st.session_state.silver}</div><div class='stat-label'>SP</div></div>", unsafe_allow_html=True)
    
    tab_hero, tab_play, tab_bag, tab_sys = st.tabs(["👤", "🎲", "🎒", "💾"])
    
    with tab_hero:
        st.text_input("Name", key="char_name")
        st.selectbox("Class", CLASSES, key="char_class")
        st.selectbox("Race", RACES, key="char_race")
        st.number_input("Max HP", key="hp_max")

    with tab_play:
        c1, c2, c3 = st.columns(3)
        if c1.button("d4"): roll_dice(4)
        if c2.button("d6"): roll_dice(6)
        if c3.button("d8"): roll_dice(8)
        c4, c5, c6 = st.columns(3)
        if c4.button("d10"): roll_dice(10)
        if c5.button("d12"): roll_dice(12)
        if c6.button("d20", type="primary"): roll_dice(20)

    with tab_bag:
        # Data Editor with sanitized column config
        st.session_state.inventory_df = st.data_editor(
            st.session_state.inventory_df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Item": st.column_config.TextColumn("Item", required=True),
                "Value": st.column_config.TextColumn("Value"),
                "Rarity": st.column_config.SelectboxColumn("Rarity", options=["Common", "Uncommon", "Rare", "Legendary"])
            }
        )

    with tab_sys:
        if st.button("🔗 Generate Share Link"):
            # Safe Serialization
            # Convert DF to dict, force all to string to be safe
            inv_safe = st.session_state.inventory_df.astype(str).to_dict(orient="records")
            
            payload = {
                "char_name": st.session_state.char_name,
                "history": st.session_state.history[-4:], # Last 4 turns
                "hp_curr": st.session_state.hp_curr,
                "gold": st.session_state.gold,
                "inventory_data": inv_safe
            }
            b64 = base64.b64encode(json.dumps(payload).encode()).decode()
            st.code(f"http://localhost:8501?seed={b64}")

# ==========================================
# 5. MAIN STAGE
# ==========================================
if not st.session_state.game_started:
    st.title("✨ Begin Your Adventure")
    st.write(f"Welcome, **{st.session_state.char_name or 'Traveler'}**.")
    if st.button("Start Game"):
        st.session_state.gold = random.randint(10, 50)
        st.session_state.game_started = True
        
        start_prompt = f"I am {st.session_state.char_name}, a {st.session_state.char_race} {st.session_state.char_class}. I have {st.session_state.gold} gold. Begin."
        st.session_state.history.append({"role": "user", "content": start_prompt})
        
        with st.spinner("Initializing World..."):
            resp = get_dm_response(start_prompt)
            st.session_state.history.append({"role": "assistant", "content": resp})
        st.rerun()
else:
    # History
    for msg in st.session_state.history:
        if "Begin." in msg["content"]: continue
        with st.chat_message(msg["role"], avatar="🧙‍♂️" if msg["role"] == "assistant" else "🗡️"):
            content = msg["content"]
            # Render Images
            if "[IMAGE:" in content:
                parts = content.split("[IMAGE:")
                st.markdown(parts[0].strip(), unsafe_allow_html=True) # Allow HTML for the badges
                if len(parts) > 1:
                    img_prompt = parts[1].split("]")[0].strip()
                    st.image(generate_image_url(img_prompt), use_container_width=True)
            else:
                st.markdown(content, unsafe_allow_html=True)

    # Input
    if prompt := st.chat_input("What do you do?"):
        st.session_state.history.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🗡️"):
            st.markdown(prompt)
        
        with st.chat_message("assistant", avatar="🧙‍♂️"):
            with st.spinner("Thinking..."):
                resp = get_dm_response(prompt)
                
                # Render logic (duplicated for immediate feedback)
                if "[IMAGE:" in resp:
                    parts = resp.split("[IMAGE:")
                    st.markdown(parts[0].strip(), unsafe_allow_html=True)
                    if len(parts) > 1:
                        st.image(generate_image_url(parts[1].split("]")[0]), use_container_width=True)
                else:
                    st.markdown(resp, unsafe_allow_html=True)
        
        st.session_state.history.append({"role": "assistant", "content": resp})
        st.rerun()
