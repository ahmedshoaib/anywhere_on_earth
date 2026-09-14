# AoE Deadline API

Paste any deadline text (a call for papers, an email, a syllabus) and get every date
extracted, interpreted with correct **Anywhere-on-Earth (AoE = UTC−12)** semantics,
converted to **your** timezone, and shown as a **live countdown**.

A tiny local LLM (Qwen2.5-1.5B-Instruct, ~1 GB GGUF) handles oddly-phrased dates;
a deterministic regex/dateparser fast path handles formulaic ones instantly and
validates everything. All timezone, DST and leap-year math is done in Python —
the model never does arithmetic.
MAKE sure to create a models/ folder in the working dir
## Quick start (Docker)

```bash
docker compose up -d --build     # CPU image, ~1.7 GB, bakes the model
open http://localhost:8000
```

GPU variant (needs `nvidia-container-toolkit`, ~10–25 min build) — **experimental**:

```bash
docker compose --profile gpu up -d --build
```


## Performance

| Mode | LLM extraction latency | Notes |
|---|---|---|
| CPU image (default, 14 threads) | ~15–40 s | formulaic dates parse instantly via the rules fast path; results are cached (`AOE_CACHE_TTL`) so repeats are instant |
| `fast: true` / "fast (skip LLM)" | ~10 ms | rules-only — instant, but relative/unusual phrasing is skipped |
| GPU image | ~0.4 s while alive | experimental — see warning above |

The regex fast path answers in milliseconds for standard CFP phrasing; the LLM
tier only adds the odd cases (relative dates, unusual formats). Pass
`"fast": true` in the request body (or tick the box on the page) to skip the
LLM tier entirely for instant responses.

## The webpage

`http://localhost:8000` — paste text, pick a timezone (auto-detected by default),
hit **Extract deadlines** (or Ctrl+Enter). Each deadline card shows:

- the raw phrase and its label ("Full paper deadline", "Camera-ready due", …)
- your local date/time (large), plus UTC and epoch
- a **ticking countdown** (green > 24 h, amber < 24 h, red < 1 h, grey when passed)
- an **AoE badge** when the phrase is Anywhere-on-Earth
- alternative interpretations when the phrasing is ambiguous

Results are shareable: the URL carries `?text=…&tz=…` (Copy link button).

## API

### `POST /api/extract`

```bash
curl -s localhost:8000/api/extract \
  -H 'Content-Type: application/json' \
  -H 'X-Timezone: Asia/Karachi' \
  -d '{"text": "Full paper deadline: March 3, 2027, 11:59 PM AoE"}' | jq
```

Request body: `{"text": "...", "tz": "Asia/Karachi", "fast": false}` — `tz`
optional (resolution order: body `tz` → `X-Timezone` header → `AOE_DEFAULT_TZ`
env → UTC); `fast: true` skips the LLM tier.

Response (abridged):

```json
{
  "now_utc": "2026-09-14T12:00:00Z",
  "requester_tz": "Asia/Karachi",
  "degraded": false,
  "deadlines": [
    {
      "raw_text": "March 3, 2027, 11:59 PM AoE",
      "label": "Full paper deadline",
      "kind": "deadline",
      "aoe": true,
      "tz_source": "aoe",
      "source": "rules",
      "deadline_utc": "2027-03-04T11:59:00Z",
      "epoch_seconds": 1801874340,
      "local": {"tz": "Asia/Karachi", "iso": "2027-03-04T16:59:00+05:00",
                 "human": "Thu, Mar 04, 2027 · 4:59 pm PKT"},
      "remaining": {"expired": false, "total_seconds": 17551434, "days": 203,
                     "hours": 3, "minutes": 44, "seconds": 54, "human": "203d 3h 44m"}
    }
  ]
}
```

Fields: `kind` ∈ deadline / abstract_deadline / notification / camera_ready /
rebuttal / other; `source` ∈ rules (fast path) / llm; `tz_source` ∈ aoe / explicit /
date_only_default / requester_tz_fallback / relative.

### Other endpoints

- `GET /api/now?tz=Asia/Karachi` — server time in your timezone
- `GET /api/health` — liveness, model status
- `GET /docs` — OpenAPI UI

Errors: unknown timezone → 400; text > `AOE_MAX_TEXT_CHARS` → 413; empty text → 422.

## Interpretation rules

| Phrase | Interpretation |
|---|---|
| `11:59 PM AoE` / `Anywhere on Earth` / `UTC-12` | time at UTC−12 (AoE) |
| explicit zone (`CEST`, `PDT`, `Asia/Tokyo`, `UTC+2`) | exactly as stated |
| date **and** time, no zone | your timezone (UTC & AoE alternatives returned) |
| date only (`due May 10, 2027`) | **23:59 AoE** primary; UTC and your-tz end-of-day returned as alternatives |
| relative (`tomorrow`, `next Friday`) | your timezone as of now |
| no year (`Jan 15`) | next occurrence (future) |

Notes: fixed offsets are used for abbreviations (`PST` = UTC−8 even in summer);
`IST` is read as India UTC+5:30; `15/03/2026` day-first slash dates are supported
as a fallback but `03/15/2026` month-first wins; timezone-qualified ISO-8601
(`2027-06-01T23:59:59-12:00`) is parsed directly.

## Configuration (env vars)

| Var | Default | Meaning |
|---|---|---|
| `AOE_MODEL_PATH` | `models/qwen2.5-1.5b-instruct-q4_k_m.gguf` | GGUF path; missing → rules-only degraded mode |
| `AOE_THREADS` | min(8, cpus) | llama.cpp CPU threads |
| `AOE_N_CTX` | 4096 | context window |
| `AOE_N_GPU_LAYERS` | 0 | offload layers (GPU image sets 999) |
| `AOE_LLM_TIMEOUT` | 60 s | per-request LLM timeout; timeout → fast path only |
| `AOE_LLM_COOLDOWN` | 60 s | after a timeout, skip LLM calls for this long (avoids queue pile-up) |
| `AOE_LLM_JSON_MODE` | free | `free` = unconstrained decoding (default; llama.cpp grammar sampling crashes the process with some models); `json` = built-in JSON grammar; `schema` = JSON-schema grammar — only use these if stable on your build |
| `AOE_MAX_TEXT_CHARS` | 6000 | request size cap |
| `AOE_DEFAULT_TZ` | UTC | fallback timezone |
| `AOE_CACHE_TTL` / `AOE_CACHE_SIZE` | 600 / 64 | parse cache |

Swap models by overriding the build arg, e.g. Qwen2.5-0.5B:

```bash
docker build --build-arg MODEL_URL=https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0_5b-instruct-q4_k_m.gguf -t aoe-api:0125b .
```

## Local development (no Docker)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
bash scripts/download_model.sh
bash scripts/dev_server.sh          # or: uvicorn app.main:app --port 8000
```

Without the model file the API still works in degraded (fast-path) mode.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Layout

```
app/
├── main.py            FastAPI routes, cache, static page
├── config.py          env knobs
├── schema.py          pydantic models
├── resolve.py         AoE/tz math, defaults, alternates, remaining time
├── extract/
│   ├── rules.py       regex fast path (tier 1)
│   ├── llm.py         Qwen 1.5B + JSON-schema-constrained decoding (tier 2)
│   └── merge.py       span dedupe + enrichment
└── static/index.html  dependency-free page with live countdown
```
