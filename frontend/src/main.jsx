import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const label = { pending: 'Queued', processing: 'Analyzing', completed: 'Ready', inconclusive: 'Needs review', error: 'Analysis failed', not_required: 'Not required' };
const date = value => value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';
const seconds = value => value == null ? '—' : value < 60 ? `${Math.round(value)}s` : `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;

function Mark() {
  return <svg className="mark" viewBox="0 0 40 40" aria-hidden="true"><path d="M3 21h9l4-11 7 22 5-11h9"/></svg>;
}
function Badge({ value, analysis = false }) {
  return <span className={`badge ${value || 'unknown'}`}><span className="dot"/>{analysis ? label[value] || value : (value || 'unknown').replaceAll('_', ' ')}</span>;
}
function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('cloudpulse-token') || '');
  const [draftToken, setDraftToken] = useState('');
  const [authorized, setAuthorized] = useState(false);
  const [config, setConfig] = useState(null);
  const [runs, setRuns] = useState([]);
  const [stats, setStats] = useState({ total: 0, successful: 0, failed: 0, processing: 0 });
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(() => Number(location.hash.match(/^#run\/(\d+)$/)?.[1]) || null);
  const [detail, setDetail] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [importRepo, setImportRepo] = useState('');
  const [importID, setImportID] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const requestVersion = useRef(0);

  const api = useCallback(async (path, options = {}) => {
    const response = await fetch(path, { ...options, headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json', ...(options.headers || {}) } });
    let body;
    try { body = await response.json(); } catch { throw new Error('The server returned an unreadable response. Check that the backend is running.'); }
    if (response.status === 401) { setAuthorized(false); sessionStorage.removeItem('cloudpulse-token'); throw new Error('The dashboard token was rejected. Enter the token from your server configuration.'); }
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}).`);
    return body;
  }, [token]);

  useEffect(() => {
    let active = true;
    if (!token) { setLoading(false); return; }
    setLoading(true);
    api('/api/config').then(data => {
      if (!active) return;
      setConfig(data); setImportRepo(data.repositories[0] || ''); setAuthorized(true);
      sessionStorage.setItem('cloudpulse-token', token); setError('');
    }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, token]);

  const refresh = useCallback(async () => {
    const version = ++requestVersion.current;
    try {
      const query = new URLSearchParams({ limit: '25', offset: String(offset) });
      if (filter) query.set('conclusion', filter);
      const [list, counts, item] = await Promise.all([
        api(`/api/runs?${query}`), api('/api/stats'), selected ? api(`/api/runs/${selected}`) : Promise.resolve(null),
      ]);
      if (version !== requestVersion.current) return;
      setRuns(list.items); setTotal(list.total); setStats(counts); setDetail(item); setError('');
    } catch (e) { if (version === requestVersion.current) setError(e.message); }
    finally { if (version === requestVersion.current) setLoading(false); }
  }, [api, offset, filter, selected]);

  useEffect(() => {
    if (!authorized) return;
    setLoading(true); refresh();
    const timer = setInterval(() => { if (!document.hidden) refresh(); }, 5000);
    return () => { clearInterval(timer); requestVersion.current++; };
  }, [authorized, refresh]);
  useEffect(() => {
    const changed = () => { setDetail(null); setSelected(Number(location.hash.match(/^#run\/(\d+)$/)?.[1]) || null); };
    const escape = event => { if (event.key === 'Escape') location.hash = ''; };
    window.addEventListener('hashchange', changed);
    window.addEventListener('keydown', escape);
    return () => { window.removeEventListener('hashchange', changed); window.removeEventListener('keydown', escape); };
  }, []);

  function login(event) {
    event.preventDefault();
    if (draftToken.trim() === token) {
      setToken(''); setTimeout(() => setToken(draftToken.trim()), 0);
    } else setToken(draftToken.trim());
  }
  function logout() { sessionStorage.removeItem('cloudpulse-token'); setToken(''); setAuthorized(false); setDraftToken(''); setError(''); }
  async function importRun(event) {
    event.preventDefault(); setBusy(true); setNotice('');
    try {
      const match = importID.trim().match(/\/actions\/runs\/(\d+)/);
      const runID = Number(match ? match[1] : importID.trim());
      if (!Number.isSafeInteger(runID) || runID <= 0) throw new Error('Enter a workflow run ID or its GitHub run URL.');
      const result = await api('/api/import', { method: 'POST', body: JSON.stringify({ repository: importRepo, run_id: runID }) });
      setShowImport(false); setImportID(''); setOffset(0); location.hash = `run/${result.id}`;
      setNotice(result.status === 'already_exists' ? 'This attempt is already recorded.' : 'Run imported and queued.');
      await refresh();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function retry() {
    setBusy(true);
    try { await api(`/api/runs/${selected}/retry`, { method: 'POST' }); await refresh(); setNotice('Analysis queued again. This may use Gemini quota.'); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  if (!authorized) return <main className="login-shell"><section className="login-card">
    <div className="brand"><Mark/><span>CloudPulse</span></div>
    <p className="eyebrow">WORKFLOW INTELLIGENCE</p><h1>Know what broke.<br/>See the evidence.</h1>
    <p className="muted">Sign in to your team's build dashboard with the access token configured on your server.</p>
    <form onSubmit={login}><label htmlFor="token">Dashboard access token</label><input id="token" type="password" autoComplete="current-password" value={draftToken} onChange={e => setDraftToken(e.target.value)} required/><button className="primary" disabled={loading}>{loading ? 'Connecting…' : 'Open dashboard →'}</button></form>
    {error && <p className="alert" role="alert">{error}</p>}
    <p className="fine">The token stays in this browser tab. Your Gemini and GitHub keys belong on the server.</p>
  </section></main>;

  return <div className="shell">
    <aside className="sidebar"><div className="brand"><Mark/><span>CloudPulse</span></div>
      <p className="nav-label">WORKSPACE</p><div className="nav-active">◉ &nbsp; Workflow runs</div>
      <div className="sidebar-section"><p className="nav-label">MONITORED REPOSITORIES</p>{config.repositories.map(repo => <a key={repo} href={`https://github.com/${repo}`} target="_blank" rel="noreferrer">{repo} ↗</a>)}</div>
      <div className="sidebar-bottom"><span className="small-label">ANALYSIS MODEL</span><p>{config.model}</p><span className="fine">Part 1 · Completed workflows</span><button className="ghost" onClick={logout}>Lock dashboard</button></div>
    </aside>
    <main className="main"><header className="topbar"><span>Workspace <span className="slash">/</span> Overview</span><span className="live"><span className="dot"/> Refreshes every 5s</span></header>
      <section className="page-heading"><div><p className="eyebrow">GITHUB ACTIONS OBSERVABILITY</p><h1>Workflow runs</h1><p className="muted">Build outcomes, probable causes, and the log lines behind them.</p></div><button className="primary" onClick={() => setShowImport(!showImport)}>+ Import a run</button></section>
      {(!config.gemini_configured || !config.github_configured) && <p className="alert warning">{!config.gemini_configured ? 'Gemini API key is missing. ' : ''}{!config.github_configured ? 'GitHub token is missing. Log downloads may fail. ' : ''}Update the server configuration, restart, and retry affected analyses.</p>}
      {error && <div className="alert" role="alert">{error}<button className="text-button" onClick={refresh}>Try refresh</button></div>}
      {notice && <div className="notice" role="status">{notice}<button aria-label="Dismiss notification" className="text-button" onClick={() => setNotice('')}>×</button></div>}
      {showImport && <form className="import-form panel" onSubmit={importRun}><div><label htmlFor="repo">Repository</label><select id="repo" value={importRepo} onChange={e => setImportRepo(e.target.value)}>{config.repositories.map(repo => <option key={repo}>{repo}</option>)}</select></div><div><label htmlFor="run-id">Completed run URL or ID</label><input id="run-id" value={importID} onChange={e => setImportID(e.target.value)} placeholder="https://github.com/…/actions/runs/12345" required/></div><button className="primary" disabled={busy}>{busy ? 'Importing…' : 'Import'}</button></form>}
      <section className="stats" aria-label="Build statistics">{[['Total attempts', stats.total, 'Recorded in this workspace'], ['Successful', stats.successful, 'Passed on GitHub'], ['Failed', stats.failed, 'Failures and timeouts'], ['In progress', stats.processing, 'Queued or analyzing']].map(([title, value, caption], i) => <article key={title} className={`stat stat-${i}`}><span>{title}</span><strong>{value}</strong><small>{caption}</small></article>)}</section>
      <section className="panel runs-panel"><div className="panel-heading"><h2>Recent activity <span className="count">{total}</span></h2><select aria-label="Filter by build conclusion" value={filter} onChange={e => { setFilter(e.target.value); setOffset(0); }}><option value="">All outcomes</option><option value="success">Success</option><option value="failure">Failure</option><option value="timed_out">Timed out</option><option value="cancelled">Cancelled</option></select></div>
        {loading && !runs.length ? <div className="empty">Loading workflows…</div> : runs.length ? <div className="table-wrap"><table><thead><tr><th>Workflow / repository</th><th>Branch / commit</th><th>Outcome</th><th>Analysis</th><th>Started</th><th>Duration</th></tr></thead><tbody>{runs.map(run => <tr key={run.id} className={selected === run.id ? 'selected-row' : ''}><td><a className="run-link" href={`#run/${run.id}`}>{run.workflow_name} <span>#{run.run_number || run.run_id}</span></a><small>{run.repository} · attempt {run.run_attempt}</small></td><td><span className="branch">{run.branch || '—'}</span><small className="mono">{run.commit_sha.slice(0, 7)}</small></td><td><Badge value={run.conclusion}/></td><td><Badge value={run.state} analysis/></td><td className="date-cell">{date(run.created_at)}</td><td className="mono">{seconds(run.duration_seconds)}</td></tr>)}</tbody></table></div> : <div className="empty"><div className="empty-symbol">⌁</div><h3>{filter ? 'No matching runs yet' : 'Your first workflow starts here'}</h3><p>{filter ? 'Choose a different outcome or run another workflow.' : 'Connect the GitHub webhook, then push to your test repository. Completed runs will appear here automatically.'}</p><button className="ghost" onClick={() => setShowImport(true)}>Or import an existing run</button></div>}
        <footer className="table-footer"><span>Showing {runs.length ? offset + 1 : 0}–{offset + runs.length} of {total}</span><div><button className="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>← Previous</button><button className="ghost" disabled={offset + 25 >= total} onClick={() => setOffset(offset + 25)}>Next →</button></div></footer>
      </section><p className="page-footnote">Explanations are generated after a workflow completes. Review suggested fixes before changing code.</p>
    </main>
    {selected && <div className="detail-backdrop" onClick={() => { location.hash = ''; }}><aside className="detail" role="dialog" aria-modal="true" aria-label="Workflow details" onClick={e => e.stopPropagation()}><header className="detail-header"><span className="eyebrow">WORKFLOW DETAILS</span><button className="close" aria-label="Close workflow details" onClick={() => { location.hash = ''; }}>×</button></header>
      {!detail ? <div className="empty">Loading run details…</div> : <>
        <h2>{detail.workflow_name} <span className="muted">#{detail.run_number || detail.run_id}</span></h2><div className="detail-badges"><Badge value={detail.conclusion}/><Badge value={detail.state} analysis/></div>
        <dl className="metadata"><dt>Repository</dt><dd>{detail.repository}</dd><dt>Branch</dt><dd>{detail.branch || '—'}</dd><dt>Commit</dt><dd className="mono">{detail.commit_sha.slice(0, 12)}</dd><dt>Attempt</dt><dd>{detail.run_attempt}</dd><dt>Started</dt><dd>{date(detail.created_at)}</dd><dt>Duration</dt><dd>{seconds(detail.duration_seconds)}</dd></dl>
        <a className="github-link" href={detail.github_url} target="_blank" rel="noreferrer">Open workflow on GitHub ↗</a>
        {detail.error && <p className="alert" role="alert">{detail.error}{detail.state === 'pending' && <span> Automatic retry is scheduled.</span>}</p>}
        {['pending','processing'].includes(detail.state) && <div className="analysis-wait"><span className="pulse"/>{detail.state === 'pending' ? 'Waiting for analysis…' : 'Retrieving logs and preparing an explanation…'}<small>Processing attempt {detail.attempts} · This panel updates automatically.</small></div>}
        {detail.state === 'not_required' && <section className="analysis-section"><h3>Analysis not required</h3><p>This workflow concluded with “{detail.conclusion}”. Gemini is only called for failures and timeouts with available logs.</p></section>}
        {detail.analysis && <><section className="analysis-section"><span className="category">{detail.analysis.category}</span><h3>Probable root cause</h3><p>{detail.analysis.root_cause}</p><span className="uncertainty">Uncertainty: {detail.analysis.uncertainty}</span></section>
          <section className="analysis-section"><h3>Supporting evidence</h3>{detail.analysis.evidence?.length ? detail.analysis.evidence.map(line => <div className="evidence" key={line.id}><span>{line.job_name} · line {line.line}</span><pre>{line.text}</pre></div>) : <p className="muted">No supporting lines were established.</p>}<p className="fine">{detail.analysis.evidence_check}</p></section>
          <section className="analysis-section"><h3>Suggested next step</h3><p className="suggestion">{detail.analysis.suggested_fix}</p></section></>}
        {detail.jobs?.length > 0 && <section className="analysis-section"><h3>Jobs</h3>{detail.jobs.map(job => <div className="job" key={job.id}><div><strong>{job.name}</strong><Badge value={job.conclusion}/></div>{job.failed_steps.length > 0 && <p>Failed steps: {job.failed_steps.join(', ')}</p>}</div>)}</section>}
        {detail.log_note && <p className="alert warning">{detail.log_note}</p>}
        {detail.excerpt?.length > 0 && <details className="excerpt"><summary>View excerpt sent for analysis ({detail.excerpt.length} lines)</summary><pre>{detail.excerpt.map(line => `[${line.id}] ${line.text}`).join('\n')}</pre></details>}
        <footer className="detail-footer">{detail.model && <p className="fine">Model: {detail.model}{detail.usage?.totalTokenCount ? ` · ${detail.usage.totalTokenCount.toLocaleString()} tokens` : ''}</p>}{['error','inconclusive','completed'].includes(detail.state) && <button className="ghost" onClick={retry} disabled={busy}>{busy ? 'Queuing…' : 'Analyze again'}</button>}</footer>
      </>}
    </aside></div>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
