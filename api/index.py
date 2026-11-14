"""FastAPI entrypoint. Runs locally with uvicorn and on Vercel's Python runtime (api/index.py)."""
from __future__ import annotations

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from _radar import clients, config, pipeline  # noqa: E402

app = FastAPI(title="Reputation Radar API")


def _load(name: str) -> Any:
    p = config.DATA_DIR / name
    return json.loads(p.read_text()) if p.exists() else None


@app.exception_handler(config.MissingKey)
async def _missing(_: Request, exc: config.MissingKey):
    return JSONResponse(status_code=400, content={"error": str(exc), "missing_env": exc.var})


@app.exception_handler(clients.ApiError)
async def _api_err(_: Request, exc: clients.ApiError):
    return JSONResponse(status_code=502, content={"error": str(exc), "service": exc.service, "upstream_status": exc.status})


class Profile(BaseModel):
    name: str
    kind: str = "company"
    aliases: list[str] = []
    description: str = ""
    website: str = ""
    region: str = ""
    industry: str = ""
    priorities: str = ""


class SearchReq(BaseModel):
    profile: Profile
    mode: str = "live"  # live | fixture
    seen_urls: list[str] = []
    published_after: str = "30d"
    max_results: int = Field(8, ge=1, le=20)


class FetchReq(BaseModel):
    candidate: dict[str, Any]
    mode: str = "live"


class ExtractReq(BaseModel):
    profile: Profile
    doc: dict[str, Any]
    mode: str = "live"
    use_cache: bool = True


class DecideReq(BaseModel):
    profile: Profile
    doc: dict[str, Any]
    facts: dict[str, Any] | None = None
    prior: list[dict[str, Any]] = []
    replay: bool = False  # fixture-only: return a recorded real Drex response instead of calling the API


class BriefReq(BaseModel):
    profile: Profile
    items: list[dict[str, Any]]


@app.get("/api/health")
def health():
    keys = config.key_status()
    keys.pop("KEENABLE_API_KEY", None)  # optional: keyless /public endpoints are used when unset
    return {"keys": keys, "keenable_mode": clients.keenable_mode(), "drex_model": config.DREX_MODEL, "llm_model": config.DEEPINFRA_MODEL,
            "baseline_model": config.BASELINE_MODEL}


@app.get("/api/fixtures")
def fixtures():
    return _load("fixtures.json")


@app.post("/api/search")
def search(req: SearchReq):
    if req.mode == "fixture":
        fx = _load("fixtures.json")
        seen = {pipeline.canonical_url(u) for u in req.seen_urls}
        cands, already = [], 0
        for a in fx["articles"]:
            cu = pipeline.canonical_url(a["url"])
            if cu in seen:
                already += 1
                continue
            cands.append({"id": a["id"], "url": a["url"], "canonical_url": cu, "title": a["title"], "snippet": a["text"][:200],
                          "published_at": a["published_at"], "query": "(fixture)"})
        return {"queries": ["(fixture dataset — no web search)"], "candidates": cands,
                "stats": {"raw": len(fx["articles"]), "duplicates_in_scan": 0, "already_seen": already, "unique_new": len(cands)},
                "mode": "fixture"}
    out = pipeline.search(req.profile.model_dump(), seen_urls=req.seen_urls, published_after=req.published_after,
                          max_results=req.max_results)
    out["mode"] = "live"
    return out


@app.post("/api/fetch")
def fetch(req: FetchReq):
    if req.mode == "fixture":
        fx = _load("fixtures.json")
        a = next((x for x in fx["articles"] if x["id"] == req.candidate.get("id")), None)
        if not a:
            return JSONResponse(status_code=404, content={"error": "fixture not found"})
        return {**req.candidate, "title": a["title"], "outlet": a["outlet"], "published_at": a["published_at"],
                "retrieved_at": pipeline.now_iso(), "text": a["text"], "source": "fixture"}
    return pipeline.fetch(req.candidate)


@app.post("/api/extract")
def extract(req: ExtractReq):
    if req.mode == "fixture" and req.use_cache:
        cache = _load("ndi_cache.json") or {}
        if req.doc.get("id") in cache:
            return {**cache[req.doc["id"]], "cached": True}
    ndi = pipeline.ndi_extract(req.doc, req.profile.model_dump())
    return {**ndi, "cached": False}


@app.post("/api/decide")
def decide(req: DecideReq):
    profile = req.profile.model_dump()
    facts = pipeline.facts_with_fields(req.facts) if req.facts and "data" in req.facts else req.facts
    if req.replay:
        rec = (_load("drex_replay.json") or {}).get(req.doc.get("id"))
        if not rec:
            return JSONResponse(status_code=404, content={"error": f"No recorded Drex response for {req.doc.get('id')} (replay is fixture-only)."})
        return {**rec, "replayed": True, "evidence": pipeline.pick_evidence(req.doc, facts)}
    out = pipeline.drex_decide(profile, req.doc, pipeline.strip_internal(facts), req.prior)
    out["evidence"] = pipeline.pick_evidence(req.doc, facts)
    return out


@app.post("/api/brief")
def brief(req: BriefReq):
    return pipeline.write_briefing(req.profile.model_dump(), req.items)


@app.get("/api/benchmark")
def benchmark():
    return _load("benchmark_latest.json") or {"available": False, "message": "No benchmark run yet. Run: python scripts/benchmark.py"}
