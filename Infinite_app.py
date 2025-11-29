import streamlit as st
import json
import requests
import random
from datetime import datetime
from openai import OpenAI

# ==========================================
# 1. CONFIGURATION & DESIGN SETTINGS
# ==========================================
st.set_page_config(
    page_title="The Infinite Tabletop",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS hacks for that "Design Council" polish
st.markdown("""
<style>
    .stChatMessage {
        border-radius: 10px;
        padding: 10px;
    }
    .stButton button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. STATE MANAGEMENT (The Architect)
# ==========================================
DEFAULT_STATE = {
    "history": [],
    "char_name": "Traveler",
    "char_class": "Adventurer",
    "char_level": 1,
    "hp_curr": 10,
    "hp_max": 10,
    "inventory": "Rations, Waterskin, Dagger",
    "api_key": ""
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def generate_image_url(prompt):
    """Uses Pollinations.ai (No key required) to generate scene imagery."""
    # Clean prompt for URL
    clean_prompt = prompt.replace(" ", "%20")
    # Add style modifiers for consistent D&D fantasy art look
    style = "fantasy%20concept%20art,%20dungeons%20and%20dragons,%20highly%20detailed,%20digital%20painting,%20cinematic%20lighting"
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20{style}?nologo=true"

def get_ai_response(user_input):
    """Communicates with OpenRouter/OpenAI."""
    if not st.session_state.api_key:
        return "⚠️ SYSTEM ERROR: Please enter an OpenRouter/OpenAI API Key in the sidebar to begin."
    
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1", # Switching to OpenRouter for model variety
        api_key=st.session_state.api_key,
    )

    # Dynamic System Prompt Injection (Context Awareness)
    system_prompt = f"""
    You are the Infinite Dungeon Master (Style: Brennan Lee Mulligan meets Matt Mercer).
    
    PLAYER CONTEXT:
    Name: {st.session_state.char_name} | Class: {st.session_state.char_class}
    Level: {st.session_state.char_level} | HP: {st.session_state.hp_curr}/{st.session_state.hp_max}
    Inventory: {st.session_state.inventory}
    
    INSTRUCTIONS:
    1. Narrate the adventure. Be evocative.
    2. Ask for dice rolls (D20) when necessary.
    3. If a visual scene description is needed, end your response with: [IMAGE: description of scene].
    4. Keep the story moving.
    """

    messages = [{"role": "system", "content": system_prompt}] + st.session_state.history
    
    try:
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://infinite-tabletop.streamlit.app",
                "X-Title": "The Infinite Tabletop",
            },
            model="meta-llama/llama-3.1-70b-instruct:free", # Using a solid free model via OpenRouter
            messages=messages,
            temperature=0.8, # High creativity
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ CONNECTION SEVERED: {str(e)}"

# ==========================================
# 4. SIDEBAR - THE CHARACTER SHEET & TOOLS
# ==========================================
with st.sidebar:
    st.title("📜 Character Sheet")
    
    # API Key Input
    st.session_state.api_key = st.text_input("OpenRouter API Key", type="password", help="Required for the DM brain.")
    
    # Stats Grid
    c1, c2 = st.columns(2)
    st.session_state.char_name = c1.text_input("Name", st.session_state.char_name)
    st.session_state.char_class = c2.text_input("Class", st.session_state.char_class)
    
    c3, c4, c5 = st.columns(3)
    st.session_state.char_level = c3.number_input("Lvl", value=st.session_state.char_level)
    st.session_state.hp_curr = c4.number_input("HP", value=st.session_state.hp_curr)
    st.session_state.hp_max = c5.number_input("Max", value=st.session_state.hp_max)
    
    st.session_state.inventory = st.text_area("Inventory", st.session_state.inventory)
    
    st.divider()
    
    # Dice Roller (Mechanical Support)
    st.subheader("🎲 Dice Tray")
    col_d20, col_d8, col_d6 = st.columns(3)
    if col_d20.button("D20"):
        roll = random.randint(1, 20)
        st.toast(f"You rolled a {roll}!")
        # We don't auto-send to chat to allow player agency, but they can type it.
        
    st.divider()

    # Save/Load System (Persistence)
    st.subheader("💾 Cartridge Slot")
    
    # Download
    game_state = {k: v for k, v in st.session_state.items() if k != "api_key"} # Don't save API key
    json_str = json.dumps(game_state, indent=2)
    st.download_button(
        label="Save Game (JSON)",
        data=json_str,
        file_name=f"save_{st.session_state.char_name}_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json"
    )
    
    # Upload
    uploaded_file = st.file_uploader("Load Game", type=["json"])
    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            for key, value in data.items():
                st.session_state[key] = value
            st.success("Game Loaded!")
            st.rerun()
        except Exception as e:
            st.error(f"Corrupted Cartridge: {e}")

# ==========================================
# 5. MAIN STAGE - NARRATIVE FLOW
# ==========================================
st.title("The Infinite Tabletop")
st.caption("Powered by the Omni-Mind Collective")

# Initialize Chat if empty
if not st.session_state.history:
    welcome_msg = "The mists part. The world waits. Who are you, and where do we begin?"
    st.session_state.history.append({"role": "assistant", "content": welcome_msg})

# Display Chat History
for message in st.session_state.history:
    with st.chat_message(message["role"]):
        content = message["content"]
        
        # Check for Image Injection (The "Delight" Factor)
        if "[IMAGE:" in content:
            parts = content.split("[IMAGE:")
            text_part = parts[0].strip()
            image_prompt = parts[1].replace("]", "").strip()
            
            st.markdown(text_part)
            st.image(generate_image_url(image_prompt), caption=image_prompt, use_container_width=True)
        else:
            st.markdown(content)

# User Input Logic
if prompt := st.chat_input("What do you do?"):
    # 1. Show User Message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.history.append({"role": "user", "content": prompt})
    
    # 2. Generate AI Response
    with st.chat_message("assistant"):
        with st.spinner("The DM is thinking..."):
            response = get_ai_response(prompt)
            
            # Parsing for Image Tags again for the new response
            if "[IMAGE:" in response:
                parts = response.split("[IMAGE:")
                text_part = parts[0].strip()
                image_prompt = parts[1].replace("]", "").strip()
                
                st.markdown(text_part)
                st.image(generate_image_url(image_prompt), caption="Visualized by Pollinations.ai", use_container_width=True)
            else:
                st.markdown(response)
                
    st.session_state.history.append({"role": "assistant", "content": response})