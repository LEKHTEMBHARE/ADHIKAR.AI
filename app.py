import os
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import requests
from pypdf import PdfReader
from PIL import Image
import json

app = Flask(__name__)

# ==========================================
# 🔑 API KEYS CONFIGURATION
# ==========================================
# Note: Production mein keys ko Environment Variables (.env) mein rakhna behtar hota hai.
GEMINI_API_KEY = "Paste Your Gemini PRo API kEY " 

# Configure Google API
genai.configure(api_key=GEMINI_API_KEY)

# --- MODEL SETUP ---
def get_working_model():
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Priority check for faster/better models
        if 'models/gemini-1.5-flash' in available_models: return genai.GenerativeModel('models/gemini-1.5-flash')
        if 'models/gemini-pro' in available_models: return genai.GenerativeModel('models/gemini-pro')
        if available_models: return genai.GenerativeModel(available_models[0])
        return None
    except:
        return None

model = get_working_model()

# --- HELPER FUNCTIONS ---
def extract_text_from_pdf(file_stream):
    try:
        reader = PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except:
        return ""

def text_to_speech_elevenlabs(text):
    if not ELEVENLABS_API_KEY or "PASTE_YOUR" in ELEVENLABS_API_KEY:
        return None
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = { 
        "Accept": "audio/mpeg", 
        "Content-Type": "application/json", 
        "xi-api-key": ELEVENLABS_API_KEY 
    }
    
    # Text truncation to avoid API errors (limit to 300 chars for audio)
    safe_text = text[:400] 
    
    data = { 
        "text": safe_text, 
        "model_id": "eleven_multilingual_v2", 
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.6} 
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200: 
            return response.content
        else:
            print(f"ElevenLabs Error: {response.text}") # Debugging ke liye
            return None
    except: 
        return None

# --- ROUTES ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    if not model: return jsonify({"reply": "Server Error: Model not loaded.", "audio_url": None})

    user_text = request.form.get('message', '')
    user_details_json = request.form.get('user_details', '{}') 
    file = request.files.get('file')
    
    # 1. User Profile Parsing
    try:
        ud = json.loads(user_details_json)
        profile_context = f"""
        USER PROFILE DATA:
        - Name: {ud.get('name', 'N/A')} | Age: {ud.get('age', 'N/A')}
        - State: {ud.get('state', 'N/A')} | Category: {ud.get('category', 'N/A')}
        - Profession: {ud.get('profession', 'N/A')} | Income: {ud.get('income', 'N/A')}
        - Farmer Status: {ud.get('farmer', 'No')} | Land Holder: {ud.get('aplbhudharak', 'No')}
        """
    except:
        profile_context = "User Profile: Not provided."

    # 2. File Context Processing
    context_text = ""
    image_parts = []

    if file:
        filename = file.filename.lower()
        if filename.endswith('.pdf'):
            context_text = f"DOCUMENT CONTEXT:\n{extract_text_from_pdf(file)}\n\n"
        elif filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            try:
                img = Image.open(file)
                image_parts.append(img)
            except: pass
    
    # 3. FINAL PROMPT (UPDATED FOR MULTILINGUAL SUPPORT)
    system_instruction = f"""
    You are a polite and helpful 'Government Scheme (Sarkari Yojana) Expert'.
    
    {profile_context}
    
    *** CRITICAL INSTRUCTION ON LANGUAGE ***
    1. **MIRROR THE USER'S LANGUAGE:** You must reply in the **EXACT SAME LANGUAGE** that the user uses in their question.
       - If user asks in **Marathi**, reply in **Marathi**.
       - If user asks in **Tamil**, reply in **Tamil**.
       - If user asks in **Hindi**, reply in **Hindi**.
       - If user asks in **English**, reply in **English**.
    
    2. **DO NOT** force Hindi if the user is speaking a regional language.
    
    *** DOMAIN INSTRUCTIONS ***
    1. Answer the user's question checking their ELIGIBILITY from the Profile Data above.
    2. If they ask for a scheme they are not eligible for (e.g., PM Kisan but 'Farmer: No'), politely explain why.
    3. Keep the answer concise (under 300 characters is best for Audio).
    """
    
    if image_parts:
        final_prompt = [system_instruction, "User Question: " + user_text, image_parts[0]]
    else:
        final_prompt = f"{system_instruction}\n\n{context_text}\nUser Question: {user_text}"

    try:
        # Generate Text
        response = model.generate_content(final_prompt)
        bot_reply = response.text
        
        # Generate Audio
        audio_content = text_to_speech_elevenlabs(bot_reply)
        audio_url = None
        
        if audio_content:
            # Static folder check
            if not os.path.exists('static'): os.makedirs('static')
            
            save_path = "static/reply.mp3"
            with open(save_path, "wb") as f: f.write(audio_content)
            
            # Cache busting ke liye random query param add kiya
            audio_url = "/" + save_path + "?t=" + str(os.urandom(4).hex())
            
        return jsonify({"reply": bot_reply, "audio_url": audio_url})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"reply": "Sorry, I encountered an error. Please try again.", "audio_url": None})

if __name__ == '__main__':
    if not os.path.exists('static'): os.makedirs('static')

    app.run(debug=True, port=5000)
