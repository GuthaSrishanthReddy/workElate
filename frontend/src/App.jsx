import { useEffect, useRef, useState } from 'react'
import { ArrowDownToLine, ArrowUp, Check, ChevronDown, ChevronRight, CircleAlert, Clock3, Copy, ExternalLink, Globe2, LoaderCircle, MessageSquareText, PanelLeft, Plus, ShieldCheck, Sparkles, Square, Terminal } from 'lucide-react'
import './execution.css'

const starter = 'Crawl https://quotes.toscrape.com, extract the key details, and summarize what this site offers.'

function App() {
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [activeJob, setActiveJob] = useState(null)
  const [copied, setCopied] = useState(false)
  const bottomRef = useRef(null)
  const requestRef = useRef(null)

  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }), [messages])

  async function submit(value = draft) {
    const message = value.trim()
    if (!message || busy) return
    const userMessage = { id: crypto.randomUUID(), role: 'user', text: message }
    const assistantMessage = { id: crypto.randomUUID(), role: 'assistant', events: [], loading: true }
    setMessages(prev => [...prev, userMessage, assistantMessage])
    setDraft(''); setBusy(true)
    const controller = new AbortController()
    requestRef.current = controller
    try {
      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify({ message }), signal: controller.signal })
      if (!response.ok) {
        const error = await response.json().catch(() => ({}))
        throw new Error(error.detail || 'The request could not be started.')
      }
      if (!response.body) throw new Error('This browser could not open the live crawl stream.')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const handleFrame = frame => {
        const line = frame.split('\n').find(value => value.startsWith('data: '))
        if (!line) return
        const parsed = JSON.parse(line.slice(6))
        if (parsed.event === 'task') setActiveJob(parsed.job_id)
        if (parsed.event === 'reply') {
          setMessages(prev => prev.map(item => item.id === assistantMessage.id ? { ...item, text: parsed.text, planner: parsed.planner, loading: false } : item))
          return
        }
        if (parsed.event === 'planning' || parsed.event === 'complete') return
        setMessages(prev => prev.map(item => item.id === assistantMessage.id ? {
          ...item, loading: parsed.event === 'result' ? false : item.loading,
          result: parsed.event === 'result' ? parsed.result : item.result,
          events: [...item.events, parsed],
        } : item))
      }
      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replaceAll('\r\n', '\n')
        const frames = buffer.split('\n\n')
        buffer = frames.pop() || ''
        frames.forEach(handleFrame)
        if (done) break
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        setMessages(prev => prev.map(item => item.id === assistantMessage.id ? { ...item, text: error.message, loading: false, error: true } : item))
      }
    } finally {
      requestRef.current = null
      setBusy(false)
      setActiveJob(null)
    }
  }

  async function cancel() {
    if (!activeJob) { requestRef.current?.abort(); return }
    try {
      const response = await fetch(`/api/jobs/${activeJob}/cancel`, { method: 'POST' })
      if (!response.ok) throw new Error('Cancel could not reach the running crawl. Check the Upstash settings.')
    } catch (error) {
      setMessages(prev => prev.map(item => item.role === 'assistant' && item.loading ? { ...item, text: error.message, error: true } : item))
    }
  }

  function copyJSON(result) {
    navigator.clipboard.writeText(JSON.stringify(result, null, 2)).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })
  }

  function downloadJSON(result) {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'sitecrawl-result.json'; a.click(); URL.revokeObjectURL(a.href)
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand-lockup"><div className="brand-mark"><Globe2 size={18}/></div><span>fieldnotes<span className="brand-dot">.</span></span><button className="icon-button sidebar-toggle" title="Collapse sidebar"><PanelLeft size={16}/></button></div>
      <button className="new-chat" onClick={() => { cancel(); setMessages([]); setBusy(false); setActiveJob(null) }}><Plus size={16}/> New research</button>
      <div className="sidebar-section-label">WORKSPACE</div>
      <div className="workspace-card"><div className="workspace-icon"><Sparkles size={15}/></div><div><strong>BuildSprint</strong><span>Round 2 · Site research</span></div><ChevronDown size={15} className="workspace-chevron"/></div>
      <div className="sidebar-section-label recent-label">RECENT</div>
      <button className="recent-item active"><MessageSquareText size={15}/><span>Website research</span></button>
      <div className="sidebar-bottom"><div className="security-note"><ShieldCheck size={15}/><span>Requests stay on the<br/>same website host</span></div><div className="profile"><div className="avatar">B</div><div><b>BuildSprint</b><small>Local workspace</small></div><ChevronDown size={14}/></div></div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="breadcrumb"><span>Workspace</span><ChevronRight size={14}/><strong>Website research</strong></div><div className="top-actions"><span className="local-pill"><i/> Local run</span><button className="icon-button" title="Workspace options"><span className="more-dots">···</span></button><div className="avatar top-avatar">B</div></div></header>
      <div className="conversation">
      {messages.length === 0 ? <section className="welcome">
          <div className="welcome-icon"><Globe2 size={21}/><span className="welcome-spark">✳</span></div>
          <div className="eyebrow"><span className="eyebrow-line"/> SITE RESEARCH <span className="eyebrow-line"/></div>
          <h1>Make sense of any<br/><em>website.</em></h1>
          <p className="welcome-copy">I’ll visit the pages, gather the details, and show you exactly what I found.</p>
          <div className="starter-card"><div className="starter-top"><span className="starter-label">TRY A LIVE CRAWL</span><span className="live-dot"><i/> LIVE</span></div><p>“Crawl quotes.toscrape.com and summarize what this site offers.”</p><button onClick={() => submit(starter)}>Try this request <ArrowUp size={14}/></button></div>
          <div className="welcome-foot"><ShieldCheck size={14}/> Real pages, real results. No canned output.</div>
        </section> : <div className="message-list">
          {messages.map(message => message.role === 'user' ? <div className="user-row" key={message.id}><div className="user-bubble">{message.text}</div><div className="avatar user-avatar">Y</div></div> : <div className="assistant-row" key={message.id}>
            <div className="assistant-mark"><Globe2 size={15}/></div><div className="assistant-content">
              {message.text && <div className={`reply-text ${message.error ? 'reply-error' : ''}`}>{message.text}</div>}
              {message.loading && <div className="working-label"><LoaderCircle size={15} className="spin"/> Getting things ready…</div>}
              {message.events?.length > 0 && <Timeline events={message.events} loading={message.loading} />}
              {message.result && <ResultCard result={message.result} events={message.events} onCopy={() => copyJSON(message.result)} onDownload={() => downloadJSON(message.result)} copied={copied}/>}
              {!message.result && message.events?.some(event => event.event === 'execution_complete') && <ExecutionNotice events={message.events}/>}
            </div></div>)}
          <div ref={bottomRef}/>
        </div>}
      </div>
      <div className="composer-wrap"><form className="composer" onSubmit={e => { e.preventDefault(); submit() }}><textarea value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }} placeholder="Ask me to crawl a website…" rows={1} disabled={busy}/>{busy ? <button type="button" className="send-button stop-button" onClick={cancel} title="Cancel crawl"><Square size={14} fill="currentColor"/></button> : <button className="send-button" disabled={!draft.trim()} title="Send request"><ArrowUp size={17}/></button>}</form><div className="composer-hint"><span><kbd>↵</kbd> to send <span className="hint-divider">·</span> <kbd>shift ↵</kbd> for new line</span><span className="hint-right"><ShieldCheck size={13}/> Public pages only</span></div></div>
      <footer className="main-footer"><span>FIELDNOTES <i>·</i> BUILT FOR BUILDSPRINT</span><span>Every crawl is a real run of <code>sitecrawl</code></span></footer>
    </main>
  </div>
}

