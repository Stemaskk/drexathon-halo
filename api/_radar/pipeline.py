"""Project Halo pipeline: retrieval -> NDI extraction -> Drex decisions -> DeepInfra briefing."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import clients, config

# ------------------------------------------------------------------ taxonomy
CATEGORIES = {
    "security_concern": "Reported breach, vulnerability, data exposure, outage with security impact, or hacking",
    "allegation_or_legal": "Accusations of wrongdoing, lawsuits, regulatory action, investigations, or misconduct claims",
    "impersonation_or_scam": "Fake accounts, phishing, fraud or scams that use the subject's name or brand",
    "customer_complaint": "Specific customers reporting problems with the subject's product, service, billing or support",
    "routine_criticism": "General opinion-level criticism, negative reviews or commentary without new factual claims",
    "business_news": "Funding, launches, partnerships, hires, financial results or other neutral/positive developments",
    "other": "Anything else, including passing mentions",
}
REPORT_TYPES = {
    "allegation": "Reports claims or accusations that are not established (e.g. 'X alleges', 'lawsuit claims')",
    "official_statement": "A statement, filing or announcement issued by the subject or an authority",
    "news_report": "Straight reporting of events or facts by a publication",
    "opinion": "Commentary, review, editorial, or personal opinion",
    "correction": "A correction, retraction or update to earlier coverage",
    "satire": "Parody, satire or humor not meant literally",
    "other": None,
}
ACTIONS = {
    "ignore": "Not about the subject, or irrelevant to the customer's priorities",
    "digest": "Relevant but routine; include in the periodic digest",
    "watch": "Could grow into a problem or opportunity; track for follow-up coverage",
    "review_now": "Needs the customer's attention today given their stated priorities",
}
ACTION_RANK = {"review_now": 3, "watch": 2, "digest": 1, "ignore": 0}
IMPROVEMENT_AREAS = {
    "marketing_messaging": "How the brand or product is positioned, explained or perceived; unclear, misleading or off-target messaging",
    "advertising": "Ad campaigns, sponsored posts or promotions: their tone, claims, targeting, frequency or reception",
    "product_quality": "Features, reliability, bugs, accuracy, usability, design or performance of the product itself",
    "customer_support": "Support responsiveness, billing handling, refunds, onboarding or account help",
    "pricing_value": "Price level, value for money, plans, fees or discounts",
    "trust_safety": "Security, privacy, scams or impersonation, legal or regulatory trust issues",
    "financial_market": "Stock price, funding, investor or analyst sentiment, financial results",
    "none": "No actionable feedback for the subject in this item",
}
SENTIMENT_LEVELS = ["Very negative", "Negative", "Neutral", "Positive", "Very positive"]


# ------------------------------------------------------------------ helpers
TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|ref_src|igshid|si$)")


def canonical_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    host = p.netloc.lower().removeprefix("www.").removeprefix("m.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query) if not TRACKING.match(k.lower())))
    path = re.sub(r"/+$", "", p.path) or "/"
    return urlunsplit(("https", host, path, query, ""))


def doc_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:12]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_queries(profile: dict[str, Any]) -> list[str]:
    name = profile["name"].strip()
    aliases = [a.strip() for a in profile.get("aliases", []) if a.strip()]
    context = " ".join(x for x in [profile.get("industry", ""), profile.get("region", "")] if x).strip()
    names = " OR ".join(f'"{n}"' for n in [name, *aliases][:4])
    qs = [f'"{name}" news',
          f"({names}) {context}".strip(),
          f'"{name}" reviews OR complaints OR "customer experience"',
          f'"{name}" ad OR advertisement OR campaign OR marketing']
    if profile.get("kind", "company") == "company":
        qs.append(f'"{name}" stock OR shares OR investors OR funding')
    order = [0, 2, 3, 1, 4]  # news, reviews, ads, general, stock
    return [qs[i] for i in order if i < len(qs)]


# ------------------------------------------------------------------ retrieval
def search(profile: dict[str, Any], *, seen_urls: list[str], published_after: str = "30d",
           max_results: int = 10) -> dict[str, Any]:
    seen = {canonical_url(u) for u in seen_urls}
    queries = build_queries(profile)
    candidates: dict[str, dict[str, Any]] = {}
    raw_count, dup_count, seen_count = 0, 0, 0
    # The subject's own site and profile pages are not third-party coverage.
    exclude = ["linkedin.com", "facebook.com", "instagram.com"]
    own = urlsplit(profile.get("website") or "").netloc.lower().removeprefix("www.")
    if own:
        exclude.append(own)
    per_query = [clients.keenable_search(q, published_after=published_after, max_results=max_results,
                                         exclude_domains=exclude).get("results", []) for q in queries]
    # Interleave results across queries so news, reviews, ads and market coverage all make the batch.
    merged = [(queries[qi], res[ri]) for ri in range(max((len(r) for r in per_query), default=0))
              for qi, res in enumerate(per_query) if ri < len(res)]
    for q, r in merged:
        for r in [r]:
            raw_count += 1
            cu = canonical_url(r["url"])
            if cu in seen:
                seen_count += 1
                continue
            if cu in candidates:
                dup_count += 1
                continue
            candidates[cu] = {"id": doc_id(r["url"]), "url": r["url"], "canonical_url": cu, "title": r.get("title", ""),
                              "snippet": r.get("snippet", ""), "published_at": r.get("published_at"), "query": q}
    return {"queries": queries, "candidates": list(candidates.values()),
            "stats": {"raw": raw_count, "duplicates_in_scan": dup_count, "already_seen": seen_count,
                      "unique_new": len(candidates)}}


def fetch(candidate: dict[str, Any]) -> dict[str, Any]:
    res = clients.keenable_fetch(candidate["url"])
    return {**candidate, "url": res.get("url", candidate["url"]), "title": res.get("title") or candidate.get("title"),
            "author": res.get("author"), "published_at": res.get("published_at") or candidate.get("published_at"),
            "retrieved_at": now_iso(), "text": res.get("content", ""), "truncated": res.get("truncated", False),
            "source": "live"}


def to_markdown(doc: dict[str, Any]) -> str:
    return (f"# {doc.get('title') or 'Untitled'}\n\n"
            f"- Source URL: {doc['url']}\n- Published: {doc.get('published_at') or 'unknown'}\n"
            f"- Retrieved: {doc.get('retrieved_at') or 'unknown'}\n\n---\n\n{doc.get('text', '')}\n")


# ------------------------------------------------------------------ NDI extraction
NDI_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "maxItems": 12, "description": "People and organizations named in the article",
                     "items": {"type": "object", "properties": {
                         "name": {"type": "string"},
                         "kind": {"type": "string", "enum": ["person", "organization", "product", "other"]},
                         "role": {"type": "string", "description": "Role or description of this entity in the article"}}}},
        "claims": {"type": "array", "maxItems": 8, "description": "Factual claims, allegations or statements the article reports",
                   "items": {"type": "object", "properties": {
                       "claim": {"type": "string", "description": "The claim in a short sentence"},
                       "attributed_to": {"type": "string", "description": "Who makes the claim (reporter, a named person, the company, a lawsuit...)"},
                       "status": {"type": "string", "enum": ["alleged", "confirmed_by_subject", "officially_stated", "reported", "opinion"]},
                       "supporting_passage": {"type": "string", "description": "Exact sentence copied verbatim from the article"}}}},
        "event_dates": {"type": "array", "maxItems": 6, "description": "Dates of events in the article as YYYY-MM-DD where possible",
                        "items": {"type": "object", "properties": {"date": {"type": "string"}, "event": {"type": "string"}}}},
        "publication_date": {"type": "string", "description": "Article publication date as YYYY-MM-DD, or empty if not stated"},
    },
}


def ndi_extract(doc: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    path = f"halo/{doc['id']}.md"
    source = clients.ndi_upload_markdown(path, to_markdown(doc))
    instructions = (f"The reader monitors '{profile['name']}' ({profile.get('description', '')}). Extract entities, "
                    "reported claims and dates. Copy supporting passages verbatim. Mark allegations as 'alleged'.")
    job = clients.ndi_extract(source, NDI_SCHEMA, instructions)
    result = job.get("result") or {}
    return {"data": result.get("data") or {}, "fields": result.get("fields") or [], "job_id": job.get("job_id"),
            "cost": job.get("cost"), "units": result.get("units"), "latency_ms": job.get("_latency_ms"),
            "warnings": result.get("warnings") or []}


def llm_extract(doc: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Fallback for NDI: same schema, filled by the DeepInfra LLM. Passages are still verified verbatim downstream."""
    messages = [
        {"role": "system", "content": "You extract structured facts from an article. Return ONLY a JSON object matching the schema. "
                                      "supporting_passage must be an exact sentence copied verbatim from the article. Mark accusations as 'alleged'."},
        {"role": "user", "content": f"The reader monitors '{profile['name']}' ({profile.get('description', '')}).\n\n"
                                    f"SCHEMA:\n{json.dumps(NDI_SCHEMA)}\n\nKeep it short: at most 4 claims, 6 entities, 3 dates.\n\n"
                                    f"ARTICLE:\n{to_markdown(doc)[:4500]}"},
    ]
    resp = clients.deepinfra_chat(messages, max_tokens=800, temperature=0, json_mode=True)
    text = clients.chat_text(resp)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    return {"data": data, "fields": [], "job_id": None, "cost": {"total_usd": (resp.get("usage") or {}).get("estimated_cost")},
            "latency_ms": resp.get("_latency_ms"), "engine": resp.get("model") or config.DEEPINFRA_MODEL, "warnings": []}


