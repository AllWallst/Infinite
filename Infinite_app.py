import streamlit as st
import json
import random
import pandas as pd
import base64
from openai import OpenAI
from urllib.parse import urlencode

# ==========================================
# 1. CONFIGURATION & URL DECODING
# ==========================================
st.set_page_config(
    page_title="Infinite Tabletop v4.2",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stChatMessage { border-radius: 15px; padding: 15px; background-color: #262730; border: 1px solid #444; }
    div.stButton > button { width: 100%; border-radius: 6px; font-weight: 600; }
    .gold-text { color: #FFD700; font-weight: bold; font-family: monospace; font-size: 1.2em; }
    .stToast { background-color: #2b2b2b !important; }
</style>
""", unsafe_allow_html=True)

# --- TIMELINE FORK LOADER (URL HANDLING) ---
# We check this BEFORE initializing default state to override if needed
query_params = st.query_params
seed_payload = None
fork_success = False

if "seed" in query_params:
    try:
        # Decode Base64 -> JSON string -> Dictionary
        decoded_bytes = base64.b64decode(query_params["seed"])
        decoded_str = decoded_bytes.decode('utf-8')
        seed_payload = json.loads(decoded_str)
        fork_success = True
    except Exception as e:
        st.error(f"⚠️ Timeline Fork Failed: {e}")

# ==========================================
# 2. STATE INITIALIZATION
# ==========================================
RACES = ["Human", "Elf", "Dwarf", "Halfling", "Orc", "Tiefling", "Dragonborn", "Gnome", "Tabaxi", "Warforged"]
CLASSES = ["Fighter", "Wizard", "Rogue", "Cleric", "Bard", "Paladin", "Ranger", "Barbarian", "Druid", "Sorcerer", "Monk", "Warlock"]
RANDOM_NAMES = ["Thorne", "Elara", "Grom", "Vex", "Lyra", "Kael", "Seraphina", "Durnik", "Zane", "Mirella"]

# Determine Initial Values (Default vs Seeded)
init_char_name = seed_payload.get("char_name", "") if seed_payload else ""
init_char_race = seed_payload.get("char_race", "Human") if seed_payload else "Human"
init_char_class = seed_payload.get("char_class", "Fighter") if seed_payload else "Fighter"
init_hp_curr = seed_payload.get("hp_curr", 10) if seed_payload else 10
init_hp_max = seed_payload.get("hp_max", 10) if seed_payload else 10
init_gold = seed_payload.get("gold", 0) if seed_payload else 0
init_history = seed_payload.get("history", []) if seed_payload else []
init_game_started = True if seed_payload else False

# Inventory: Seed (List of Dicts) -> DataFrame, or Default DataFrame
if seed_payload and "inventory_data" in seed_payload:
    init_inv_df = pd.DataFrame(seed_payload["inventory_data"])
else:
    init_inv_df = pd.DataFrame([
        {"Item": "Rations (1 day)", "Value": "5sp", "Rarity": "Common"},
        {"Item": "Waterskin", "Value": "2sp", "Rarity": "Common"},
        {"Item": "Dagger", "Value": "2gp", "Rarity": "Common"}
    ])

DEFAULT_STATE = {
    "history": init_history,
    "game_started": init_game_started,
    "api_key": "",
    "custom_model_id": "", 
    "char_name": init_char_name,
    "char_race": init_char_race,
    "char_class": init_char_class,
    "hp_curr": init_hp_curr,
    "hp_max": init_hp_max,
    "gold": init_gold,
    "inventory_df": init_inv_df,
    "char_img": "https://image.pollinations.ai/prompt/mysterious%20adventurer%20fantasy%20art?nologo=true"
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

if fork_success:
    st.toast("🌍 Parallel Universe Loaded. Enter API Key to Resume.", icon="⚡")

# ==========================================
# 3. LOGIC & HELPERS
# ==========================================
def generate_image_url(prompt):
    clean_prompt = prompt.replace(" ", "%20")
    style = "fantasy%20rpg%20character%20portrait,%20dnd%205e,%20oil%20painting"
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20{style}?nologo=true"

def roll_starting_gold():
    roll = random.randint(1, 20)
    if roll <= 5: amount = 10
    elif roll <= 10: amount = 25
    elif roll <= 15: amount = 50
    elif roll <= 19: amount = 100
    else: amount = 500
    st.session_state.gold = amount
    return amount

def generate_share_link():
    """Serializes current state into a base64 URL parameter"""
    # 1. Convert Inventory DF to simple list of dicts
    inv_data = st.session_state.inventory_df.to_dict(orient="records")
    
    # 2. Grab only necessary state (Limit history to last 2 turns to prevent URL bloat)
    short_history = st.session_state.history[-4:] if len(st.session_state.history) > 4 else st.session_state.history
    
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
    
    # 3. Encode
    json_str = json.dumps(payload)
    b64_str = base64.b64encode(json_str.encode()).decode()
    
    # 4. Construct Link (Assumes running locally or on standard port, change base_url for production)
    base_url = "http://localhost:8501" # REPLACE with actual Streamlit Share URL if deployed
    return f"{base_url}?seed={b64_str}"

def get_dm_response(user_input, dice_result=None):
    if not st.session_state.api_key or not st.session_state.custom_model_id:
        return "⚠️ **SYSTEM ERROR:** Credentials missing."

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=st.session_state.api_key)
    inv_str = st.session_state.inventory_df.to_string(index=False)
    
    sys_prompt = f"""
    You are the Infinite Dungeon Master.
    HERO: {st.session_state.char_name} ({st.session_state.char_race} {st.session_state.char_class})
    STATUS: HP {st.session_state.hp_curr}/{st.session_state.hp_max} | Gold: {st.session_state.gold}gp
    BAG: {inv_str}
    
    TASK: Narrate the adventure. Manage gold/loot. End scenes with [IMAGE: description].
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
        return completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ **Connection Failed:** {str(e)}"

# ==========================================
# 4. SIDEBAR & GATEKEEPER
# ==========================================
with st.sidebar:
    st.title("🧙‍♂️ Infinite Tabletop v4.2")
    
    # --- GATEKEEPER ---
    # We expand this if the key is missing OR if we just loaded a seed (to prompt user to enter key)
    with st.expander("⚙️ Neural Engine (REQUIRED)", expanded=not bool(st.session_state.api_key)):
        st.info("Credentials required to animate the world.")
        temp_key = st.text_input("OpenRouter Key", value=st.session_state.api_key, type="password")
        temp_model = st.text_input("Custom Model ID", value=st.session_state.custom_model_id, placeholder="vendor/model-name")
        
        if st.button("💾 Connect Neural Link"):
            st.session_state.api_key = temp_key
            st.session_state.custom_model_id = temp_model
            if temp_key and temp_model:
                st.toast("Connected!", icon="🟢")
                st.rerun()
            else:
                st.error("Missing credentials.")

    if not st.session_state.api_key or not st.session_state.custom_model_id:
        st.warning("⚠️ Enter credentials above to proceed.")
        st.stop()

    # --- TABS ---
    tab_char, tab_inv, tab_sys = st.tabs(["👤 Hero", "🎒 Bag", "🔗 System"])
    
    with tab_char:
        c1, c2 = st.columns([3, 1])
        st.session_state.char_name = c1.text_input("Name", st.session_state.char_name)
        if c2.button("🎲"):
            st.session_state.char_name = random.choice(RANDOM_NAMES)
            st.rerun()
        st.session_state.char_race = st.selectbox("Race", RACES, index=RACES.index(st.session_state.char_race) if st.session_state.char_race in RACES else 0)
        st.session_state.char_class = st.selectbox("Class", CLASSES, index=CLASSES.index(st.session_state.char_class) if st.session_state.char_class in CLASSES else 0)
        
        vc1, vc2 = st.columns(2)
        st.session_state.hp_curr = vc1.number_input("HP Curr", value=st.session_state.hp_curr)
        st.session_state.hp_max = vc2.number_input("HP Max", value=st.session_state.hp_max)
        st.markdown(f"<div class='gold-text'>🪙 Gold: {st.session_state.gold}</div>", unsafe_allow_html=True)

    with tab_inv:
        st.session_state.inventory_df = st.data_editor(
            st.session_state.inventory_df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Rarity": st.column_config.SelectboxColumn("Rarity", options=["Common", "Uncommon", "Rare", "Legendary"])
            }
        )

    with tab_sys:
        st.caption("Persistence")
        # Standard JSON Save
        save_state = {k:v for k,v in st.session_state.items() if k not in ["api_key", "inventory_df"]}
        save_state["inventory_data"] = st.session_state.inventory_df.to_dict(orient="records")
        st.download_button("💾 Save File", json.dumps(save_state), "save.json")
        
        st.divider()
        st.caption("Multiplayer (Timeline Forking)")
        if st.button("🔗 Create Share Link"):
            link = generate_share_link()
            st.code(link, language=None)
            st.success("Link generated! Anyone with this link starts from this exact moment.")

# ==========================================
# 5. GAME START OR RESUME
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
            with st.spinner("World building..."):
                st.session_state.history.append({"role": "assistant", "content": get_dm_response(intro)})
            st.rerun()
else:
    # If loaded from link, show title
    st.title(f"The Saga of {st.session_state.char_name}")

# ==========================================
# 6. MAIN CHAT LOOP
# ==========================================
# Render History
for msg in st.session_state.history:
    if msg["role"] == "user" and "Start the story" in msg["content"]: continue
    
    with st.chat_message(msg["role"], avatar="🧙‍♂️" if msg["role"] == "assistant" else "🗡️"):
        content = msg["content"]
        if "[IMAGE:" in content:
            parts = content.split("[IMAGE:")
            st.markdown(parts[0].strip())
            if len(parts) > 1:
                img_prompt = parts[1].split("]")[0].strip()
                st.image(generate_image_url(img_prompt), use_container_width=True)
        else:
            st.markdown(content)

# Input
if prompt := st.chat_input("Action..."):
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