function ExecutionNotice({ events }) {
  const execution = events.find(event => event.event === 'execution_complete') || {}
  const failure = events.find(event => event.event === 'error')
  return <div className="execution-notice"><div><CircleAlert size={15}/><strong>Crawl {execution.exit_code === 3 ? 'blocked' : 'failed'}</strong><span>Exit {execution.exit_code ?? '—'} · {((execution.duration_ms || 0)/1000).toFixed(1)}s</span></div>
    {failure?.message && <p>{failure.message}</p>}{execution.stderr_tail?.length > 0 && <pre>{execution.stderr_tail.join('\n')}</pre>}
    <details><summary><Terminal size={13}/> Execution details</summary><code>{(execution.argv || []).join(' ')}</code></details></div>
}

function Timeline({ events, loading }) {
  const pages = events.filter(e => ['page','skip','error'].includes(e.event))
  const phase = events.some(e => e.event === 'execution_complete') ? 'Complete' : events.some(e => e.event === 'process_started') ? 'Crawling pages' : 'Preparing crawl'
  return <div className="timeline-card"><div className="timeline-head"><div className="timeline-title"><span className={`timeline-pulse ${loading ? 'is-live' : ''}`}>{loading ? <LoaderCircle size={14} className="spin"/> : <Check size={13}/>}</span><strong>{phase}</strong></div><span className="timeline-count">{pages.filter(p => p.event === 'page').length} pages fetched</span></div>
    {pages.length > 0 ? <div className="event-list">{pages.map((event, i) => <div className="event-row" key={`${event.url}-${i}`}><span className={`event-icon ${event.event}`}>{event.event === 'page' ? <Check size={12}/> : event.event === 'skip' ? <ShieldCheck size={12}/> : <CircleAlert size={12}/>}</span><span className="event-label">{event.event === 'page' ? event.title || new URL(event.url).pathname || 'Home page' : event.event === 'skip' ? `Skipped · ${event.reason}` : `Could not fetch · ${event.type}`}</span><span className="event-url">{event.url ? new URL(event.url).pathname || '/' : ''}</span></div>)}</div> : <div className="timeline-empty">{events.some(e => e.event === 'robots') ? 'Checking robots.txt and the start page…' : 'Starting the sitecrawl process…'}</div>}
  </div>
}

