# Project Halo

**Public-reputation monitoring and improvement feedback for teams without a PR or marketing department.** Built for early-stage startups, public-facing founders, emerging creators and anyone starting to get public attention.

Project Halo reads what is publicly said about you: news coverage, customer reviews and complaints, how your product is advertised and received, and stock or investor news. It answers two questions:
1. **What needs attention now?** Halo filters out namesakes and repeat stories, separates routine criticism from real developments, and triages each item (ignore, digest, watch, review now) with a verified source passage.
2. **Where should you improve?** Each relevant item is tagged with an improvement area (marketing and messaging, advertising, product quality, customer support, pricing and value, trust and safety, financial and market) and a sentiment score. Halo combines these into a **Feedback scorecard** with concrete, evidence-based recommendations.

Built for the **Drexathon (Nace.AI), November 14, 2026**. Primary track: **Apex Predator**. Decisions that would normally go to a general-purpose LLM go to **Drex**, and the decision stage is measured against an LLM baseline.

> RepWave (https://repwave.in/) already offers a similar product. This project shows filtering, personalized decisions and efficient processing with Drex. It makes **no** claim to beat existing products.

---

## What each tool does

| Component | Responsibility in Halo | Code |
|---|---|---|
| **Keenable** | Web search (date-filtered, multiple identity-aware queries) and article fetch as Markdown | `api/_radar/clients.py` → `keenable_search`, `keenable_fetch` |
| **NDI (Nace Perception)** | Each fetched article is uploaded as a Markdown document. Extract fills a JSON schema with entities, reported claims (with *alleged / officially stated / reported / opinion* status), event dates and verbatim supporting passages, with citations | `pipeline.ndi_extract`, `NDI_SCHEMA` |
| **Drex** (`/v1/systemone`) | One batched request per article with 6 typed questions: *is this the right subject?* (noul), *risk category* (choice), *report type* (choice: allegation / official statement / news / opinion / correction / satire), *new vs prior coverage?* (noul), *action* (ignore / digest / watch / review now), *urgency* (score 0–4). Probabilities are kept and shown in the UI | `pipeline.drex_questions`, `drex_decide` |
| **DeepInfra** (`Qwen/Qwen3.8-27B`) | Writes the readable briefing and one-line "why it matters" explanations, using only Drex's decisions and verified evidence. It is also the LLM baseline in the benchmark | `pipeline.write_briefing`, `baseline_decide` |
| **Intern** | Coding agent used during development (see [Intern usage](#intern-usage)) | `docs/intern/` |
| **Our app** | Profiles, scan trigger and progress, canonical-URL deduplication, history of seen URLs and prior coverage, evidence validation, a rules layer for uncertainty, benchmark | `api/`, `src/` |

### Improvement feedback (Feedback tab)
- Keenable queries cover general and news coverage, **reviews and complaints**, **ads and campaigns**, and **stock and investor** news (company profiles).
- Drex answers two more typed questions per article in the same batched call: `improvement_area` (choice: marketing_messaging, advertising, product_quality, customer_support, pricing_value, trust_safety, financial_market, none) and `sentiment` (score: very negative to very positive, 0–4).
- `pipeline.build_scorecard` groups the items that weren't ignored by area. For each area it counts mentions, negative and positive items, and the average sentiment. It marks an area **Needs attention** when negative items outnumber positive ones or the average is below 1.5, **Strength** when the average is above 2.5, and **Mixed** otherwise.
- DeepInfra writes 1–2 sentences of practical advice per area, using only the scorecard and verified evidence.
- Limits: there is no live stock-price feed (only news about stocks and investors), and advertising is judged from public coverage of the ads, not from ad-platform data.

### Rules applied after Drex (deterministic, in `pipeline.apply_policy`)
- P(subject) < 0.35 → **ignore** (namesake or unrelated).
- 0.35 ≤ P(subject) < 0.65 → flag `identity_uncertain` and never silently ignore it (at least **watch**).
- If Drex says the article repeats prior coverage, **review now** is downgraded to **watch** (`repeat_coverage_downgraded`).
- Action confidence < 0.5 → flag `low_confidence_action`.
- Report type `allegation` → flag `allegation_not_fact`. The briefing prompt also requires wording like "reports allege".

### Evidence rules
- A supporting passage is shown only if it appears **verbatim** in the stored source text (ignoring whitespace and quote style). Otherwise the UI says the evidence is unknown.
- A missing publication date is shown as "unknown". It is never guessed.
- Confidence values are labeled as model-estimated probabilities.

## Architecture

```
 React (Vite) UI ──► /api/search ──► Keenable search  (dedupe by canonical URL, skip already-seen URLs)
   profile, scan        /api/fetch  ──► Keenable fetch   (title, URL, published_at, retrieved_at, text)
   progress, feed,      /api/extract──► NDI upload (.md) + Extract (JSON schema + citations)
   evidence, history    /api/decide ──► Drex systemone (6 typed questions, batched) + rules + evidence check
   (localStorage)       /api/brief  ──► DeepInfra Qwen3.8-27B (JSON: briefing + explanations)
                        /api/benchmark ◄── scripts/benchmark.py (Drex vs LLM baseline on the fixtures)
```

- The frontend drives the scan one stage at a time, so each request stays short and fits serverless time limits on Vercel. Progress is shown per stage.
- Single user. History (seen URLs, prior stories, last 10 scans) is kept in the browser's `localStorage`. The backend is stateless apart from bundled fixture data.
- API failures show up as errors on the stage that failed. They are **never** replaced with mock results.

## Fixture mode vs live mode

- **Fixture mode** (yellow banner) uses 18 **synthetic articles about a fictional company, "Nimbleroot"** (`api/_radar/data/fixtures.json`, generated by `scripts/make_fixtures.py`). The labels were written by hand. They cover namesakes (a plant nursery and a musician who shares the CEO's name), repeat coverage, a critical review, billing complaints, an impersonation scam, a data exposure, a legal allegation, an official statement, a correction, satire, a listicle mention and a state regulator inquiry. NDI output for the fixtures is cached once (`ndi_cache.json`), so demos are reproducible. Drex and DeepInfra are still called live.
- **Live mode** (green banner) uses real Keenable search and fetch, NDI, Drex and DeepInfra calls. The number of articles is capped (default 6, max 10).

### Automatic LLM fallback when Nace is unreachable
If a Drex or NDI call fails (for example the 403 bot challenge described below), the backend runs that step with the DeepInfra LLM instead, using the same questions and schema, and skips Nace for 60 seconds. Results from the fallback are tagged **LLM FALLBACK** in the feed and detail panel and carry no probabilities. Set `DECISION_FALLBACK=0` to disable it and surface the error instead.

### Replay of recorded Drex responses (fixture mode only, opt-in)
On the afternoon of Nov 14, `console.nace.ai` switched on a Vercel bot challenge (`x-vercel-mitigated: challenge`). That blocked every API call to Drex and NDI with HTTP 403, from our app and from Intern alike. The app reports this explicitly. To keep the fixture demo usable, the Scan panel has a **"Replay recorded Drex responses"** checkbox. It serves the **real** `drex-latest` responses captured in the 2026-11-14 20:32 UTC benchmark run (`api/_radar/data/drex_replay.json`, built by `scripts/make_drex_replay.py`). Every replayed item is tagged **RECORDED DREX**, and its detail panel shows the capture time. Replay is off by default and never applies in live mode.

## Setup

Requirements: Python 3.10+ and Node 18+.

```bash
cp .env.example .env        # then fill in keys locally; never commit .env
python -m venv .venv && .venv/bin/pip install -r requirements.txt uvicorn pytest
npm install
```

Run (two terminals):

```bash
.venv/bin/uvicorn api.index:app --port 8000 --reload --reload-dir api
```

```bash
npm run dev    # http://localhost:5173 (proxies /api to :8000)
```

### Environment variables (server-side only)

| Variable | Required | Notes |
|---|---|---|
| `NACE_API_KEY` | yes | Drex and NDI. Get one at console.nace.ai. Redeem `DREXATHON` under Billing for event credits |
| `DEEPINFRA_API_KEY` | yes | Briefing writer and LLM baseline |
| `KEENABLE_API_KEY` | optional | If unset, Halo uses Keenable's documented keyless `/public` endpoints (rate-limited) |
| `DREX_MODEL` | no | Default `drex-latest` (currently resolves to `drex-max-v1.1`) |
| `DEEPINFRA_MODEL`, `BASELINE_MODEL` | no | Default `Qwen/Qwen3.8-27B` |
| `DREX_PRICE_PER_M_INPUT` | no | Used only for benchmark cost estimates. See limitations |

Keys are read only in `api/_radar/config.py`. They are never sent to the browser or written to logs. If a key is missing, the UI names the variable to set.

### Deploy to Vercel
`vercel.json` builds the Vite app and serves `api/index.py` (FastAPI) on Vercel's Python runtime. Set the env vars in the Vercel project settings, then run `vercel deploy`.

## Benchmark (Apex Predator)

```bash
.venv/bin/python scripts/benchmark.py                 # Drex (drex-latest, drex-v2.0) vs Qwen baseline
.venv/bin/python scripts/benchmark.py --baseline-model <deepinfra-model-id>
```

All systems get the **same** state text: the profile, monitoring criteria, a fixed prior-coverage list, the shared NDI extraction and the article text. They also share the same rules layer, so only the decision stage differs. Results go to `api/_radar/data/benchmark_latest.json` (shown in the **Benchmark** tab), and raw responses go to `docs/benchmark_runs/`.

### Results (run 2026-11-14T21:21Z, 18 synthetic articles × 3 repeats = 54 calls per system, 8 questions per call)

| Metric | Drex `drex-latest` (→ drex-max-v1.1) | Drex `drex-v2.0` | Qwen baseline `Qwen/Qwen3.8-27B` |
|---|---|---|---|
| Important items caught (gold = review now, n=4) | **4/4** | **4/4** | 3/4 (the allegation was sent to *watch*) |
| Important items escalated to watch or higher | 4/4 | 4/4 | 4/4 |
| Irrelevant alerts (gold ignore/digest → watch/review) | 0 | 1 (namesake musician) | 0 |
| Namesakes correctly ignored (n=2) | 2/2 | 1/2 | 2/2 |
| Final-action agreement with labels | 61% | 72% | 65% |
| Category agreement | 78% | 89% | 93% |
| Report-type agreement | 78% | 56% | 76% |
| **Improvement-area agreement** | **89%** | 83% | 81% |
| Identity agreement | 100% | 100% | 98% |
| Novelty agreement | 89% | 94% | 87% |
| Median latency per article (wall clock) | **378 ms** | **340 ms** | 2,538 ms |
| Input tokens (54 calls) | 109,854 | 101,862 | 103,860 |
| Decision-stage cost (54 calls) | ≈ $0.013 (assumed price) | ≈ $0.012 (assumed price) | $0.015 (DeepInfra-reported) |

**What this shows:** on the same inputs and the same rules, Drex answered all 8 questions **about 6.7–7.5× faster** (median) than the Qwen baseline. It caught every gold "review now" item, while Qwen downgraded the legal allegation to "watch". `drex-latest` agreed with our labels most often on the improvement area (89%). Label agreement is otherwise mixed: Qwen did better on risk category, and every system over-escalated the billing complaints and the company's own statement (gold: watch) and under-rated the ad backlash (gold: watch, all said digest). Cost per article is about $0.0002–0.0003 for each system. The Drex figure depends on an **assumed** price, so we do **not** claim a cost win.

An earlier run (20:32Z, 14 articles, 6 questions) is kept in `docs/benchmark_runs/` for reference: Drex median 326 ms vs 1,547 ms.

**Whole-pipeline cost is dominated by NDI, not decisions.** Measured NDI cost was $0.012 for a 1-page fixture article and $0.036–0.048 per live web article (about 12k chars). That is roughly 100× the decision stage.

Raw responses: `docs/benchmark_runs/2026-11-14T212144+0000.json`.

## Intern usage

We used **Intern** (`intern-agent`, installed with `uv tool install`) as a headless coding agent with the organizer setup: System 1 `drex-latest`, System 2 `deepinfra/Qwen/Qwen3.8-27B`.

**Task given** (bounded, no network): write pytest unit tests for the pure helpers in `api/_radar/pipeline.py` (`canonical_url`, `validate_passage`, `pick_evidence`, `apply_policy`, `_as_bool`), run them, and fix any genuine bug in `pipeline.py` that the tests reveal.

```bash
intern -p --json --no-session --max-turns 40 --cwd . \
  --system1 drex-latest --system2 deepinfra/Qwen/Qwen3.8-27B "<task above>"
```

**What Intern contributed (verified by us):**
- `tests/test_pipeline.py` with **37 tests**: URL canonicalization (tracking params, `www.`/`m.`, trailing slashes), verbatim-passage validation (curly quotes, whitespace), evidence selection and fallback, every rule in `apply_policy`, and boolean parsing. Running `.venv/bin/python -m pytest -q tests` gives `37 passed`.
- **A real bug fix** in `apply_policy`. When identity was uncertain (0.35 ≤ P(subject) < 0.65), only `ignore` was raised to `watch`. A Drex action of `digest` slipped through, which broke the "at least watch" rule. Intern replaced `if action == "ignore"` with a rank comparison (`ACTION_RANK.get(action, 0) < ACTION_RANK["watch"]`). The benchmark below was run after this fix.
- Run stats: 9 turns, 10 tool calls (read, bash, write, edit), 19 Drex supervision decisions inside Intern (8 supervise, 8 wrap-up, 3 guard), about 6 minutes.

Sanitized record: [`docs/intern/run1.transcript.md`](docs/intern/run1.transcript.md) and [`docs/intern/run1.events.jsonl`](docs/intern/run1.events.jsonl). Token-level reasoning is dropped, and keys and local paths are redacted by `scripts/sanitize_intern_log.py`.

Intern's internal Drex supervision is separate from the product. Halo's reputation decisions are explicit `/v1/systemone` calls made by our backend.

## Limitations and next steps
- The benchmark dataset is tiny and synthetic, and the labels were written by the authors. Treat the results as directional.
- Drex per-call cost is not returned by the API. The Drex cost estimate uses an **assumed** rate (`DREX_PRICE_PER_M_INPUT`, $0.12 per 1M input tokens, taken from the Drex Max rate on Nace's pricing page). The baseline cost uses DeepInfra's reported `estimated_cost`. NDI cost is the job's reported `cost.total_usd`.
- The baseline model is the organizer-suggested worker model, not necessarily a frontier model. Whether it qualifies for the Apex Predator track needs organizer confirmation.
- NDI is the slowest stage (about 7–14 s per article). Next steps: extract only articles that pass a cheap Drex identity check first, and schedule recurring scans with email or Slack alerts.
- Keyless Keenable is rate-limited, so a key is recommended for real use.
- Single-user prototype with no authentication. History lives in the browser.
