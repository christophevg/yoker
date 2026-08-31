import json
import os

import requests

api_key = os.environ["OLLAMA_API_KEY"]

resp = requests.get(
  "https://ollama.com/api/usage",
  headers={"Authorization": f"Bearer {api_key}"},
)
data = resp.json()
print(json.dumps(data, indent=2))
