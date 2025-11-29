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
    page_title="Infinite Tabletop v4.3",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* Chat & Immersion */
    .stChatMessage { border-radius: 15px; padding: 15px; background-color: #262730; border: 1px solid #444; }
    
    /* Stats Bar */
    .stat-box { 
        background-color: #333; 
        padding: 10px; 
        border-radius: 8px; 
        text-align: center; 
        border: 1px solid #555;
        margin-bottom: 5px;
    }
    .stat-val { font-size: 1.5em; font-weight: bold; }
    .stat-label { font-size: 0.8em; text-transform: uppercase; color: #aaa; }
    
    /* Dice Buttons */
    div.stButton > button { width: 100%; border-radius: 6px; font-weight: 600; transition: 0.2s; }
    div.stButton > button:hover { border-color: #FFD700; color: #FFD700; }
    
    /* Gold/Silver Text */
    .currency { font-family: monospace; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. STATE & URL HANDLING
# ==========================================
# --- URL DECODER (Timeline Forking) ---
query_params = st.query_params
seed_payload = None
fork_success = False

if "seed" in query_params:
    try:
        decoded_bytes = base64.b64decode(query_params["seed"])
        seed_payload = json.loads(decoded_bytes.decode('utf-8'))
        fork_success = True
    except Exception as e:
        st.error(f"⚠️ Timeline Fork Failed: {e}")

# --- DEFAULTS ---
RACES = ["Human", "Elf", "Dwarf", "Halfling", "Orc", "Tiefling", "Dragonborn", "Gnome", "Warforged"]
CLASSES = ["Fighter", "Wizard", "Rogue", "Cleric", "Bard", "Paladin", "Ranger", "Barbarian", "Druid", "Sorcerer", "Warlock"]
RANDOM_NAMES = ["Thorne", "Elara", "Grom", "Vex", "Lyra", "Kael", "Seraphina", "Durnik", "Zane"]

# Inventory Initialization
if seed_payload and "inventory_data" in seed_payload:
    init_inv_df = pd.DataFrame(seed_payload["inventory_data"])
else:
    init_inv_df = pd.DataFrame([
        {"Item": "Rations", "Value": "5sp", "Rarity": "Common"},
        {"Item": "Dagger", "Value": "2gp", "Rarity": "Common"}
    ])

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
    "inventory_df": init_inv_df,
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

if fork_success:
    st.toast("🌍 Parallel Universe Loaded.", icon="⚡")

# ==========================================
# 3. CORE LOGIC & AUTONOMIC PARSER
# ==========================================
def generate_image_url(prompt):
    clean_prompt = prompt.replace(" ", "%20")
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20fantasy%20art?nologo=true"

def roll_dice_logic(sides):
    """Rolls a die, updates history, triggers DM."""
    result = random.randint(1, sides)
    
    # 1. User sees the roll
    st.toast(f"🎲 Rolled {result} (D{sides})")
    roll_msg = f"🎲 **I rolled a {result} on a D{sides}!**"
    st.session_state.history.append({"role": "user", "content": roll_msg})
    
    # 2. DM reacts
    with st.spinner("The DM adjudicates..."):
        resp = get_dm_response(None, dice_result=f"{result} (D{sides})")
        # Process the response (render + state update) is handled in the main loop logic normally, 
        # but here we must force a rerun or append directly.
        # To keep it clean, we append to history here and let the main loop render.
        st.session_state.history.append({"role": "assistant", "content": resp})
    st.rerun()

def parse_and_update_state(llm_response):
    """
    Scans the LLM response for a [STATE: ...] block.
    Updates st.session_state variables automatically.
    Returns the clean text (without the JSON block).
    """
    # Regex to find [STATE: { ... }] (non-greedy)
    match = re.search(r'\[STATE:\s*({.*?})\]', llm_response, re.DOTALL)
    
    if match:
        json_str = match.group(1)
        try:
            data = json.loads(json_str)
            
            # 1. HP Update
            if "hp_change" in data:
                change = int(data["hp_change"])
                st.session_state.hp_curr = max(0, min(st.session_state.hp_max, st.session_state.hp_curr + change))
                if change != 0:
                    st.toast(f"HP {'+' if change > 0 else ''}{change}", icon="❤️")

            # 2. Currency Update
            if "gold_change" in data:
                g_change = int(data["gold_change"])
                st.session_state.gold = max(0, st.session_state.gold + g_change)
                if g_change != 0: st.toast(f"{g_change} GP", icon="🪙")
                
            if "silver_change" in data:
                s_change = int(data["silver_change"])
                st.session_state.silver = max(0, st.session_state.silver + s_change)

            # 3. Inventory Update
            if "add_items" in data and isinstance(data["add_items"], list):
                for item in data["add_items"]:
                    # Expecting dict like {"Item": "Sword", "Value": "10gp", "Rarity": "Common"}
                    # Or just a string, which we handle gracefully
                    if isinstance(item, str):
                        new_row = {"Item": item, "Value": "?", "Rarity": "Common"}
                    else:
                        new_row = item
                    
                    # Add to DataFrame
                    st.session_state.inventory_df = pd.concat([
                        st.session_state.inventory_df, 
                        pd.DataFrame([new_row])
                    ], ignore_index=True)
                    st.toast(f"Added: {new_row['Item']}", icon="🎒")

            if "remove_items" in data and isinstance(data["remove_items"], list):
                for item_name in data["remove_items"]:
                    # Remove rows where Item column contains the name (case insensitive)
                    df = st.session_state.inventory_df
                    st.session_state.inventory_df = df[~df["Item"].str.contains(item_name, case=False, na=False)]
                    st.toast(f"Removed: {item_name}", icon="🗑️")

        except json.JSONDecodeError:
            print("Failed to parse State JSON")
        
        # Return text without the block
        return llm_response.replace(match.group(0), "").strip()
    
    return llm_response

def get_dm_response(user_input, dice_result=None):
    if not st.session_state.api_key or not st.session_state.custom_model_id:
        return "⚠️ **SYSTEM ERROR:** Credentials missing."

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=st.session_state.api_key)
    
    # Context Construction
    inv_list = st.session_state.inventory_df["Item"].tolist()
    inv_str = ", ".join(inv_list) if inv_list else "Empty"
    
    sys_prompt = f"""
    You are the Infinite Game Engine & DM.
    
    PLAYER STATUS:
    HP: {st.session_state.hp_curr}/{st.session_state.hp_max}
    Wealth: {st.session_state.gold} GP, {st.session_state.silver} SP
    Inventory: {inv_str}
    
    CRITICAL INSTRUCTION - STATE UPDATES:
    If the narrative changes HP, Gold, Silver, or Inventory, you MUST output a JSON block at the end of your response.
    Format: [STATE: {{"hp_change": int, "gold_change": int, "silver_change": int, "add_items": [{{"Item": "name", "Value": "val", "Rarity": "type"}}], "remove_items": ["name"]}}]
    
    Example: You take 5 damage and find 10 gold. -> [STATE: {{"hp_change": -5, "gold_change": 10}}]
    Example: You buy a Sword for 2 gold. -> [STATE: {{"gold_change": -2, "add_items": [{{"Item": "Sword", "Value": "5gp", "Rarity": "Common"}}]}}]
    
    Narrate normally. End scenes with [IMAGE: description].
    """

    messages = [{"role": "system", "content": sys_prompt}] + st.session_state.history
    
    if dice_result:
        messages.append({"role": "user", "content": f"[SYSTEM EVENT: Player rolled {dice_result}. Interpret result.]"})

    try:
        completion = client.chat.completions.create(
            model=st.session_state.custom_model_id,
            messages=messages,
            extra_headers={"HTTP-Referer": "https://infinite-tabletop.streamlit.app"},
            temperature=0.8
        )
        raw_content = completion.choices[0].message.content
        
        # Parse State and Return Clean Text
        clean_content = parse_and_update_state(raw_content)
        return clean_content
        
    except Exception as e:
        return f"⚠️ **Connection Failed:** {str(e)}"

# ==========================================
# 4. SIDEBAR COMMAND CENTER
# ==========================================
with st.sidebar:
    st.title("🧙‍♂️ Infinite Tabletop v4.3")
    
    # --- GATEKEEPER ---
    with st.expander("⚙️ Neural Engine", expanded=not bool(st.session_state.api_key)):
        key_input = st.text_input("OpenRouter Key", value=st.session_state.api_key, type="password")
        model_input = st.text_input("Model ID", value=st.session_state.custom_model_id, placeholder="e.g. meta-llama/llama-3.1-70b-instruct:free")
        if st.button("Connect"):
            st.session_state.api_key = key_input
            st.session_state.custom_model_id = model_input
            if key_input and model_input: st.rerun()

    if not st.session_state.api_key: st.stop()

    # --- TABS ---
    tab_hero, tab_play, tab_bag, tab_sys = st.tabs(["👤 Hero", "🎲 Play", "🎒 Bag", "🔗 Sys"])
    
    with tab_hero:
        # HUD for Auto-Updates
        col_hp, col_ac = st.columns(2)
        with col_hp:
            st.markdown(f"<div class='stat-box'><div class='stat-val'>{st.session_state.hp_curr}/{st.session_state.hp_max}</div><div class='stat-label'>Health</div></div>", unsafe_allow_html=True)
        with col_ac:
            st.markdown(f"<div class='stat-box'><div class='stat-val'>{st.session_state.gold}</div><div class='stat-label'>Gold</div></div>", unsafe_allow_html=True)
            
        c1, c2 = st.columns(2)
        st.session_state.char_name = c1.text_input("Name", st.session_state.char_name)
        if c2.button("Name Gen"): 
            st.session_state.char_name = random.choice(RANDOM_NAMES)
            st.rerun()
            
        st.session_state.char_race = st.selectbox("Race", RACES, index=RACES.index(st.session_state.char_race) if st.session_state.char_race in RACES else 0)
        st.session_state.char_class = st.selectbox("Class", CLASSES, index=CLASSES.index(st.session_state.char_class) if st.session_state.char_class in CLASSES else 0)
        
        # Manual Overrides
        with st.expander("Manual Edit"):
            st.session_state.hp_curr = st.number_input("Set HP", value=st.session_state.hp_curr)
            st.session_state.gold = st.number_input("Set Gold", value=st.session_state.gold)
            st.session_state.silver = st.number_input("Set Silver", value=st.session_state.silver)

    with tab_play:
        st.subheader("Dice Tray")
        d1, d2, d3 = st.columns(3)
        if d1.button("D4"): roll_dice_logic(4)
        if d2.button("D6"): roll_dice_logic(6)
        if d3.button("D8"): roll_dice_logic(8)
        
        d4, d5, d6 = st.columns(3)
        if d4.button("D10"): roll_dice_logic(10)
        if d5.button("D12"): roll_dice_logic(12)
        if d6.button("D20", type="primary"): roll_dice_logic(20)

    with tab_bag:
        # Editable DataFrame (Auto-updates reflect here on rerun)
        st.session_state.inventory_df = st.data_editor(
            st.session_state.inventory_df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Rarity": st.column_config.SelectboxColumn("Rarity", options=["Common", "Uncommon", "Rare", "Legendary"])
            }
        )

    with tab_sys:
        # Save/Share
        if st.button("🔗 Copy Share Link"):
            # Serialize
            inv_data = st.session_state.inventory_df.to_dict(orient="records")
            payload = {
                "char_name": st.session_state.char_name,
                "history": st.session_state.history[-4:], # Last 4 turns
                "hp_curr": st.session_state.hp_curr,
                "gold": st.session_state.gold,
                "silver": st.session_state.silver,
                "inventory_data": inv_data
            }
            b64 = base64.b64encode(json.dumps(payload).encode()).decode()
            link = f"http://localhost:8501?seed={b64}"
            st.code(link)

# ==========================================
# 5. MAIN NARRATIVE
# ==========================================
if not st.session_state.game_started:
    st.title("✨ Begin Your Adventure")
    st.markdown(f"**Hero:** {st.session_state.char_name or 'Nameless'}")
    
    if st.button("Start Game"):
        if not st.session_state.char_name:
            st.error("Name required.")
        else:
            # Starting Gold Roll
            g_roll = random.randint(10, 100)
            st.session_state.gold = g_roll
            st.session_state.game_started = True
            
            prompt = f"I am {st.session_state.char_name}, a {st.session_state.char_race} {st.session_state.char_class}. I have {g_roll} gold. Begin the story."
            st.session_state.history.append({"role": "user", "content": prompt})
            with st.spinner("World Building..."):
                resp = get_dm_response(prompt)
                st.session_state.history.append({"role": "assistant", "content": resp})
            st.rerun()

else:
    # Chat Interface
    st.title(f"{st.session_state.char_name}'s Journal")
    
    for msg in st.session_state.history:
        if "Begin the story" in msg["content"]: continue
        with st.chat_message(msg["role"], avatar="🧙‍♂️" if msg["role"] == "assistant" else "🗡️"):
            content = msg["content"]
            # Image Rendering
            if "[IMAGE:" in content:
                parts = content.split("[IMAGE:")
                st.markdown(parts[0].strip())
                if len(parts) > 1:
                    img_prompt = parts[1].split("]")[0].strip()
                    st.image(generate_image_url(img_prompt), use_container_width=True)
            else:
                st.markdown(content)

    if prompt := st.chat_input("What do you do?"):
        st.session_state.history.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🗡️"):
            st.markdown(prompt)
        
        with st.chat_message("assistant", avatar="🧙‍♂️"):
            with st.spinner("Thinking..."):
                resp = get_dm_response(prompt)
                # Render logic duplicated for immediate feedback
                if "[IMAGE:" in resp:
                    parts = resp.split("[IMAGE:")
                    st.markdown(parts[0].strip())
                    if len(parts) > 1:
                        st.image(generate_image_url(parts[1].split("]")[0]), use_container_width=True)
                else:
                    st.markdown(resp)
        
        st.session_state.history.append({"role": "assistant", "content": resp})
        # Rerun to update Sidebar Stats immediately if they changed
        st.rerun()
