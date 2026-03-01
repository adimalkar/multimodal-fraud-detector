import os
import base64
import json
import requests
import glob
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

from PIL import Image
import io

def encode_image(image_path, max_size=(800, 800)):
    # Open the image, resize and compress it in memory before encoding to save payload bytes
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=75)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

def get_few_shot_examples():
    examples_dir = r"D:\Stevens Hackathon\car-accident images"
    images = glob.glob(os.path.join(examples_dir, "*.jpeg"))
    # Take 2 images for the few-shot context
    images = images[:2]
    
    few_shot_messages = []
    for img_path in images:
        try:
            b64 = encode_image(img_path)
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
            few_shot_messages.append({
                "role": "assistant",
                "content": json.dumps({
                    "thought_process": "Scanning the image for AI artifacts. (1) Text checking: The street signs and license plates consist of unreadable, non-alphanumeric alien text. (2) Anatomy: The people in the background have distorted faces and an incorrect number of fingers. (3) Physics/Structure: The car's crumpled bumper seems to melt into the asphalt seamlessly without proper texturing. (4) Lighting: Shadows fall in contradictory directions. Conclusion: The image is riddled with generative AI artifacts.",
                    "classification": "Fake",
                    "confidence_score": 0.99,
                    "reason": "Unreadable garbled text on signs, morphing structural components on the cars, and anatomically incorrect bystanders in the background."
                })
            })
        except Exception as e:
            print(f"Failed to load few-shot image {img_path}: {e}")
            
    return few_shot_messages

def analyze_media(file_path, content_type):
    """
    Sends the media to Qwen-VL to extract visual anomalies, then passes those findings
    to a Qwen LLM Critic to determine the final fraud classification.
    """
    if not OPENROUTER_API_KEY:
        raise Exception("OPENROUTER_API_KEY environment variable not set.")
    
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
    vlm_prompt = """
You are an elite forensic image analyzer. 
Scan this image aggressively for AI GENERATION ARTIFACTS.
Look specifically for:
1. Garbled/alien text on signs or vehicles.
2. Mangled hands, faces, or limbs on people.
3. Physics/geometry errors (cars melting, doors leading nowhere).
4. Studio-quality lighting or perfect cinematic framing (real claims are amateur).
5. Impossible camera angles (e.g. drone height without reason).
6. Damage that doesn't make physical sense.
7. Shadow logic errors.
8. Background blurring or morphing.
9. Faint watermarks/logos in the corners.

List all visual anomalies you find in detail. If you find none, explicitly state "No anomalies found." 
Do NOT output JSON. Just output a detailed forensic report of what you see.
    """

    vlm_messages = [
        {"role": "system", "content": vlm_prompt}
    ]
    
    # Inject few-shot examples into the VLM phase
    vlm_messages.extend(get_few_shot_examples())
    
    vlm_messages.append({
        "role": "user",
        "content": [
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
    })

    vlm_payload = {
        "model": "qwen/qwen-vl-plus", 
        "messages": vlm_messages,
    }
    
    print("Calling Agent 1: Vision Forensics...")
    vlm_response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=vlm_payload)
    if vlm_response.status_code != 200:
        raise Exception(f"Vision Agent API Error: {vlm_response.text}")
        
    vlm_findings = vlm_response.json()['choices'][0]['message']['content']
    print(f"Vision Agent Findings:\n{vlm_findings}\n")

    # ==========================================
    # AGENT 2: LLM CRITIC (Text Model)
    # ==========================================
    llm_prompt = f"""
You are the Lead Fraud Investigator and Critic.
Your subordinate (a Vision AI) has extracted the following raw visual anomalies from an insurance claim image:

--- VISION AGENT FINDINGS ---
{vlm_findings}
-----------------------------

Your job is to CRITIQUE these findings contextually and make the final ruling on whether the image is genuinely Real or an AI-generated Fake.
- Keep in mind that real insurance photos are taken by amateurs, which explains bad lighting or weird framing.
- If the Vision Agent spotted explicitly garbled text or mangled hands, you should heavily penalize the image.

THINK STEP-BY-STEP before classifying.
You MUST output your final decision in strict JSON format.

Required JSON Schema:
{{
  "thought_process": "<Critique the Vision Agent's findings step-by-step and reason towards a conclusion.>",
  "classification": "Real" | "Fake",
  "confidence_score": <float between 0.0 and 1.0>,
  "reason": "<A summary explanation of your final verdict based on your critique.>"
}}
    """

    llm_payload = {
        "model": "qwen/qwen-turbo", # Advanced reasoning text model
        "messages": [
            {"role": "user", "content": llm_prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    
    print("Calling Agent 2: LLM Critic...")
    llm_response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=llm_payload)
    if llm_response.status_code != 200:
        raise Exception(f"LLM Critic API Error: {llm_response.text}")
        
    result_text = llm_response.json()['choices'][0]['message']['content']
    result_text = result_text.replace("```json\n", "").replace("```\n", "").replace("```", "").strip()
    
    try:
        final_json = json.loads(result_text)
        # Inject the raw vision findings into the UI payload so the user can see them
        final_json["vision_findings"] = vlm_findings
        return final_json
    except json.JSONDecodeError:
        return {
            "thought_process": "Failed to parse JSON from LLM Critic.",
            "classification": "Error Parsing JSON",
            "confidence_score": 0.0,
            "reason": f"Raw output: {result_text}",
            "vision_findings": vlm_findings
        }