# ------------------------------------------------------------------ Drex decisions
def drex_questions(profile: dict[str, Any]) -> dict[str, Any]:
    name = profile["name"]
    priorities = profile.get("priorities") or "general reputation"
    return {
        "is_subject": {"type": "noul", "instructions": f"Is this coverage about the monitored subject '{name}' as described in the profile (not a different person or organization with a similar name)?",
                       "criteria": {"true": f"The article is about, or substantively mentions, the {name} described in the profile",
                                    "false": "The article concerns a namesake, an unrelated entity, or only a coincidental keyword match"}},
        "category": {"type": "choice", "instructions": "What is the primary topic or risk category of this coverage, as it relates to the subject?", "criteria": CATEGORIES},
        "report_type": {"type": "choice", "instructions": "What kind of development is the article mainly reporting? Classify what the source reports; do not treat allegations as established facts.", "criteria": REPORT_TYPES},
        "is_novel": {"type": "noul", "instructions": "Does this article add meaningful new information compared with the PRIOR COVERAGE listed in the state?",
                     "criteria": {"true": "It reports a new event, new facts, or a material update not in prior coverage",
                                  "false": "It repeats or rewrites a story already in prior coverage, without material new facts"}},
        "action": {"type": "choice", "instructions": f"Given the customer's monitoring priorities ({priorities}), what action fits this coverage? Repeated coverage of an already-known story should not be escalated.", "criteria": ACTIONS},
        "urgency": {"type": "score", "instructions": "How urgent is this for the subject's reputation in the next 48 hours?", "criteria": ["None", "Low", "Moderate", "High", "Critical"]},
        "improvement_area": {"type": "choice", "instructions": f"Which area of {name}'s business does this item give the most actionable feedback on?", "criteria": IMPROVEMENT_AREAS},
        "sentiment": {"type": "score", "instructions": f"Overall, how does this item portray {name}?", "criteria": SENTIMENT_LEVELS},
    }


