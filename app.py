import streamlit as st
import pandas as pd
import json
import re
from io import BytesIO
from fpdf import FPDF
import time
from datetime import datetime
import requests

# Try to import groq, provide fallback if not available
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    # Don't call st.warning() at import time if Streamlit not fully initialized in some contexts.
    # We'll show status in sidebar instead.

# Optional PDF reading
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# ---------------------------
# Page Configuration
# ---------------------------
st.set_page_config(
    page_title="Smart MCQ Generator",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------
# Custom CSS for Professional Look
# ---------------------------
def load_custom_css():
    st.markdown("""
    <style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Global Styles */
    .main {
        font-family: 'Inter', sans-serif;
    }
    
    /* Header Styles */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
    }
    
    .main-header h1 {
        color: white;
        font-size: 3rem;
        font-weight: 700;
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .main-header p {
        color: rgba(255,255,255,0.9);
        font-size: 1.2rem;
        margin: 0.5rem 0 0 0;
        font-weight: 300;
    }
    
    /* Card Styles */
    .info-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        border-left: 4px solid #667eea;
        margin: 1rem 0;
    }
    
    .feature-card {
        background: linear-gradient(145deg, #f8f9fa, #e9ecef);
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        margin: 1rem 0;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        transition: transform 0.3s ease;
    }
    
    .feature-card:hover {
        transform: translateY(-5px);
    }
    
    .feature-icon {
        font-size: 2.5rem;
        margin-bottom: 1rem;
    }
    
    /* Input Styles */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 2px solid #e1e5e9;
        font-family: 'Inter', sans-serif;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    /* Button Styles */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        font-family: 'Inter', sans-serif;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
    }
    
    /* Sidebar Styles */
    .css-1d391kg {
        background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);
    }
    
    /* Success/Error Messages */
    .stSuccess {
        background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
        border-radius: 8px;
    }
    
    .stError {
        background: linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%);
        border-radius: 8px;
    }
    
    /* Footer */
    .footer {
        text-align: center;
        padding: 2rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-top: 3rem;
    }
    
    .team-member {
        display: inline-block;
        margin: 0 1rem;
        padding: 0.5rem 1rem;
        background: rgba(255,255,255,0.2);
        border-radius: 20px;
        font-weight: 500;
    }
    
    /* Progress Bar */
    .progress-container {
        background: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    /* Auth Container */
    .auth-container {
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 60vh;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 15px;
        padding: 2rem;
    }
    
    .auth-box {
        background: white;
        padding: 3rem;
        border-radius: 15px;
        box-shadow: 0 15px 35px rgba(0,0,0,0.1);
        text-align: center;
        max-width: 400px;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------
# Helper Functions
# ---------------------------
def try_load_json(text):
    """Try to load JSON directly or find a JSON array inside the text."""
    try:
        return json.loads(text)
    except Exception:
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                return None
        return None

def parse_plain_mcqs(text):
    """Parse plain-text MCQs into list of dicts."""
    text = text.replace('\r\n', '\n').strip()
    if not text:
        return []

    # Split by numbered questions
    pattern = r'^\s*\d+\.\s*(.*?)(?=^\s*\d+\.|\Z)'
    blocks = re.findall(pattern, text, flags=re.M | re.S)

    if not blocks:
        blocks = [b.strip() for b in re.split(r'\n\s*\n', text) if b.strip()]

    parsed = []
    opt_pattern = re.compile(
        r'(?s)(?:^|[\n\r])\s*([a-dA-D])[\.\)]\s*(.*?)(?=(?:\n\s*[a-dA-D][\.\)]\s*)|\Z)',
        flags=re.M,
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        opts = [(m.group(1).lower(), m.group(2).strip()) for m in opt_pattern.finditer(block)]
        first_opt = opt_pattern.search(block)
        q_text = block[:first_opt.start()].strip() if first_opt else block.splitlines()[0].strip()

        answer_match = re.search(r'(?mi)^\s*Answer[:\s\-]*([a-dA-D])(?:[\)\.]?)\s*(.*)$', block)
        explanation_match = re.search(r'(?mi)^\s*Explanation[:\s\-]*(.*)$', block)

        options_list = ["", "", "", ""]
        for letter, content in opts:
            idx = ord(letter) - ord('a')
            if 0 <= idx < 4:
                options_list[idx] = content

        if not any(options_list):
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            for ln in lines[1:]:
                m = re.match(r'^([a-dA-D])[\.\)]\s*(.*)', ln)
                if m:
                    idx = ord(m.group(1).lower()) - ord('a')
                    if 0 <= idx < 4:
                        options_list[idx] = m.group(2).strip()

        if answer_match:
            ans_letter = answer_match.group(1).lower()
            ans_extra = answer_match.group(2).strip()
            idx = ord(ans_letter) - ord('a')
            if ans_extra:
                answer_text = f"{ans_letter}) {ans_extra}"
            else:
                opt_text = options_list[idx] if 0 <= idx < 4 else ""
                answer_text = f"{ans_letter}) {opt_text}" if opt_text else ans_letter
        else:
            answer_text = ""

        explanation_text = explanation_match.group(1).strip() if explanation_match else ""

        parsed.append({
            "question": q_text,
            "options": options_list,
            "answer": answer_text,
            "explanation": explanation_text
        })

    return parsed

def parse_mcqs(text):
    loaded = try_load_json(text)
    if isinstance(loaded, list):
        normalized = []
        for item in loaded:
            q = item.get("question") if isinstance(item, dict) else None
            opts = item.get("options") if isinstance(item, dict) else None
            ans = item.get("answer") if isinstance(item, dict) else ""
            expl = item.get("explanation") if isinstance(item, dict) else ""
            if isinstance(opts, list):
                opts_fixed = opts + [""]*(4 - len(opts)) if len(opts) < 4 else opts[:4]
            else:
                opts_fixed = ["", "", "", ""]
            normalized.append({
                "question": q if q else "",
                "options": opts_fixed,
                "answer": ans if ans else "",
                "explanation": expl if expl else ""
            })
        return normalized
    else:
        return parse_plain_mcqs(text)

def generate_mcqs(api_key, content, level, grade, num_mcqs):
    """Generate MCQs using Groq API with fallback method"""
    
    prompt = f"""
    Generate exactly {num_mcqs} high-quality multiple-choice questions based on the following content/topic: {content}
    
    Requirements:
    - Difficulty Level: {level}
    - Target Audience: {grade}
    - Each question should have exactly 4 options (A, B, C, D)
    - Only one correct answer per question
    - Include a brief, clear explanation for each answer
    - Questions should be educational and test understanding, not just memorization
    
    Please format your response as a JSON array with this exact structure:
    [
      {{
        "question": "Your question here?",
        "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
        "answer": "A) Correct option text",
        "explanation": "Brief explanation of why this answer is correct"
      }}
    ]
    
    Make sure the JSON is valid and properly formatted.
    """
    
    try:
        if GROQ_AVAILABLE:
            # Use official Groq client
            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert educational content creator specializing in generating high-quality multiple-choice questions. Always respond with valid JSON format."},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=4000
            )
            return chat_completion.choices[0].message.content
        else:
            # Fallback method using requests
            return generate_mcqs_fallback(api_key, prompt)
            
    except Exception as e:
        raise Exception(f"Error generating MCQs: {str(e)}")

def generate_mcqs_fallback(api_key, prompt):
    """Fallback method for MCQ generation using direct API calls"""
    try:
        # NOTE: This endpoint path and host may vary for Groq; update if your provider uses different URL.
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are an expert educational content creator specializing in generating high-quality multiple-choice questions. Always respond with valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        # This assumes the response is in OpenAI-like format. Adjust if Groq returns different structure.
        return result["choices"][0]["message"]["content"]
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"API request failed: {str(e)}")
    except Exception as e:
        raise Exception(f"Fallback method failed: {str(e)}")

# ---------------------------
# Authentication Functions
# ---------------------------
def display_authentication():
    """Display authentication screen"""
    st.markdown("""
    <div class="auth-container">
        <div class="auth-box">
            <h1 style="color: #667eea; margin-bottom: 1rem;">🔐 Smart MCQ Generator</h1>
            <p style="color: #666; margin-bottom: 2rem;">Please enter the access code to continue</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Center the input
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input(
            "Access Code:", 
            type="password", 
            placeholder="Enter your access code...",
            key="auth_password"
        )
        
        if st.button("🚀 Access Application", use_container_width=True, key="auth_button"):
            if password == "2004":
                st.session_state.authenticated = True
                st.success("✅ Access Granted! Redirecting...")
                time.sleep(1)
                st.rerun()  # Changed from experimental_rerun()
            else:
                st.error("❌ Invalid access code. Please try again.")

def check_authentication():
    """Check if user is authenticated"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    return st.session_state.authenticated

# ---------------------------
# Main Application Functions
# ---------------------------
def render_sidebar():
    """Render the sidebar configuration"""
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        
        # API Key Input
        st.markdown("### 🔑 API Configuration")
        
        # Show package status
        if GROQ_AVAILABLE:
            st.success("✅ Groq Package: Available")
        else:
            st.warning("⚠️ Groq Package: Using Fallback Method")
        
        api_key = st.text_input(
            "Groq API Key:",
            type="password",
            placeholder="Enter your Groq API key...",
            help="Get your free API key from https://console.groq.com",
            key="api_key_input"
        )
        
        if api_key:
            st.success("✅ API Key Configured")
        else:
            st.warning("⚠️ API Key Required")
        
        st.markdown("---")
        
        # MCQ Settings
        st.markdown("### 📊 MCQ Settings")
        
        level = st.selectbox(
            "Difficulty Level:",
            ["Beginner", "Intermediate", "Advanced"],
            help="Select the complexity level for your questions",
            key="difficulty_level"
        )
        
        grade = st.selectbox(
            "Target Grade:",
            [f"Grade {i}" for i in range(1, 13)] + ["University", "Professional"],
            index=4,
            help="Choose the appropriate academic level",
            key="target_grade"
        )
        
        num_mcqs = st.slider(
            "Number of Questions:",
            min_value=5,
            max_value=50,
            value=10,
            step=5,
            help="Select how many questions to generate",
            key="num_questions"
        )
        
        st.markdown("---")
        
        # Export Options
        st.markdown("### 📄 Export Options")
        include_answers = st.checkbox("Include Answers & Explanations", value=True, key="include_answers")
        exam_mode = st.checkbox("Exam Mode (Hide Answers)", value=False, key="exam_mode")
        
        st.markdown("---")
        
        # Installation Instructions
        if not GROQ_AVAILABLE:
            st.markdown("### 🔧 Installation Help")
            st.code("pip install groq", language="bash")
            st.caption("Run this command to install the Groq package")
        
        st.markdown("### 💡 Tips")
        st.markdown("""
        - **Topic Mode**: Enter any subject or topic
        - **File Mode**: Upload PDF or text files
        - **Best Results**: Provide specific, focused topics
        """)
    
    return api_key, level, grade, num_mcqs, include_answers, exam_mode

def render_content_input():
    """Render the main content input area"""
    st.markdown("## 📝 Content Input")
    
    # Input Method Selection
    input_method = st.radio(
        "Choose your input method:",
        ["📚 Enter Topic", "📁 Upload File"],
        horizontal=True,
        key="input_method"
    )
    
    content = ""
    
    if input_method == "📚 Enter Topic":
        st.markdown("### 💭 Topic Input")
        topic = st.text_area(
            "Enter your topic or subject:",
            placeholder="e.g., Photosynthesis, World War II, Calculus Derivatives, Python Programming...",
            height=100,
            help="Be specific for better results. You can enter multiple related topics.",
            key="topic_input"
        )
        if topic:
            content = topic.strip()
            
    elif input_method == "📁 Upload File":
        st.markdown("### 📎 File Upload")
        uploaded_file = st.file_uploader(
            "Upload your content file:",
            type=["pdf", "txt"],
            help="Supported formats: PDF, TXT (Max size: 200MB)",
            key="file_uploader"
        )
        
        if uploaded_file:
            with st.spinner("📖 Processing file..."):
                try:
                    if uploaded_file.type == "application/pdf":
                        if PDF_SUPPORT:
                            with pdfplumber.open(uploaded_file) as pdf:
                                content = ""
                                for page_num, page in enumerate(pdf.pages, 1):
                                    text = page.extract_text()
                                    if text:
                                        content += text + "\n"
                                    
                                    # Progress indicator for large files
                                    if len(pdf.pages) > 10:
                                        progress = page_num / len(pdf.pages)
                                        st.progress(progress, f"Processing page {page_num}/{len(pdf.pages)}")
                            
                            st.success(f"✅ PDF processed successfully! ({len(content)} characters extracted)")
                        else:
                            st.error("⚠️ PDF support not available. Please install pdfplumber or upload a .txt file.")
                    else:
                        content = uploaded_file.read().decode("utf-8")
                        st.success(f"✅ Text file loaded successfully! ({len(content)} characters)")
                except Exception as e:
                    st.error(f"❌ Error processing file: {str(e)}")
    
    return content

def render_features():
    """Render the features section"""
    st.markdown("## 🌟 Features")
    
    features = [
        {"icon": "🤖", "title": "AI-Powered", "desc": "Advanced AI generates contextual questions"},
        {"icon": "📊", "title": "Multiple Formats", "desc": "Export as PDF, CSV, or Google Forms"},
        {"icon": "🎯", "title": "Customizable", "desc": "Adjust difficulty and grade level"},
        {"icon": "⚡", "title": "Fast Generation", "desc": "Get results in seconds"}
    ]
    
    for feature in features:
        st.markdown(f"""
        <div class="feature-card">
            <div class="feature-icon">{feature['icon']}</div>
            <h4 style="margin: 0.5rem 0;">{feature['title']}</h4>
            <p style="margin: 0; color: #666;">{feature['desc']}</p>
        </div>
        """, unsafe_allow_html=True)

def handle_mcq_generation(api_key, content, level, grade, num_mcqs):
    """Handle MCQ generation process"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        generate_btn = st.button(
            "🚀 Generate MCQs",
            use_container_width=True,
            disabled=not (api_key and content.strip()),
            key="generate_button"
        )
    
    # Validation Messages
    if not api_key:
        st.warning("⚠️ Please enter your Groq API Key in the sidebar to continue.")
    elif not content.strip():
        st.warning("⚠️ Please provide content (topic or file) to generate questions from.")
    
    # MCQ Generation
    if generate_btn and api_key and content.strip():
        with st.spinner("🔄 Generating high-quality MCQs... This may take a moment."):
            try:
                # Progress bar simulation
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("🤖 Initializing AI model...")
                progress_bar.progress(20)
                time.sleep(0.5)
                
                status_text.text("📝 Analyzing content...")
                progress_bar.progress(50)
                
                mcqs_output = generate_mcqs(api_key, content, level, grade, num_mcqs)
                
                status_text.text("✨ Formatting questions...")
                progress_bar.progress(80)
                time.sleep(0.3)
                
                st.session_state["mcqs"] = mcqs_output
                st.session_state["generation_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state["generation_params"] = {
                    "level": level,
                    "grade": grade,
                    "num_mcqs": num_mcqs
                }
                
                progress_bar.progress(100)
                status_text.text("✅ MCQs generated successfully!")
                time.sleep(0.5)
                
                # Clear progress indicators
                progress_bar.empty()
                status_text.empty()
                
                st.success(f"🎉 Successfully generated {num_mcqs} MCQs!")
                
            except Exception as e:
                st.error(f"❌ Error generating MCQs: {str(e)}")
                st.info("💡 Tips to resolve this issue:")
                st.markdown("""
                - Check your internet connection
                - Verify your Groq API key is valid
                - Try reducing the number of questions
                - Ensure your content is clear and specific
                """)

def display_generated_mcqs(include_answers, exam_mode):
    """Display and handle generated MCQs"""
    if "mcqs" not in st.session_state:
        return
    
    st.markdown("---")
    st.markdown("## 📋 Generated MCQs")
    
    # Get generation parameters
    params = st.session_state.get("generation_params", {})
    
    # Metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Questions Generated", params.get("num_mcqs", "N/A"))
    with col2:
        st.metric("Difficulty Level", params.get("level", "N/A"))
    with col3:
        st.metric("Target Grade", params.get("grade", "N/A"))
    
    # Display generation time
    if "generation_time" in st.session_state:
        st.caption(f"Generated on: {st.session_state['generation_time']}")
    
    st.markdown("### ✏️ Edit Your MCQs")
    edited_mcqs = st.text_area(
        "Review and edit your questions below:",
        value=st.session_state["mcqs"],
        height=400,
        help="You can modify the generated questions, add more, or fix any formatting issues.",
        key="mcqs_editor"
    )
    
    # Update session state if edited
    if edited_mcqs != st.session_state["mcqs"]:
        st.session_state["mcqs"] = edited_mcqs
    
    # Preview MCQs in a nice format
    st.markdown("### 👀 Preview")
    try:
        mcq_list = parse_mcqs(st.session_state["mcqs"])
        if mcq_list:
            for i, mcq in enumerate(mcq_list[:3], 1):  # Show first 3 as preview
                with st.expander(f"Question {i}: {mcq['question'][:50]}..."):
                    st.markdown(f"**Question:** {mcq['question']}")
                    for idx, option in enumerate(mcq['options']):
                        if option:
                            st.markdown(f"**{chr(65+idx)})** {option}")
                    if not exam_mode:
                        st.markdown(f"**Answer:** {mcq['answer']}")
                        if mcq['explanation']:
                            st.markdown(f"**Explanation:** {mcq['explanation']}")
            
            if len(mcq_list) > 3:
                st.info(f"Showing preview of first 3 questions. Total: {len(mcq_list)} questions generated.")
        else:
            st.warning("⚠️ Could not parse the generated MCQs. Please check the format.")
    except Exception as e:
        st.error(f"Error parsing MCQs: {str(e)}")
    
    # Export Options
    render_export_options(include_answers, exam_mode)

def render_export_options(include_answers, exam_mode):
    """Render export options for MCQs"""
    st.markdown("### 📤 Export Options")
    
    col1, col2, col3 = st.columns(3)
    
    # Helper to make text safe for FPDF (latin-1)
    def safe_text(text):
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        # Replace unsupported characters with '?'
        try:
            return text.encode("latin-1", "replace").decode("latin-1")
        except Exception:
            # As a fallback, return a simplified ASCII form
            return text.encode("ascii", "replace").decode("ascii")

    with col1:
        if st.button("📕 Export as PDF", use_container_width=True, key="export_pdf"):
            try:
                with st.spinner("Creating PDF..."):
                    raw = st.session_state.get("mcqs", "")
                    mcq_list = parse_mcqs(raw)
                    params = st.session_state.get("generation_params", {})
                    
                    pdf = FPDF()
                    pdf.set_auto_page_break(auto=True, margin=15)
                    pdf.add_page()
                    
                    # Header
                    pdf.set_font("Arial", 'B', 16)
                    pdf.cell(0, 10, safe_text("Smart MCQ Generator - Question Bank"), ln=True, align='C')
                    pdf.ln(5)
                    
                    pdf.set_font("Arial", size=10)
                    pdf.cell(0, 8, safe_text(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), ln=True)
                    pdf.cell(0, 8, safe_text(f"Difficulty: {params.get('level', 'N/A')} | Grade: {params.get('grade', 'N/A')}"), ln=True)
                    pdf.ln(5)
                    
                    pdf.set_font("Arial", size=12)
                    
                    if mcq_list:
                        for i, mcq in enumerate(mcq_list, 1):
                            # Question
                            question_text = f"{i}. {mcq.get('question','')}"
                            pdf.multi_cell(0, 8, safe_text(question_text))
                            pdf.ln(1)
                            
                            # Options
                            for idx, opt in enumerate(mcq.get("options", ["", "", "", ""])):
                                if opt:
                                    label = chr(ord('A') + idx)
                                    opt_line = f"   {label}) {opt}"
                                    pdf.multi_cell(0, 8, safe_text(opt_line))
                            pdf.ln(1)
                            
                            # Answer & Explanation (if allowed)
                            if include_answers and not exam_mode:
                                if mcq.get("answer"):
                                    pdf.multi_cell(0, 8, safe_text(f"Answer: {mcq.get('answer')}"))
                                if mcq.get("explanation"):
                                    pdf.multi_cell(0, 8, safe_text(f"Explanation: {mcq.get('explanation')}"))
                            pdf.ln(4)
                    else:
                        # If parsing failed, dump raw text safely
                        for line in raw.splitlines():
                            pdf.multi_cell(0, 8, safe_text(line))
                    
                    # Prepare and send PDF bytes
                    pdf_bytes = pdf.output(dest="S").encode("latin-1", "replace")
                    pdf_out = BytesIO(pdf_bytes)
                    
                    st.download_button(
                        "📥 Download PDF",
                        data=pdf_out,
                        file_name=f"mcqs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="download_pdf"
                    )
                    st.success("✅ PDF created successfully!")
                    
            except Exception as e:
                st.error(f"❌ Error creating PDF: {str(e)}")
    
    with col2:
        if st.button("📊 Export as CSV", use_container_width=True, key="export_csv"):
            try:
                with st.spinner("Creating CSV..."):
                    raw = st.session_state.get("mcqs", "")
                    mcq_list = parse_mcqs(raw)
                    params = st.session_state.get("generation_params", {})
                    
                    if mcq_list:
                        rows = []
                        for m in mcq_list:
                            rows.append({
                                "question": m.get("question", ""),
                                "option_a": m.get("options", ["", "", "", ""])[0],
                                "option_b": m.get("options", ["", "", "", ""])[1],
                                "option_c": m.get("options", ["", "", "", ""])[2],
                                "option_d": m.get("options", ["", "", "", ""])[3],
                                "answer": m.get("answer", ""),
                                "explanation": m.get("explanation", ""),
                                "difficulty": params.get("level", "N/A"),
                                "grade": params.get("grade", "N/A"),
                                "generated_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
                        df = pd.DataFrame(rows)
                        csv = df.to_csv(index=False).encode("utf-8")
                    else:
                        df = pd.DataFrame({"text": raw.splitlines()})
                        csv = df.to_csv(index=False).encode("utf-8")
                    
                    st.download_button(
                        "📥 Download CSV",
                        data=csv,
                        file_name=f"mcqs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="download_csv"
                    )
                    st.success("✅ CSV created successfully!")
                    
            except Exception as e:
                st.error(f"❌ Error creating CSV: {str(e)}")
    
    with col3:
        if st.button("📝 Google Forms Guide", use_container_width=True, key="google_forms"):
            st.info("""
            📋 **How to create Google Forms:**
            1. Copy your MCQs above
            2. Go to Google Forms: https://forms.google.com
            3. Create a new form
            4. Paste and format your questions
            5. Share with students!
            """)

def render_footer():
    """Render the footer section"""
    st.markdown("---")
    st.markdown("""
    <div class="footer">
        <h3 style="margin-bottom: 1rem;">👥 Development Team</h3>
        <div>
            <span class="team-member">💼 Engr. Azhar</span>
            <span class="team-member">💼 Engr. Khubaib</span>
            <span class="team-member">⚡ Engr. Fawad</span>
            <span class="team-member">🚀 Engr. Arfa</span>
            <span class="team-member">💡 Engr. M Zain</span>
            <span class="team-member">🎯 Engr. Rehman</span>
        </div>
        <p style="margin-top: 1rem; opacity: 0.8;">Built with ❤️ using Streamlit & Groq AI</p>
    </div>
    """, unsafe_allow_html=True)

def main_application():
    """Main application function"""
    # Load custom CSS
    load_custom_css()
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🎯 Smart MCQ Generator</h1>
        <p>Generate Professional Multiple Choice Questions with AI</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar Configuration
    api_key, level, grade, num_mcqs, include_answers, exam_mode = render_sidebar()
    
    # Main Content Area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        content = render_content_input()
    
    with col2:
        render_features()
    
    # Generation Section
    st.markdown("---")
    handle_mcq_generation(api_key, content, level, grade, num_mcqs)
    
    # Display Generated MCQs
    display_generated_mcqs(include_answers, exam_mode)
    
    # Footer
    render_footer()

# ---------------------------
# Application Entry Point
# ---------------------------
def main():
    """Main entry point of the application"""
    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    # Check authentication
    if not check_authentication():
        display_authentication()
    else:
        main_application()

if __name__ == "__main__":
    main()
