import json
from backend.qwen_agent import call_critic, CRITIC_MODELS
import urllib3
urllib3.disable_warnings()

deepseek_config = next(m for m in CRITIC_MODELS if "DeepSeek" in m["name"])
findings = "The image shows unnaturally smooth paint, characteristic of AI generation."
print("Testing DeepSeek...")
result = call_critic(deepseek_config, findings)
print(result)
