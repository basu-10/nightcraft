import { useMemo, useState } from "react";

export default function LeftSidebarTabs({
  chatHistory,
  settings,
  onUpdateSettings,
  profiles,
  policies,
  usage = {},
  workspaceId,
}) {
  const [tab, setTab] = useState("history");

  const capRows = useMemo(() => {
    if (!settings?.tool_caps) return [];
    return Object.entries(settings.tool_caps).map(([tool, cap]) => ({
      tool,
      used: usage[tool] || 0,
      cap,
      percent: cap > 0 ? Math.round(((usage[tool] || 0) / cap) * 100) : 0,
    }));
  }, [settings, usage]);

  return (
    <div className="left-sidebar-tabs">
      <div className="sidebar-tab-bar">
        <button className={`sidebar-tab ${tab === "history" ? "sidebar-tab--active" : ""}`} onClick={() => setTab("history")}>Chat History</button>
        <button className={`sidebar-tab ${tab === "settings" ? "sidebar-tab--active" : ""}`} onClick={() => setTab("settings")}>Workspace Settings</button>
      </div>
      <div className="left-sidebar-tab-content">
        {tab === "history" && chatHistory}
        {tab === "settings" && (
          <div className="workspace-settings-panel">
            {!workspaceId ? (
              <p className="muted">Create a workspace first to configure settings.</p>
            ) : (<>
            <label className="form-label">Provider preset</label>
            <select
              className="form-input"
              value={settings?.profile_id || ""}
              onChange={(e) => onUpdateSettings({ profile_id: e.target.value || null })}
            >
              <option value="">Select preset</option>
              {(profiles || []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>

            <label className="form-label">Tool hard-cap policy</label>
            <select
              className="form-input"
              value={settings?.tool_policy_id || ""}
              onChange={(e) => onUpdateSettings({ tool_policy_id: e.target.value || null })}
            >
              <option value="">Select policy</option>
              {(policies || []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>

            <div className="settings-preview muted">
              Active preset: {(profiles || []).find((p) => p.id === settings?.profile_id)?.name || "None"}
            </div>
            <div className="settings-preview muted">
              Active policy: {(policies || []).find((p) => p.id === settings?.tool_policy_id)?.name || "None"}
            </div>

            <div className="tool-cap-table">
              <h4>Tool usage vs caps</h4>
              {capRows.length === 0 && <p className="muted">No hard caps configured.</p>}
              {capRows.map((row) => (
                <div key={row.tool} className="tool-cap-row">
                  <span>{row.tool}</span>
                  <span>{row.used} / {row.cap}</span>
                  <span className={row.percent >= 100 ? "danger" : row.percent >= 80 ? "warn" : "ok"}>{row.percent}%</span>
                </div>
              ))}
            </div>
            </>)}
          </div>
        )}
      </div>
    </div>
  );
}
