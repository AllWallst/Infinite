import streamlit as st
import json
import random
from datetime import datetime
from openai import OpenAI

# ==========================================
# 1. CONFIGURATION & STYLING
# ==========================================
st.set_page_config(
    page_title="The Infinite Tabletop",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stChatMessage {
        border-radius: 10px;
        padding: 10px;
        border: 1px solid #333;
    }
    .stButton button {
        width: 100%;
        border-radius: 5px;
    }
    /* Hide the deploy button to keep immersion */
    .stDeployButton {display:none;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. STATE MANAGEMENT
# ==========================================
# Curated list of models known to be good DMs
DM_MODELS = {
    "Llama 3.1 70B (Free)": "meta-llama/llama-3.1-70b-instruct:free",
    "Claude 3.5 Sonnet": "anthropic/claude-3.5-sonnet",
    "GPT-4o Mini": "openai/gpt-4o-mini",
    "Mistral Large": "mistralai/mistral-large",
    "Mythomax 13B (RP Specialized)": "gryphe/mythomax-l2-13b",
}

DEFAULT_STATE = {
    "history": [],
    "char_name": "Traveler",
    "char_class": "Adventurer",
    "char_level": 1,
    "hp_curr": 10,
    "hp_max": 10,
    "inventory": "Rations, Waterskin, Dagger",
    "api_key": "",
    "selected_model_name": "Llama 3.1 70B (Free)",
    "custom_model_id": ""
}

for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ==========================================
# 3. LOGIC CORE
# ==========================================
def generate_image_url(prompt):
    """Generates visual assets via Pollinations."""
    clean_prompt = prompt.replace(" ", "%20")
    style = "fantasy%20art,%20dnd,%20cinematic,%20detailed"
    return f"https://image.pollinations.ai/prompt/{clean_prompt}%20{style}?nologo=true"

def get_active_model_id():
    """Determines which model string to send to OpenRouter."""
    if st.session_state.selected_model_name == "Custom Input":
        return st.session_state.custom_model_id
    return DM_MODELS[st.session_state.selected_model_name]

def get_ai_response(user_input):
    """Interacts with OpenRouter using the selected model."""
    if not st.session_state.api_key:
        return "⚠️ **SYSTEM HALT:** Please open the ⚙️ Settings in the sidebar and enter your OpenRouter API Key."

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=st.session_state.api_key,
    )

    # The Persona Injection
    system_prompt = f"""
    You are the Infinite Dungeon Master.
    Style: A mix of Brennan Lee Mulligan (improv/emotional hooks) and Matt Mercer (world-building/sensory detail).
    
    CURRENT PLAYER STATUS:
    Name: {st.session_state.char_name} | Class: {st.session_state.char_class}
    HP: {st.session_state.hp_curr}/{st.session_state.hp_max} | Level: {st.session_state.char_level}
    Inventory: {st.session_state.inventory}
    
    DIRECTIVES:
    1. Narrate the outcome of the user's action.
    2. If a check is needed, ask for a D20 roll.
    3. Use bolding for emphasis on key items or NPCs.
    4. DIRECTOR MODE: If a new location or monster appears, end your response with exactly: [IMAGE: <visual description>]
    """

    messages = [{"role": "system", "content": system_prompt}] + st.session_state.history

    try:
        model_id = get_active_model_id()
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://infinite-tabletop.streamlit.app",
                "X-Title": "The Infinite Tabletop",
            },
            model=model_id,
            messages=messages,
            temperature=0.8, 
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ **ORACLE DISCONNECT:** {str(e)}"

# ==========================================
# 4. SIDEBAR INTERFACE
# ==========================================
with st.sidebar:
    st.title("🧙‍♂️ The Infinite Tabletop")
    
    # --- SECTION A: SETTINGS COG ---
    with st.expander("⚙️ Game Settings", expanded=not bool(st.session_state.api_key)):
        st.caption("Configuration")
        
        # API Key
        st.session_state.api_key = st.text_input(
            "OpenRouter Key", 
            value=st.session_state.api_key, 
            type="password",
            help="Get one at openrouter.ai"
        )
        
        # Model Selector
        model_options = list(DM_MODELS.keys()) + ["Custom Input"]
        st.session_state.selected_model_name = st.selectbox(
            "AI DM Model", 
            options=model_options,
            index=model_options.index(st.session_state.selected_model_name) if st.session_state.selected_model_name in model_options else 0
        )
        
        # Custom Model Input (Conditional)
        if st.session_state.selected_model_name == "Custom Input":
            st.session_state.custom_model_id = st.text_input(
                "Model ID", 
                value=st.session_state.custom_model_id,
                placeholder="vendor/model-name"
            )
            
        if st.button("Clear History"):
            st.session_state.history = []
            st.rerun()

    st.divider()

    # --- SECTION B: CHARACTER SHEET ---
    st.subheader("📜 Character Sheet")
    c1, c2 = st.columns(2)
    st.session_state.char_name = c1.text_input("Name", st.session_state.char_name)
    st.session_state.char_class = c2.text_input("Class", st.session_state.char_class)
    
    c3, c4, c5 = st.columns(3)
    st.session_state.char_level = c3.number_input("Lvl", value=st.session_state.char_level, step=1)
    st.session_state.hp_curr = c4.number_input("HP", value=st.session_state.hp_curr, step=1)
    st.session_state.hp_max = c5.number_input("Max", value=st.session_state.hp_max, step=1)
    
    st.session_state.inventory = st.text_area("Inventory", st.session_state.inventory, height=100)
    
    # --- SECTION C: SAVE / LOAD ---
    st.divider()
    col_save, col_load = st.columns(2)
    
    # Save Logic
    save_data = {k: v for k, v in st.session_state.items() if k != "api_key"} # Security Excluson
    json_str = json.dumps(save_data, indent=2)
    col_save.download_button(
        "💾 Save", 
        data=json_str, 
        file_name="adventure_save.json", 
        mime="application/json"
    )
    
    # Load Logic
    uploaded_file = col_load.file_uploader("📂 Load", type=["json"], label_visibility="collapsed")
    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            for k, v in data.items():
                st.session_state[k] = v
            st.success("Loaded!")
            st.rerun()
        except Exception:
            st.error("Bad File")

# ==========================================
# 5. MAIN NARRATIVE INTERFACE
# ==========================================
st.title(f"The Saga of {st.session_state.char_name}")

if not st.session_state.history:
    intro = "The world is vast, dangerous, and waiting. Where do you find yourself right now?"
    st.session_state.history.append({"role": "assistant", "content": intro})

# Render Chat
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        content = msg["content"]
        # Image Parsing
        if "[IMAGE:" in content:
            parts = content.split("[IMAGE:")
            st.markdown(parts[0].strip())
            if len(parts) > 1:
                img_prompt = parts[1].split("]")[0].strip()
                st.image(generate_image_url(img_prompt), caption="Scene Visualization", use_container_width=True)
        else:
            st.markdown(content)

# Input
if prompt := st.chat_input("What do you do?"):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.history.append({"role": "user", "content": prompt})
    
    with st.chat_message("assistant"):
        with st.spinner("The Dungeon Master is rolling..."):
            response = get_ai_response(prompt)
            
            # Display immediately
            if "[IMAGE:" in response:
                parts = response.split("[IMAGE:")
                st.markdown(parts[0].strip())
                if len(parts) > 1:
                    img_prompt = parts[1].split("]")[0].strip()
                    st.image(generate_image_url(img_prompt), caption="Scene Visualization", use_container_width=True)
            else:
                st.markdown(response)
    
    st.session_state.history.append({"role": "assistant", "content": response})