function ResultCard({ result, events, onCopy, onDownload, copied }) {
  const [open, setOpen] = useState(false)
  const execution = events.find(e => e.event === 'execution_complete') || {}
  const pages = result.extracted?.pages || []
  const badge = result.status || 'failed'
  return <div className="result-card">
    <div className="result-head"><div><div className="result-kicker"><Sparkles size={13}/> SITE REPORT</div><h2>{result.extracted?.site_title || result.source?.domain || 'Crawl results'}</h2><a href={result.source?.start_url} target="_blank" rel="noreferrer" className="source-url">{result.source?.domain}<ExternalLink size={12}/></a></div><span className={`status-badge ${badge}`}><i/>{badge}</span></div>
    {badge === 'partial' && <div className="run-note partial-note">{execution.killed === 'cancelled' ? 'Cancelled' : execution.killed === 'timeout' ? 'Stopped at the time limit' : 'Crawl was partial'} after {result.execution?.pages_ok ?? pages.length} page{(result.execution?.pages_ok ?? pages.length) === 1 ? '' : 's'}.</div>}
    {badge === 'failed' && <div className="run-note failed-note">{failureReason(result.execution?.exit_code)}{result.errors?.[0]?.message ? ` ${result.errors[0].message}` : ''}</div>}
    {result.summary && <div className="summary-block"><div className="section-label">OVERVIEW <span>{result.summary.generated_by === 'llm' ? 'AI summary' : 'Extractive summary'}</span></div><p>{result.summary.text}</p></div>}
    {result.summary?.key_points?.length > 0 && <div className="key-points"><div className="section-label">KEY FINDINGS</div>{result.summary.key_points.map((point,i)=><div className="key-point" key={i}><span className="point-mark">↗</span><div>{point.point}<a href={point.source_url} target="_blank" rel="noreferrer">{new URL(point.source_url).pathname || '/'} <ExternalLink size={10}/></a></div></div>)}</div>}
    <div className="result-stats"><div><span>PAGES FETCHED</span><b>{result.execution?.pages_ok ?? pages.length}</b></div><div><span>EXIT CODE</span><b className={execution.exit_code === 0 ? 'code-ok' : 'code-other'}>{execution.exit_code ?? result.execution?.exit_code}</b></div><div><span>DURATION</span><b><Clock3 size={13}/>{((execution.duration_ms ?? result.execution?.duration_ms ?? 0)/1000).toFixed(1)}s</b></div></div>
    {result.extracted?.contacts && (result.extracted.contacts.emails?.length || result.extracted.contacts.phones?.length) ? <div className="contacts-block"><div className="section-label">CONTACT DETAILS</div><div className="contact-chips">{result.extracted.contacts.emails.map(email=><a key={email} href={`mailto:${email}`} className="contact-chip">{email}</a>)}{result.extracted.contacts.phones.map(phone=><span className="contact-chip" key={phone}>{phone}</span>)}</div></div> : null}
    <details className="execution-drawer" open={open} onToggle={e => setOpen(e.currentTarget.open)}><summary><Terminal size={14}/> Execution details <ChevronDown size={14}/></summary><div className="drawer-body"><div className="drawer-row"><span>Command</span><code>{(execution.argv || []).join(' ') || '—'}</code></div><div className="drawer-row"><span>Exit status</span><code>{execution.exit_code ?? result.execution?.exit_code ?? '—'}</code></div>{execution.killed && <div className="drawer-row"><span>Stopped</span><code>{execution.killed}</code></div>}{execution.stderr_tail?.length > 0 && <div className="stderr"><span>STDERR</span><pre>{execution.stderr_tail.join('\n')}</pre></div>}</div></details>
    <div className="result-actions"><button onClick={onCopy}><Copy size={13}/>{copied ? 'Copied' : 'Copy JSON'}</button><button onClick={onDownload}><ArrowDownToLine size={14}/>Download</button><span>{result.errors?.length ? `${result.errors.length} page issue${result.errors.length > 1 ? 's' : ''}` : `${pages.length} page${pages.length === 1 ? '' : 's'} in report`}</span></div>
    <details className="json-details"><summary>View structured result <ChevronDown size={13}/></summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
  </div>
}

function failureReason(code) {
  return ({1:'Crawler internal error.',2:'Crawler arguments were invalid.',3:'URL policy or robots.txt blocked the crawl.',4:'The start site could not be reached.',5:'The start URL had no usable HTML text.'})[code] || `Crawl failed with exit code ${code ?? 'unknown'}.`
}

export default App
