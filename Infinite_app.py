import streamlit as st
import json
import base64
import random
import requests
from datetime import datetime
from openai import OpenAI

# ==========================================
# 1. VISUAL CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="The Infinite Tabletop v4",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* Immersion Tweaks */
    .stChatMessage { border-radius: 15px; padding: 15px; background-color: #262730; border: 1px solid #444; }
    div.stButton > button { width: 100%; border-radius: 8px; font-weight: bold; }
    
    /* Dice Buttons */
    .dice-btn { background-color: #444; color: white; }
    
    /* Character Card */
    .char-card { border: 1px solid #555; padding: 10px; border-radius: 10px; text-align: center; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. STATE MANAGEMENT
# ==========================================
DM_MODELS = {
    "Llama 3.1 70B (Free)": "meta-llama/llama-3.1-70b-instruct:free",
    "Claude 3.5 Sonnet": "anthropic/claude-3.5-sonnet",
    "GPT-4o": "openai/gpt-4o",
    "Mistral Large": "mistralai/mistral-large",
    "Custom...": "custom"
}

DEFAULT_STATE = {
    "history": [],
    "char_name": "Traveler",
    "char_class": "Commoner",
    "char_race": "Human",
    "char_stats": "STR:10 DEX:10 CON:10 INT:10 WIS:10 CHA:10",
    "hp_curr": 10,
    "hp_max": 10,
    "inventory": "Rations, Waterskin, Dagger",
    "char_img": "https://image.pollinations.ai/prompt/mysterious%20hooded%20figure%20fantasy%20art?nologo=true",
    "api_key": "",
    "selected_model_label": "Llama 3.1 70B (Free)",
    "custom_model_id": "",
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ==========================================
# 3. CORE LOGIC ENGINE
# ==========================================
def generate_image_url(prompt):
    """Pollinations.ai API for dynamic visuals"""
    clean_prompt = prompt.replace(" ", "%20")
    style = "fantasy%20rpg%20character%20portrait,%20dnd%205e,%20oil%20painting,%20masterpiece"
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20{style}?nologo=true"

def get_active_model():
    """Resolves the model ID based on user selection"""
    label = st.session_state.selected_model_label
    if label == "Custom...":
        return st.session_state.custom_model_id
    return DM_MODELS[label]

def ai_generate_character():
    """Uses the LLM to auto-roll a full character"""
    if not st.session_state.api_key:
        st.error("⚠️ API Key required for Neural Generation.")
        return

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=st.session_state.api_key)
    
    prompt = """
    Create a unique, interesting D&D 5e Level 1 Character. 
    Return ONLY a JSON object (no markdown) with these exact keys:
    {
        "name": "String",
        "race": "String",
        "class": "String",
        "stats": "String (e.g. 'STR:16 DEX:14...')",
        "hp": Integer,
        "inventory": "String list of items",
        "visual_description": "String describing appearance for an art generator"
    }
    """
    
    try:
        with st.spinner("Forging a new soul..."):
            response = client.chat.completions.create(
                model="meta-llama/llama-3.1-70b-instruct:free", # Use a cheap/free model for gen
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9
            )
            content = response.choices[0].message.content
            # Clean potential markdown wrapping
            content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)
            
            # Update State
            st.session_state.char_name = data.get("name", "Unknown")
            st.session_state.char_race = data.get("race", "Human")
            st.session_state.char_class = data.get("class", "Fighter")
            st.session_state.char_stats = data.get("stats", "Standard Array")
            st.session_state.hp_max = data.get("hp", 10)
            st.session_state.hp_curr = data.get("hp", 10)
            st.session_state.inventory = data.get("inventory", "None")
            
            # Generate Portrait
            desc = data.get("visual_description", f"{st.session_state.char_race} {st.session_state.char_class}")
            st.session_state.char_img = generate_image_url(desc)
            st.toast("New Character Generated!", icon="✨")
            st.rerun()
            
    except Exception as e:
        st.error(f"Generation Failed: {e}")

def get_dm_response(user_input, dice_result=None):
    """The Main Game Loop"""
    if not st.session_state.api_key:
        return "⚠️ **SYSTEM HALT:** Please configure your API Key in the System Tab."

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=st.session_state.api_key)
    
    # Context Injection
    sys_prompt = f"""
    You are the Infinite Dungeon Master.
    
    HERO CONTEXT:
    Name: {st.session_state.char_name} ({st.session_state.char_race} {st.session_state.char_class})
    Stats: {st.session_state.char_stats}
    HP: {st.session_state.hp_curr}/{st.session_state.hp_max}
    Inventory: {st.session_state.inventory}
    
    DIRECTIVES:
    1. Narrate the story with sensory details.
    2. If a dice roll is provided, adjudicate the result strictly.
    3. If a new scene/monster appears, end with: [IMAGE: <visual prompt>]
    """

    messages = [{"role": "system", "content": sys_prompt}] + st.session_state.history
    
    if dice_result:
        messages.append({"role": "user", "content": f"[SYSTEM EVENT: User rolled a {dice_result}. Result?]"})

    try:
        completion = client.chat.completions.create(
            model=get_active_model(),
            messages=messages,
            extra_headers={"HTTP-Referer": "https://infinite-tabletop.streamlit.app"},
            temperature=0.8
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ **Connection Lost:** {str(e)}"

def roll_dice(sides):
    res = random.randint(1, sides)
    st.toast(f"Rolled {res} (d{sides})")
    
    # Add to history invisible to user prompt, or as a system note
    st.session_state.history.append({"role": "user", "content": f"🎲 **I rolled a {res} on a d{sides}!**"})
    
    # Trigger DM
    with st.spinner("The Fates decide..."):
        resp = get_dm_response(None, dice_result=res)
        st.session_state.history.append({"role": "assistant", "content": resp})
    st.rerun()

# ==========================================
# 4. SIDEBAR - THE COMMAND DECK
# ==========================================
with st.sidebar:
    st.title("🧙‍♂️ Infinite Tabletop v4")
    
    tab_hero, tab_play, tab_sys = st.tabs(["👤 Hero", "🎲 Play", "⚙️ System"])
    
    # --- TAB 1: HERO (THE SOUL FORGE) ---
    with tab_hero:
        # Portrait
        st.image(st.session_state.char_img, caption=st.session_state.char_name, use_container_width=True)
        
        # Generator
        if st.button("✨ Auto-Generate New Hero", help="Uses AI to create a full character"):
            ai_generate_character()
        
        st.divider()
        
        # Manual Edit
        c1, c2 = st.columns(2)
        st.session_state.char_name = c1.text_input("Name", st.session_state.char_name)
        st.session_state.char_class = c2.text_input("Class", st.session_state.char_class)
        st.session_state.char_race = st.text_input("Race", st.session_state.char_race)
        
        c3, c4 = st.columns(2)
        st.session_state.hp_curr = c3.number_input("HP Now", value=st.session_state.hp_curr)
        st.session_state.hp_max = c4.number_input("HP Max", value=st.session_state.hp_max)
        
        st.session_state.char_stats = st.text_area("Stats", st.session_state.char_stats, height=70)
        st.session_state.inventory = st.text_area("Inventory", st.session_state.inventory, height=100)
        
        # Character Persistence (Load/Save ONLY Character Data)
        st.divider()
        st.caption("Soul Jar (Character Only)")
        
        char_data = {k: v for k, v in st.session_state.items() if k.startswith("char_") or k in ["hp_curr", "hp_max", "inventory"]}
        st.download_button("💾 Export Character", json.dumps(char_data), "character.json")
        
        uploaded_char = st.file_uploader("📂 Import Character", type=["json"])
        if uploaded_char:
            try:
                d = json.load(uploaded_char)
                for k, v in d.items(): st.session_state[k] = v
                st.success("Soul Imported!")
                st.rerun()
            except: st.error("Invalid Soul File")

    # --- TAB 2: PLAY (DICE) ---
    with tab_play:
        st.subheader("Dice Tray")
        col1, col2, col3 = st.columns(3)
        if col1.button("d4"): roll_dice(4)
        if col2.button("d6"): roll_dice(6)
        if col3.button("d8"): roll_dice(8)
        
        col4, col5, col6 = st.columns(3)
        if col4.button("d10"): roll_dice(10)
        if col5.button("d12"): roll_dice(12)
        if col6.button("d20", type="primary"): roll_dice(20)
        
        st.info("Dice rolls are immediately sent to the DM to influence the narrative.")

    # --- TAB 3: SYSTEM (SETTINGS & CAMPAIGN) ---
    with tab_sys:
        st.subheader("Neural Engine")
        st.session_state.api_key = st.text_input("OpenRouter Key", value=st.session_state.api_key, type="password")
        
        # Custom Model Logic
        st.session_state.selected_model_label = st.selectbox("LLM Model", list(DM_MODELS.keys()))
        if st.session_state.selected_model_label == "Custom...":
            st.session_state.custom_model_id = st.text_input("Enter Model ID (e.g. vendor/model-name)", value=st.session_state.custom_model_id)

        st.divider()
        st.subheader("Campaign State")
        st.caption("Saves the entire game history + character.")
        
        # Campaign Save
        full_state = {k:v for k,v in st.session_state.items() if k != "api_key"}
        st.download_button("💾 Save Campaign", json.dumps(full_state), "campaign_v4.json")
        
        # Campaign Load
        uploaded_game = st.file_uploader("📂 Load Campaign", type=["json"], key="game_load")
        if uploaded_game:
            try:
                d = json.load(uploaded_game)
                for k,v in d.items(): st.session_state[k] = v
                st.success("Timeline Restored!")
                st.rerun()
            except: st.error("Corrupted Timeline")

# ==========================================
# 5. MAIN NARRATIVE UI
# ==========================================
if not st.session_state.history:
    st.session_state.history.append({
        "role": "assistant", 
        "content": f"The adventure begins. You are {st.session_state.char_name}, a {st.session_state.char_race} {st.session_state.char_class}. Where are you?"
    })

# Render Chat
for msg in st.session_state.history:
    with st.chat_message(msg["role"], avatar="🧙‍♂️" if msg["role"] == "assistant" else st.session_state.char_img):
        content = msg["content"]
        if "[IMAGE:" in content:
            parts = content.split("[IMAGE:")
            st.markdown(parts[0].strip())
            if len(parts) > 1:
                img_prompt = parts[1].split("]")[0].strip()
                st.image(generate_image_url(img_prompt), use_container_width=True)
        else:
            st.markdown(content)

# Input Area
if prompt := st.chat_input("What do you do?"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=st.session_state.char_img):
        st.markdown(prompt)
        
    with st.chat_message("assistant", avatar="🧙‍♂️"):
        with st.spinner("The DM is thinking..."):
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
