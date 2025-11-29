import streamlit as st
import json
import random
import pandas as pd
from openai import OpenAI

# ==========================================
# 1. CONFIGURATION & STATE INITIALIZATION
# ==========================================
st.set_page_config(
    page_title="Infinite Tabletop v4.1",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* UI Polish */
    .stChatMessage { border-radius: 15px; padding: 15px; background-color: #262730; border: 1px solid #444; }
    div.stButton > button { width: 100%; border-radius: 6px; font-weight: 600; }
    .gold-text { color: #FFD700; font-weight: bold; font-family: monospace; font-size: 1.2em; }
</style>
""", unsafe_allow_html=True)

# Lists for Dropdowns
RACES = ["Human", "Elf", "Dwarf", "Halfling", "Orc", "Tiefling", "Dragonborn", "Gnome", "Tabaxi", "Warforged"]
CLASSES = ["Fighter", "Wizard", "Rogue", "Cleric", "Bard", "Paladin", "Ranger", "Barbarian", "Druid", "Sorcerer", "Monk", "Warlock"]
RANDOM_NAMES = ["Thorne", "Elara", "Grom", "Vex", "Lyra", "Kael", "Seraphina", "Durnik", "Zane", "Mirella"]

# Default State Setup
DEFAULT_STATE = {
    "history": [],
    "game_started": False,
    # System
    "api_key": "",
    "custom_model_id": "", # No defaults, user must provide
    # Character
    "char_name": "",
    "char_race": "Human",
    "char_class": "Fighter",
    "hp_curr": 10,
    "hp_max": 10,
    "gold": 0,
    "inventory_df": pd.DataFrame([
        {"Item": "Rations (1 day)", "Value": "5sp", "Rarity": "Common"},
        {"Item": "Waterskin", "Value": "2sp", "Rarity": "Common"},
        {"Item": "Dagger", "Value": "2gp", "Rarity": "Common"}
    ]),
    "char_img": "https://image.pollinations.ai/prompt/mysterious%20adventurer%20fantasy%20art?nologo=true"
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def generate_image_url(prompt):
    clean_prompt = prompt.replace(" ", "%20")
    style = "fantasy%20rpg%20character%20portrait,%20dnd%205e,%20oil%20painting"
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20{style}?nologo=true"

def roll_starting_gold():
    """Rolls a D20 to determine starting wealth bracket."""
    roll = random.randint(1, 20)
    if roll <= 5: amount = 10
    elif roll <= 10: amount = 25
    elif roll <= 15: amount = 50
    elif roll <= 19: amount = 100
    else: amount = 500 # Critical Success
    
    st.session_state.gold = amount
    st.toast(f"🪙 Wealth Roll: {roll}. You start with {amount} Gold Coins!", icon="💰")
    return roll, amount

def get_dm_response(user_input, dice_result=None):
    if not st.session_state.api_key or not st.session_state.custom_model_id:
        return "⚠️ **SYSTEM ERROR:** Credentials missing."

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=st.session_state.api_key)
    
    # Parse Inventory DF to string for Context
    inv_str = st.session_state.inventory_df.to_string(index=False)
    
    sys_prompt = f"""
    You are the Infinite Dungeon Master.
    
    HERO CONTEXT:
    Name: {st.session_state.char_name} | Race: {st.session_state.char_race} | Class: {st.session_state.char_class}
    HP: {st.session_state.hp_curr}/{st.session_state.hp_max} | Gold: {st.session_state.gold} gp
    INVENTORY:
    {inv_str}
    
    DIRECTIVES:
    1. Act as a D&D 5e DM. Narrate clearly and vividly.
    2. Manage the player's currency. If they buy something, narrate the gold deduction.
    3. If a dice roll is sent, interpret it strictly.
    4. End scene descriptions with [IMAGE: <visual description>]
    """

    messages = [{"role": "system", "content": sys_prompt}] + st.session_state.history
    
    if dice_result:
        messages.append({"role": "user", "content": f"[SYSTEM EVENT: User rolled a {dice_result}.]"})

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
# 3. SIDEBAR (SETUP & SHEET)
# ==========================================
with st.sidebar:
    st.title("🧙‍♂️ Infinite Tabletop v4.1")
    
    # --- SECTION 1: NEURAL ENGINE (GATEKEEPER) ---
    with st.expander("⚙️ Neural Engine (REQUIRED)", expanded=not st.session_state.game_started):
        st.info("Enter credentials to unlock the adventure.")
        
        # Temp inputs to allow "Save" button logic
        temp_key = st.text_input("OpenRouter API Key", value=st.session_state.api_key, type="password")
        temp_model = st.text_input("Custom Model ID", value=st.session_state.custom_model_id, placeholder="e.g. meta-llama/llama-3.1-70b-instruct:free")
        
        if st.button("💾 Save Connection Settings"):
            st.session_state.api_key = temp_key
            st.session_state.custom_model_id = temp_model
            if temp_key and temp_model:
                st.toast("Neural Link Established. AI Context Refreshed.", icon="🧠")
                st.rerun()
            else:
                st.error("Both Key and Model ID are required.")

    # --- BLOCKER: STOP IF NO CREDENTIALS ---
    if not st.session_state.api_key or not st.session_state.custom_model_id:
        st.warning("⚠️ Please configure the Neural Engine above to begin.")
        st.stop()

    # --- SECTION 2: CHARACTER SHEET ---
    tab_char, tab_inv, tab_sys = st.tabs(["👤 Hero", "🎒 Bag", "💾 System"])
    
    with tab_char:
        # Character Identity
        st.caption("Identity")
        c1, c2 = st.columns([3, 1])
        st.session_state.char_name = c1.text_input("Name", st.session_state.char_name)
        if c2.button("🎲", help="Auto-Name"):
            st.session_state.char_name = random.choice(RANDOM_NAMES)
            st.rerun()
            
        st.session_state.char_race = st.selectbox("Race", RACES, index=RACES.index(st.session_state.char_race) if st.session_state.char_race in RACES else 0)
        st.session_state.char_class = st.selectbox("Class", CLASSES, index=CLASSES.index(st.session_state.char_class) if st.session_state.char_class in CLASSES else 0)
        
        st.divider()
        st.caption("Vitals")
        vc1, vc2 = st.columns(2)
        st.session_state.hp_curr = vc1.number_input("HP Current", value=st.session_state.hp_curr)
        st.session_state.hp_max = vc2.number_input("HP Max", value=st.session_state.hp_max)
        
        st.markdown(f"<div class='gold-text'>🪙 Gold: {st.session_state.gold} gp</div>", unsafe_allow_html=True)

    with tab_inv:
        st.caption("Inventory Management")
        # Data Editor for structured inventory
        edited_df = st.data_editor(
            st.session_state.inventory_df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "Item": st.column_config.TextColumn("Item Name"),
                "Value": st.column_config.TextColumn("Value"),
                "Rarity": st.column_config.SelectboxColumn("Rarity", options=["Common", "Uncommon", "Rare", "Epic", "Legendary"])
            }
        )
        # Update state with edits
        st.session_state.inventory_df = edited_df

    with tab_sys:
        st.caption("Save/Load")
        # Serialize DataFrame for JSON save
        save_state = {k:v for k,v in st.session_state.items() if k not in ["api_key", "inventory_df"]}
        save_state["inventory_data"] = st.session_state.inventory_df.to_dict(orient="records")
        
        st.download_button("💾 Save Game", json.dumps(save_state), "save_v4.1.json")
        
        uploaded = st.file_uploader("📂 Load Game", type=["json"])
        if uploaded:
            try:
                data = json.load(uploaded)
                for k,v in data.items():
                    if k == "inventory_data":
                        st.session_state.inventory_df = pd.DataFrame(v)
                    else:
                        st.session_state[k] = v
                st.success("Loaded!")
                st.rerun()
            except: st.error("Bad File")

# ==========================================
# 4. GAME START SEQUENCE
# ==========================================
# If game hasn't started, show the "Begin" button to roll gold and init prompt
if not st.session_state.game_started:
    st.title("✨ Begin Your Adventure")
    st.markdown(f"**Hero:** {st.session_state.char_name or 'Nameless'} the {st.session_state.char_race} {st.session_state.char_class}")
    
    if st.button("🎲 Roll for Starting Gold & Begin Game", type="primary"):
        if not st.session_state.char_name:
            st.error("Please name your character first!")
        else:
            roll_starting_gold()
            st.session_state.game_started = True
            
            # Initial Prompt Injection
            intro_prompt = f"I am {st.session_state.char_name}, a Level 1 {st.session_state.char_race} {st.session_state.char_class}. I have {st.session_state.gold} gold pieces. Start the adventure in a tavern or dungeon entrance. Describe the scene."
            st.session_state.history.append({"role": "user", "content": intro_prompt})
            
            with st.spinner("Summoning the world..."):
                resp = get_dm_response(intro_prompt)
                st.session_state.history.append({"role": "assistant", "content": resp})
            st.rerun()
    st.stop() # Halt rendering the rest until clicked

# ==========================================
# 5. MAIN GAME LOOP
# ==========================================
st.title(f"The Saga of {st.session_state.char_name}")

# Render Chat
for msg in st.session_state.history:
    if msg["role"] == "user" and "Start the adventure" in msg["content"]: continue # Hide setup prompt
    
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
if prompt := st.chat_input("What do you do?"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🗡️"):
        st.markdown(prompt)
    
    with st.chat_message("assistant", avatar="🧙‍♂️"):
        with st.spinner("DM is thinking..."):
            response = get_dm_response(prompt)
            if "[IMAGE:" in response:
                parts = response.split("[IMAGE:")
                st.markdown(parts[0].strip())
                if len(parts) > 1:
                    img_prompt = parts[1].split("]")[0].strip()
                    st.image(generate_image_url(img_prompt), use_container_width=True)
            else:
                st.markdown(response)
    
    st.session_state.history.append({"role": "assistant", "content": response})
