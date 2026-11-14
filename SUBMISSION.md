# Drexathon submission checklist

Deadline: **Saturday, November 14, 2026, 3:00 PM America/Los_Angeles**. Only finalized entries are judged, and nothing can be edited after you click Finalize.

## Done (in this repo)
- [x] Public GitHub repo with runnable source (React/Vite + FastAPI, Vercel-ready)
- [x] End-to-end live path verified: Keenable → NDI → Drex → DeepInfra
- [x] Fixture mode (synthetic, clearly labeled) for a reproducible demo
- [x] Intern used as a coding agent: 37 unit tests plus a real bug fix, with a sanitized transcript in `docs/intern/`
- [x] README: setup, architecture, env vars, Intern usage, limitations
- [x] Presentation deck (5 slides). The link is in the hand-off message; export to PDF/PPTX from the deck's Share menu

## Remaining (you)
- [ ] Rotate the Nace and DeepInfra keys after the event (they were shared in a chat)
- [ ] Optional demo URL: `npx vercel` (log in), then set `NACE_API_KEY` and `DEEPINFRA_API_KEY` (and optionally `KEENABLE_API_KEY`) in Vercel → Project → Settings → Environment Variables, then `npx vercel --prod`
- [ ] Go to https://www.nace.ai/drexathon/submit and submit the repo URL, the deck (PDF/PPTX export) and the optional demo URL
- [ ] Push any final commits, then click **Finalize** before 3:00 PM PT

## If the Nace API is down during the demo
`console.nace.ai` may return a Vercel security checkpoint (HTTP 403). The app says so explicitly. The app then falls back to the DeepInfra LLM automatically and labels those results **LLM FALLBACK**. In Fixture mode you can also tick **Replay recorded Drex responses** (real responses captured earlier, each item labeled).

## Demo script (about 3 min)
1. Profile → pick **Nimbleroot** (fictional demo) → Continue to scan → Scan now.
2. In the feed, point out: the namesakes (nursery, musician) are **Ignored**, the funding repost is marked *repeat coverage* and sent to the digest, the pricey review goes to the **Digest**, and the scam accounts, data exposure and Oregon DOJ inquiry are **Review now**.
3. Open the staging-bucket item to show the verified passage, Drex's probabilities (labeled model estimates) and the *allegation, not fact* flag.
4. Show the **Feedback** tab (improvement areas with advice), then the Briefing tab.
5. Profile → pick a real company (e.g. **Duolingo**) → Scan now (live web, 6 articles), then open Feedback.
