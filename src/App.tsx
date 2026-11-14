import { useEffect, useMemo, useState } from "react";
import { ACTION_LABEL, ACTION_RANK, api, ApiFailure, Item, load, Profile, save } from "./api";

type Mode = "live" | "fixture";
type StepState = { label: string; status: "pending" | "running" | "done" | "error"; detail?: string };
type Prior = { title: string; published_at?: string | null; summary: string; url?: string };
type ScanRecord = { at: string; mode: Mode; profile: string; stats: any; items: Item[]; briefing?: string };

const EMPTY: Profile = { name: "", kind: "company", aliases: [], description: "", website: "", region: "", industry: "", priorities: "" };
const PRIORITIES = "product quality, customer complaints, advertising and marketing reception, pricing, security or legal issues, investor sentiment";
const PRESETS: Profile[] = [
  { name: "Nvidia", kind: "company", aliases: ["NVIDIA Corporation", "NVDA"], description: "American chip designer based in Santa Clara, California, led by CEO Jensen Huang. Makes GPUs and AI accelerators for data centers, gaming (GeForce) and automotive, plus the CUDA software platform. Publicly traded (NASDAQ: NVDA).", website: "https://www.nvidia.com", region: "USA", industry: "semiconductors and AI computing", priorities: PRIORITIES },
  { name: "Nace AI", kind: "company", aliases: ["Nace.AI", "Nace", "Drex"], description: "AI startup that builds Drex decision models, NDI document processing (Perception) and the Intern agent harness, and runs the Drexathon hackathon. Not the National Association of Colleges and Employers (NACE) or the corrosion-engineering body NACE International.", website: "https://www.nace.ai", region: "USA", industry: "artificial intelligence", priorities: PRIORITIES },
  { name: "Adobe", kind: "company", aliases: ["Adobe Inc.", "ADBE"], description: "American software company based in San Jose, California. Makes Creative Cloud (Photoshop, Illustrator, Premiere Pro), Acrobat and PDF tools, Firefly generative AI and Experience Cloud marketing software. Publicly traded (NASDAQ: ADBE).", website: "https://www.adobe.com", region: "USA", industry: "creative and marketing software", priorities: PRIORITIES },
];
const TABS = ["Profile", "Scan", "Feedback", "Briefing"] as const;
type Area = { area: string; label: string; mentions: number; negative: number; positive: number; avg_sentiment: number | null;
  status: "needs_attention" | "mixed" | "strength"; items: { id: string; title: string; url: string; sentiment: number | null; evidence: string | null }[] };
type Scorecard = { areas: Area[]; items_without_area: number };

async function pool<T, R>(xs: T[], n: number, fn: (x: T, i: number) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(xs.length); let next = 0;
  await Promise.all(Array.from({ length: Math.min(n, xs.length) }, async () => {
    while (next < xs.length) { const i = next++; out[i] = await fn(xs[i], i); }
  }));
  return out;
}

const pct = (x?: number | null) => (x == null ? "unknown" : `${Math.round(x * 100)}%`);
const date = (x?: string | null) => (x ? x.slice(0, 10) : "date unknown");

