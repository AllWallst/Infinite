import streamlit as st
import json
import random
import pandas as pd
import base64
import zlib
import re
from openai import OpenAI

# ==========================================
# 1. CONFIGURATION & URL DECODING (COMPRESSED)
# ==========================================
st.set_page_config(
    page_title="Infinite Tabletop v4.3",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stChatMessage { border-radius: 15px; padding: 15px; background-color: #262730; border: 1px solid #444; }
    div.stButton > button { width: 100%; border-radius: 6px; font-weight: 600; }
    .gold-text { color: #FFD700; font-weight: bold; font-family: monospace; font-size: 1.2em; }
    .hp-text { color: #FF4B4B; font-weight: bold; font-family: monospace; font-size: 1.2em; }
</style>
""", unsafe_allow_html=True)

# --- URL DECOMPRESSION LOGIC ---
query_params = st.query_params
seed_payload = None
fork_success = False

if "seed" in query_params:
    try:
        # 1. Decode Base64
        compressed = base64.b64decode(query_params["seed"])
        # 2. Decompress Zlib
        json_str = zlib.decompress(compressed).decode('utf-8')
        # 3. Load JSON
        seed_payload = json.loads(json_str)
        fork_success = True
    except Exception as e:
        st.error(f"⚠️ Corrupted Timeline Link: {e}")

# ==========================================
# 2. STATE INITIALIZATION
# ==========================================
RACES = ["Human", "Elf", "Dwarf", "Halfling", "Orc", "Tiefling", "Dragonborn", "Gnome", "Tabaxi", "Warforged"]
CLASSES = ["Fighter", "Wizard", "Rogue", "Cleric", "Bard", "Paladin", "Ranger", "Barbarian", "Druid", "Sorcerer", "Monk", "Warlock"]
RANDOM_NAMES = ["Thorne", "Elara", "Grom", "Vex", "Lyra", "Kael", "Seraphina", "Durnik", "Zane", "Mirella"]

# Hydrate State from Seed or Defaults
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
    "inventory_df": pd.DataFrame(seed_payload["inventory_data"]) if (seed_payload and "inventory_data" in seed_payload) else pd.DataFrame([
        {"Item": "Rations (1 day)", "Value": "5sp", "Rarity": "Common"},
        {"Item": "Waterskin", "Value": "2sp", "Rarity": "Common"},
        {"Item": "Dagger", "Value": "2gp", "Rarity": "Common"}
    ]),
    "char_img": "https://image.pollinations.ai/prompt/mysterious%20adventurer%20fantasy%20art?nologo=true"
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

if fork_success:
    st.toast("🌍 Timeline Fork Loaded. Connect Neural Engine to resume.", icon="⚡")

# ==========================================
# 3. LOGIC, COMPRESSION & AUTO-UPDATES
# ==========================================
def generate_image_url(prompt):
    clean_prompt = prompt.replace(" ", "%20")
    style = "fantasy%20rpg%20character%20portrait,%20dnd%205e,%20oil%20painting"
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20{style}?nologo=true"

def roll_starting_gold():
    roll = random.randint(1, 20)
    amounts = {5: 10, 10: 25, 15: 50, 19: 100, 20: 500}
    amount = 10 # Default
    for threshold, val in amounts.items():
        if roll <= threshold:
            amount = val
            break
    st.session_state.gold = amount
    return amount

def generate_compressed_link():
    """Compresses state using zlib to fix URL length issues."""
    inv_data = st.session_state.inventory_df.to_dict(orient="records")
    # Only keep last 3 messages to keep link small and relevant
    short_history = st.session_state.history[-3:] if len(st.session_state.history) > 3 else st.session_state.history
    
    payload = {
        "char_name": st.session_state.char_name,
        "char_race": st.session_state.char_race,
        "char_class": st.session_state.char_class,
        "hp_curr": st.session_state.hp_curr,
        "hp_max": st.session_state.hp_max,
        "gold": st.session_state.gold,
        "inventory_data": inv_data,
        "history": short_history
    }
    
    json_str = json.dumps(payload)
    # Compress
    compressed = zlib.compress(json_str.encode('utf-8'))
    b64_str = base64.b64encode(compressed).decode()
    
    base_url = "http://localhost:8501" # In production, this is your app's domain
    return f"{base_url}?seed={b64_str}"

def process_game_updates(response_text):
    """Parses hidden [DATA: ...] tags from the AI to update UI."""
    # Pattern to find [DATA: {...}]
    pattern = r"\[DATA:\s*({.*?})\]"
    match = re.search(pattern, response_text)
    
    clean_text = response_text
    
    if match:
        try:
            json_str = match.group(1)
            data = json.loads(json_str)
            
            # Auto-Update HP
            if "hp" in data:
                change = data["hp"]
                st.session_state.hp_curr = max(0, min(st.session_state.hp_max, st.session_state.hp_curr + change))
                msg = f"{'Healed' if change > 0 else 'Took'} {abs(change)} HP"
                st.toast(msg, icon="❤️" if change > 0 else "🩸")
                
            # Auto-Update Gold
            if "gold" in data:
                change = data["gold"]
                st.session_state.gold = max(0, st.session_state.gold + change)
                msg = f"{'Gained' if change > 0 else 'Spent'} {abs(change)} Gold"
                st.toast(msg, icon="💰")
            
            # Auto-Update Inventory (Simple Append)
            if "new_item" in data:
                new_item = {"Item": data["new_item"], "Value": "?", "Rarity": "Unknown"}
                st.session_state.inventory_df = pd.concat([st.session_state.inventory_df, pd.DataFrame([new_item])], ignore_index=True)
                st.toast(f"Acquired: {data['new_item']}", icon="🎒")

            # Remove the tag from the visible text so user doesn't see code
            clean_text = re.sub(pattern, "", response_text)
            
        except Exception as e:
            print(f"Auto-Update Error: {e}")
            
    return clean_text

def get_dm_response(user_input, dice_result=None):
    if not st.session_state.api_key or not st.session_state.custom_model_id:
        return "⚠️ **SYSTEM ERROR:** Credentials missing."

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=st.session_state.api_key)
    inv_str = st.session_state.inventory_df.to_string(index=False)
    
    sys_prompt = f"""
    You are the Infinite Dungeon Master.
    HERO: {st.session_state.char_name} | HP: {st.session_state.hp_curr}/{st.session_state.hp_max} | Gold: {st.session_state.gold}gp
    BAG: {inv_str}
    
    CRITICAL INSTRUCTION FOR AUTO-UPDATES:
    If the player's HP or Gold changes, or they get a specific new item, you MUST output a hidden JSON tag at the end of your response.
    Format: [DATA: {{"hp": -5, "gold": 10, "new_item": "Rusty Key"}}]
    - Use negative numbers for damage/cost.
    - Use positive numbers for healing/income.
    - Do NOT include the tag if no stats change.
    
    NARRATIVE:
    Narrate vividly. If [SYSTEM EVENT: Dice Roll] appears, judge it strictly (1=Fail, 20=Crit).
    End scenes with [IMAGE: visual description].
    """

    messages = [{"role": "system", "content": sys_prompt}] + st.session_state.history
    if dice_result:
        messages.append({"role": "user", "content": f"[SYSTEM EVENT: Rolled {dice_result}.]"})

    try:
        completion = client.chat.completions.create(
            model=st.session_state.custom_model_id,
            messages=messages,
            extra_headers={"HTTP-Referer": "https://infinite-tabletop.streamlit.app"},
            temperature=0.8
        )
        raw_content = completion.choices[0].message.content
        # Process the updates immediately
        clean_content = process_game_updates(raw_content)
        return clean_content
    except Exception as e:
        return f"⚠️ **Connection Failed:** {str(e)}"

def roll_dice(sides):
    res = random.randint(1, sides)
    # Log roll
    st.session_state.history.append({"role": "user", "content": f"🎲 **I rolled a {res} on a d{sides}!**"})
    
    with st.spinner(f"Rolling D{sides}..."):
        resp = get_dm_response(None, dice_result=res)
        st.session_state.history.append({"role": "assistant", "content": resp})
    st.rerun()

# ==========================================
# 4. SIDEBAR 
# ==========================================
with st.sidebar:
    st.title("🧙‍♂️ Infinite Tabletop v4.3")
    
    # Gatekeeper
    with st.expander("⚙️ Neural Engine (REQUIRED)", expanded=not bool(st.session_state.api_key)):
        temp_key = st.text_input("OpenRouter Key", value=st.session_state.api_key, type="password")
        temp_model = st.text_input("Custom Model ID", value=st.session_state.custom_model_id, placeholder="vendor/model-name")
        if st.button("💾 Connect"):
            st.session_state.api_key = temp_key
            st.session_state.custom_model_id = temp_model
            if temp_key and temp_model: st.rerun()

    if not st.session_state.api_key or not st.session_state.custom_model_id:
        st.stop()

    tab_char, tab_play, tab_sys = st.tabs(["👤 Hero", "🎲 Play", "🔗 System"])
    
    with tab_char:
        c1, c2 = st.columns([3, 1])
        st.session_state.char_name = c1.text_input("Name", st.session_state.char_name)
        if c2.button("🎲", key="rnd_name"):
            st.session_state.char_name = random.choice(RANDOM_NAMES)
            st.rerun()
            
        st.session_state.char_race = st.selectbox("Race", RACES, index=RACES.index(st.session_state.char_race) if st.session_state.char_race in RACES else 0)
        st.session_state.char_class = st.selectbox("Class", CLASSES, index=CLASSES.index(st.session_state.char_class) if st.session_state.char_class in CLASSES else 0)
        
        st.divider()
        # LIVE STATS
        kc1, kc2 = st.columns(2)
        st.session_state.hp_curr = kc1.number_input("HP", value=st.session_state.hp_curr)
        st.session_state.hp_max = kc2.number_input("Max", value=st.session_state.hp_max)
        
        st.markdown(f"<div class='hp-text'>❤️ HP: {st.session_state.hp_curr}/{st.session_state.hp_max}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='gold-text'>🪙 Gold: {st.session_state.gold}</div>", unsafe_allow_html=True)
        
        st.divider()
        st.caption("Inventory (Auto-updates enabled)")
        st.session_state.inventory_df = st.data_editor(st.session_state.inventory_df, num_rows="dynamic", use_container_width=True)

    with tab_play:
        st.subheader("Dice Tray")
        c_d1, c_d2, c_d3 = st.columns(3)
        if c_d1.button("d4"): roll_dice(4)
        if c_d2.button("d6"): roll_dice(6)
        if c_d3.button("d8"): roll_dice(8)
        c_d4, c_d5, c_d6 = st.columns(3)
        if c_d4.button("d10"): roll_dice(10)
        if c_d5.button("d12"): roll_dice(12)
        if c_d6.button("d20", type="primary"): roll_dice(20)

    with tab_sys:
        save_state = {k:v for k,v in st.session_state.items() if k not in ["api_key", "inventory_df"]}
        save_state["inventory_data"] = st.session_state.inventory_df.to_dict(orient="records")
        st.download_button("💾 Save JSON", json.dumps(save_state), "save.json")
        
        st.divider()
        st.caption("Multiplayer (Compressed Link)")
        if st.button("🔗 Generate Short Link"):
            link = generate_compressed_link()
            st.code(link, language=None)
            st.success("Link generated! (Compressed for easy sharing)")

# ==========================================
# 5. MAIN UI
# ==========================================
if not st.session_state.game_started:
    st.title("✨ Begin Your Adventure")
    st.markdown(f"**Hero:** {st.session_state.char_name or 'Nameless'} the {st.session_state.char_race} {st.session_state.char_class}")
    
    if st.button("🎲 Roll Gold & Start", type="primary"):
        if not st.session_state.char_name:
            st.error("Name your hero first!")
        else:
            roll_starting_gold()
            st.session_state.game_started = True
            intro = f"I am {st.session_state.char_name}, a Level 1 {st.session_state.char_race} {st.session_state.char_class}. I have {st.session_state.gold} gold. Start the story."
            st.session_state.history.append({"role": "user", "content": intro})
            with st.spinner("Building world..."):
                resp = get_dm_response(intro)
                st.session_state.history.append({"role": "assistant", "content": resp})
            st.rerun()
else:
    st.title(f"The Saga of {st.session_state.char_name}")

# Chat Rendering
for msg in st.session_state.history:
    if msg["role"] == "user" and "Start the story" in msg["content"]: continue
    
    with st.chat_message(msg["role"], avatar="🧙‍♂️" if msg["role"] == "assistant" else "🗡️"):
        content = msg["content"]
        # Image Parsing
        if "[IMAGE:" in content:
            parts = content.split("[IMAGE:")
            st.markdown(parts[0].strip())
            if len(parts) > 1:
                img_prompt = parts[1].split("]")[0].strip()
                st.image(generate_image_url(img_prompt), use_container_width=True)
        else:
            st.markdown(content)

# Input
if prompt := st.chat_input("What do you do?"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🗡️"):
        st.markdown(prompt)
    
    with st.chat_message("assistant", avatar="🧙‍♂️"):
        with st.spinner("Rolling..."):
            resp = get_dm_response(prompt)
            if "[IMAGE:" in resp:
                parts = resp.split("[IMAGE:")
                st.markdown(parts[0].strip())
                if len(parts) > 1:
                    st.image(generate_image_url(parts[1].split("]")[0]), use_container_width=True)
            else:
                st.markdown(resp)
    st.session_state.history.append({"role": "assistant", "content": resp})
