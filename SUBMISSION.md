# Drexathon submission checklist

Deadline: **Saturday, November 14, 2026, 3:00 PM America/Los_Angeles**. Only finalized entries are judged, and nothing can be edited after you click Finalize.

## Done (in this repo)
- [x] Public GitHub repo with runnable source (React/Vite + FastAPI, Vercel-ready)
- [x] End-to-end live path verified: Keenable → NDI → Drex → DeepInfra
- [x] Fixture mode (synthetic, clearly labeled) for a reproducible demo
- [x] Decision-stage benchmark (Drex vs Qwen3.8-27B baseline) with measured latency, tokens and cost basis: `scripts/benchmark.py`
- [x] Intern used as a coding agent: 37 unit tests plus a real bug fix, with a sanitized transcript in `docs/intern/`
- [x] README: setup, architecture, env vars, Intern usage, benchmark, limitations
- [x] Presentation deck (6 slides). The link is in the hand-off message; export to PDF/PPTX from the deck's Share menu

## Remaining (you)
- [ ] Rotate the Nace and DeepInfra keys after the event (they were shared in a chat)
- [ ] Optional demo URL: `npx vercel` (log in), then set `NACE_API_KEY` and `DEEPINFRA_API_KEY` (and optionally `KEENABLE_API_KEY`) in Vercel → Project → Settings → Environment Variables, then `npx vercel --prod`
- [ ] Confirm with organizers that `Qwen/Qwen3.8-27B` is an acceptable baseline for Apex Predator (it is not claimed to be a frontier model)
- [ ] Go to https://www.nace.ai/drexathon/submit and submit the repo URL, the deck (PDF/PPTX export) and the optional demo URL
- [ ] Push any final commits, then click **Finalize** before 3:00 PM PT

## If the Nace API is down during the demo
`console.nace.ai` may return a Vercel security checkpoint (HTTP 403). The app says so explicitly. In Fixture mode, tick **Replay recorded Drex responses**: real responses captured earlier, each item labeled. Live mode needs Nace to be reachable.

## Demo script (about 3 min)
1. Profile → **Load demo profile (fictional “Nimbleroot”)** → Scan (Fixture mode).
2. In the feed, point out: the namesakes (nursery, musician) are **Ignored**, the funding repost is marked *repeat coverage* and sent to the digest, the pricey review goes to the **Digest**, and the scam accounts, data exposure and Oregon DOJ inquiry are **Review now**.
3. Open the staging-bucket item to show the verified passage, Drex's probabilities (labeled model estimates) and the *allegation, not fact* flag.
4. Show the Briefing tab.
5. Show the Benchmark tab: same inputs, Drex vs the Qwen baseline.
6. Switch to **Live**, set a real profile (e.g. “Nace AI”) and scan 3 articles.