def profile_block(profile: dict[str, Any]) -> str:
    return (f"MONITORED SUBJECT: {profile['name']}\nType: {profile.get('kind', 'company')}\n"
            f"Aliases: {', '.join(profile.get('aliases', [])) or 'none'}\nDescription: {profile.get('description', '')}\n"
            f"Official website: {profile.get('website', '') or 'unknown'}\nRegion/industry: {profile.get('region', '')} {profile.get('industry', '')}\n"
            f"Monitoring priorities: {profile.get('priorities', '') or 'general reputation'}")


def build_state(profile: dict[str, Any], doc: dict[str, Any], facts: dict[str, Any] | None,
                prior: list[dict[str, Any]], max_chars: int = 3500) -> str:
    prior_txt = "\n".join(f"- [{p.get('published_at') or 'date unknown'}] {p.get('title')}: {p.get('summary', '')}" for p in prior[-12:]) or "- (none)"
    facts_txt = json.dumps(facts, ensure_ascii=False)[:2500] if facts else "(no structured extraction available)"
    return (f"{profile_block(profile)}\n\nPRIOR COVERAGE ALREADY SEEN:\n{prior_txt}\n\n"
            f"ARTICLE\nTitle: {doc.get('title')}\nURL: {doc.get('url')}\nPublished: {doc.get('published_at') or 'unknown'}\n\n"
            f"EXTRACTED FACTS (NDI):\n{facts_txt}\n\nARTICLE TEXT:\n{(doc.get('text') or '')[:max_chars]}")


