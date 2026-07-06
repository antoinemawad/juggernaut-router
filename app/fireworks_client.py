import json
import os
import urllib.request


def ask_fireworks(prompt: str) -> str:
    api_key = os.environ.get("FIREWORKS_API_KEY")
    base_url = os.environ.get("FIREWORKS_BASE_URL")
    allowed_models = os.environ.get("ALLOWED_MODELS", "")

    if not api_key or not base_url or not allowed_models:
        return "Missing Fireworks environment variables."

    model = allowed_models.split(",")[0].strip()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Answer accurately and concisely in English."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0,
        "max_tokens": 256
    }

    url = base_url.rstrip("/") + "/chat/completions"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))

    return data["choices"][0]["message"]["content"].strip()
