import os, requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435/api/chat")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Reply with the single word: READY"}
    ],
    "stream": False  # ask for single json response
}

r = requests.post(OLLAMA_URL, json=payload, timeout=60)
r.raise_for_status()

data = r.json()
# prefer message.content; fallback to response
content = (data.get("message") or {}).get("content") or data.get("response") or ""
print("MODEL:", MODEL)
print("REPLY:", content.strip())
