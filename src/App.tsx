import { useEffect, useMemo, useState } from "react";
import { ACTION_LABEL, ACTION_RANK, api, ApiFailure, Item, load, Profile, save } from "./api";

type Mode = "live" | "fixture";
type StepState = { label: string; status: "pending" | "running" | "done" | "error"; detail?: string };
type Prior = { title: string; published_at?: string | null; summary: string; url?: string };
type ScanRecord = { at: string; mode: Mode; profile: string; stats: any; items: Item[]; briefing?: string };

const EMPTY: Profile = { name: "", kind: "company", aliases: [], description: "", website: "", region: "", industry: "", priorities: "" };
const TABS = ["Profile", "Scan", "Briefing", "Benchmark"] as const;

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
  const [tab, setTab] = useState<(typeof TABS)[number]>(() => load("rr.tab", "Profile"));
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
  const [batch, setBatch] = useState(6);

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
    setSeen([]); setItems([]); setBriefing("");
  }

  function resetHistory() { setSeen([]); setPrior([]); setItems([]); setBriefing(""); setHistory([]); }

  const setStep = (i: number, patch: Partial<StepState>) =>
    setSteps((s) => s.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  async function runScan() {
    if (!profile.name.trim()) { setError("Create a profile first."); setTab("Profile"); return; }
    setRunning(true); setError(null); setSelected(null); setBriefing(""); setItems([]);
    setSteps([
      { label: mode === "live" ? "Search the web (Keenable)" : "Load fixture articles", status: "pending" },
      { label: mode === "live" ? "Fetch article text (Keenable)" : "Load fixture text", status: "pending" },
      { label: "Extract facts & passages (NDI)", status: "pending" },
      { label: "Decide relevance, category, novelty, action (Drex)", status: "pending" },
      { label: "Write briefing (DeepInfra)", status: "pending" },
    ]);
    let cur = 0;
    try {
      // Fixture mode is a reproducible demo: it always starts from the fixture's own history.
      // Live mode keeps a per-browser history of seen URLs and prior stories.
      let scanSeen = seen, scanPrior = prior;
      if (mode === "fixture") {
        const fx = await api("fixtures");
        scanSeen = [];
        scanPrior = fx.history.map((h: any) => ({ title: h.title, published_at: h.published_at, summary: h.summary }));
      }
      setStep(0, { status: "running" });
      const s = await api("search", { profile, mode, seen_urls: scanSeen, published_after: "30d", max_results: 8 });
      const limit = mode === "fixture" ? s.candidates.length : batch;
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
      const docs: Item[] = await pool(picked, 3, async (c) => {
        try { const d = await api<Item>("fetch", { candidate: c, mode }); setStep(1, { detail: `${++fetched}/${picked.length}` }); return d; }
        catch (e: any) { return { ...c, error: `fetch failed: ${e.message}` }; }
      });
      const ok = docs.filter((d) => !d.error && (d.text || "").length > 80);
      setStep(1, { status: ok.length ? "done" : "error", detail: `${ok.length}/${docs.length} fetched${docs.length - ok.length ? `, ${docs.length - ok.length} failed or empty` : ""}` });
      if (!ok.length) throw new Error(docs.find((d) => d.error)?.error || "No article text retrieved.");

      cur = 2; setStep(2, { status: "running" });
      let extracted = 0, cachedN = 0;
      await pool(ok, 3, async (d) => {
        try {
          const n = await api("extract", { profile, doc: d, mode });
          d.facts = n; d.ndi = { job_id: n.job_id, cached: n.cached, latency_ms: n.latency_ms, cost: n.cost };
          if (n.cached) cachedN++;
        } catch (e: any) { d.error = `NDI failed: ${e.message}`; if (e instanceof ApiFailure && e.missingEnv) throw e; }
        setStep(2, { detail: `${++extracted}/${ok.length}` });
      });
      const nOk = ok.filter((d) => d.facts).length;
      setStep(2, { status: nOk ? "done" : "error", detail: `${nOk}/${ok.length} extracted${cachedN ? ` (${cachedN} from cached NDI output for fixtures)` : ""}` });

      cur = 3; setStep(3, { status: "running" });
      const ordered = [...ok].sort((a, b) => (a.published_at || "").localeCompare(b.published_at || ""));
      const running: Prior[] = [...scanPrior];
      for (let i = 0; i < ordered.length; i++) {
        const d = ordered[i];
        try {
          const r = await api("decide", { profile, doc: d, facts: d.facts, prior: running });
          Object.assign(d, { decisions: r.decisions, final_action: r.final_action, flags: r.flags, evidence: r.evidence,
            drex: { model: r.model, latency_ms: r.latency_ms, usage: r.usage, request_id: r.request_id } });
          if (r.final_action !== "ignore") {
            const claim = d.facts?.data?.claims?.[0]?.claim;
            running.push({ title: d.title, published_at: d.published_at, summary: claim || (d.text || "").slice(0, 160), url: d.url });
          }
        } catch (e: any) { d.error = `Drex failed: ${e.message}`; if (e instanceof ApiFailure && e.missingEnv) throw e; }
        setStep(3, { detail: `${i + 1}/${ordered.length}` });
        setItems([...ordered]);
      }
      const decided = ordered.filter((d) => d.decisions);
      setStep(3, { status: decided.length ? "done" : "error", detail: `${decided.length}/${ordered.length} decided` });
      if (!decided.length) throw new Error(ordered.find((d) => d.error)?.error || "Drex returned no decisions.");

      cur = 4; setStep(4, { status: "running" });
      const b = await api("brief", { profile, items: decided.map(({ text, ...rest }) => rest) });
      for (const d of decided) d.explanation = b.explanations?.[d.id];
      setBriefing(b.briefing); setItems([...ordered]);
      setStep(4, { status: "done", detail: b.model ? `${b.model} · ${b.latency_ms ?? "?"} ms` : "skipped — no relevant items to brief" });

      if (mode === "live") {
        setSeen((x) => [...x, ...ordered.map((d) => d.canonical_url || d.url)]);
        setPrior(running);
      }
      setHistory((h) => [...h, { at: new Date().toISOString(), mode, profile: profile.name, stats: s.stats,
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
        <div className="brand"><span className="dot" />Reputation Radar</div>
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
          <h2>Monitored profile</h2>
          <p className="muted">Who should Radar watch? Identifying context helps separate namesakes.</p>
          <div className="grid2">
            <label>Name<input value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} placeholder="Acme Robotics" /></label>
            <label>Type<select value={profile.kind} onChange={(e) => setProfile({ ...profile, kind: e.target.value })}>
              <option value="company">Company</option><option value="person">Person</option><option value="team">Team / group</option></select></label>
          </div>
          <label>Aliases (comma-separated)<input value={profile.aliases.join(", ")} onChange={(e) => setProfile({ ...profile, aliases: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></label>
          <label>Description<textarea rows={2} value={profile.description} onChange={(e) => setProfile({ ...profile, description: e.target.value })} /></label>
          <div className="grid2">
            <label>Official website<input value={profile.website} onChange={(e) => setProfile({ ...profile, website: e.target.value })} /></label>
            <label>Region<input value={profile.region} onChange={(e) => setProfile({ ...profile, region: e.target.value })} /></label>
          </div>
          <label>Industry<input value={profile.industry} onChange={(e) => setProfile({ ...profile, industry: e.target.value })} /></label>
          <label>Monitoring priorities<textarea rows={3} value={profile.priorities} onChange={(e) => setProfile({ ...profile, priorities: e.target.value })} placeholder="e.g. security incidents, lawsuits, impersonation; routine reviews → digest" /></label>
          <div className="row">
            <button className="primary" onClick={() => setTab("Scan")} disabled={!profile.name.trim()}>Save & go to scan</button>
            <button onClick={loadFixtureProfile}>Load demo profile (fictional “Nimbleroot”)</button>
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
            {mode === "live" && <label className="small">Articles to process<input type="number" min={1} max={10} value={batch} onChange={(e) => setBatch(Math.max(1, Math.min(10, +e.target.value || 1)))} /></label>}
            <button className="primary wide" onClick={runScan} disabled={running}>{running ? "Scanning…" : "Scan now"}</button>
            <ol className="steps">{steps.map((s, i) => (
              <li key={i} className={s.status}><span className="ico" />{s.label}{s.detail && <div className="small muted">{s.detail}</div>}</li>))}</ol>
            {error && <div className="err">{error}</div>}
          </aside>
          <main>
            {!feed.length && <div className="card muted">No results yet. Run a scan.</div>}
            {feed.map((it) => (
              <article key={it.id} className={`item ${it.final_action || "err"} ${selected === it.id ? "sel" : ""}`} onClick={() => setSelected(it.id)}>
                <div className="itemhead">
                  <span className={`act ${it.final_action}`}>{it.final_action ? ACTION_LABEL[it.final_action] : "Error"}</span>
                  <span className="src">{it.source === "fixture" ? "fixture" : "live"}</span>
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

      {tab === "Benchmark" && <Benchmark />}
      <footer className="muted small">Confidence values are model-estimated probabilities from Drex, not guarantees. Demo data in fixture mode is fictional.</footer>
    </div>
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
        <h4>Drex decisions <span className="muted small">(model-estimated confidence)</span></h4>
        <table className="dec"><tbody>
          <tr><td>About this subject?</td><td>{d.is_subject.value ? "yes" : "no"}</td><td>P(yes) {pct(d.is_subject.p_yes)}</td></tr>
          <tr><td>Category</td><td>{d.category.value}</td><td>{pct(d.category.confidence)}</td></tr>
          <tr><td>Report type</td><td>{d.report_type.value}</td><td>{pct(d.report_type.confidence)}</td></tr>
          <tr><td>New vs prior coverage?</td><td>{d.is_novel.value ? "new" : "repeat"}</td><td>P(new) {pct(d.is_novel.p_yes)}</td></tr>
          <tr><td>Drex action</td><td>{d.action.value}</td><td>{pct(d.action.confidence)}</td></tr>
          <tr><td>Final action (after policy)</td><td><b>{item.final_action}</b></td><td>{(item.flags || []).join(", ") || "—"}</td></tr>
          <tr><td>Urgency (0–4)</td><td>{d.urgency.score?.toFixed(2)}</td><td>{pct(d.urgency.confidence)}</td></tr>
        </tbody></table>
        <Probs title="Action probabilities" p={d.action.probabilities} />
        <Probs title="Category probabilities" p={d.category.probabilities} />
        <p className="small muted">Drex {item.drex?.model} · {item.drex?.latency_ms} ms · {item.drex?.usage?.input_tokens ?? "?"} input tokens</p>
      </>}
      {item.facts?.data && <>
        <h4>NDI extraction <span className="muted small">{item.ndi?.cached ? "(cached fixture output)" : `job ${item.ndi?.job_id ?? ""}`}</span></h4>
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

function Benchmark() {
  const [b, setB] = useState<any>(null);
  useEffect(() => { api("benchmark").then(setB).catch((e) => setB({ available: false, message: e.message })); }, []);
  if (!b) return <section className="card narrow muted">Loading…</section>;
  if (b.available === false) return <section className="card narrow"><h2>Benchmark</h2><p className="muted">{b.message}</p></section>;
  const sys = b.systems as any[];
  const metrics: [string, string, (s: any) => string][] = [
    ["Important items caught (gold = review now)", "important_caught", (s) => `${s.important_caught}/${b.dataset.important}`],
    ["Important items escalated ≥ watch", "important_ge_watch", (s) => `${s.important_ge_watch}/${b.dataset.important}`],
    ["Irrelevant alerts (gold ignore/digest → watch/review)", "false_alerts", (s) => `${s.false_alerts}`],
    ["Namesakes correctly ignored", "namesake_ok", (s) => `${s.namesake_ok}/${b.dataset.namesakes}`],
    ["Action agreement", "action_acc", (s) => pct(s.action_acc)],
    ["Category agreement", "category_acc", (s) => pct(s.category_acc)],
    ["Report-type agreement", "report_type_acc", (s) => pct(s.report_type_acc)],
    ["Identity agreement", "subject_acc", (s) => pct(s.subject_acc)],
    ["Novelty agreement", "novel_acc", (s) => pct(s.novel_acc)],
    ["Median latency / article", "lat", (s) => `${s.latency_ms_median} ms`],
    ["Mean latency / article", "latm", (s) => `${s.latency_ms_mean} ms`],
    ["Input tokens (total)", "tin", (s) => `${s.input_tokens}`],
    ["Output tokens (total; not billed for Drex)", "tout", (s) => `${s.output_tokens}`],
    ["Est. decision-stage cost", "cost", (s) => s.est_cost_usd == null ? "price not set" : `$${s.est_cost_usd.toFixed(5)}`],
    ["Cost basis", "cbasis", (s) => s.cost_source ?? "—"],
    ["Errors / parse failures", "err", (s) => `${s.errors}`],
  ];
  return (
    <section className="card">
      <h2>Decision-stage benchmark</h2>
      <p className="small muted">Run at {b.run_at} · {b.dataset.size} articles ({b.dataset.label}) · same profile, criteria, article text and NDI extraction for every system · {b.repeats ?? 1} run(s).</p>
      <table className="bench"><thead><tr><th>Metric</th>{sys.map((s) => <th key={s.name}>{s.name}<div className="small muted">{s.model}</div></th>)}</tr></thead>
        <tbody>{metrics.map(([label, k, f]) => <tr key={k}><td>{label}</td>{sys.map((s) => <td key={s.name}>{f(s)}</td>)}</tr>)}</tbody></table>
      <h3>Per-article actions</h3>
      <table className="bench small"><thead><tr><th>Article</th><th>Gold</th>{sys.map((s) => <th key={s.name}>{s.name}</th>)}</tr></thead>
        <tbody>{b.per_article.map((r: any) => <tr key={r.id}><td>{r.id} · {r.title}</td><td>{r.gold_action}</td>
          {sys.map((s) => { const v = r.pred[s.name]; return <td key={s.name} className={v === r.gold_action ? "ok" : "bad"}>{v ?? "error"}</td>; })}</tr>)}</tbody></table>
      <h3>Limitations</h3><ul className="small">{(b.limitations || []).map((l: string, i: number) => <li key={i}>{l}</li>)}</ul>
    </section>
  );
}
