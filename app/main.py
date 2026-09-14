from __future__ import annotations

import hashlib
import threading
import time as _time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import config, resolve
from .extract import llm, merge, rules
from .schema import ExtractRequest, ExtractResponse, HealthResponse, Localized, NowResponse

STATIC_INDEX = config.APP_DIR / "static" / "index.html"

_cache: "OrderedDict[str, tuple[float, list[resolve.ResolvedCore], bool]]" = OrderedDict()
_cache_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ok = llm.load_model()
    if ok:
        print(f"[aoe] model loaded: {config.MODEL_PATH} (threads={config.THREADS})")
    else:
        print(f"[aoe] {llm.load_error()}")
    yield


app = FastAPI(title="AoE Deadline API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _resolve_tz_name(body_tz: str | None, header_tz: str | None) -> str:
    name = (body_tz or header_tz or config.DEFAULT_TZ or "UTC").strip()
    if resolve.valid_tz(name) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown timezone {name!r}. Use an IANA name such as 'Asia/Karachi' or 'UTC'.",
        )
    return name


def _cores_for(text: str, tz_name: str, fast: bool = False) -> tuple[list[resolve.ResolvedCore], bool]:
    key = hashlib.sha1(f"{text}\x00{tz_name}\x00{int(fast)}".encode("utf-8", "replace")).hexdigest()
    now = _time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < config.CACHE_TTL:
            _cache.move_to_end(key)
            return hit[1], hit[2]
    rules_cands = rules.find_candidates(text)
    if fast:
        llm_cands, degraded = [], True
    else:
        llm_cands, degraded = llm.extract(text)
    now_utc = datetime.now(timezone.utc)
    cores = []
    for c in merge.merge_candidates(rules_cands, llm_cands):
        try:
            core = resolve.resolve_candidate(c, now_utc, tz_name)
        except Exception:
            core = None
        if core is not None:
            cores.append(core)
    seen: set = set()
    uniq: list[resolve.ResolvedCore] = []
    for core in cores:
        k = (core.deadline_utc, core.raw_text.strip().lower())
        if k not in seen:
            seen.add(k)
            uniq.append(core)
    degraded = degraded or not llm.model_available()
    with _cache_lock:
        _cache[key] = (now, uniq, degraded)
        _cache.move_to_end(key)
        while len(_cache) > config.CACHE_SIZE:
            _cache.popitem(last=False)
    return uniq, degraded


@app.post("/api/extract", response_model=ExtractResponse)
def api_extract(req: ExtractRequest, x_timezone: Annotated[str | None, Header()] = None) -> ExtractResponse:
    if len(req.text) > config.MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Text too long (max {config.MAX_TEXT_CHARS} characters).",
        )
    tz_name = _resolve_tz_name(req.tz, x_timezone)
    cores, degraded = _cores_for(req.text, tz_name, req.fast)
    now_utc = datetime.now(timezone.utc)
    deadlines = [resolve.finalize(core, now_utc, tz_name) for core in cores]
    deadlines.sort(key=lambda d: d.epoch_seconds)
    return ExtractResponse(now_utc=now_utc, requester_tz=tz_name, degraded=degraded, deadlines=deadlines)


@app.get("/api/now", response_model=NowResponse)
def api_now(tz: str | None = None, x_timezone: Annotated[str | None, Header()] = None) -> NowResponse:
    name = _resolve_tz_name(tz, x_timezone)
    now_utc = datetime.now(timezone.utc)
    local_dt = now_utc.astimezone(resolve.valid_tz(name))
    return NowResponse(
        now_utc=now_utc, tz=name,
        local=Localized(tz=name, iso=local_dt, human=resolve.humanize(local_dt, resolve.valid_tz(name))),
    )


@app.get("/api/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=llm.model_available(),
        degraded=not llm.model_available(),
        model_path=config.MODEL_PATH,
        model_error=llm.load_error(),
    )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_INDEX)
