import streamlit as st
import requests
import json
from PIL import Image
import os
import io

# Set page configuration for a premium look
st.set_page_config(
    page_title="FraudSight AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Optional Custom CSS for sleek UI
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        width: 100%;
        background-color: #0066cc;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.5rem 1rem;
    }
    .stButton>button:hover {
        background-color: #0052a3;
        color: white;
    }
    .metric-card {
        background-color: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        text-align: center;
        margin-bottom: 20px;
    }
    .real-badge {
        color: #2e7d32;
        font-size: 2rem;
        font-weight: 900;
        text-transform: uppercase;
    }
    .fake-badge {
        color: #c62828;
        font-size: 2rem;
        font-weight: 900;
        text-transform: uppercase;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🕵️‍♂️ FraudSight AI Vision")
st.markdown("### Detect AI-Generated Forensics, Accidents, and Damage Reports")
st.markdown("Upload incident evidence (Images, PDFs, or Videos) below to leverage Qwen3 Vision analysis.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Upload Evidence")
    uploaded_file = st.file_uploader("Choose a file...", type=["jpg", "jpeg", "png"])
    
    if uploaded_file is not None:
        # Show preview
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded Evidence", use_container_width=True)

with col2:
    st.subheader("Analysis Results")
    if uploaded_file is not None:
        if st.button("🔍 Analyze Authenticity", type="primary"):
            with st.spinner("Analyzing forensics via Qwen3..."):
                try:
                    # Prepare file for upload
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    
                    # Call FastAPI backend
                    response = requests.post("http://localhost:8000/analyze_media", files=files)
                    
                    if response.status_code == 200:
                        result = response.json()
                        class_result = result.get('classification', 'Unknown')
                        conf_score = result.get('confidence_score', 0.0)
                        reason = result.get('reason', 'No reasoning provided')
                        thought_process = result.get('thought_process', None)
                        vision_findings = result.get('vision_findings', None)
                        
                        # Display Results
                        badge_class = "real-badge" if "Real" in class_result else "fake-badge"
                        
                        st.markdown(f"""
                        <div class="metric-card">
                            <h3 style="margin-top:0;">Final Verdict (Agent 2 - Critic)</h3>
                            <div class="{badge_class}">{class_result}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.metric("Confidence Score", f"{conf_score * 100:.2f}%")
                        st.progress(float(conf_score))
                        
                        if vision_findings:
                            st.markdown("### 👁️ Agent 1: Raw Vision Findings")
                            st.warning(vision_findings)
                            
                        if thought_process:
                            st.markdown("### 🧠 Agent 2: Critic's Chain of Thought")
                            st.info(thought_process)
                            
                        st.markdown("### 📝 Final Reasoning Summary")
                        st.success(reason)
                    else:
                        st.error(f"Error from server: {response.text}")
                except Exception as e:
                    st.error(f"Failed to connect to backend: {e}")
    else:
        st.info("Upload an image on the left to begin analysis.")