def parse_drex(resp: dict[str, Any]) -> dict[str, Any]:
    a = resp.get("answers", {})

    def ch(k: str) -> dict[str, Any]:
        x = a.get(k, {})
        return {"value": x.get("choice"), "confidence": x.get("confidence"), "probabilities": x.get("probabilities", {})}

    def nl(k: str) -> dict[str, Any]:
        x = a.get(k, {})
        p = x.get("noul")
        return {"value": (p >= 0.5) if p is not None else None, "p_yes": p, "confidence": x.get("confidence")}

    urg = a.get("urgency", {})
    sen = a.get("sentiment", {})
    return {"is_subject": nl("is_subject"), "category": ch("category"), "report_type": ch("report_type"),
            "is_novel": nl("is_novel"), "action": ch("action"), "improvement_area": ch("improvement_area"),
            "sentiment": {"score": sen.get("score"), "confidence": sen.get("confidence"), "probabilities": sen.get("probabilities", {})},
            "urgency": {"score": urg.get("score"), "confidence": urg.get("confidence"), "probabilities": urg.get("probabilities", {}),
                        "legend": urg.get("legend")}}


def apply_policy(d: dict[str, Any]) -> dict[str, Any]:
    """Deterministic post-processing over Drex's probabilities, including uncertainty handling."""
    p_subj = d["is_subject"]["p_yes"]
    action = d["action"]["value"] or "watch"
    flags: list[str] = []
    if p_subj is not None and p_subj < 0.35:
        action = "ignore"
        flags.append("namesake_or_unrelated")
    elif p_subj is not None and p_subj < 0.65:
        flags.append("identity_uncertain")
        if ACTION_RANK.get(action, 0) < ACTION_RANK["watch"]:
            action = "watch"
    if d["is_novel"]["value"] is False and action == "review_now":
        action = "watch"
        flags.append("repeat_coverage_downgraded")
    if (d["action"]["confidence"] or 1) < 0.5:
        flags.append("low_confidence_action")
    if d["report_type"]["value"] == "allegation":
        flags.append("allegation_not_fact")
    return {"final_action": action, "flags": flags}


def drex_decide(profile: dict[str, Any], doc: dict[str, Any], facts: dict[str, Any] | None,
                prior: list[dict[str, Any]], model: str | None = None) -> dict[str, Any]:
    state = build_state(profile, doc, facts, prior)
    resp = clients.drex_systemone(state, drex_questions(profile), model=model)
    d = parse_drex(resp)
    return {"decisions": d, **apply_policy(d), "model": resp.get("model"), "usage": resp.get("usage", {}),
            "latency_ms": resp.get("_latency_ms"), "evaluation_time_ms": resp.get("evaluation_time_ms"),
            "request_id": resp.get("request_id")}


