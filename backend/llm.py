"""LLM layer backed by a self-hosted Ollama server.

IRIS and the recommendation-justification engine call a local Ollama instance
(e.g. Qwen / Llama) over HTTP. If Ollama is unreachable (for example in the
Emergent preview pod, which has no Ollama service), every entry point degrades
gracefully to the deterministic rule-based engine so the app never breaks.

Config (env):
  OLLAMA_BASE_URL   default http://localhost:11434
  OLLAMA_MODEL      default qwen2.5:1.5b
"""
import logging
import os
import threading
import time
from typing import Optional

import requests

logger = logging.getLogger("mssp-soc.llm")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")

# Cached availability so status() is cheap and doesn't hammer the server.
_state = {"available": False, "checked_at": 0.0, "pulling": False, "error": None}
_AVAIL_TTL = 15.0  # seconds


def _ping() -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if r.status_code != 200:
            return False
        models = [m.get("name", "") for m in r.json().get("models", [])]
        # Ready only when the target model tag is present locally.
        return any(m == OLLAMA_MODEL or m.startswith(OLLAMA_MODEL.split(":")[0]) for m in models)
    except Exception as e:
        _state["error"] = str(e)[:200]
        return False


def _refresh_availability(force: bool = False) -> bool:
    now = time.time()
    if not force and (now - _state["checked_at"]) < _AVAIL_TTL:
        return _state["available"]
    _state["available"] = _ping()
    _state["checked_at"] = now
    return _state["available"]


def _pull_model():
    """Ensure the configured model is present (blocking; run in a thread)."""
    if _state["pulling"]:
        return
    _state["pulling"] = True
    try:
        # Wait for the Ollama server to accept connections.
        for _ in range(60):
            try:
                requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
                break
            except Exception:
                time.sleep(2)
        if _ping():
            _refresh_availability(force=True)
            logger.info("Ollama model %s already present", OLLAMA_MODEL)
            return
        logger.info("Pulling Ollama model %s …", OLLAMA_MODEL)
        # Streaming pull; drain the response so it blocks until complete.
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"name": OLLAMA_MODEL},
            stream=True,
            timeout=1800,
        ) as resp:
            for _line in resp.iter_lines():
                pass
        _refresh_availability(force=True)
        logger.info("Ollama model %s ready: %s", OLLAMA_MODEL, _state["available"])
    except Exception:
        logger.exception("Ollama model pull failed (will use rule-based fallback)")
        _state["error"] = "pull failed"
    finally:
        _state["pulling"] = False


def preload_async():
    """Kick off model availability check + pull on startup without blocking."""
    threading.Thread(target=_pull_model, daemon=True).start()


def is_ready() -> bool:
    return _refresh_availability()


def status() -> dict:
    return {
        "model": OLLAMA_MODEL,
        "provider": "ollama",
        "base_url": OLLAMA_BASE_URL,
        "loaded": _refresh_availability(),
        "loading": _state["pulling"],
        "error": _state["error"],
    }


def chat(messages: list, *, max_new_tokens: int = 180, temperature: float = 0.6, top_p: float = 0.9) -> Optional[str]:
    """Send a chat completion to Ollama. Returns text or None on any failure."""
    if not _refresh_availability():
        return None
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": top_p,
                    "num_predict": max_new_tokens,
                },
            },
            timeout=90,
        )
        if r.status_code != 200:
            logger.warning("Ollama chat non-200: %s %s", r.status_code, r.text[:200])
            return None
        content = (r.json().get("message", {}) or {}).get("content", "")
        return content.strip() or None
    except Exception:
        logger.exception("Ollama chat failed")
        return None


SYSTEM_PROMPT = (
    "You are a senior MSSP SOC advisor. Given SOC KPI signals, produce a concise, "
    "cybersecurity-focused justification for the recommendation. Reference MITRE ATT&CK "
    "tactics when relevant, be specific and operationally actionable in 3-4 sentences. "
    "Do NOT invent numbers not present in the context."
)


def _build_prompt(rec: dict, ctx: dict) -> str:
    return (
        f"Recommendation: {rec['title']}\n"
        f"Area: {rec['area']} | Priority: {rec['priority']}\n"
        f"Signal: {rec['insight']}\n"
        f"Suggested action: {rec['action']}\n"
        f"Context: SLA={ctx.get('sla_compliance')}%, MTTR={ctx.get('mttr_hours')}h, "
        f"Detection Coverage={ctx.get('detection_coverage')}%, "
        f"Automation={ctx.get('automation_rate')}%, "
        f"Top Threat Actor={ctx.get('top_threat_actor')}, "
        f"Risk Score={ctx.get('risk_score')}.\n"
        f"Provide a 3-4 sentence executive justification and technical reasoning."
    )


def justify(rec: dict, ctx: dict) -> Optional[str]:
    """Return an LLM-generated justification for a recommendation, or None on failure."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_prompt(rec, ctx)},
    ]
    return chat(messages, max_new_tokens=180, temperature=0.6)


def enrich_recommendations(recs: list, ctx: dict, max_llm: int = 3) -> list:
    """Attach `reasoning` field to top-N recs using the LLM. Others get a placeholder."""
    ready = _refresh_availability()
    for i, r in enumerate(recs):
        if i < max_llm and ready:
            reasoning = justify(r, ctx)
            r["reasoning"] = reasoning or r.get("action")
            r["reasoning_source"] = "ollama" if reasoning else "rule"
        else:
            r["reasoning"] = r.get("action")
            r["reasoning_source"] = "rule"
    return recs
