import concurrent.futures
import json
import os
import re
import threading
import time as _time

from .. import config
from .types import Candidate

KINDS = ("deadline", "abstract_deadline", "notification", "camera_ready", "rebuttal", "other")

SYSTEM_PROMPT = """You extract deadline dates and times from text such as calls for papers.
Find every mention of a date or deadline, including date-only and relative dates.
For each one, output an object with these fields:
- "text": the exact phrase from the input containing the date (include its time and timezone if present)
- "label": a short nearby label such as "Full paper deadline" ("" if none)
- "kind": one of "deadline", "abstract_deadline", "notification", "camera_ready", "rebuttal", "other"
- "date": the date part exactly as written ("" if the phrase is relative)
- "time": the time part exactly as written ("" if none)
- "aoe": true only if the phrase mentions AoE, Anywhere on Earth, or UTC-12
- "tz_hint": the timezone exactly as written, e.g. "CET", "Asia/Tokyo", "UTC+2" ("" if none)
- "relative": true only for dates relative to today, such as "tomorrow" or "next Friday"
Never invent dates that are not in the input. Output only JSON: {"deadlines": [ ... ]}"""

_EX1_USER = (
    "Important dates: Abstracts due January 15, 2027, 11:59 PM AoE. "
    "Notification of acceptance: April 20, 2027, 17:00 CEST. "
    "Camera-ready versions are due 2026-05-01."
)
_EX1_ASSISTANT = {
    "deadlines": [
        {"text": "January 15, 2027, 11:59 PM AoE", "label": "Abstracts due", "kind": "abstract_deadline",
         "date": "January 15, 2027", "time": "11:59 PM", "aoe": True, "tz_hint": "", "relative": False},
        {"text": "April 20, 2027, 17:00 CEST", "label": "Notification of acceptance", "kind": "notification",
         "date": "April 20, 2027", "time": "17:00", "aoe": False, "tz_hint": "CEST", "relative": False},
        {"text": "2026-05-01", "label": "Camera-ready versions are due", "kind": "camera_ready",
         "date": "2026-05-01", "time": "", "aoe": False, "tz_hint": "", "relative": False},
    ]
}
_EX2_USER = "Submissions close tomorrow at 5pm. Workshop proposals are due in 3 days."
_EX2_ASSISTANT = {
    "deadlines": [
        {"text": "tomorrow at 5pm", "label": "Submissions close", "kind": "deadline",
         "date": "", "time": "5pm", "aoe": False, "tz_hint": "", "relative": True},
        {"text": "in 3 days", "label": "Workshop proposals are due", "kind": "deadline",
         "date": "", "time": "", "aoe": False, "tz_hint": "", "relative": True},
    ]
}

FEWSHOT = [
    {"role": "user", "content": _EX1_USER},
    {"role": "assistant", "content": json.dumps(_EX1_ASSISTANT)},
    {"role": "user", "content": _EX2_USER},
    {"role": "assistant", "content": json.dumps(_EX2_ASSISTANT)},
]

SCHEMA = {
    "type": "object",
    "properties": {
        "deadlines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "label": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                    "aoe": {"type": "boolean"},
                    "tz_hint": {"type": "string"},
                    "relative": {"type": "boolean"},
                },
                "required": ["text", "label", "kind", "date", "time", "aoe", "tz_hint", "relative"],
            },
        }
    },
    "required": ["deadlines"],
}

_llm = None
_load_error: str | None = None
_lock = threading.Lock()
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm")
_cooldown_until = 0.0


def model_available() -> bool:
    return _llm is not None


def load_error() -> str | None:
    return _load_error


def load_model() -> bool:
    global _llm, _load_error
    path = config.MODEL_PATH
    if not path or not os.path.exists(path):
        _load_error = f"model file not found: {path!r} - running in rules-only degraded mode"
        return False
    try:
        from llama_cpp import Llama
    except ImportError as e:
        _load_error = f"llama-cpp-python not installed: {e}"
        return False
    try:
        _llm = Llama(
            model_path=path,
            n_ctx=config.N_CTX,
            n_threads=config.THREADS,
            n_gpu_layers=config.N_GPU_LAYERS,
            verbose=False,
        )
        _chat_completion("Abstracts due January 15, 2027, 11:59 PM AoE")
        return True
    except Exception as e:
        _llm = None
        _load_error = f"failed to load model: {e}"
        return False


def extract(text: str) -> tuple[list[Candidate], bool]:
    global _cooldown_until
    if _llm is None:
        return [], True
    if _time.monotonic() < _cooldown_until:
        return [], True
    fut = _executor.submit(_chat_completion, text[:4000])
    try:
        content = fut.result(timeout=config.LLM_TIMEOUT)
    except concurrent.futures.TimeoutError:
        _cooldown_until = _time.monotonic() + config.LLM_COOLDOWN
        return [], True
    except Exception:
        return [], True
    return _parse_content(content, text), False


def _response_format() -> dict | None:
    mode = config.LLM_JSON_MODE
    if mode == "schema":
        return {"type": "json_object", "schema": SCHEMA}
    if mode == "json":
        return {"type": "json_object"}
    return None


def _chat_completion(text: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *FEWSHOT, {"role": "user", "content": text}]
    kwargs = dict(messages=messages, temperature=0.0, max_tokens=config.LLM_MAX_TOKENS)
    rf = _response_format()
    if rf is not None:
        kwargs["response_format"] = rf
    with _lock:
        resp = _llm.create_chat_completion(**kwargs)
    return resp["choices"][0]["message"]["content"]


def _parse_content(content: str, text: str) -> list[Candidate]:
    data = _loads_lenient(content)
    if not isinstance(data, dict):
        return []
    cands: list[Candidate] = []
    for d in data.get("deadlines") or []:
        if not isinstance(d, dict):
            continue
        phrase = (d.get("text") or "").strip()
        if not phrase:
            continue
        span = _locate(phrase, text)
        if span is None:
            continue
        kind = d.get("kind") if d.get("kind") in KINDS else "other"
        cands.append(
            Candidate(
                raw=phrase,
                start=span[0],
                end=span[1],
                date_str=(d.get("date") or "").strip() or None,
                time_str=(d.get("time") or "").strip() or None,
                aoe=bool(d.get("aoe")),
                tz_hint=(d.get("tz_hint") or "").strip() or None,
                relative=bool(d.get("relative")),
                label=(d.get("label") or "").strip() or None,
                kind=kind,
                source="llm",
            )
        )
    return cands


def _loads_lenient(content: str):
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    lo = content.find("{")
    hi = content.rfind("}")
    if lo >= 0 and hi > lo:
        try:
            return json.loads(content[lo:hi + 1])
        except json.JSONDecodeError:
            return None
    return None


def _locate(phrase: str, text: str) -> tuple[int, int] | None:
    i = text.find(phrase)
    if i >= 0:
        return (i, i + len(phrase))
    pat = re.escape(phrase).replace(r"\ ", r"\s+")
    m = re.search(pat, text, re.IGNORECASE)
    if m is not None:
        return (m.start(), m.end())
    return None
