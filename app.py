import streamlit as st
import os
import sys

import streamlit as st
import os
import sys

import json
import time
import tempfile
import sqlite3
from PIL import Image

from backend.qwen_agent import analyze_media, analyze_video

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), "database", "fraud_detection.db")

# ==========================================
# PAGE CONFIG & STYLING
# ==========================================
st.set_page_config(
    page_title="FraudSight AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&display=swap');

    /* Global */
    .main { 
        background-color: #030712; 
        background-image: 
            radial-gradient(circle at 15% 50%, rgba(56, 189, 248, 0.04) 0%, transparent 25%),
            radial-gradient(circle at 85% 30%, rgba(139, 92, 246, 0.04) 0%, transparent 25%);
    }
    html, body, [class*="css"] { font-family: 'Outfit', sans-serif; }

    /* Streamlit overrides */
    div[data-testid="stSidebar"] {
        background-color: rgba(15, 23, 42, 0.95) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #38bdf8 0%, #3b82f6 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.2s ease;
        box-shadow: 0 4px 14px 0 rgba(59, 130, 246, 0.25);
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
    }

    /* Hero header */
    .hero-title {
        font-size: 3.5rem;
        font-weight: 900;
        background: linear-gradient(135deg, #e0e7ff 0%, #38bdf8 50%, #8b5cf6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.25rem;
        letter-spacing: -0.02em;
    }
    .hero-subtitle {
        font-size: 1.25rem;
        color: #94a3b8;
        margin-bottom: 2.5rem;
        font-weight: 300;
    }

    /* Cards - Glassmorphism */
    .verdict-card {
        border-radius: 20px;
        padding: 32px;
        text-align: center;
        margin-bottom: 24px;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);    
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    }
    .verdict-fake {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(0, 0, 0, 0.4) 100%);
        border-top: 1px solid rgba(239, 68, 68, 0.3);
    }
    .verdict-real {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(0, 0, 0, 0.4) 100%);
        border-top: 1px solid rgba(16, 185, 129, 0.3);
    }
    .verdict-label {
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        color: #cbd5e1;
        margin-bottom: 8px;
    }
    .verdict-value-fake {
        font-size: 3.5rem;
        font-weight: 900;
        color: #f87171;
        text-shadow: 0 0 20px rgba(248, 113, 113, 0.3);
        letter-spacing: -0.02em;
    }
    .verdict-value-real {
        font-size: 3.5rem;
        font-weight: 900;
        color: #34d399;
        text-shadow: 0 0 20px rgba(52, 211, 153, 0.3);
        letter-spacing: -0.02em;
    }

    /* Confidence bar */
    .conf-bar-bg {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 12px;
        height: 16px;
        overflow: hidden;
        margin: 12px 0 24px 0;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.2);
    }
    .conf-bar-fill-fake {
        height: 100%;
        border-radius: 12px;
        background: linear-gradient(90deg, #f43f5e, #e11d48);
        box-shadow: 0 0 10px rgba(244, 63, 94, 0.5);
    }
    .conf-bar-fill-real {
        height: 100%;
        border-radius: 12px;
        background: linear-gradient(90deg, #10b981, #059669);
        box-shadow: 0 0 10px rgba(16, 185, 129, 0.5);
    }

    /* Stats row */
    .stat-card {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(8px);
        border-radius: 16px;
        padding: 24px 16px;
        text-align: center;
        transition: transform 0.2s ease;
    }
    .stat-card:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 255, 255, 0.1);
    }
    .stat-value {
        font-size: 2rem;
        font-weight: 800;
        color: #f8fafc;
        margin-bottom: 4px;
    }
    .stat-label {
        font-size: 0.75rem;
        font-weight: 600;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    /* Vote chips */
    .vote-chip {
        display: inline-flex;
        align-items: center;
        padding: 8px 16px;
        border-radius: 100px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 6px 6px 12px 0;
        border: 1px solid rgba(255,255,255,0.05);
        backdrop-filter: blur(4px);
    }
    .vote-fake { background: rgba(239, 68, 68, 0.1); color: #fca5a5; border-color: rgba(239, 68, 68, 0.2); }
    .vote-real { background: rgba(16, 185, 129, 0.1); color: #6ee7b7; border-color: rgba(16, 185, 129, 0.2); }
    .vote-error { background: rgba(245, 158, 11, 0.1); color: #fcd34d; border-color: rgba(245, 158, 11, 0.2); }

    /* Upload area */
    .stFileUploader > div > div {
        border: 2px dashed rgba(56, 189, 248, 0.3) !important;
        border-radius: 16px !important;
        background: rgba(56, 189, 248, 0.02) !important;
        transition: all 0.2s ease;
    }
    .stFileUploader > div > div:hover {
        border-color: rgba(56, 189, 248, 0.6) !important;
        background: rgba(56, 189, 248, 0.05) !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background: rgba(15, 23, 42, 0.4);
        padding: 8px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(255, 255, 255, 0.1) !important;
        color: white !important;
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        background: rgba(30, 41, 59, 0.4) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }

    /* Pipeline badge */
    .pipeline-badge {
        background: linear-gradient(90deg, rgba(56, 189, 248, 0.1), rgba(139, 92, 246, 0.1));
        border: 1px solid rgba(139, 92, 246, 0.2);
        border-radius: 20px;
        padding: 10px 20px;
        font-size: 0.85rem;
        font-weight: 500;
        color: #bae6fd;
        display: inline-flex;
        align-items: center;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    
    /* Animations */
    @keyframes blink {
        0%, 100% { opacity: 0.3; transform: scale(0.8); }
        50% { opacity: 1; transform: scale(1.2); }
        
    }
    @keyframes float {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
    }
    .pulsing-icon {
        display: inline-block;
        animation: float 3s ease-in-out infinite;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# HEADER
# ==========================================
st.markdown('<div class="hero-title">🕵️ FraudSight AI</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-subtitle">Multi-Agent Insurance Fraud Detection — Images & Documents</div>', unsafe_allow_html=True)
st.markdown('<div class="pipeline-badge">⚡ Pipeline: Qwen-VL-Plus (Vision) → Qwen Turbo + DeepSeek R1-0528 + GLM 4.6 (Critics)</div>', unsafe_allow_html=True)


# ==========================================
# HELPER FUNCTIONS
# ==========================================
def render_result(result, filename, elapsed_time):
    """Render analysis results in a beautiful card layout."""
    classification = result.get("classification", "Unknown")
    confidence = result.get("confidence_score", 0.0)
    reason = result.get("reason", "")
    vision_findings = result.get("vision_findings", "")
    vote_breakdown = result.get("vote_breakdown", {})
    consensus = result.get("consensus", "")
    calibration = result.get("calibration", "")

    is_fake = classification == "Fake"
    css_class = "fake" if is_fake else "real"

    # Verdict card
    st.markdown(f"""
    <div class="verdict-card verdict-{css_class}">
        <div class="verdict-label">Final Verdict</div>
        <div class="verdict-value-{css_class}">{classification}</div>
        <div style="color: #8b95a5; font-size: 0.9rem; margin-top: 4px;">{consensus.upper()} decision</div>
    </div>
    """, unsafe_allow_html=True)

    # Confidence bar
    conf_pct = confidence * 100
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: 600; color: #e2e8f0;">Confidence</span>
        <span style="font-weight: 700; color: #e2e8f0;">{conf_pct:.1f}%</span>
    </div>
    <div class="conf-bar-bg">
        <div class="conf-bar-fill-{css_class}" style="width: {conf_pct}%;"></div>
    </div>
    """, unsafe_allow_html=True)

    # Executive Summary (Prominent layout)
    if reason:
        st.markdown("#### 📋 Executive Summary")
        st.info(reason)

    # Stats row
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(f'<div class="stat-card"><div class="stat-value">{elapsed_time:.0f}s</div><div class="stat-label">Processing Time</div></div>', unsafe_allow_html=True)
    with col_b:
        valid_votes = len([v for v in vote_breakdown.values() if isinstance(v, dict) and v.get("classification") in ["Real", "Fake"]])
        total_votes = len(vote_breakdown) if vote_breakdown else 3
        st.markdown(f'<div class="stat-card"><div class="stat-value">{valid_votes}/{total_votes}</div><div class="stat-label">Models/Frames Voted</div></div>', unsafe_allow_html=True)
    with col_c:
        emoji = "✅" if is_fake else "🟢"
        st.markdown(f'<div class="stat-card"><div class="stat-value">{emoji}</div><div class="stat-label">Status</div></div>', unsafe_allow_html=True)

    # Vote breakdown chips
    if vote_breakdown:
        st.markdown("#### 🗳️ Model Votes")
        chips_html = ""
        for model, info in vote_breakdown.items():
            if isinstance(info, dict):
                cls = info.get("classification", "Error")
                conf = info.get("confidence", 0)
                chip_class = "vote-fake" if cls == "Fake" else ("vote-real" if cls == "Real" else "vote-error")
                chips_html += f'<span class="vote-chip {chip_class}">{model}: {cls} ({conf*100:.0f}%)</span>'
        st.markdown(chips_html, unsafe_allow_html=True)

    # Expandable details
    with st.expander("👁️ Raw Vision Agent Forensics (Technical)", expanded=False):
        st.markdown(vision_findings)

    if calibration:
        with st.expander("⚖️ Confidence Calibration (What would change my mind?)", expanded=False):
            st.markdown(calibration)


def process_uploaded_file(uploaded_file):
    """Save uploaded file to temp dir and run analysis."""
    filename = uploaded_file.name
    ext = filename.split(".")[-1].lower()

    if ext == "pdf":
        content_type = "application/pdf"
        media_type = "Document"
    elif ext in ["mp4", "avi", "mov"]:
        content_type = "video/mp4"
        media_type = "Video"
    elif ext == "png":
        content_type = "image/png"
        media_type = "Image"
    else:
        content_type = "image/jpeg"
        media_type = "Image"

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        start_time = time.time()
        if media_type == "Video":
            result = analyze_video(tmp_path)
        else:
            result = analyze_media(tmp_path, content_type, media_type=media_type)
        elapsed = time.time() - start_time
        return result, elapsed
    finally:
        os.unlink(tmp_path)


# ==========================================
# SIDEBAR - DATABASE STATS
# ==========================================
with st.sidebar:
    st.markdown("### 📊 Database Overview")

    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM evidence")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM evidence WHERE is_processed = 1")
        processed = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM evidence WHERE is_processed = 1 AND ai_prediction = 'Fake'")
        flagged_fraud = float(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM evidence WHERE media_type = 'Document'")
        doc_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM evidence WHERE media_type = 'Image'")
        img_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM evidence WHERE media_type = 'Video'")
        vid_count = cursor.fetchone()[0]

        conn.close()

        fraud_rate = (flagged_fraud / processed * 100) if processed > 0 else 0
        progress_val = float(processed / total) if total > 0 else 0.0

        st.metric("Total Records", total)
        
        st.markdown(f"<div style='font-size: 0.85rem; color: #94a3b8; font-weight: 600; margin-bottom: 8px;'>PIPELINE PROGRESS</div>", unsafe_allow_html=True)
        st.progress(progress_val)
        st.markdown(f"<div style='font-size: 0.75rem; color: #64748b; margin-top: -12px; margin-bottom: 16px; text-align: right;'>{processed} / {total} Processed</div>", unsafe_allow_html=True)
        
        st.metric("🚨 Suspicious (Flagged)", f"{fraud_rate:.1f}%", f"{int(flagged_fraud)} identified", delta_color="inverse")
        st.divider()
        st.metric("🖼️ Images", img_count)
        st.metric("📄 Documents", doc_count)
        st.metric("🎥 Videos", vid_count)
    else:
        st.warning("Database not found. Run `init_db.py` first.")

    st.divider()
    st.markdown("### 🔧 Pipeline Config")
    st.code("Vision: Qwen-VL-Plus\nCritic 1: Qwen Turbo\nCritic 2: DeepSeek V3.2\nCritic 3: GLM 4.6", language="text")


# ==========================================
# MAIN CONTENT - TABS
# ==========================================
tab1, tab2, tab3 = st.tabs(["🔍 Single Analysis", "📦 Batch Upload", "📈 Results Dashboard"])

# ------------------------------------------
# TAB 1: SINGLE FILE ANALYSIS
# ------------------------------------------
with tab1:
    st.markdown("#### Upload a single image or document for instant fraud detection")

    col_upload, col_result = st.columns([1, 1])

    with col_upload:
        uploaded_file = st.file_uploader(
            "Drop an image, PDF, or Video here",
            type=["jpg", "jpeg", "png", "pdf", "mp4", "avi", "mov"],
            key="single_upload",
            help="Supports JPEG, PNG, PDF, MP4, AVI, MOV"
        )

        if uploaded_file:
            ext = uploaded_file.name.split(".")[-1].lower()
            if ext == "pdf":
                st.info(f"📄 **PDF Document:** {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
            elif ext in ["mp4", "avi", "mov"]:
                st.video(uploaded_file)
                st.info(f"🎥 **Video File:** {uploaded_file.name} ({uploaded_file.size / (1024*1024):.1f} MB)")
            else:
                image = Image.open(uploaded_file)
                st.image(image, caption=uploaded_file.name, use_container_width=True)
                uploaded_file.seek(0)  # Reset file pointer after preview

    with col_result:
        if uploaded_file:
            if st.button("🔍 Analyze Authenticity", type="primary", key="single_analyze"):
                loading_placeholder = st.empty()
                with loading_placeholder.container():
                    st.markdown("""
<div class="verdict-card" style="border-color: rgba(56, 189, 248, 0.3); padding: 50px 32px;">
<div class="pulsing-icon" style="font-size: 4rem; margin-bottom: 24px;">🕵️</div>
<h3 style="color: #e0e7ff; font-weight: 700; margin-bottom: 12px; font-size: 1.5rem;">AI Forensics in Progress</h3>
<p style="color: #94a3b8; font-size: 0.95rem; margin-bottom: 32px; line-height: 1.5;">
Running the Multi-Agent Zero-Trust Pipeline.<br>
This deep analysis usually takes <b>2-3 minutes</b> to complete.
</p>

<div style="display: flex; flex-direction: column; gap: 16px; width: fit-content; margin: 0 auto; text-align: left;">
<div style="display: flex; align-items: center;">
<div style="width: 12px; height: 12px; border-radius: 50%; background: #38bdf8; margin-right: 16px; animation: blink 1.5s infinite; box-shadow: 0 0 10px #38bdf8;"></div>
<span style="color: #cbd5e1; font-size: 0.95rem; font-weight: 500;">Extracting microscopic anomaly features...</span>
</div>
<div style="display: flex; align-items: center;">
<div style="width: 12px; height: 12px; border-radius: 50%; background: #8b5cf6; margin-right: 16px; animation: blink 1.5s infinite 0.5s; box-shadow: 0 0 10px #8b5cf6;"></div>
<span style="color: #cbd5e1; font-size: 0.95rem; font-weight: 500;">Cross-examining LLM Critics (DeepSeek, GLM)...</span>
</div>
<div style="display: flex; align-items: center;">
<div style="width: 12px; height: 12px; border-radius: 50%; background: #34d399; margin-right: 16px; animation: blink 1.5s infinite 1s; box-shadow: 0 0 10px #34d399;"></div>
<span style="color: #cbd5e1; font-size: 0.95rem; font-weight: 500;">Computing final consensus & confidence score...</span>
</div>
</div>
</div>
""", unsafe_allow_html=True)
                
                try:
                    result, elapsed = process_uploaded_file(uploaded_file)
                    loading_placeholder.empty()
                    render_result(result, uploaded_file.name, elapsed)
                except Exception as e:
                    loading_placeholder.empty()
                    st.error(f"❌ Analysis failed: {e}")
        else:
            st.info("👈 Upload an image or PDF on the left to begin.")


# ------------------------------------------
# TAB 2: BATCH UPLOAD
# ------------------------------------------
with tab2:
    st.markdown("#### Upload multiple files for batch fraud detection")

    batch_files = st.file_uploader(
        "Drop multiple images, PDFs, or Videos here",
        type=["jpg", "jpeg", "png", "pdf", "mp4", "avi", "mov"],
        accept_multiple_files=True,
        key="batch_upload",
        help="Upload as many files as you want — they'll be processed sequentially"
    )

    if batch_files:
        # Show preview grid
        st.markdown(f"**{len(batch_files)} files selected:**")
        preview_cols = st.columns(min(len(batch_files), 6))
        for i, f in enumerate(batch_files[:6]):
            ext = f.name.split(".")[-1].lower()
            with preview_cols[i]:
                if ext == "pdf":
                    st.markdown(f"📄 {f.name[:15]}...")
                elif ext in ["mp4", "avi", "mov"]:
                    st.markdown(f"🎥 {f.name[:15]}...")
                else:
                    img = Image.open(f)
                    st.image(img, caption=f.name[:15], use_container_width=True)
                    f.seek(0)

        if len(batch_files) > 6:
            st.caption(f"...and {len(batch_files) - 6} more files")

        if st.button(f"🚀 Analyze All {len(batch_files)} Files", type="primary", key="batch_analyze"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_container = st.container()

            all_results = []

            for i, f in enumerate(batch_files):
                status_text.markdown(f"**Processing [{i+1}/{len(batch_files)}]:** {f.name}")
                progress_bar.progress((i) / len(batch_files))

                try:
                    result, elapsed = process_uploaded_file(f)
                    classification = result.get("classification", "Error")
                    confidence = result.get("confidence_score", 0.0)
                    all_results.append({
                        "filename": f.name,
                        "classification": classification,
                        "confidence": confidence,
                        "time": elapsed,
                        "result": result,
                    })

                    with results_container:
                        is_fake = classification == "Fake"
                        emoji = "🔴" if is_fake else "🟢"
                        st.markdown(f"{emoji} **{f.name}** → **{classification}** ({confidence*100:.0f}%) — {elapsed:.0f}s")

                except Exception as e:
                    all_results.append({
                        "filename": f.name,
                        "classification": "Error",
                        "confidence": 0.0,
                        "time": 0,
                        "result": {},
                    })
                    with results_container:
                        st.markdown(f"⚠️ **{f.name}** → Error: {e}")

            progress_bar.progress(1.0)
            status_text.markdown("**✅ Batch complete!**")

            # Summary stats
            st.divider()
            fake_count = sum(1 for r in all_results if r["classification"] == "Fake")
            real_count = sum(1 for r in all_results if r["classification"] == "Real")
            err_count = sum(1 for r in all_results if r["classification"] == "Error")
            total_time = sum(r["time"] for r in all_results)

            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            col_s1.metric("🔴 Fake", fake_count)
            col_s2.metric("🟢 Real", real_count)
            col_s3.metric("⚠️ Errors", err_count)
            col_s4.metric("⏱️ Total Time", f"{total_time:.0f}s")

            # Expandable details per file
            for r in all_results:
                if r["result"]:
                    with st.expander(f"{'🔴' if r['classification'] == 'Fake' else '🟢'} {r['filename']} — {r['classification']} ({r['confidence']*100:.0f}%)"):
                        render_result(r["result"], r["filename"], r["time"])


# ------------------------------------------
# TAB 3: DATABASE RESULTS DASHBOARD
# ------------------------------------------
with tab3:
    st.markdown("#### Results from Batch Processing Pipeline")

    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)

        # Overall stats
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM evidence WHERE is_processed = 1")
        total_processed = cursor.fetchone()[0]

        if total_processed == 0:
            st.info("No processed records yet. Run `batch_processor.py` to process images from the database.")
        else:
            cursor.execute("SELECT COUNT(*) FROM evidence WHERE is_processed = 1 AND ai_prediction = ground_truth")
            correct = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM evidence WHERE is_processed = 1 AND ai_prediction != ground_truth")
            incorrect = cursor.fetchone()[0]

            cursor.execute("SELECT AVG(confidence) FROM evidence WHERE is_processed = 1")
            avg_conf = cursor.fetchone()[0] or 0

            cursor.execute("SELECT AVG(processing_time) FROM evidence WHERE is_processed = 1")
            avg_time = cursor.fetchone()[0] or 0

            accuracy = (correct / total_processed * 100) if total_processed > 0 else 0

            # Stats row
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Processed", total_processed)
            c2.metric("✅ Correct", correct)
            c3.metric("❌ Incorrect", incorrect)
            c4.metric("Accuracy", f"{accuracy:.1f}%")
            c5.metric("Avg Time", f"{avg_time:.0f}s")

            st.divider()

            # Filters
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                filter_type = st.selectbox("Media Type", ["All", "Image", "Document", "Video"])
            with col_f2:
                filter_truth = st.selectbox("Ground Truth", ["All", "Fake", "Real"])
            with col_f3:
                filter_result = st.selectbox("AI Prediction", ["All", "Correct Only", "Incorrect Only"])

            # Build query
            query = "SELECT filename, media_type, fraud_category, ground_truth, ai_prediction, confidence, processing_time FROM evidence WHERE is_processed = 1"
            if filter_type != "All":
                query += f" AND media_type = '{filter_type}'"
            if filter_truth != "All":
                query += f" AND ground_truth = '{filter_truth}'"
            if filter_result == "Correct Only":
                query += " AND ai_prediction = ground_truth"
            elif filter_result == "Incorrect Only":
                query += " AND ai_prediction != ground_truth"

            cursor.execute(query)
            rows = cursor.fetchall()

            if rows:
                st.markdown(f"**Showing {len(rows)} records:**")
                for row in rows:
                    fname, mtype, category, truth, pred, conf, ptime = row
                    is_correct = truth == pred
                    emoji = "✅" if is_correct else "❌"
                    if mtype == "Document":
                        type_icon = "📄"
                    elif mtype == "Video":
                        type_icon = "🎥"
                    else:
                        type_icon = "🖼️"
                    pred_color = "🔴" if pred == "Fake" else "🟢"
                    ptime_str = f"{ptime:.0f}s" if ptime is not None else "N/A"

                    st.markdown(
                        f"{emoji} {type_icon} **{fname}** | "
                        f"Truth: **{truth}** | "
                        f"Pred: {pred_color} **{pred}** ({conf*100:.0f}%) | "
                        f"⏱️ {ptime_str} | "
                        f"📁 {category}"
                    )
            else:
                st.info("No records match the selected filters.")

        conn.close()
    else:
        st.warning("Database not found. Run `init_db.py` first.")
