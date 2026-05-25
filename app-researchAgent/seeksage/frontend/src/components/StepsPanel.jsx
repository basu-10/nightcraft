import { useState } from "react";

const TYPE_ICON = {
  thinking: "💭",
  tool_call: "🔧",
  tool_result: "📋",
  answer: "✅",
};

export default function StepsPanel({ events, onClose }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside className={`steps-panel ${collapsed ? "steps-panel--collapsed" : ""}`}>
      <div className="steps-panel-header">
        <span>Steps</span>
        <div className="steps-panel-actions">
          <button
            className="icon-btn"
            onClick={() => setCollapsed((p) => !p)}
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? "«" : "»"}
          </button>
          {onClose && (
            <button className="icon-btn" onClick={onClose} title="Close">
              ×
            </button>
          )}
        </div>
      </div>
      {!collapsed && (
        <ol className="steps-panel-list">
          {(!events || events.length === 0) && (
            <li className="steps-empty">No steps yet.</li>
          )}
          {(events || []).map((ev, i) => (
            <li key={i} className={`step-item step-${ev.type}`}>
              <span className="step-icon">{TYPE_ICON[ev.type] || "•"}</span>
              <div className="step-body">
                <span className="step-label">{ev.label || ev.type}</span>
                {ev.detail && <pre className="step-detail">{ev.detail}</pre>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
