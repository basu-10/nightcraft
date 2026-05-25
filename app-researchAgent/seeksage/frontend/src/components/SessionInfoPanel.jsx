import { useMemo, useState } from "react";

function formatTimestamp(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return `${value}`;
  return d.toLocaleString();
}

function summarizeEvent(event) {
  const payload = event?.payload_json || {};
  const eventType = event?.event_type || event?.type || "event";
  const toolName = payload.tool_name || payload.tool || null;
  const node = payload.node || null;
  const detailText =
    payload.agent_message ||
    payload.error ||
    payload.note ||
    payload.message ||
    payload.status ||
    payload.summary ||
    "";

  const parts = [];
  if (toolName) parts.push(`Tool: ${toolName}`);
  if (node) parts.push(`Node: ${node}`);
  if (detailText) parts.push(`${detailText}`);

  return {
    eventType,
    title: toolName ? `${eventType} - ${toolName}` : eventType,
    toolName,
    detail: parts.join(" | "),
    payload,
  };
}

function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function SessionInfoPanel({
  session,
  run,
  events,
  workspaceSettings,
  notes,
  onSaveNote,
  onDeleteNote,
  files,
  onDeleteFile,
}) {
  const [tab, setTab] = useState("info");
  const [logFilter, setLogFilter] = useState("");
  const [noteDraft, setNoteDraft] = useState({ title: "", body: "", tags: "" });

  const normalizedEvents = useMemo(() => {
    return (events || []).map((e) => ({ ...e, ...summarizeEvent(e) }));
  }, [events]);

  const filteredLogs = useMemo(() => {
    const q = logFilter.trim().toLowerCase();
    if (!q) return normalizedEvents;
    return normalizedEvents.filter((e) => JSON.stringify(e).toLowerCase().includes(q));
  }, [normalizedEvents, logFilter]);

  const saveNote = () => {
    if (!session || !noteDraft.title.trim()) return;
    onSaveNote({
      id: crypto.randomUUID(),
      session_id: session.id,
      title: noteDraft.title.trim(),
      body: noteDraft.body.trim(),
      tags: noteDraft.tags.split(",").map((t) => t.trim()).filter(Boolean),
      created_at: new Date().toISOString(),
    });
    setNoteDraft({ title: "", body: "", tags: "" });
  };

  const exportLogs = () => {
    const content = JSON.stringify(filteredLogs, null, 2);
    downloadTextFile(`session-${session?.id || "unknown"}-logs.json`, content);
  };

  return (
    <aside className="session-info-panel">
      <div className="tab-bar right-tabs">
        <button className={`tab-btn ${tab === "info" ? "tab-btn--active" : ""}`} onClick={() => setTab("info")}>Chat Info</button>
        <button className={`tab-btn ${tab === "steps" ? "tab-btn--active" : ""}`} onClick={() => setTab("steps")}>Steps</button>
        <button className={`tab-btn ${tab === "logs" ? "tab-btn--active" : ""}`} onClick={() => setTab("logs")}>Logs</button>
        <button className={`tab-btn ${tab === "notes" ? "tab-btn--active" : ""}`} onClick={() => setTab("notes")}>Notes</button>
        <button className={`tab-btn ${tab === "files" ? "tab-btn--active" : ""}`} onClick={() => setTab("files")}>Files</button>
      </div>

      <div className="session-info-content">
        {tab === "info" && (
          <div className="stack">
            <div><strong>Session:</strong> {session?.title || "No active session"}</div>
            <div><strong>Status:</strong> {run?.status || "idle"}</div>
            <div><strong>Provider preset:</strong> {workspaceSettings?.profile_id || "not set"}</div>
            <div><strong>Tool policy:</strong> {workspaceSettings?.tool_policy_id || "not set"}</div>
            <div><strong>Step count:</strong> {normalizedEvents.length}</div>
          </div>
        )}

        {tab === "steps" && (
          <div className="stack">
            {normalizedEvents.length === 0 && <p className="muted">No steps for this run yet.</p>}
            {normalizedEvents.map((event, index) => (
              <details key={`${event.id || "event"}-${index}`} className="step-detail-card">
                <summary>{`#${event.seq ?? index + 1} ${event.title}`}</summary>
                <div className="step-meta-row">
                  <span className="muted">{formatTimestamp(event.created_at)}</span>
                  {event.toolName && <span className="file-tag">{event.toolName}</span>}
                </div>
                {event.detail && <div className="step-detail-text">{event.detail}</div>}
                <pre>{JSON.stringify(event.payload, null, 2)}</pre>
              </details>
            ))}
          </div>
        )}

        {tab === "logs" && (
          <div className="stack">
            <input
              className="form-input"
              placeholder="Filter logs by text/type/tool"
              value={logFilter}
              onChange={(e) => setLogFilter(e.target.value)}
            />
            <button className="btn btn-secondary" onClick={exportLogs}>Export Logs</button>
            {(filteredLogs || []).map((event, index) => (
              <div key={index} className="log-row">
                <div className="muted">{formatTimestamp(event.created_at || event.ts)}</div>
                <div className="log-row-title">{event.title}</div>
                {event.detail && <div className="log-row-detail">{event.detail}</div>}
              </div>
            ))}
          </div>
        )}

        {tab === "notes" && (
          <div className="stack">
            <input className="form-input" placeholder="Title" value={noteDraft.title} onChange={(e) => setNoteDraft((p) => ({ ...p, title: e.target.value }))} />
            <textarea className="form-input" rows={4} placeholder="Note body" value={noteDraft.body} onChange={(e) => setNoteDraft((p) => ({ ...p, body: e.target.value }))} />
            <input className="form-input" placeholder="tags,comma,separated" value={noteDraft.tags} onChange={(e) => setNoteDraft((p) => ({ ...p, tags: e.target.value }))} />
            <button className="btn btn-primary" onClick={saveNote} disabled={!session}>Save Note</button>
            {(notes || []).map((n) => (
              <div key={n.id} className="note-item">
                <div className="row"><strong>{n.title}</strong><button className="btn btn-sm btn-danger" onClick={() => onDeleteNote(n.id)}>Delete</button></div>
                <p>{n.body}</p>
                <div className="muted">{(n.tags || []).join(", ")}</div>
              </div>
            ))}
          </div>
        )}

        {tab === "files" && (
          <div className="stack">
            {(files || []).length === 0 && <p className="muted">No files uploaded or generated in this session.</p>}
            {(files || []).map((f) => (
              <div key={f.id} className="file-row">
                <span>{f.name}</span>
                <span className="file-tag">{f.kind}</span>
                <span className="muted">{new Date(f.created_at).toLocaleString()}</span>
                <div className="row gap">
                  <a className="link-btn file-download-link" href={f.download_url} target="_blank" rel="noreferrer">Download</a>
                  <button className="btn btn-sm btn-danger" onClick={() => onDeleteFile?.(f.id)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
