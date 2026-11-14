"""Influencer evaluation and recommendation.

- evaluate(): Keenable finds public pages about a creator, the DeepInfra LLM pulls out follower counts (with the
  snippet they came from), and Drex estimates the content-focus split and an authenticity risk signal.
- recommend(): picks N creators from the database that add the most NEW estimated reach for a company, using the
  company's analysis (areas needing attention) and a simple audience-overlap model.

Everything here is an estimate from public search results. The authenticity score is a risk signal, not proof.
"""
from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import clients, config, pipeline

AREAS = {
    "ai_ml": "Artificial intelligence, machine learning, AI tools and research",
    "consumer_tech": "Consumer technology and hardware: phones, PCs, GPUs, gadgets, reviews",
    "gaming": "Video games, esports, game hardware and streaming",
    "software_dev": "Programming, developer tools, cloud and engineering",
    "creative_design": "Design, photography, video editing, art and creative software",
    "business_finance": "Business, startups, investing, markets and marketing",
    "education_science": "Science, education and explainers",
    "lifestyle_entertainment": "Lifestyle, entertainment, vlogs, comedy and general interest",
}
SAME_SEGMENT_OVERLAP = 0.85  # assumption: creators on the same platform and topic share most of their audience


def evaluate(name: str) -> dict[str, Any]:
    name = name.strip()
    res = clients.keenable_search(f'"{name}" youtube OR instagram OR tiktok OR twitter subscribers OR followers creator',
                                  max_results=10, published_after="3y")
    results = res.get("results", [])
    evidence = [{"title": r.get("title", ""), "url": r["url"], "snippet": (r.get("snippet") or "")[:700]} for r in results]
    ev_text = "\n\n".join(f"[{i + 1}] {e['title']} ({e['url']})\n{e['snippet']}" for i, e in enumerate(evidence)) or "(no results)"

    # LLM: pull follower numbers out of the evidence. Numbers must come from the evidence, never from memory.
    messages = [
        {"role": "system", "content": "You extract facts about an online creator from search results. Use ONLY the results given. "
                                      "If a number is not in the results, use null. Return JSON only."},
        {"role": "user", "content": f"Creator: {name}\n\nSEARCH RESULTS:\n{ev_text}\n\nReturn JSON: {{\"found\": true/false (is this a real identifiable creator in the results), "
                                    "\"platforms\": [{\"platform\": \"youtube|instagram|tiktok|x|twitch|other\", \"handle\": string or null, "
                                    "\"followers\": integer or null, \"source\": result number the figure came from or null}], "
                                    "\"summary\": one sentence on what they make, \"topics\": [up to 5 short topics]}"},
    ]
    resp = clients.deepinfra_chat(messages, max_tokens=500, temperature=0, json_mode=True)
    m = re.search(r"\{.*\}", clients.chat_text(resp), re.S)
    try:
        info = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        info = {}
    platforms = [p for p in (info.get("platforms") or []) if isinstance(p, dict) and p.get("platform")]
    for p in platforms:
        f = p.get("followers")
        p["followers"] = int(f) if isinstance(f, (int, float)) and f > 0 else None
        src = p.get("source")
        p["source_url"] = evidence[src - 1]["url"] if isinstance(src, int) and 0 < src <= len(evidence) else None

    # Drex: content-focus split and authenticity risk signal.
    state = f"CREATOR: {name}\nSummary: {info.get('summary')}\nTopics: {info.get('topics')}\nPlatforms: {json.dumps(platforms)}\n\nPUBLIC SEARCH RESULTS:\n{ev_text[:6000]}"
    qs = {
        "focus": {"type": "choice", "instructions": "Which content area best describes what this creator covers?", "criteria": {**AREAS, "other": None}},
        "authentic": {"type": "noul", "instructions": "Do these public results indicate an established creator with a genuine human audience?",
                      "criteria": {"true": "Covered by independent sources, long-running original content, real engagement or press coverage",
                                   "false": "No independent coverage, signs of purchased or bot followers, impersonation, spam or a fabricated persona"}},
        "identifiable": {"type": "noul", "instructions": "Do the results clearly identify a specific real creator by this name?"},
        "brand_safety": {"type": "score", "instructions": "How safe is this creator for a company to sponsor, based on these results?",
                         "criteria": ["Serious controversy", "Some concerns", "No concerns found", "Strong positive reputation"]},
    }
    engine = "drex"
    try:
        a = clients.drex_systemone(state, qs).get("answers", {})
        focus = {k: round(v, 4) for k, v in (a.get("focus", {}).get("probabilities") or {}).items()}
        p_auth, p_ident = a.get("authentic", {}).get("noul"), a.get("identifiable", {}).get("noul")
        safety = a.get("brand_safety", {}).get("score")
    except clients.ApiError as exc:
        engine, focus, p_auth, p_ident, safety = f"unavailable: {str(exc)[:120]}", {}, None, None, None
    total = sum(p["followers"] for p in platforms if p["followers"])
    return {"name": name, "found": bool(info.get("found")) and bool(evidence), "summary": info.get("summary"), "topics": info.get("topics") or [],
            "platforms": platforms, "followers_total": total or None, "focus": focus, "p_authentic": p_auth, "p_identifiable": p_ident,
            "brand_safety": safety, "evidence": evidence[:6], "engine": engine, "evaluated_at": pipeline.now_iso()}