# ------------------------------------------------------------------ LLM baseline (same inputs)
def baseline_decide(profile: dict[str, Any], doc: dict[str, Any], facts: dict[str, Any] | None,
                    prior: list[dict[str, Any]], model: str | None = None) -> dict[str, Any]:
    state = build_state(profile, doc, facts, prior)
    qs = drex_questions(profile)
    spec = {
        "is_subject": "true/false — " + qs["is_subject"]["instructions"],
        "category": f"one of {list(CATEGORIES)} — {json.dumps(CATEGORIES)}",
        "report_type": f"one of {list(REPORT_TYPES)} — {json.dumps({k: v for k, v in REPORT_TYPES.items() if v})}",
        "is_novel": "true/false — " + qs["is_novel"]["instructions"],
        "action": f"one of {list(ACTIONS)} — {json.dumps(ACTIONS)}",
        "urgency": "integer 0-4 (None, Low, Moderate, High, Critical)",
        "improvement_area": f"one of {list(IMPROVEMENT_AREAS)} — {json.dumps(IMPROVEMENT_AREAS)}",
        "sentiment": "integer 0-4 (Very negative, Negative, Neutral, Positive, Very positive)",
    }
    messages = [
        {"role": "system", "content": "You are a reputation-monitoring analyst. Answer strictly as a JSON object with exactly the requested keys."},
        {"role": "user", "content": f"{state}\n\nAnswer these questions as JSON:\n{json.dumps(spec, indent=1)}"},
    ]
    resp = clients.deepinfra_chat(messages, model=model or config.BASELINE_MODEL, max_tokens=400, temperature=0, json_mode=True)
    text = clients.chat_text(resp)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
        parse_error = None
    except json.JSONDecodeError as exc:
        out, parse_error = {}, str(exc)
    d = {"is_subject": {"value": _as_bool(out.get("is_subject")), "p_yes": None, "confidence": None},
         "category": {"value": out.get("category"), "confidence": None, "probabilities": {}},
         "report_type": {"value": out.get("report_type"), "confidence": None, "probabilities": {}},
         "is_novel": {"value": _as_bool(out.get("is_novel")), "p_yes": None, "confidence": None},
         "action": {"value": out.get("action"), "confidence": None, "probabilities": {}},
         "urgency": {"score": out.get("urgency")},
         "improvement_area": {"value": out.get("improvement_area"), "confidence": None, "probabilities": {}},
         "sentiment": {"score": out.get("sentiment")}}
    pol = apply_policy({**d, "is_subject": {**d["is_subject"], "p_yes": None if d["is_subject"]["value"] is None else float(d["is_subject"]["value"])}})
    return {"decisions": d, **pol, "model": resp.get("model") or model or config.BASELINE_MODEL, "usage": resp.get("usage", {}),
            "latency_ms": resp.get("_latency_ms"), "parse_error": parse_error}


def _as_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return {"true": True, "yes": True, "false": False, "no": False}.get(v.strip().lower())
    return None


# ------------------------------------------------------------------ evidence + briefing
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[“”\"'‘’*_`]", "", s or "")).strip().lower()


def validate_passage(passage: str, text: str) -> bool:
    return bool(passage) and len(passage) >= 12 and _norm(passage) in _norm(text)


def pick_evidence(doc: dict[str, Any], facts: dict[str, Any] | None) -> dict[str, Any]:
    """Return a supporting passage that is verified verbatim against the stored source text."""
    text = doc.get("text", "")
    candidates: list[tuple[str, str]] = []
    for c in (facts or {}).get("claims", []) or []:
        if c.get("supporting_passage"):
            candidates.append((c["supporting_passage"], "ndi_claim"))
    for f in (facts or {}).get("_fields", []) or []:
        for cit in f.get("citations", []) or []:
            if cit.get("source_text"):
                candidates.append((cit["source_text"], "ndi_citation"))
    for passage, origin in candidates:
        if validate_passage(passage, text):
            return {"passage": passage.strip(), "origin": origin, "verified": True}
    return {"passage": None, "origin": None, "verified": False,
            "note": "No extracted passage could be verified against the stored source text."}


