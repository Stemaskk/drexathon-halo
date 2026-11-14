"""Decision-stage benchmark: Drex vs a text-LLM baseline on the same fixed articles, profile, criteria and NDI output.

Usage:
  .venv/bin/python scripts/benchmark.py                       # Drex + baseline (BASELINE_MODEL)
  .venv/bin/python scripts/benchmark.py --baseline-model X    # override baseline model id (DeepInfra)
  .venv/bin/python scripts/benchmark.py --limit 4 --repeats 1

Writes api/_radar/data/benchmark_latest.json (shown in the UI) and a raw copy under docs/benchmark_runs/.
Only measured responses are recorded; failed calls are counted as errors, never filled in.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from _radar import clients, config, pipeline  # noqa: E402

DATA = config.DATA_DIR
FIELDS = ["is_subject", "category", "report_type", "is_novel", "action"]


def ensure_ndi(fx: dict, refresh: bool) -> dict:
    """Shared preprocessing: run NDI once per fixture article and cache the output for every system."""
    path = DATA / "ndi_cache.json"
    cache = json.loads(path.read_text()) if path.exists() and not refresh else {}
    for a in fx["articles"]:
        if a["id"] in cache:
            continue
        doc = {**a, "retrieved_at": pipeline.now_iso()}
        print(f"  NDI extract {a['id']} …", flush=True)
        try:
            cache[a["id"]] = pipeline.ndi_extract(doc, fx["profile"])
        except Exception as exc:  # record and continue; decisions then run without facts for this article
            print(f"    NDI failed: {exc}")
            continue
        path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    return cache


def fixed_prior(fx: dict, upto: dict) -> list[dict]:
    prior = [dict(h) for h in fx["history"]]
    for a in fx["articles"]:
        if (a["published_at"], a["id"]) >= (upto["published_at"], upto["id"]):
            continue
        if a["gold"]["is_subject"]:
            prior.append({"title": a["title"], "published_at": a["published_at"], "summary": a["text"].split("\n")[0][:200]})
    return prior


def value(d: dict, f: str):
    return d["decisions"][f]["value"]


def run(args) -> dict:
    fx = json.loads((DATA / "fixtures.json").read_text())
    arts = sorted(fx["articles"], key=lambda a: (a["published_at"], a["id"]))[: args.limit or None]
    print("Shared NDI preprocessing …")
    cache = ensure_ndi(fx, args.refresh_ndi)

    systems = []
    if "drex" in args.systems:
        for dm in args.drex_models.split(","):
            systems.append((f"Drex ({dm})", dm, lambda p, d, f, pr, dm=dm: pipeline.drex_decide(p, d, f, pr, model=dm)))
    if "baseline" in args.systems:
        bm = args.baseline_model or config.BASELINE_MODEL
        systems.append((f"LLM baseline", bm, lambda p, d, f, pr, bm=bm: pipeline.baseline_decide(p, d, f, pr, model=bm)))

    raw: dict[str, list] = {s[0]: [] for s in systems}
    for rep in range(args.repeats):
        for a in arts:
            ndi = cache.get(a["id"])
            facts = pipeline.strip_internal(pipeline.facts_with_fields(ndi)) if ndi else None
            prior = fixed_prior(fx, a)
            for name, model, fn in systems:
                try:
                    out = fn(fx["profile"], a, facts, prior)
                    err = out.get("parse_error")
                except Exception as exc:
                    out, err = None, str(exc)
                print(f"  [{rep}] {name:<12} {a['id']} → {(out or {}).get('final_action', 'ERROR')}  ({(out or {}).get('latency_ms', '-')} ms){'  ERR ' + err[:120] if err else ''}", flush=True)
                raw[name].append({"id": a["id"], "rep": rep, "out": out, "error": err})

    pin_drex = config.env_float("DREX_PRICE_PER_M_INPUT")
    pin_b, pout_b = config.env_float("BASELINE_PRICE_PER_M_INPUT"), config.env_float("BASELINE_PRICE_PER_M_OUTPUT")
    gold = {a["id"]: a["gold"] for a in arts}
    important = [i for i, g in gold.items() if g["action"] == "review_now"]
    namesakes = [i for i, g in gold.items() if not g["is_subject"]]

    summaries = []
    for name, model, _ in systems:
        rows = raw[name]
        good = [r for r in rows if r["out"] and not r["error"]]
        n = len(rows)
        acc = {f: sum(1 for r in good if value(r["out"], f) == gold[r["id"]][f]) / n if n else None for f in FIELDS}
        final_ok = sum(1 for r in good if r["out"]["final_action"] == gold[r["id"]]["action"]) / n if n else None
        lat = [r["out"]["latency_ms"] for r in good if r["out"].get("latency_ms") is not None]
        tin = sum((r["out"].get("usage") or {}).get("input_tokens", (r["out"].get("usage") or {}).get("prompt_tokens", 0)) for r in good)
        tout = sum((r["out"].get("usage") or {}).get("output_tokens", (r["out"].get("usage") or {}).get("completion_tokens", 0)) for r in good)
        reported = [(r["out"].get("usage") or {}).get("estimated_cost") for r in good]
        if name.startswith("Drex"):
            cost = tin / 1e6 * pin_drex if pin_drex is not None else None  # Drex bills input tokens only
            cost_source = f"assumed ${pin_drex}/1M input tokens (DREX_PRICE_PER_M_INPUT)" if pin_drex is not None else "price not set"
        elif reported and all(x is not None for x in reported):
            cost = sum(reported)
            cost_source = "sum of DeepInfra usage.estimated_cost (provider-reported)"
        else:
            cost = (tin / 1e6 * pin_b + tout / 1e6 * pout_b) if pin_b is not None and pout_b is not None else None
            cost_source = "assumed env prices" if cost is not None else "price not set"
        fa = {r["id"]: r["out"]["final_action"] for r in good if r["rep"] == 0}
        summaries.append({
            "name": name, "model": model, "n_calls": n, "errors": n - len(good),
            "important_caught": sum(1 for i in important if fa.get(i) == "review_now"),
            "important_ge_watch": sum(1 for i in important if fa.get(i) in ("review_now", "watch")),
            "false_alerts": sum(1 for i, g in gold.items() if g["action"] in ("ignore", "digest") and fa.get(i) in ("watch", "review_now")),
            "namesake_ok": sum(1 for i in namesakes if fa.get(i) == "ignore"),
            "action_acc": final_ok, "drex_raw_action_acc": acc["action"], "category_acc": acc["category"],
            "report_type_acc": acc["report_type"], "subject_acc": acc["is_subject"], "novel_acc": acc["is_novel"],
            "latency_ms_median": round(statistics.median(lat), 1) if lat else None,
            "latency_ms_mean": round(statistics.mean(lat), 1) if lat else None,
            "input_tokens": tin, "output_tokens": tout, "est_cost_usd": cost,
            "cost_source": cost_source,
        })

    per_article = []
    for a in arts:
        pred = {}
        for name, _, _ in systems:
            r = next((r for r in raw[name] if r["id"] == a["id"] and r["rep"] == 0), None)
            pred[name] = r["out"]["final_action"] if r and r["out"] else None
        per_article.append({"id": a["id"], "title": a["title"], "gold_action": a["gold"]["action"], "pred": pred})

    result = {
        "available": True, "run_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "repeats": args.repeats,
        "dataset": {"size": len(arts), "label": "synthetic fixtures, fictional company 'Nimbleroot', hand-labeled by the authors",
                    "important": len(important), "namesakes": len(namesakes)},
        "systems": summaries, "per_article": per_article,
        "limitations": [
            f"Tiny dataset ({len(arts)} synthetic articles, labels written by the project authors) — results are indicative, not statistically significant.",
            "Both systems receive identical state text (profile, criteria, fixed prior coverage, NDI facts, article text) and the same deterministic post-policy.",
            "Latency is wall-clock from this machine, including network; it varies by region and load.",
            "Baseline cost is the DeepInfra-reported usage.estimated_cost. Drex cost = measured input tokens x DREX_PRICE_PER_M_INPUT, an ASSUMED rate (Nace docs list $0.12 per 1M Drex Max input tokens; the API returns no per-call cost). See cost_source per system.",
            f"Baseline model '{next((x['model'] for x in summaries if not x['name'].startswith('Drex')), '')}' is the organizer-suggested worker LLM; it is not claimed to be a frontier model.",
            "Decision-stage only: Keenable retrieval and NDI extraction costs are shared and excluded from these numbers.",
        ],
    }
    (DATA / "benchmark_latest.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    runs = ROOT / "docs" / "benchmark_runs"
    runs.mkdir(parents=True, exist_ok=True)
    stamp = result["run_at"].replace(":", "")
    (runs / f"{stamp}.json").write_text(json.dumps({"summary": result, "raw": raw}, indent=1, ensure_ascii=False, default=str))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default="drex,baseline")
    ap.add_argument("--baseline-model", default=None)
    ap.add_argument("--drex-models", default="drex-latest,drex-v2.0")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--refresh-ndi", action="store_true")
    res = run(ap.parse_args())
    for s in res["systems"]:
        print(json.dumps(s, indent=1))
