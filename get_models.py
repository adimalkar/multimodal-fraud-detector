import os
import requests
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "").strip()

response = requests.get(
    "https://api.featherless.ai/v1/models",
    headers={"Authorization": f"Bearer {FEATHERLESS_API_KEY}"}
)

if response.status_code == 200:
    models = response.json().get("data", [])
    deepseek_models = [m["id"] for m in models if "deepseek" in m["id"].lower()]
    print("Found DeepSeek models on Featherless:")
    print(json.dumps(deepseek_models, indent=2))
else:
    print(f"Error fetching models: {response.text}")