def build_scorecard(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Drex's per-item improvement area and sentiment (0-4) into a per-area scorecard."""
    areas: dict[str, dict[str, Any]] = {}
    for it in items:
        if it.get("final_action") == "ignore":
            continue
        d = it.get("decisions") or {}
        area = (d.get("improvement_area") or {}).get("value")
        score = (d.get("sentiment") or {}).get("score")
        if not area or area == "none":
            continue
        a = areas.setdefault(area, {"area": area, "label": area.replace("_", " "), "mentions": 0, "negative": 0,
                                    "positive": 0, "scores": [], "items": []})
        a["mentions"] += 1
        if isinstance(score, (int, float)):
            a["scores"].append(score)
            a["negative"] += score < 1.5
            a["positive"] += score > 2.5
        a["items"].append({"id": it["id"], "title": it.get("title"), "url": it.get("url"), "sentiment": score,
                           "evidence": (it.get("evidence") or {}).get("passage")})
    out = []
    for a in areas.values():
        sc = a.pop("scores")
        a["avg_sentiment"] = round(sum(sc) / len(sc), 2) if sc else None
        # needs attention: more negative than positive mentions, or average below neutral
        a["status"] = "needs_attention" if (a["negative"] > a["positive"] or (a["avg_sentiment"] is not None and a["avg_sentiment"] < 1.5)) \
            else ("strength" if a["avg_sentiment"] is not None and a["avg_sentiment"] > 2.5 else "mixed")
        out.append(a)
    order = {"needs_attention": 0, "mixed": 1, "strength": 2}
    out.sort(key=lambda a: (order[a["status"]], -a["mentions"]))
    unlabeled = sum(1 for it in items if it.get("final_action") != "ignore" and not ((it.get("decisions") or {}).get("improvement_area") or {}).get("value"))
    return {"areas": out, "items_without_area": unlabeled}


def write_briefing(profile: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    scorecard = build_scorecard(items)
    rows = []
    for it in items:
        if it.get("final_action") == "ignore":
            continue
        d = it["decisions"]
        rows.append({"id": it["id"], "title": it.get("title"), "url": it.get("url"), "published_at": it.get("published_at") or "unknown",
                     "action": it["final_action"], "category": d["category"]["value"], "report_type": d["report_type"]["value"],
                     "novel": d["is_novel"]["value"], "flags": it.get("flags", []),
                     "improvement_area": (d.get("improvement_area") or {}).get("value"), "sentiment_0_4": (d.get("sentiment") or {}).get("score"),
                     "evidence": (it.get("evidence") or {}).get("passage"),
                     "claims": [c.get("claim") for c in ((it.get("facts") or {}).get("claims") or [])][:4]})
    rows.sort(key=lambda r: -ACTION_RANK.get(r["action"], 0))
    if not rows:
        return {"briefing": "No relevant coverage in this scan.", "explanations": {}, "usage": {}, "latency_ms": 0, "model": None,
                "scorecard": scorecard, "recommendations": {}}
    messages = [
        {"role": "system", "content": (
            "You write concise reputation briefings for a busy founder. Use ONLY the decisions and evidence given. "
            "Never present an allegation as fact: say 'reports allege' or 'according to'. Do not infer causes or links between items unless the evidence states them. If evidence is missing, say it is unknown. "
            "Return JSON: {\"briefing\": markdown string under 180 words with a 1-line headline then bullets ordered by action, "
            "\"explanations\": {item_id: one sentence on why it matters to this profile}, "
            "\"recommendations\": {area: 1-2 sentences of concrete, practical advice for that improvement area, citing what the evidence shows; "
            "only for areas in the SCORECARD}}.")},
        {"role": "user", "content": f"{profile_block(profile)}\n\nTRIAGED ITEMS (decisions by Drex):\n{json.dumps(rows, ensure_ascii=False)}"
                                    f"\n\nSCORECARD (improvement areas and sentiment 0=very negative..4=very positive, from Drex):\n"
                                    f"{json.dumps(scorecard, ensure_ascii=False)}"},
    ]
    resp = clients.deepinfra_chat(messages, max_tokens=1800, temperature=0.2, json_mode=True)
    text = clients.chat_text(resp)
    try:
        m = re.search(r"\{.*\}", text, re.S)
        out = json.loads(m.group(0)) if m else {"briefing": text, "explanations": {}}
    except json.JSONDecodeError:
        out = {"briefing": text, "explanations": {}}
    recs = {k: v for k, v in (out.get("recommendations") or {}).items() if k in {a["area"] for a in scorecard["areas"]}}
    return {"briefing": out.get("briefing", ""), "explanations": out.get("explanations", {}), "usage": resp.get("usage", {}),
            "scorecard": scorecard, "recommendations": recs,
            "latency_ms": resp.get("_latency_ms"), "model": resp.get("model") or config.DEEPINFRA_MODEL}


def facts_with_fields(ndi: dict[str, Any]) -> dict[str, Any]:
    data = dict(ndi.get("data") or {})
    data["_fields"] = ndi.get("fields") or []
    return data


def strip_internal(facts: dict[str, Any] | None) -> dict[str, Any] | None:
    if not facts:
        return facts
    return {k: v for k, v in facts.items() if not k.startswith("_")}


def timed(fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, round((time.perf_counter() - t0) * 1000, 1)
