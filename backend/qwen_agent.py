import os
import base64
import json
import requests
import glob
import subprocess
import tempfile
import cv2
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try to load dotenv, otherwise read .env manually
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, val = line.strip().split("=", 1)
                    os.environ[key.strip()] = val.strip()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "").strip()

from PIL import Image
import io

def encode_image(image_path, max_size=(4000, 4000)):
    # Open the image, resize if unnecessarily massive, and compress it with minimal loss
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=95)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')


def encode_pdf_pages(pdf_path, max_size=(1200, 1200), dpi=200):
    """
    Converts each page of a PDF into a base64-encoded JPEG image using pdftoppm.
    Returns a list of base64 strings, one per page.
    """
    pages_b64 = []
    with tempfile.TemporaryDirectory() as tmpdir:
        # Render PDF pages to PPM images
        prefix = os.path.join(tmpdir, "page")
        subprocess.run(
            ["pdftoppm", "-jpeg", "-r", str(dpi), pdf_path, prefix],
            check=True, capture_output=True
        )
        
        # Collect rendered page images (sorted by page number)
        page_files = sorted([
            os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
            if f.endswith(".jpg")
        ])
        
        for page_file in page_files:
            with Image.open(page_file) as img:
                img = img.convert("RGB")
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)  # Higher quality for documents
                pages_b64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
    
    return pages_b64


