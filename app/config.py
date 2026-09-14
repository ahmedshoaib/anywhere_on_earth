import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


MODEL_PATH = os.environ.get("AOE_MODEL_PATH", "") or str(
    PROJECT_ROOT / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
)
MODEL_URL = os.environ.get(
    "AOE_MODEL_URL",
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
)
THREADS = _env_int("AOE_THREADS", min(8, os.cpu_count() or 4))
N_CTX = _env_int("AOE_N_CTX", 4096)
N_GPU_LAYERS = _env_int("AOE_N_GPU_LAYERS", 0)
LLM_TIMEOUT = _env_int("AOE_LLM_TIMEOUT", 60)
LLM_COOLDOWN = _env_int("AOE_LLM_COOLDOWN", 60)
LLM_JSON_MODE = os.environ.get("AOE_LLM_JSON_MODE", "free")
LLM_MAX_TOKENS = _env_int("AOE_LLM_MAX_TOKENS", 512)
MAX_TEXT_CHARS = _env_int("AOE_MAX_TEXT_CHARS", 6000)
DEFAULT_TZ = os.environ.get("AOE_DEFAULT_TZ", "UTC")
CACHE_TTL = _env_int("AOE_CACHE_TTL", 600)
CACHE_SIZE = _env_int("AOE_CACHE_SIZE", 64)
