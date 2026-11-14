"""Thin HTTP clients for Keenable, Nace (Drex + NDI/Perception) and DeepInfra.

Endpoints and shapes follow the official docs (Nov 2026):
- Keenable: POST /v1/search, GET /v1/fetch, header X-API-Key
- Drex:     POST {NACE}/v1/systemone {model, state, questions}
- NDI:      POST /v1/documents/upload-grants -> multipart upload -> POST /v1/documents/extract?wait_seconds=N
            GET /v1/documents/jobs/{job_id}
- DeepInfra: OpenAI-compatible POST /v1/openai/chat/completions
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from . import config


class ApiError(RuntimeError):
    def __init__(self, service: str, message: str, status: int | None = None):
        super().__init__(f"{service}: {message}")
        self.service, self.status = service, status


def _check(service: str, resp: httpx.Response) -> dict[str, Any]:
    if resp.status_code >= 400:
        if resp.headers.get("x-vercel-mitigated") or "Vercel Security Checkpoint" in resp.text[:2000]:
            raise ApiError(service, f"HTTP {resp.status_code}: {resp.request.url.host} is behind a Vercel security checkpoint "
                           "(bot challenge on the provider's side), so API calls are blocked. Not a key or app problem; "
                           "retry later or tell the organizers.", resp.status_code)
        body = resp.text[:500]
        raise ApiError(service, f"HTTP {resp.status_code}: {body}", resp.status_code)
    try:
        return resp.json()
    except ValueError as exc:
        raise ApiError(service, f"non-JSON response: {resp.text[:200]}") from exc


# ---------------------------------------------------------------- Keenable
def _keenable(path: str) -> tuple[str, dict[str, str]]:
    """Keyed endpoint when KEENABLE_API_KEY is set; otherwise Keenable's documented keyless /public endpoint."""
    key = config.env("KEENABLE_API_KEY")
    if key:
        return f"{config.KEENABLE_BASE_URL}{path}", {"X-API-Key": key}
    return f"{config.KEENABLE_BASE_URL}{path}/public", {"X-Keenable-Title": "Project Halo"}


def keenable_mode() -> str:
    return "keyed" if config.env("KEENABLE_API_KEY") else "keyless-public"


def keenable_search(query: str, *, published_after: str | None = None, max_results: int = 10,
                    exclude_domains: list[str] | None = None) -> dict[str, Any]:
    url, headers = _keenable("/v1/search")
    body: dict[str, Any] = {"query": query, "max_results": max_results, "snippet_max_length": 400}
    if published_after:
        body["published_after"] = published_after
    if exclude_domains:
        body["exclude_domains"] = exclude_domains
    with httpx.Client(timeout=30) as c:
        r = c.post(url, json=body, headers=headers)
    return _check("keenable.search", r)


def keenable_fetch(url: str, *, max_chars: int = 12000) -> dict[str, Any]:
    endpoint, headers = _keenable("/v1/fetch")
    with httpx.Client(timeout=45) as c:
        r = c.get(endpoint, params={"url": url, "max_chars": max_chars}, headers=headers)
    return _check("keenable.fetch", r)


# ---------------------------------------------------------------- Nace common
def _nace_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.require('NACE_API_KEY')}"}


# ---------------------------------------------------------------- Drex
def drex_systemone(state: str, questions: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    body = {"model": model or config.DREX_MODEL, "state": state, "questions": questions}
    t0 = time.perf_counter()
    with httpx.Client(timeout=60) as c:
        r = c.post(f"{config.NACE_BASE_URL}/v1/systemone", json=body, headers=_nace_headers())
    data = _check("drex", r)
    data["_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return data


# ---------------------------------------------------------------- NDI / Perception
def ndi_upload_markdown(path: str, markdown: str) -> dict[str, str]:
    """Upload a Markdown document to the Nace workspace and return a workspace_file source."""
    with httpx.Client(timeout=60) as c:
        g = _check("ndi.upload-grant", c.post(f"{config.NACE_BASE_URL}/v1/documents/upload-grants",
                                              json={"path": path, "ttl_seconds": 600}, headers=_nace_headers()))
        files = {"file": (path.split("/")[-1], markdown.encode("utf-8"), "text/markdown")}
        meta = {"metadata": json.dumps({"path": path, "on_conflict": "new_version"})}
        up = _check("ndi.upload", c.post(g["upload_url"], headers={"X-Upload-Token": g["token"]}, files=files, data=meta))
        job = up
        # The upload response is a job; wait for it if it is not finished yet.
        deadline = time.time() + 60
        while (job.get("status") not in (None, "succeeded")) and time.time() < deadline:
            if job.get("status") in ("failed", "cancelled"):
                raise ApiError("ndi.upload", f"upload job {job.get('status')}: {job.get('error')}")
            time.sleep(1.0)
            job = _check("ndi.job", c.get(f"{config.NACE_BASE_URL}/v1/documents/jobs/{job['job_id']}", headers=_nace_headers()))
    f = (job.get("result") or {}).get("file") or {}
    if not f.get("file_id"):
        raise ApiError("ndi.upload", f"no file_id in upload result: {json.dumps(job)[:300]}")
    return {"type": "workspace_file", "workspace_id": f["workspace_id"], "file_id": f["file_id"]}


def ndi_extract(source: dict[str, Any], schema: dict[str, Any], instructions: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    body = {"source": source, "schema": schema, "instructions": instructions,
            "citations": {"enabled": True, "include_source_text": True}}
    with httpx.Client(timeout=90) as c:
        job = _check("ndi.extract", c.post(f"{config.NACE_BASE_URL}/v1/documents/extract",
                                           params={"wait_seconds": 60}, json=body, headers=_nace_headers()))
        deadline = time.time() + 90
        while job.get("status") not in ("succeeded", "failed", "cancelled") and time.time() < deadline:
            time.sleep(2.0)
            job = _check("ndi.job", c.get(f"{config.NACE_BASE_URL}/v1/documents/jobs/{job['job_id']}", headers=_nace_headers()))
    if job.get("status") != "succeeded":
        raise ApiError("ndi.extract", f"job {job.get('job_id')} status={job.get('status')} error={job.get('error')}")
    job["_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return job


# ---------------------------------------------------------------- DeepInfra
def deepinfra_chat(messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int = 900,
                   temperature: float = 0.2, json_mode: bool = False) -> dict[str, Any]:
    key = config.require("DEEPINFRA_API_KEY")
    body: dict[str, Any] = {"model": model or config.DEEPINFRA_MODEL, "messages": messages,
                            "max_tokens": max_tokens, "temperature": temperature,
                            # Qwen3-family models think by default; disable for short structured answers.
                            "chat_template_kwargs": {"enable_thinking": False}}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    t0 = time.perf_counter()
    with httpx.Client(timeout=120) as c:
        r = c.post(f"{config.DEEPINFRA_BASE_URL}/chat/completions", json=body,
                   headers={"Authorization": f"Bearer {key}"})
    data = _check("deepinfra", r)
    data["_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return data


def chat_text(resp: dict[str, Any]) -> str:
    try:
        text = resp["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""
    # Qwen3 reasoning models may emit <think> blocks; strip them from prose.
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()
