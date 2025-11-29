import streamlit as st
import json
import base64
import random
from datetime import datetime
from openai import OpenAI
from urllib.parse import urlencode

# ==========================================
# 1. VISUAL CONFIGURATION & CSS
# ==========================================
st.set_page_config(
    page_title="The Infinite Tabletop v3",
    page_icon="🎲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for the "Design Council" Polish
st.markdown("""
<style>
    /* Chat Bubbles */
    .stChatMessage {
        border-radius: 15px;
        padding: 15px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    
    /* Dice Buttons */
    div.stButton > button {
        background-color: #2b2b2b;
        color: #ffffff;
        border: 1px solid #4f4f4f;
        border-radius: 8px;
        transition: all 0.2s;
    }
    div.stButton > button:hover {
        background-color: #e63946;
        border-color: #e63946;
        color: white;
        transform: scale(1.05);
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. STATE & URL HANDLING
# ==========================================
DM_MODELS = {
    "Llama 3.1 70B (Free)": "meta-llama/llama-3.1-70b-instruct:free",
    "Claude 3.5 Sonnet": "anthropic/claude-3.5-sonnet",
    "GPT-4o Mini": "openai/gpt-4o-mini",
    "Mythomax 13B (RP)": "gryphe/mythomax-l2-13b",
}

# Check for URL parameters (The "World Seed" Logic)
query_params = st.query_params
initial_context = None

if "seed" in query_params:
    try:
        decoded = base64.b64decode(query_params["seed"]).decode('utf-8')
        initial_context = json.loads(decoded)
        st.toast("🌍 World Seed Loaded! Timeline Forked.", icon="⚡")
    except:
        st.error("Invalid Timeline Seed.")

DEFAULT_STATE = {
    "history": [],
    "char_name": initial_context.get("name", "Traveler") if initial_context else "Traveler",
    "char_class": initial_context.get("class", "Adventurer") if initial_context else "Adventurer",
    "char_level": 1,
    "hp_curr": 10,
    "hp_max": 10,
    "inventory": "Rations, Waterskin, Dagger",
    "api_key": "",
    "selected_model_name": "Llama 3.1 70B (Free)",
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

# Inject initial prompt if loaded from seed but history is empty
if initial_context and not st.session_state.history:
    st.session_state.history.append({
        "role": "assistant", 
        "content": f"The timeline shifts. You are {initial_context['name']}, a {initial_context['class']}. The world is exactly as you remember: {initial_context.get('desc', 'Unknown')}. What do you do?"
    })

# ==========================================
# 3. CORE FUNCTIONS
# ==========================================
def generate_image_url(prompt):
    clean_prompt = prompt.replace(" ", "%20")
    style = "fantasy%20rpg%20art,%20oil%20painting,%20dnd%205e,%20highly%20detailed,%20cinematic"
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20{style}?nologo=true"

def get_ai_response(user_input, dice_roll=None):
    if not st.session_state.api_key:
        return "⚠️ **SYSTEM HALT:** Please enter an API Key in the 'System' tab."

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=st.session_state.api_key)

    system_prompt = f"""
    You are the Infinite Dungeon Master.
    
    PLAYER: {st.session_state.char_name} ({st.session_state.char_class})
    HP: {st.session_state.hp_curr}/{st.session_state.hp_max}
    INVENTORY: {st.session_state.inventory}
    
    RULES:
    1. Narrate the adventure. Be evocative.
    2. DICE: If the user input contains [DICE ROLL], interpret the result purely.
       - Low roll (1-8): Failure or complication.
       - Mid roll (9-14): Mixed success or struggle.
       - High roll (15-20): Success.
       - 20: Critical Triumph.
    3. VISUALS: End responses with [IMAGE: <description>] when a new scene is set.
    """

    # Prepare message chain
    messages = [{"role": "system", "content": system_prompt}] + st.session_state.history
    
    # If this is a dice roll triggered event, we treat it as a user message
    if dice_roll:
        roll_msg = f"[SYSTEM: I rolled a {dice_roll}. Interpret this result.]"
        messages.append({"role": "user", "content": roll_msg})
    
    try:
        model = DM_MODELS[st.session_state.selected_model_name]
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            extra_headers={"HTTP-Referer": "https://infinite-tabletop.streamlit.app", "X-Title": "Infinite Tabletop"},
            temperature=0.8
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ **ORACLE FAILURE:** {str(e)}"

def roll_dice(sides):
    result = random.randint(1, sides)
    st.toast(f"🎲 Rolled a {result} on D{sides}!")
    
    # 1. Log the roll visibly (optional, or just in history)
    roll_text = f"🎲 **I rolled a {result} on a D{sides}!**"
    st.session_state.history.append({"role": "user", "content": roll_text})
    
    # 2. Trigger AI immediately to narrate the result
    with st.spinner(f"Adjudicating the {result}..."):
        response = get_ai_response(None, dice_roll=result)
        st.session_state.history.append({"role": "assistant", "content": response})
    st.rerun()

# ==========================================
# 4. SIDEBAR - THE COMMAND CENTER
# ==========================================
with st.sidebar:
    st.title("🧙‍♂️ Infinite Tabletop")
    
    tab_hero, tab_play, tab_sys = st.tabs(["👤 Hero", "🎲 Play", "⚙️ System"])
    
    # --- TAB 1: HERO SHEET ---
    with tab_hero:
        c1, c2 = st.columns(2)
        st.session_state.char_name = c1.text_input("Name", st.session_state.char_name)
        st.session_state.char_class = c2.text_input("Class", st.session_state.char_class)
        st.session_state.hp_curr = st.number_input("Current HP", value=st.session_state.hp_curr)
        st.session_state.hp_max = st.number_input("Max HP", value=st.session_state.hp_max)
        st.session_state.inventory = st.text_area("Inventory", st.session_state.inventory, height=150)

    # --- TAB 2: PLAY (DICE & TOOLS) ---
    with tab_play:
        st.subheader("Dice Tray")
        d_cols = st.columns(3)
        if d_cols[0].button("D4"): roll_dice(4)
        if d_cols[1].button("D6"): roll_dice(6)
        if d_cols[2].button("D8"): roll_dice(8)
        
        d_cols_2 = st.columns(3)
        if d_cols_2[0].button("D10"): roll_dice(10)
        if d_cols_2[1].button("D12"): roll_dice(12)
        if d_cols_2[2].button("D20", type="primary"): roll_dice(20) # Highlight D20
        
        st.divider()
        st.info("Clicking a die immediately sends the result to the DM.")

    # --- TAB 3: SYSTEM (SETTINGS & SHARE) ---
    with tab_sys:
        st.caption("Neural Engine")
        st.session_state.api_key = st.text_input("OpenRouter Key", value=st.session_state.api_key, type="password")
        st.session_state.selected_model_name = st.selectbox("Model", list(DM_MODELS.keys()))
        
        st.divider()
        st.caption("Persistence")
        
        # JSON Save
        save_data = {k:v for k,v in st.session_state.items() if k != "api_key"}
        st.download_button("💾 Save Cartridge", json.dumps(save_data), "save.json", "application/json")
        
        # Multiplayer / Share Link
        st.caption("Multiplayer (Timeline Fork)")
        if st.button("🔗 Generate Invite Link"):
            # Create a lightweight seed
            seed_data = {
                "name": st.session_state.char_name,
                "class": st.session_state.char_class,
                "desc": "Forked from a previous timeline."
            }
            seed_str = base64.b64encode(json.dumps(seed_data).encode()).decode()
            base_url = "http://localhost:8501" # In production this would be the actual URL
            link = f"{base_url}?seed={seed_str}"
            st.code(link, language=None)
            st.toast("Link generated! Send this to a friend.")

# ==========================================
# 5. MAIN STAGE
# ==========================================
if not st.session_state.history:
    intro = "The tavern is loud, but your corner is quiet. A shadowed figure approaches. 'I have a job,' they whisper. What do you do?"
    st.session_state.history.append({"role": "assistant", "content": intro})

# Chat Rendering
chat_container = st.container()
with chat_container:
    for msg in st.session_state.history:
        with st.chat_message(msg["role"], avatar="🧙‍♂️" if msg["role"] == "assistant" else "🗡️"):
            content = msg["content"]
            # Visual Parsing
            if "[IMAGE:" in content:
                parts = content.split("[IMAGE:")
                st.markdown(parts[0].strip())
                if len(parts) > 1:
                    prompt_img = parts[1].split("]")[0].strip()
                    st.image(generate_image_url(prompt_img), use_container_width=True)
            else:
                st.markdown(content)

# Input
if prompt := st.chat_input("Describe your action..."):
    # User Logic
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🗡️"):
        st.markdown(prompt)
    
    # DM Logic
    with st.chat_message("assistant", avatar="🧙‍♂️"):
        with st.spinner("The DM is plotting..."):
            response = get_ai_response(prompt)
            # Display logic
            if "[IMAGE:" in response:
                parts = response.split("[IMAGE:")
                st.markdown(parts[0].strip())
                if len(parts) > 1:
                    prompt_img = parts[1].split("]")[0].strip()
                    st.image(generate_image_url(prompt_img), use_container_width=True)
            else:
                st.markdown(response)
    
    st.session_state.history.append({"role": "assistant", "content": response})