export default function App() {
  const [tab, setTab] = useState<(typeof TABS)[number]>(() => (TABS as readonly string[]).includes(load("rr.tab", "Profile")) ? load("rr.tab", "Profile") : "Profile");
  const [mode, setMode] = useState<Mode>(() => load("rr.mode", "fixture"));
  const [profile, setProfile] = useState<Profile>(() => load("rr.profile", EMPTY));
  const [history, setHistory] = useState<ScanRecord[]>(() => load("rr.history", []));
  const [seen, setSeen] = useState<string[]>(() => load("rr.seen", []));
  const [prior, setPrior] = useState<Prior[]>(() => load("rr.prior", []));
  const [steps, setSteps] = useState<StepState[]>([]);
  const [items, setItems] = useState<Item[]>(() => load("rr.items", []));
  const [briefing, setBriefing] = useState<string>(() => load("rr.briefing", ""));
  const [selected, setSelected] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [batch, setBatch] = useState(0); // 0 = every unique source found
  const [replay, setReplay] = useState<boolean>(() => load("rr.replay", false));
  useEffect(() => save("rr.replay", replay), [replay]);
  const replaying = mode === "fixture" && replay;
  const [naceNote, setNaceNote] = useState("");
  const [scorecard, setScorecard] = useState<Scorecard | null>(() => load("rr.scorecard", null));
  const [recs, setRecs] = useState<Record<string, string>>(() => load("rr.recs", {}));
  useEffect(() => save("rr.scorecard", scorecard), [scorecard]);
  useEffect(() => save("rr.recs", recs), [recs]);

  useEffect(() => { api("health").then(setHealth).catch(() => setHealth(null)); }, []);
  useEffect(() => save("rr.tab", tab), [tab]);
  useEffect(() => save("rr.mode", mode), [mode]);
  useEffect(() => save("rr.profile", profile), [profile]);
  useEffect(() => save("rr.history", history.slice(-10)), [history]);
  useEffect(() => save("rr.seen", seen), [seen]);
  useEffect(() => save("rr.prior", prior), [prior]);
  useEffect(() => save("rr.items", items), [items]);
  useEffect(() => save("rr.briefing", briefing), [briefing]);

  async function loadFixtureProfile() {
    const fx = await api("fixtures");
    setProfile(fx.profile); setMode("fixture");
    setPrior(fx.history.map((h: any) => ({ title: h.title, published_at: h.published_at, summary: h.summary })));
    setSeen([]); setItems([]); setBriefing(""); setScorecard(null); setRecs({}); setSteps([]); setError(null);
  }

  function chooseLive(p: Profile) {
    setNaceNote(""); setProfile(p); setMode("live"); setSeen([]); setPrior([]); setItems([]); setBriefing(""); setScorecard(null); setRecs({}); setSteps([]); setError(null);
  }
  function setName(name: string) {
    // A typed name starts a fresh live profile; details are optional and filled with sensible defaults.
    const known = PRESETS.find((x) => x.name.toLowerCase() === name.trim().toLowerCase());
    if (known) return chooseLive(known);
    setProfile({ ...EMPTY, ...profile, name, priorities: profile.priorities || PRIORITIES });
    if (mode === "fixture") setMode("live");
  }

  function resetHistory() { setSeen([]); setPrior([]); setItems([]); setBriefing(""); setHistory([]); }

  const setStep = (i: number, patch: Partial<StepState>) =>
    setSteps((s) => s.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  async function runScan() {
    if (mode === "live" && !profile.name.trim()) { setError("Pick or type a company first."); setTab("Profile"); return; }
    setRunning(true); setError(null); setSelected(null); setBriefing(""); setItems([]); setScorecard(null); setRecs({}); setNaceNote("");
    setSteps([
      { label: mode === "live" ? "Search the web (Keenable)" : "Load fixture sources", status: "pending" },
      { label: mode === "live" ? "Fetch every source (Keenable)" : "Load fixture text", status: "pending" },
      { label: "Extract facts & passages (NDI)", status: "pending" },
      { label: replaying ? "Decide (Drex — RECORDED responses, replay)" : "Decide relevance, category, novelty, action (Drex)", status: "pending" },
      { label: "Write briefing (DeepInfra)", status: "pending" },
    ]);
    let cur = 0;
    try {
      // Fixture mode is a reproducible demo: it always starts from the fixture's own history.
      // Live mode keeps a per-browser history of seen URLs and prior stories.
      let scanSeen = seen, scanPrior = prior, prof: Profile = profile;
      if (mode === "fixture") {
        const fx = await api("fixtures");
        prof = fx.profile; setProfile(fx.profile);
        scanSeen = [];
        scanPrior = fx.history.map((h: any) => ({ title: h.title, published_at: h.published_at, summary: h.summary }));
      }
      setStep(0, { status: "running" });
      const s = await api("search", { profile: prof, mode, seen_urls: scanSeen, published_after: "30d", max_results: 20 });
      const limit = mode === "fixture" || !batch ? s.candidates.length : batch;
      const picked: Item[] = s.candidates.slice(0, limit);
      setStep(0, { status: "done", detail: `${s.stats.raw} results → ${s.stats.unique_new} new unique (${s.stats.duplicates_in_scan} dupes, ${s.stats.already_seen} already seen); processing ${picked.length}` });
      if (!picked.length) {
        setItems([]);
        setSteps((st) => st.map((x, j) => (j === 0 ? x : { ...x, status: "done", detail: "skipped — no new coverage" })));
        setError("No new coverage since your last live scan. Every result was already seen. Use “Reset scan history” on the Profile tab to rescan everything.");
        return;
      }

      cur = 1; setStep(1, { status: "running" });
      let fetched = 0;
      const docs: Item[] = await pool(picked, 10, async (c) => {
        try { const d = await api<Item>("fetch", { candidate: c, mode }); setStep(1, { detail: `${++fetched}/${picked.length}` }); return d; }
        catch (e: any) { return { ...c, error: `fetch failed: ${e.message}` }; }
      });
      const ok = docs.filter((d) => !d.error && (d.text || "").length > 80);
      setStep(1, { status: ok.length ? "done" : "error", detail: `${ok.length}/${docs.length} fetched${docs.length - ok.length ? `, ${docs.length - ok.length} failed or empty` : ""}` });
      if (!ok.length) throw new Error(docs.find((d) => d.error)?.error || "No source text retrieved.");

      cur = 2; setStep(2, { status: "running" });
      let extracted = 0, cachedN = 0, exFallback = 0, deFallback = 0, nace = "";
      await pool(ok, 10, async (d) => {
        try {
          const n = await api("extract", { profile: prof, doc: d, mode });
          d.facts = n; d.ndi = { job_id: n.job_id, cached: n.cached, latency_ms: n.latency_ms, cost: n.cost, fallback: !!n.fallback, engine: n.engine };
          if (n.cached) cachedN++;
          if (n.fallback) { exFallback++; nace = n.fallback_reason || nace; }
        } catch (e: any) { d.error = `NDI failed: ${e.message}`; if (e instanceof ApiFailure && e.missingEnv) throw e; }
        setStep(2, { detail: `${++extracted}/${ok.length}` });
      });
      const nOk = ok.filter((d) => d.facts).length;
      setStep(2, { status: nOk ? "done" : "error", detail: `${nOk}/${ok.length} extracted${cachedN ? ` (${cachedN} from cached NDI output)` : ""}${exFallback ? ` · ${exFallback} by LLM fallback, NDI unreachable` : ""}` });

      cur = 3; setStep(3, { status: "running" });
      const ordered = [...ok].sort((a, b) => (a.published_at || "").localeCompare(b.published_at || ""));
      const running: Prior[] = [...scanPrior];
      for (let i = 0; i < ordered.length; i++) {
        const d = ordered[i];
        try {
          const r = await api("decide", { profile: prof, doc: d, facts: d.facts, prior: running, replay: replaying });
          Object.assign(d, { decisions: r.decisions, final_action: r.final_action, flags: r.flags, evidence: r.evidence,
            replayed: !!r.replayed, recorded_at: r.recorded_at, fallback: !!r.fallback,
            drex: { model: r.model, latency_ms: r.latency_ms, usage: r.usage, request_id: r.request_id } });
          if (r.fallback) { deFallback++; nace = r.fallback_reason || nace; }
          if (r.final_action !== "ignore") {
            const claim = d.facts?.data?.claims?.[0]?.claim;
            running.push({ title: d.title, published_at: d.published_at, summary: claim || (d.text || "").slice(0, 160), url: d.url });
          }
        } catch (e: any) { d.error = `Drex failed: ${e.message}`; if (e instanceof ApiFailure && e.missingEnv) throw e; }
        setStep(3, { detail: `${i + 1}/${ordered.length}` });
        setItems([...ordered]);
      }
      const decided = ordered.filter((d) => d.decisions);
      setStep(3, { status: decided.length ? "done" : "error", detail: `${decided.length}/${ordered.length} decided${deFallback ? ` · ${deFallback} by LLM fallback, Drex unreachable` : ""}` });
      setNaceNote(nace);
      if (!decided.length) {
        const first = ordered.find((d) => d.error)?.error || "Drex returned no decisions.";
        throw new Error(mode === "fixture" && !replay
          ? `${first} — To demo anyway, tick “Replay recorded Drex responses” (real responses captured earlier, clearly labeled).`
          : first);
      }

      cur = 4; setStep(4, { status: "running" });
      const b = await api("brief", { profile: prof, items: decided.map(({ text, ...rest }) => rest) });
      for (const d of decided) d.explanation = b.explanations?.[d.id];
      setBriefing(b.briefing); setItems([...ordered]); setScorecard(b.scorecard ?? null); setRecs(b.recommendations ?? {});
      setStep(4, { status: "done", detail: b.model ? `${b.model} · ${b.latency_ms ?? "?"} ms` : "skipped — no relevant items to brief" });

      if (mode === "live") {
        setSeen((x) => [...x, ...ordered.map((d) => d.canonical_url || d.url)]);
        setPrior(running);
      }
      setHistory((h) => [...h, { at: new Date().toISOString(), mode, profile: prof.name, stats: s.stats,
        items: ordered.map(({ text, ...rest }) => rest), briefing: b.briefing }]);
    } catch (e: any) {
      const msg = e instanceof ApiFailure && e.missingEnv
        ? `Missing server configuration: set ${e.missingEnv} in your local .env (or Vercel env vars), then retry.`
        : e.message;
      setError(msg); setStep(cur, { status: "error", detail: msg });
    } finally { setRunning(false); }
  }

  const feed = useMemo(() => [...items].sort((a, b) =>
    (ACTION_RANK[b.final_action || ""] ?? -1) - (ACTION_RANK[a.final_action || ""] ?? -1) ||
    (b.decisions?.urgency?.score ?? 0) - (a.decisions?.urgency?.score ?? 0)), [items]);
  const sel = items.find((i) => i.id === selected) || null;
  const alerts = items.filter((i) => i.final_action === "review_now").length;

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="dot" />Project Halo</div>
        <nav>{TABS.map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>
            {t}{t === "Scan" && alerts ? <span className="badge">{alerts}</span> : null}
          </button>))}</nav>
        <div className={`mode ${mode}`}>{mode === "fixture" ? "FIXTURE MODE · synthetic data" : `LIVE MODE · real web${health?.keenable_mode === "keyless-public" ? " (Keenable keyless)" : ""}`}</div>
      </header>

      {health && Object.entries(health.keys).some(([, v]) => !v) && (
        <div className="warn">Missing server env vars: {Object.entries(health.keys).filter(([, v]) => !v).map(([k]) => k).join(", ")}. Add them to <code>.env</code> (see <code>.env.example</code>).</div>
      )}
      {!health && <div className="warn">Backend not reachable at /api. Start it with <code>uvicorn api.index:app --port 8000</code>.</div>}

      {tab === "Profile" && (
        <section className="card narrow">
          <h2>Who should Project Halo study?</h2>
          <p className="muted">Pick a demo company or type any name. That is all you need.</p>
          <div className="presets">
            <button className={mode === "fixture" ? "chip on" : "chip"} onClick={loadFixtureProfile}>Nimbleroot<span>fictional demo · offline sources</span></button>
            {PRESETS.map((x) => (
              <button key={x.name} className={mode === "live" && profile.name === x.name ? "chip on" : "chip"} onClick={() => chooseLive(x)}>{x.name}<span>live web</span></button>))}
          </div>
          <label>Or type a company, person or team<input value={mode === "fixture" ? "" : profile.name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Duolingo" /></label>
          <details>
            <summary>Optional details (improves namesake filtering)</summary>
            <label>Description<textarea rows={2} value={profile.description} onChange={(e) => setProfile({ ...profile, description: e.target.value })} /></label>
            <label>Aliases (comma-separated)<input value={profile.aliases.join(", ")} onChange={(e) => setProfile({ ...profile, aliases: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></label>
            <div className="grid2">
              <label>Official website<input value={profile.website} onChange={(e) => setProfile({ ...profile, website: e.target.value })} /></label>
              <label>Industry<input value={profile.industry} onChange={(e) => setProfile({ ...profile, industry: e.target.value })} /></label>
            </div>
            <label>What to watch for<textarea rows={2} value={profile.priorities} onChange={(e) => setProfile({ ...profile, priorities: e.target.value })} /></label>
          </details>
          <div className="row">
            <button className="primary" onClick={() => setTab("Scan")} disabled={!profile.name.trim()}>Continue to scan</button>
            <button className="ghost" onClick={resetHistory}>Reset scan history</button>
          </div>
          <p className="muted small">History: {seen.length} URLs seen · {prior.length} prior stories in context · {history.length} scans stored in this browser.</p>
        </section>
      )}

      {tab === "Scan" && (
        <div className="scan">
          <aside className="card">
            <h3>{profile.name || "No profile"}</h3>
            <div className="seg">
              <button className={mode === "fixture" ? "active" : ""} onClick={() => setMode("fixture")} disabled={running}>Fixture</button>
              <button className={mode === "live" ? "active" : ""} onClick={() => setMode("live")} disabled={running}>Live</button>
            </div>
            {mode === "fixture" && <label className="small check"><input type="checkbox" checked={replay} disabled={running} onChange={(e) => setReplay(e.target.checked)} />
              Replay recorded Drex responses<span className="muted"> (real drex-latest output captured 2026-11-14 21:21 UTC; use if the Nace API is down)</span></label>}
            {mode === "live" && <label className="small">Limit sources (blank = all found)<input type="number" min={1} placeholder="all" value={batch || ""} onChange={(e) => setBatch(Math.max(0, +e.target.value || 0))} /></label>}
            <button className="primary wide" onClick={runScan} disabled={running}>{running ? "Scanning…" : "Scan now"}</button>
            <ol className="steps">{steps.map((s, i) => (
              <li key={i} className={s.status}><span className="ico" />{s.label}{s.detail && <div className="small muted">{s.detail}</div>}</li>))}</ol>
            {error && <div className="err">{error}</div>}
            {naceNote && <div className="warn small">Nace (Drex/NDI) was unreachable, so the affected steps used the DeepInfra LLM fallback and are labeled. Reason: {naceNote.slice(0, 160)}</div>}
          </aside>
          <main>
            {!feed.length && <div className="card muted">No results yet. Run a scan.</div>}
            {feed.map((it) => (
              <article key={it.id} className={`item ${it.final_action || (it.error ? "err" : "pending")} ${selected === it.id ? "sel" : ""}`} onClick={() => setSelected(it.id)}>
                <div className="itemhead">
                  <span className={`act ${it.final_action}`}>{it.final_action ? ACTION_LABEL[it.final_action] : it.error ? "Error" : "Analyzing…"}</span>
                  <span className="src">{it.source === "fixture" ? "fixture" : "live"}</span>
                  {it.replayed && <span className="src rec">recorded Drex</span>}
                  {it.fallback && <span className="src rec">LLM fallback</span>}
                  <span className="muted small">{it.outlet || hostOf(it.url)} · {date(it.published_at)}</span>
                </div>
                <h4>{it.title}</h4>
                {it.decisions && <div className="tags">
                  <span>{it.decisions.category.value}</span><span>{it.decisions.report_type.value}</span>
                  {it.decisions.is_novel.value === false && <span className="repeat">repeat coverage</span>}
                  {(it.flags || []).map((f) => <span key={f} className="flag">{f.replace(/_/g, " ")}</span>)}
                </div>}
                {it.explanation && <p className="small">{it.explanation}</p>}
                {it.error && <div className="err small">{it.error}</div>}
              </article>
            ))}
          </main>
          {sel && <Detail item={sel} onClose={() => setSelected(null)} />}
        </div>
      )}

      {tab === "Briefing" && (
        <section className="card narrow">
          <h2>Briefing — {profile.name || "no profile"}</h2>
          <p className="muted small">Written by {health?.llm_model ?? "DeepInfra LLM"} from Drex decisions and verified evidence. Allegations are reported as claims, not facts.</p>
          {briefing ? <Markdown text={briefing} /> : <p className="muted">Run a scan to generate a briefing.</p>}
          {history.length > 0 && <><h3>Scan history</h3><ul className="small">{[...history].reverse().map((h, i) => (
            <li key={i}>{h.at.slice(0, 16).replace("T", " ")} · {h.mode} · {h.profile} · {h.items.length} items · {h.items.filter((x) => x.final_action === "review_now").length} review-now</li>))}</ul></>}
        </section>
      )}

      {tab === "Feedback" && <Feedback profile={profile.name} scorecard={scorecard} recs={recs} onOpen={(id) => { setSelected(id); setTab("Scan"); }} />}
      <footer className="muted small">Confidence values are model-estimated probabilities from Drex, not guarantees. Demo data in fixture mode is fictional.</footer>
    </div>
  );
}

const STATUS_LABEL: Record<Area["status"], string> = { needs_attention: "Needs attention", mixed: "Mixed", strength: "Strength" };
const SENT_LABEL = ["very negative", "negative", "neutral", "positive", "very positive"];
const sentWord = (s: number | null) => (s == null ? "unknown" : SENT_LABEL[Math.max(0, Math.min(4, Math.round(s)))]);

function Feedback({ profile, scorecard, recs, onOpen }: { profile: string; scorecard: Scorecard | null; recs: Record<string, string>; onOpen: (id: string) => void }) {
  if (!scorecard) return <section className="card narrow"><h2>Improvement feedback</h2><p className="muted">Run a scan to see where {profile || "the subject"} should improve.</p></section>;
  return (
    <section className="card narrow">
      <h2>Improvement feedback — {profile}</h2>
      <p className="small muted">From public coverage: news, reviews, complaints, ads and market news. <b>Drex</b> labels each relevant item with an improvement area and a sentiment score (0 very negative to 4 very positive). <b>DeepInfra</b> writes the advice, using only those decisions and verified evidence. Scores are model estimates.</p>
      {!scorecard.areas.length && <p className="muted">No improvement areas found in this scan.</p>}
      {scorecard.items_without_area > 0 && <p className="small warnline">{scorecard.items_without_area} relevant item(s) have no improvement area, e.g. recorded Drex responses captured before this feature was added. They are not counted here.</p>}
      <div className="areas">{scorecard.areas.map((a) => (
        <div key={a.area} className={`area ${a.status}`}>
          <div className="areahead">
            <h3>{a.label}</h3>
            <span className={`pill ${a.status}`}>{STATUS_LABEL[a.status]}</span>
          </div>
          <div className="small muted">{a.mentions} mention{a.mentions === 1 ? "" : "s"} · {a.negative} negative · {a.positive} positive · average {a.avg_sentiment ?? "?"} / 4 ({sentWord(a.avg_sentiment)})</div>
          <div className="sentbar" aria-label={`average sentiment ${a.avg_sentiment ?? "unknown"} of 4`}><i style={{ width: `${((a.avg_sentiment ?? 0) / 4) * 100}%` }} /></div>
          {recs[a.area] && <p><b>Recommendation:</b> {recs[a.area]}</p>}
          <ul className="small">{a.items.map((it) => (
            <li key={it.id}><a href="#" onClick={(e) => { e.preventDefault(); onOpen(it.id); }}>{it.title}</a> <span className="muted">— {sentWord(it.sentiment)}</span>
              {it.evidence && <div className="muted">“{it.evidence}”</div>}</li>))}</ul>
        </div>))}</div>
    </section>
  );
}

function hostOf(u: string) { try { return new URL(u).hostname; } catch { return u; } }

function Detail({ item, onClose }: { item: Item; onClose: () => void }) {
  const d = item.decisions;
  return (
    <aside className="card detail">
      <button className="ghost close" onClick={onClose}>×</button>
      <h3>{item.title}</h3>
      <p className="small"><a href={item.url} target="_blank" rel="noreferrer">{item.url}</a></p>
      <p className="small muted">Published: {item.published_at || "unknown"} · Retrieved: {item.retrieved_at || "unknown"} · Source: {item.source}</p>
      {item.explanation && <><h4>Why it matters</h4><p>{item.explanation}</p></>}
      <h4>Supporting passage</h4>
      {item.evidence?.passage
        ? <blockquote>“{item.evidence.passage}”<div className="small ok">✓ verified verbatim against stored source text ({item.evidence.origin})</div></blockquote>
        : <p className="muted small">Unknown — {item.evidence?.note || "no evidence extracted"}</p>}
      {d && <>
        <h4>{item.fallback ? "Decisions — LLM fallback (Drex unreachable)" : "Drex decisions"} <span className="muted small">{item.fallback ? "(no probabilities from the LLM)" : "(model-estimated confidence)"}</span></h4>
        <table className="dec"><tbody>
          <tr><td>About this subject?</td><td>{d.is_subject.value ? "yes" : "no"}</td><td>P(yes) {pct(d.is_subject.p_yes)}</td></tr>
          <tr><td>Category</td><td>{d.category.value}</td><td>{pct(d.category.confidence)}</td></tr>
          <tr><td>Report type</td><td>{d.report_type.value}</td><td>{pct(d.report_type.confidence)}</td></tr>
          <tr><td>New vs prior coverage?</td><td>{d.is_novel.value ? "new" : "repeat"}</td><td>P(new) {pct(d.is_novel.p_yes)}</td></tr>
          <tr><td>Drex action</td><td>{d.action.value}</td><td>{pct(d.action.confidence)}</td></tr>
          <tr><td>Final action (after policy)</td><td><b>{item.final_action}</b></td><td>{(item.flags || []).join(", ") || "—"}</td></tr>
          <tr><td>Urgency (0–4)</td><td>{d.urgency.score?.toFixed(2)}</td><td>{pct(d.urgency.confidence)}</td></tr>
          <tr><td>Improvement area</td><td>{d.improvement_area?.value?.replace(/_/g, " ") ?? "not in this response"}</td><td>{pct(d.improvement_area?.confidence)}</td></tr>
          <tr><td>Sentiment (0 very neg – 4 very pos)</td><td>{d.sentiment?.score != null ? d.sentiment.score.toFixed(2) : "not in this response"}</td><td>{pct(d.sentiment?.confidence)}</td></tr>
        </tbody></table>
        <Probs title="Action probabilities" p={d.action.probabilities} />
        <Probs title="Category probabilities" p={d.category.probabilities} />
        <p className="small muted">{item.replayed ? `RECORDED Drex response (captured ${item.recorded_at}), not a live call · ` : ""}Drex {item.drex?.model} · {item.drex?.latency_ms} ms · {item.drex?.usage?.input_tokens ?? "?"} input tokens</p>
      </>}
      {item.facts?.data && <>
        <h4>Extracted facts <span className="muted small">{item.ndi?.fallback ? `(LLM fallback: ${item.ndi?.engine}; NDI unreachable)` : item.ndi?.cached ? "(cached fixture output)" : `job ${item.ndi?.job_id ?? ""}`}</span></h4>
        <ul className="small">{(item.facts.data.claims || []).map((c: any, i: number) => (
          <li key={i}><b>[{c.status || "?"}]</b> {c.claim} <span className="muted">— {c.attributed_to || "unattributed"}</span></li>))}</ul>
        {(item.facts.data.entities || []).length > 0 && <p className="small muted">Entities: {item.facts.data.entities.map((e: any) => e.name).join(", ")}</p>}
      </>}
    </aside>
  );
}

function Probs({ title, p }: { title: string; p: Record<string, number> }) {
  const rows = Object.entries(p || {}).sort((a, b) => b[1] - a[1]);
  if (!rows.length) return null;
  return <div className="probs"><div className="small muted">{title}</div>{rows.map(([k, v]) => (
    <div key={k} className="bar"><span>{k}</span><div><i style={{ width: `${v * 100}%` }} /></div><em>{pct(v)}</em></div>))}</div>;
}

function Markdown({ text }: { text: string }) {
  return <div className="md">{text.split("\n").map((l, i) => {
    const t = l.trim(); if (!t) return null;
    const html = t.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^#+\s*/, "");
    if (/^[-*]\s/.test(t)) return <li key={i} dangerouslySetInnerHTML={{ __html: escapeKeep(html.replace(/^[-*]\s/, "")) }} />;
    if (/^#/.test(t)) return <h3 key={i}>{html}</h3>;
    return <p key={i} dangerouslySetInnerHTML={{ __html: escapeKeep(html) }} />;
  })}</div>;
}
function escapeKeep(s: string) { return s.replace(/</g, "&lt;").replace(/&lt;(\/?)b>/g, "<$1b>"); }