def extract_video_frames(video_path, num_frames=5, max_size=(800, 800)):
    """
    Extracts evenly spaced keyframes from a video file.
    Returns a list of base64-encoded JPEGs.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"Failed to open video file: {video_path}")
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames == 0:
        cap.release()
        raise Exception("Video file has 0 frames or is corrupt.")
        
    # Calculate frame step
    step = max(1, total_frames // num_frames)
    
    frames_b64 = []
    
    # Extract frames
    for i in range(num_frames):
        frame_idx = min(i * step, total_frames - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        
        if ret:
            # OpenCV loads as BGR, convert to RGB for PIL
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=75)
            frames_b64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
            
    cap.release()
    return frames_b64

def get_few_shot_examples():
    base_dir = "/home/aditya/Downloads/Hackathon/Chubb_Data"
    fake_dir = os.path.join(base_dir, "Fake")
    real_dir = os.path.join(base_dir, "Real")
    
    # Grab images from directories
    fake_images = []
    if os.path.exists(fake_dir):
        fake_images = sorted([os.path.join(fake_dir, f) for f in os.listdir(fake_dir) if f.lower().endswith(('png', 'jpg', 'jpeg'))])
    
    real_images = []
    if os.path.exists(real_dir):
        real_images = sorted([os.path.join(real_dir, f) for f in os.listdir(real_dir) if f.lower().endswith(('png', 'jpg', 'jpeg'))])
    
    # Take 2 fake and 2 real
    selected_fake = fake_images[:2] if fake_images else []
    selected_real = real_images[:2] if real_images else []
    
    few_shot_messages = []
    
    # Process Fake Examples
    for i, img_path in enumerate(selected_fake):
        try:
            b64 = encode_image(img_path)
            # Add user message
            few_shot_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this image for fraud. Provide your thought process and classification."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}"
                        }
                    }
                ]
            })
            
            # Use different reasoning for the two fake images to add variety
            reasoning = ""
            if i == 0:
                reasoning = "GRID SCAN INITIATED. Sector 5 (Center): The car's crumpled front bumper has smooth, clay-like deformations without sharp, jagged metal tearing typical of real crashes. Sector 1 (Top Left): The text on the billboard contains alien, impossible characters blending together. Sector 6 (Middle Right): The bystander's hand in the background is mangled into 6 fused fingers. Conclusion: The image is riddled with generative AI artifacts."
            else:
                reasoning = "GRID SCAN INITIATED. Sector 8 (Bottom Center): The fire/water damage patterns perfectly stop at the exact edge of the vehicle panel, which is physically impossible. Sector 2 (Top Center): The lighting on the building contradicts the primary light source illuminating the street. Sector 9 (Bottom Right): Debris floating mid-air ignoring gravity. Conclusion: Highly likely to be AI-generated."

            # Add assistant response
            few_shot_messages.append({
                "role": "assistant",
                "content": json.dumps({
                    "thought_process": reasoning,
                    "classification": "Fake",
                    "confidence_score": 0.98,
                    "reason": "Presence of impossible physical structures, morphing, and unnatural lighting."
                })
            })
        except Exception as e:
            print(f"Failed to load few-shot image {img_path}: {e}")

    # Process Real Examples
    for i, img_path in enumerate(selected_real):
        try:
            b64 = encode_image(img_path)
            # Add user message
            few_shot_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this image for fraud. Provide your thought process and classification."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}"
                        }
                    }
                ]
            })
            
            reasoning = "Scanning the image for AI artifacts. (1) Text checking: License plates and text on nearby signs, if visible, follow standard typographic rules. (2) Anatomy: Any people present look anatomically correct without mangled features. (3) Physics/Structure: The damage reflects real-world physics (e.g., jagged metal edges, correct crumple zones, distinct material separation). (4) Lighting/Framing: Features ordinary, natural lighting consistent with the environment's light source. Conclusion: No generative AI artifacts detected."

            # Add assistant response
            few_shot_messages.append({
                "role": "assistant",
                "content": json.dumps({
                    "thought_process": reasoning,
                    "classification": "Real",
                    "confidence_score": 0.95,
                    "reason": "Consistent physical damage modeling, correct text/anatomy, and lack of AI morphing or unnatural lighting artifacts."
                })
            })
        except Exception as e:
            print(f"Failed to load few-shot image {img_path}: {e}")
            
    return few_shot_messages


# ==========================================
# CRITIC MODELS CONFIGURATION
# ==========================================
CRITIC_MODELS = [
    {
        "name": "Qwen Turbo",
        "model_id": "qwen/qwen-turbo",
        "api_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key": OPENROUTER_API_KEY,
        "extra_headers": {
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Fraud Detection System",
        },
        "supports_json_mode": True,
    },
    {
        "name": "DeepSeek V3.2",
        "model_id": "deepseek-ai/DeepSeek-V3.2",
        "api_url": "https://api.featherless.ai/v1/chat/completions",
        "api_key": FEATHERLESS_API_KEY,
        "extra_headers": {},
        "supports_json_mode": False,
    },
    {
        "name": "GLM 4.6",
        "model_id": "zai-org/GLM-4.6",
        "api_url": "https://api.featherless.ai/v1/chat/completions",
        "api_key": FEATHERLESS_API_KEY,
        "extra_headers": {},
        "supports_json_mode": False,
    },
]


def call_critic(model_config, vlm_findings, media_type="Image"):
    """
    Calls a single LLM critic model with the VLM findings and returns parsed JSON.
    Includes confidence calibration (what would change the model's mind).
    """
    if media_type == "Document":
        context_description = "an insurance claim DOCUMENT (such as a bill, receipt, claim form, or certificate)"
        guideline_text = """- Real scanned documents have minor imperfections: slightly uneven margins, scanner artifacts, paper texture, ink bleeding on stamps/signatures.
- AI-generated or forged documents often have: perfectly uniform text with no scanner noise, impossibly clean backgrounds, generic/uniform signatures/stamps, and inconsistent fonts or layout elements.
- If the Vision Agent spotted garbled text, font mismatches, haloing around inserted text, or impossibly uniform stamps, you MUST classify the document as "Fake".
- If the only anomalies are minor scan quality issues, it may be Real."""
    else:
        context_description = "an insurance claim image (which could be a car accident or property damage)"
        guideline_text = """- Real insurance photos are imperfect (blurry, bad lighting), but they obey the laws of physics and anatomy.
- EXCEPTION FOR DASHCAMS: Low-quality dashcam videos naturally have garbled text, pixelated license plates, and compression artifacts. Do NOT classify an image as "Fake" *solely* because a license plate is unreadable IF the rest of the image is clearly a low-res dashcam video.
- CRITICAL DASHCAM OVERRIDE: If the Vision Agent explicitly states that the image appears to be a legitimate low-quality dashcam/CCTV recording, and the only anomalies are blurriness or compression noise, you MUST vote "Real". Do not invent "unnaturally smooth paint" if the image is just blurry.
- HOWEVER, for HIGH QUALITY images, perfectly rendered but garbled text is a massive red flag.
- Do not let a few generic "lighting" or "blur" excuses mask blatant structural defects. If the vehicle's damage is "unnaturally clean", looks like "plastic/clay", or lacks chaotic, jagged real-world fracture patterns (shattered glass, crumpled metal), it is Fake.
- If the image is extremely high resolution but the damage looks painted on, it is Fake."""

    llm_prompt = f"""
You are the Lead Fraud Investigator and Critic.
Your subordinate (a Vision AI) has extracted the following raw visual findings from {context_description}:

--- VISION AGENT FINDINGS ---
{vlm_findings}
-----------------------------

Your job is to CRITIQUE these findings contextually and make the final ruling on whether the evidence is genuinely "Real" or an AI-generated/forged "Fake".
{guideline_text}

CONFIDENCE CALIBRATION: After your classification, you must also state what specific evidence would cause you to FLIP your classification. For example, if you classify as "Real", explain what you would need to see to change it to "Fake", and vice versa.

THINK STEP-BY-STEP before classifying.
You MUST output your final decision in strict JSON format.

Required JSON Schema:
{{
  "thought_process": "<Critique the Vision Agent's findings step-by-step and reason towards a conclusion.>",
  "classification": "Real" or "Fake",
  "confidence_score": <float between 0.0 and 1.0>,
  "reason": "<A highly professional, detailed 4-5 sentence Executive Summary written for an insurance claims adjuster. Explain EXACTLY why this evidence is fake or real based on the visual forensics. Make it comprehensive but accessible.>",
  "what_would_change_my_mind": "<Specific evidence that would cause you to flip your classification.>"
}}

CRITICAL INSTRUCTION FOR DEEPSEEK MODELS: You MUST output the JSON block AFTER your <think> block. Do not end your response without providing the valid JSON object.
    """

    headers = {
        "Authorization": f"Bearer {model_config['api_key']}",
        "Content-Type": "application/json",
        **model_config["extra_headers"],
    }

    payload = {
        "model": model_config["model_id"],
        "messages": [
            {"role": "user", "content": llm_prompt}
        ],
    }

    # Only add JSON mode for models that support it
    if model_config["supports_json_mode"]:
        payload["response_format"] = {"type": "json_object"}

    model_name = model_config["name"]
    print(f"  Calling Critic: {model_name}...")

    try:
        response = requests.post(model_config["api_url"], headers=headers, json=payload, timeout=120)
        if response.status_code != 200:
            print(f"  ⚠ {model_name} returned status {response.status_code}: {response.text[:200]}")
            return {
                "model": model_name,
                "classification": "Error",
                "confidence_score": 0.0,
                "reason": f"API Error: {response.status_code}",
                "thought_process": "",
                "what_would_change_my_mind": "",
            }

        raw_text = response.json()['choices'][0]['message']['content']
        result_text = raw_text.replace("```json\n", "").replace("```\n", "").replace("```", "").strip()

        # Try to strip DeepSeek <think> reasoning blocks
        think_end = result_text.find("</think>")
        if think_end != -1:
            result_text = result_text[think_end + 8:]

        # Try to extract JSON from the response (some models wrap it in text)
        json_start = result_text.find("{")
        json_end = result_text.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            result_text = result_text[json_start:json_end]

        parsed = json.loads(result_text)
        parsed["model"] = model_name
        # Normalize classification to "Real" or "Fake"
        classification = parsed.get("classification", "").strip().strip('"')
        if classification.lower() in ["real", "genuine", "authentic"]:
            parsed["classification"] = "Real"
        elif classification.lower() in ["fake", "ai-generated", "ai generated", "fraudulent"]:
            parsed["classification"] = "Fake"
        
        print(f"  ✓ {model_name} → {parsed['classification']} (confidence: {parsed.get('confidence_score', 'N/A')})")
        return parsed

    except json.JSONDecodeError as e:
        print(f"  ⚠ {model_name} returned invalid JSON: {e}\n  Raw Text: {raw_text[:200]}...")
        return {
            "model": model_name,
            "classification": "Error",
            "confidence_score": 0.0,
            "reason": f"JSON parse error. Raw Output: {raw_text[:300]}...",
            "thought_process": raw_text[:500] if 'raw_text' in locals() else "",
            "what_would_change_my_mind": "",
        }
    except Exception as e:
        print(f"  ⚠ {model_name} failed: {e}")
        return {
            "model": model_name,
            "classification": "Error",
            "confidence_score": 0.0,
            "reason": f"Exception: {str(e)}",
            "thought_process": "",
            "what_would_change_my_mind": "",
        }


def aggregate_votes(critic_results):
    """
    Aggregates the votes of multiple critics into a single final verdict.
    Uses majority voting and weighted confidence scoring.
    """
    # Filter out error results for voting
    valid_results = [r for r in critic_results if r["classification"] in ["Real", "Fake"]]

    if not valid_results:
        return {
            "classification": "Error",
            "confidence_score": 0.0,
            "consensus": "no_valid_votes",
            "reason": "All critic models failed to return valid results.",
            "vote_breakdown": {r["model"]: {"classification": r["classification"], "confidence": r.get("confidence_score", 0.0)} for r in critic_results},
            "calibration": "",
        }

    fake_votes = [r for r in valid_results if r["classification"] == "Fake"]
    real_votes = [r for r in valid_results if r["classification"] == "Real"]

    # Majority vote
    if len(fake_votes) > len(real_votes):
        final_classification = "Fake"
        winning_votes = fake_votes
    elif len(real_votes) > len(fake_votes):
        final_classification = "Real"
        winning_votes = real_votes
    else:
        # Tie — use average confidence to break it
        fake_conf = sum(r.get("confidence_score", 0.5) for r in fake_votes) / len(fake_votes)
        real_conf = sum(r.get("confidence_score", 0.5) for r in real_votes) / len(real_votes)
        final_classification = "Fake" if fake_conf >= real_conf else "Real"
        winning_votes = fake_votes if final_classification == "Fake" else real_votes

    # Weighted confidence: average of all valid votes, weighted toward majority
    all_confs = []
    for r in valid_results:
        conf = r.get("confidence_score", 0.5)
        if r["classification"] == final_classification:
            all_confs.append(conf)
        else:
            all_confs.append(1.0 - conf)  # Invert dissenting confidence
    weighted_confidence = round(sum(all_confs) / len(all_confs), 2)

    # Determine consensus type
    total_valid = len(valid_results)
    majority_count = max(len(fake_votes), len(real_votes))
    if majority_count == total_valid:
        consensus = "unanimous"
    else:
        consensus = "majority"

    # Build vote breakdown
    vote_breakdown = {}
    for r in critic_results:
        vote_breakdown[r.get("model", "Unknown")] = {
            "classification": r["classification"],
            "confidence": r.get("confidence_score", 0.0),
            "reason": r.get("reason", ""),
        }

    # Compile calibration summary
    calibration_parts = []
    for r in valid_results:
        cal = r.get("what_would_change_my_mind", "")
        if cal:
            calibration_parts.append(f"**{r.get('model', 'Unknown')}** ({r['classification']}): {cal}")
    calibration = "\n".join(calibration_parts)

    # Extract the best Executive Summary from the winning models
    best_reason = winning_votes[0].get("reason", "No reason provided")
    for r in winning_votes:
        if "Qwen" in r.get("model", ""):
            best_reason = r.get("reason", "No reason provided")
            break
            
    combined_reason = f"({majority_count}/{total_valid} Consensus): {best_reason}"

    return {
        "classification": final_classification,
        "confidence_score": weighted_confidence,
        "consensus": consensus,
        "reason": combined_reason,
        "vote_breakdown": vote_breakdown,
        "calibration": calibration,
    }


def analyze_media(file_path, content_type, media_type="Image"):
    """
    Sends the media to Qwen-VL to extract visual anomalies, then passes those findings
    to 3 different LLM Critics for majority voting with confidence calibration.
    Supports both images and PDF documents.
    """
    if not OPENROUTER_API_KEY:
        raise Exception("OPENROUTER_API_KEY environment variable not set.")
    if not FEATHERLESS_API_KEY:
        raise Exception("FEATHERLESS_API_KEY environment variable not set.")
    
    # Handle PDF documents vs images
    is_document = media_type == "Document"
    
    if is_document:
        print("  Converting PDF pages to images...")
        page_images_b64 = encode_pdf_pages(file_path)
        print(f"  Rendered {len(page_images_b64)} page(s) from PDF.")
    else:
        base64_image = encode_image(file_path)
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Fraud Detection System",
        "Content-Type": "application/json"
    }

    # ==========================================
    # AGENT 1: VISION FORENSICS (VLM)
    # ==========================================
    if is_document:
        vlm_prompt = """
You are an expert forensic document analyzer specializing in detecting digitally forged, altered, or AI-generated paperwork.
Your task is to scan this document for definitive FORGERY OR GENERATION ARTIFACTS.

Look specifically for the following strong indicators of document fraud:
1. Font inconsistencies, mismatched typography, or jagged/pixelated text that suggests insertion or editing.
2. Misaligned lines, uneven margins, or warped tables/templates.
3. Unnatural digital artifacts, haloing, or blurriness immediately surrounding text/signatures (indicating cloning or copy-pasting).
4. Non-sensical text, garbled characters, or "hallucinated" words typical of AI generation.
5. Inconsistencies in lighting or background texture (e.g., pure white background on a supposedly scanned piece of paper).
6. Missing watermarks, generic signatures, or rubber stamps that look completely uniform and lack real-world bleeding/fade.
7. Inconsistent or impossible dates, ID numbers, or reference codes.
8. Logos or letterheads that look slightly off, blurry, or not matching the official branding of the supposed issuer.

List ALL potential anomalies and indicate their severity. Do NOT output JSON. Just output a detailed forensic report of what you see.
        """
    else:
        vlm_prompt = """
You are an expert forensic image analyzer specializing in detecting high-quality, deceptive AI-generated fraud. 
Your task is to scan this image for definitive AI GENERATION ARTIFACTS.

CRITICAL INSTRUCTION - THE GRID SCAN:
Do NOT just glance at the center of the image. You must mentally divide this image into a 3x3 grid and scan every single quadrant meticulously. 
Look specifically in the deep background and the extreme foreground for microscopic failures in the generation model.

Look for these STRONG, physics-defying indicators of AI:
1. ANATOMICAL HORRORS: Scan every single person in the background. Are their hands mangled? Do they have 6 fingers, or fingers fusing together? Are their faces melting or structurally impossible?
2. IMPOSSIBLE DAMAGE: If a car is heavily dented, is the paint perfectly glossy? Real high-impact crashes cause paint to chip, splinter, and scrape. AI models often generate "dents" that look like pushed-in, smooth clay.
3. PRISTINE DEBRIS: Real accidents have chaotic micro-debris, dirt, and fluid. AI often renders perfectly uniform, clean glass chunks that look like CGI overlays.
4. GIBBERISH TEXT: Zoom in on any street signs, license plates, or storefronts. Are the letters forming coherent English words, or are they impossible, alien-looking glyphs that just *resemble* text from afar?
5. IMPOSSIBLE PHYSICS: Cars melting seamlessly into the ground, wheels intersecting solid objects without shadows.

🚨 DASHCAM OVERRIDE EXCEPTION 🚨
ONLY apply the "dashcam/low-res exception" IF AND ONLY IF the entire image unequivocally looks like a blurry, poorly lit dashcam security video. 
DO NOT use the dashcam exception to excuse unnatural physics, melting objects, or flawless paint jobs on severely dented cars. These are signs of a high-quality AI fake pretending to be real.

List ALL potential anomalies and indicate their severity. 
Did you find melted hands? State it! Did you find alien text? State it! 
Do NOT output JSON. Just output a detailed, aggressive forensic report of what you see.
        """

    vlm_messages = [
        {"role": "system", "content": vlm_prompt}
    ]
    
    # Only inject few-shot examples for images (not documents)
    if not is_document:
        vlm_messages.extend(get_few_shot_examples())
    
    # Build the user message with image(s)
    if is_document:
        # For PDFs: send all pages as separate images in one message
        user_content = [
            {
                "type": "text",
                "text": f"Analyze this {len(page_images_b64)}-page document for forgery or AI generation artifacts. Examine each page carefully."
            }
        ]
        for i, page_b64 in enumerate(page_images_b64):
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{page_b64}"
                }
            })
    else:
        user_content = [
            {
                "type": "text",
                "text": "Extract all visual anomalies from this image."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{content_type};base64,{base64_image}"
                }
            }
        ]
    
    vlm_messages.append({
        "role": "user",
        "content": user_content
    })

    vlm_payload = {
        "model": "qwen/qwen-vl-plus", 
        "messages": vlm_messages,
        "max_tokens": 1000,
    }
    
    vlm_label = "Document Forensics" if is_document else "Vision Forensics"
    print(f"Calling Agent 1: {vlm_label}...")
    vlm_response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=vlm_payload, verify=False)
    if vlm_response.status_code != 200:
        if "<html>" in vlm_response.text.lower():
            raise Exception(f"OpenRouter is down (Cloudflare 502 Bad Gateway). Please try again in a few minutes.")
        raise Exception(f"Vision Agent API Error: {vlm_response.text}")
        
    vlm_findings = vlm_response.json()['choices'][0]['message']['content']
    print(f"{vlm_label} Findings:\n{vlm_findings}\n")

    # ==========================================
    # AGENT 2: MULTI-MODEL CRITIC VOTING
    # ==========================================
    print("Calling Agent 2: Multi-Model Critic Voting (3 models, smart parallel)...")
    
    # Split models by provider to respect Featherless 4-connection limit
    openrouter_models = [m for m in CRITIC_MODELS if "openrouter" in m["api_url"]]
    featherless_models = [m for m in CRITIC_MODELS if "featherless" in m["api_url"]]
    
    def run_featherless_sequential(models, findings):
        """Run Featherless models one after another with a delay to stay within concurrency limit."""
        results = []
        for i, model in enumerate(models):
            if i > 0:
                print(f"  [Rate Limit Control] Pausing 2s before calling {model['name']}...")
                time.sleep(2)
            results.append(call_critic(model, findings, media_type=media_type))
        return results
    
    critic_results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Fire OpenRouter models and Featherless group at the same time
        future_openrouter = [executor.submit(call_critic, m, vlm_findings, media_type) for m in openrouter_models]
        future_featherless = executor.submit(run_featherless_sequential, featherless_models, vlm_findings)
        
        # Collect OpenRouter results
        for f in future_openrouter:
            critic_results.append(f.result())
        
        # Collect Featherless results (list of results)
        critic_results.extend(future_featherless.result())

    # ==========================================
    # AGENT 3: VOTE AGGREGATION
    # ==========================================
    print("\nAggregating votes...")
    aggregated = aggregate_votes(critic_results)
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"FINAL VERDICT: {aggregated['classification']} ({aggregated['consensus']})")
    print(f"Weighted Confidence: {aggregated['confidence_score']}")
    for model, info in aggregated['vote_breakdown'].items():
        print(f"  {model}: {info['classification']} (conf: {info['confidence']})")
    print(f"{'='*50}\n")

    # Build final response (compatible with existing frontend)
    final_json = {
        "thought_process": aggregated.get("reason", ""),
        "classification": aggregated["classification"],
        "confidence_score": aggregated["confidence_score"],
        "reason": aggregated["reason"],
        "vision_findings": vlm_findings,
        "vote_breakdown": aggregated["vote_breakdown"],
        "consensus": aggregated["consensus"],
        "calibration": aggregated.get("calibration", ""),
    }

    return final_json


def analyze_video(file_path):
    """
    Video-specific pipeline logic (Approach 1):
    1. Extract N keyframes.
    2. Run each keyframe through the standard Image pipeline.
    3. Aggregate the frame-level results into a video-level verdict.
    """
    print(f"  Extracting keyframes from video: {file_path}")
    frames_b64 = extract_video_frames(file_path, num_frames=5)
    print(f"  Extracted {len(frames_b64)} frames for analysis.")
    
    if not frames_b64:
        raise Exception("Failed to extract any frames from the video.")
        
    frame_results = []
    
    # Process each frame through the image pipeline
    # We create a temporary function that mimics `analyze_media` but accepts direct b64 instead of a file
    # To keep it simple and reuse existing logic without massive refactoring, we'll write temp images
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, b64_frame in enumerate(frames_b64):
            tmp_path = os.path.join(tmpdir, f"frame_{i}.jpg")
            with open(tmp_path, "wb") as f:
                f.write(base64.b64decode(b64_frame))
                
            print(f"\n--- Analyzing Video Frame {i+1}/{len(frames_b64)} ---")
            try:
                # Treat each frame directly as an Image
                result = analyze_media(tmp_path, "image/jpeg", media_type="Image")
                frame_results.append(result)
            except Exception as e:
                print(f"  ⚠ Failed to analyze frame {i+1}: {e}")
                
    if not frame_results:
        raise Exception("Failed to analyze any of the extracted video frames.")

    # Video-Level Aggregation Logic
    # If >= 60% of frames are fake, the video is fake (e.g., 3 out of 5 frames)
    fake_frames = [r for r in frame_results if r.get("classification") == "Fake"]
    real_frames = [r for r in frame_results if r.get("classification") == "Real"]
    
    total_valid = len(fake_frames) + len(real_frames)
    if total_valid == 0:
        raise Exception("All video frames resulted in errors during analysis.")
        
    fake_ratio = len(fake_frames) / total_valid
    
    if fake_ratio >= 0.6:
        video_verdict = "Fake"
        dominant_frames = fake_frames
        consensus_type = "majority_frames"
        if fake_ratio == 1.0:
            consensus_type = "unanimous_fake_frames"
    else:
        video_verdict = "Real"
        dominant_frames = real_frames
        consensus_type = "majority_frames"
        if fake_ratio == 0.0:
            consensus_type = "unanimous_real_frames"
            
    # Average the confidence of the dominant verdict
    avg_conf = sum(r.get("confidence_score", 0.0) for r in dominant_frames) / max(1, len(dominant_frames))
    
    # Flag inconsistencies
    inconsistency_flag = ""
    if 0.0 < fake_ratio < 1.0:
        inconsistency_flag = f" [! WARNING !] {len(fake_frames)} frames flagged as Fake, while {len(real_frames)} flagged as Real. This inconsistency within the same video is highly suspicious for temporal artifacts or selective editing."
        # If it's a mixed bag, we might want to boost the confidence that it's fake because a real video shouldn't have fake frames
        if video_verdict == "Real" and fake_ratio >= 0.2: # Even 1 or 2 fake frames out of 5 is super sus
            video_verdict = "Fake"
            avg_conf = 0.85 # Override confidence due to suspicious mixed frames
            inconsistency_flag += " Overriding to Fake due to presence of distinct AI artifacts in specific frames."

    # Build a consolidated reason from the worst offending frame
    if video_verdict == "Fake" and fake_frames:
        # Pick the fake frame with highest confidence
        worst_frame = max(fake_frames, key=lambda x: x.get("confidence_score", 0.0))
        consolidated_reason = f"Video-level verdict ({len(fake_frames)}/{total_valid} frames fake): {worst_frame.get('reason', '')}{inconsistency_flag}"
        vision_findings = worst_frame.get('vision_findings', 'No vision findings available.')
    else:
        best_frame = max(real_frames, key=lambda x: x.get("confidence_score", 0.0))
        consolidated_reason = f"Video-level verdict ({len(real_frames)}/{total_valid} frames real): {best_frame.get('reason', '')}{inconsistency_flag}"
        vision_findings = best_frame.get('vision_findings', 'No vision findings available.')

    # Package the final video result
    return {
        "thought_process": "Video analysis aggregated from multiple keyframes.",
        "classification": video_verdict,
        "confidence_score": round(avg_conf, 2),
        "reason": consolidated_reason,
        "vision_findings": f"(Findings from most definitive frame): \n{vision_findings}",
        "vote_breakdown": {f"Frame {i+1}": {"classification": r.get('classification'), "confidence": r.get('confidence_score')} for i, r in enumerate(frame_results)},
        "consensus": consensus_type,
        "calibration": "Temporal anomalies or flickering between frames would alter this.",
    }
