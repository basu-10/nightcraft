import { useMemo, useState } from "react";

function formatTimestamp(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return `${value}`;
  return d.toLocaleString();
}

function formatDuration(value) {
  const ms = Number(value);
  if (!Number.isFinite(ms)) return null;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(ms % 1000 === 0 ? 1 : 2)}s`;
}

function safeClass(value) {
  return String(value || "unknown").replace(/[^a-zA-Z0-9_-]/g, "-");
}

function summarizeEvent(event) {
  const payload = event?.payload_json || event?.payload || {};
  const metadata = payload.metadata || payload.metadata_json || {};
  const eventType = event?.event_type || event?.type || "event";
  const toolName = payload.tool_name || payload.tool || metadata.tool_name || metadata.tool || null;
  const modelName = payload.model || payload.model_name || payload.used_model || payload.usedModel || metadata.model || metadata.model_name || null;
  const node = payload.node || payload.node_type || payload.nodeType || null;
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
  if (modelName) parts.push(`Model: ${modelName}`);
  if (detailText) parts.push(`${detailText}`);

  let stepSuffix = "";
  if (eventType === "step") {
    if (node === "tool_executor" && toolName) {
      stepSuffix = `${node} · ${toolName}`;
    } else if (node === "agent_node" && modelName) {
      stepSuffix = `${node} · ${modelName}`;
    } else if (node) {
      stepSuffix = node;
    } else if (toolName) {
      stepSuffix = toolName;
    } else if (modelName) {
      stepSuffix = modelName;
    }
  }

  return {
    eventType,
    title: toolName ? `${eventType} - ${toolName}` : eventType,
    toolName,
    modelName,
    node,
    nodeClass: `step-node-${safeClass(node || eventType)}`,
    stepSuffix,
    detail: parts.join(" | "),
    payload,
  };
}

function summarizeActivityLog(log) {
  const data = log?.data || {};
  const toolName = data.tool || data.tool_name || null;
  const modelName = data.model || data.model_name || data.used_model || null;
  const title = [log?.event_type, toolName, modelName].filter(Boolean).join(" · ") || log?.event_type || "log";
  return {
    ...log,
    title,
    detail: JSON.stringify(data, null, 2),
    durationLabel: formatDuration(log?.duration_ms),
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
  activityLogs,
  activityLogError,
  activeWorkspace,
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

  const normalizedActivityLogs = useMemo(() => {
    return (activityLogs || []).map((log) => summarizeActivityLog(log));
  }, [activityLogs]);

  const filteredLogs = useMemo(() => {
    const q = logFilter.trim().toLowerCase();
    if (!q) return normalizedActivityLogs;
    return normalizedActivityLogs.filter((log) => JSON.stringify(log).toLowerCase().includes(q));
  }, [normalizedActivityLogs, logFilter]);

  const availableTools = useMemo(() => {
    if (!Array.isArray(activeWorkspace?.tool_ids)) return [];
    return activeWorkspace.tool_ids.filter(Boolean);
  }, [activeWorkspace]);

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
            <div>
              <strong>Available tools:</strong>
              <div className="tool-list">
                {availableTools.length === 0 ? (
                  <span className="muted">All tools enabled for this workspace</span>
                ) : (
                  availableTools.map((tool) => <span key={tool} className="file-tag tool-chip">{tool}</span>)
                )}
              </div>
            </div>
            <div><strong>Step count:</strong> {normalizedEvents.length}</div>
          </div>
        )}

        {tab === "steps" && (
          <div className="stack">
            {normalizedEvents.length === 0 && <p className="muted">No steps for this run yet.</p>}
            {normalizedEvents.map((event, index) => {
              const stepNumber = event.seq ?? index + 1;
              const title = event.eventType === "step" && event.stepSuffix
                ? `#${stepNumber} step · ${event.stepSuffix}`
                : `#${stepNumber} step ${event.title}`;
              return (
                <details key={`${event.id || "event"}-${index}`} className={`step-detail-card ${event.nodeClass || ""}`}>
                  <summary>{title}</summary>
                  <div className="step-meta-row">
                    <span className="muted">{formatTimestamp(event.created_at)}</span>
                    {event.toolName && <span className="file-tag">{event.toolName}</span>}
                    {event.modelName && <span className="file-tag">{event.modelName}</span>}
                    {event.node && <span className="file-tag">{event.node}</span>}
                  </div>
                  {event.detail && <div className="step-detail-text">{event.detail}</div>}
                  <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                </details>
              );
            })}
          </div>
        )}

        {tab === "logs" && (
          <div className="stack">
            <input
              className="form-input"
              placeholder="Filter backend logs by text/type/tool/model"
              value={logFilter}
              onChange={(e) => setLogFilter(e.target.value)}
            />
            <button className="btn btn-secondary" onClick={exportLogs} disabled={filteredLogs.length === 0}>Export Logs</button>
            {activityLogError && <div className="log-error muted">{activityLogError}</div>}
            {filteredLogs.length === 0 && <p className="muted">No backend logs yet for this run.</p>}
            {filteredLogs.map((log) => (
              <div key={log.id || log.ts || log.event_type} className="log-row log-row--backend">
                <div className="step-meta-row">
                  <span className="muted">{formatTimestamp(log.ts || log.created_at)}</span>
                  {log.durationLabel && <span className="file-tag">{log.durationLabel}</span>}
                </div>
                <div className="log-row-title">{log.title}</div>
                <pre className="log-row-detail log-json">{log.detail}</pre>
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