def _segments(inf: dict[str, Any]) -> dict[str, float]:
    """Estimated audience per (platform, area) segment = followers on that platform x focus share."""
    out: dict[str, float] = {}
    for p in inf.get("platforms") or []:
        if not p.get("followers"):
            continue
        for area, share in (inf.get("focus") or {}).items():
            if share >= 0.03:
                out[f"{p['platform']}:{area}"] = out.get(f"{p['platform']}:{area}", 0) + p["followers"] * share
    return out


def recommend(profile: dict[str, Any], db: list[dict[str, Any]], n: int, scorecard: dict[str, Any] | None,
              min_authentic: float = 0.6) -> dict[str, Any]:
    needs = [a["label"] for a in (scorecard or {}).get("areas", []) if a.get("status") == "needs_attention"]
    strengths = [a["label"] for a in (scorecard or {}).get("areas", []) if a.get("status") == "strength"]
    pool = [i for i in db if i.get("followers_total") and (i.get("p_authentic") or 0) >= min_authentic]
    excluded = [{"name": i["name"], "reason": "no follower figure found" if not i.get("followers_total") else "authenticity signal below threshold"}
                for i in db if i not in pool]
    ctx = (f"{pipeline.profile_block(profile)}\n\nFINDINGS FROM THE COMPANY'S REPUTATION ANALYSIS\n"
           f"Areas needing attention: {', '.join(needs) or 'none found or no scan yet'}\nStrengths: {', '.join(strengths) or 'none found or no scan yet'}")

    def fit(inf: dict[str, Any]) -> float | None:
        state = f"{ctx}\n\nCREATOR: {inf['name']}\nSummary: {inf.get('summary')}\nTopics: {inf.get('topics')}\nFocus split: {inf.get('focus')}"
        q = {"fit": {"type": "noul", "instructions": f"Would sponsoring this creator reach an audience that is relevant to {profile['name']}'s products and help with the areas needing attention?"}}
        try:
            return clients.drex_systemone(state, q)["answers"]["fit"]["noul"]
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        fits = list(ex.map(fit, pool))
    cands = [{**inf, "fit": f if f is not None else 0.5, "segments": _segments(inf)} for inf, f in zip(pool, fits)]

    covered: dict[str, float] = {}
    picks: list[dict[str, Any]] = []
    remaining = cands[:]
    while remaining and len(picks) < n:
        def gain(c: dict[str, Any]) -> tuple[float, float]:
            new = 0.0
            for seg, reach in c["segments"].items():
                have = covered.get(seg, 0.0)
                # audiences in the same platform+topic segment mostly overlap; other segments count in full
                new += max(reach - SAME_SEGMENT_OVERLAP * min(have, reach), 0.0) if have else reach
            return new * c["fit"] * (c.get("p_authentic") or 0.5), new
        best = max(remaining, key=lambda c: gain(c)[0])
        score, new_reach = gain(best)
        if score <= 0:
            break
        for seg, reach in best["segments"].items():
            covered[seg] = max(covered.get(seg, 0.0), reach) + (1 - SAME_SEGMENT_OVERLAP) * min(covered.get(seg, 0.0), reach)
        top = sorted(best["segments"].items(), key=lambda kv: -kv[1])[:3]
        picks.append({"name": best["name"], "summary": best.get("summary"), "followers_total": best["followers_total"],
                      "platforms": best["platforms"], "focus": best["focus"], "p_authentic": best.get("p_authentic"),
                      "fit": round(best["fit"], 3), "new_reach_estimate": int(new_reach),
                      "overlap_discount": int(sum(best["segments"].values()) - new_reach),
                      "top_segments": [{"segment": s, "reach": int(r)} for s, r in top]})
        remaining.remove(best)
    return {"picks": picks, "estimated_unique_reach": int(sum(covered.values())), "considered": len(cands), "excluded": excluded,
            "used_analysis": {"needs_attention": needs, "strengths": strengths},
            "method": (f"Greedy selection: each pick maximizes new estimated reach x Drex fit x Drex authenticity. Audience = followers x Drex focus split per "
                       f"platform and topic; creators in the same platform+topic segment are assumed to share {int(SAME_SEGMENT_OVERLAP * 100)}% of their audience. "
                       "Real audience-overlap data is not public, so this is an estimate.")}


def autoprofile(name: str) -> dict[str, Any]:
    """Fill in company details from public search results so the user only has to type a name."""
    res = clients.keenable_search(f'"{name}" company overview', max_results=6, published_after="3y")
    ev = "\n\n".join(f"- {r.get('title')} ({r['url']})\n{(r.get('snippet') or '')[:500]}" for r in res.get("results", []))
    messages = [
        {"role": "system", "content": "You fill in a short company profile from search results. Use only what the results support. Return JSON only."},
        {"role": "user", "content": f"Name typed by the user: {name}\n\nSEARCH RESULTS:\n{ev or '(none)'}\n\nReturn JSON: {{\"kind\": \"company|person|team\", "
                                    "\"aliases\": [up to 3 other names or tickers], \"description\": 1-2 sentences that would distinguish it from namesakes, "
                                    "\"website\": official site URL or \"\", \"industry\": short phrase, \"region\": country or \"\"}"},
    ]
    resp = clients.deepinfra_chat(messages, max_tokens=300, temperature=0, json_mode=True)
    m = re.search(r"\{.*\}", clients.chat_text(resp), re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        out = {}
    return {"kind": out.get("kind") or "company", "aliases": [a for a in (out.get("aliases") or []) if isinstance(a, str)][:3],
            "description": out.get("description") or "", "website": out.get("website") or "", "industry": out.get("industry") or "",
            "region": out.get("region") or ""}
