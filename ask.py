# src/ask.py
from __future__ import annotations
import os, requests, json

# read env vars for ollama
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

class OllamaUnavailable(RuntimeError):
    pass

def ensure_ollama_available() -> dict:
    """fail fast if ollama server isn't reachable"""
    # derive base from ollama_url
    base = OLLAMA_URL.split("/api/")[0]
    r = requests.get(f"{base}/api/version", timeout=10)
    r.raise_for_status()
    return r.json()

def ask_ollama(prompt: str, system: str | None = None) -> str:
    """plain q&a call to ollama"""
    if system is None:
        system = (
            "You are an AI assistant in a water analytics app. "
            "Be concise. If asked for insights, summarize clearly."
        )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role":"system","content": system},
            {"role":"user","content": prompt}
        ],
        "stream": False
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    # prefer 'message.content'; fallback to 'response'
    return (data.get("message") or {}).get("content") or data.get("response") or ""

import json, re

def _safe_json_extract(s: str) -> dict:
    """extract first json object from text; return {} on failure"""
    if not isinstance(s, str):
        return {}
    # remove optional code fences
    s = s.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.IGNORECASE | re.MULTILINE)
    # find brace bounds
    m_start = s.find("{")
    m_end = s.rfind("}")
    if m_start == -1 or m_end == -1 or m_end <= m_start:
        return {}
    try:
        return json.loads(s[m_start:m_end+1])
    except Exception:
        return {}

def plan_query(query: str) -> dict:
    """return compact json plan describing which analytic to run"""
    system = (
        "You are a planner for a water analytics app. "
        "Return ONLY a single minified JSON object describing what to run. "
        "Schema: {\"action\": <string>, \"params\": {\"parameter\": <string?>, "
        "\"range_days\": <int?>, \"min_duration_min\": <int?>}}. "
        "Allowed actions: flow_shift, flow_daily, quality_compliance, breach_events, humidity_vs_flow, none. "
        "Examples:\n"
        "{\"action\":\"quality_compliance\",\"params\":{\"parameter\":\"ETP (TDS)\",\"range_days\":7}}\n"
        "{\"action\":\"flow_shift\",\"params\":{\"range_days\":1}}\n"
        "Prefer setting range_days (e.g., 1 for yesterday, 7 for last 7 days, 30 for last month). "
        "If ambiguous, choose flow_daily with {\"range_days\":7}. "
        "Do NOT include explanations, markdown, or code fences—JSON ONLY."
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": query}
        ],
        "stream": False
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    text = (data.get("message") or {}).get("content") or data.get("response") or ""
    plan = _safe_json_extract(text)
    if not isinstance(plan, dict):
        plan = {}
    # ensure keys exist
    plan.setdefault("action", "none")
    plan.setdefault("params", {})
    if not isinstance(plan["params"], dict):
        plan["params"] = {}
    return plan
