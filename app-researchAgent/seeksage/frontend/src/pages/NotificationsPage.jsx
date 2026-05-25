import { useMemo, useState } from "react";
import { useNotifications } from "../hooks/useNotifications";

export default function NotificationsPage() {
  const { notifications, loading, error, markRead, markAllRead, removeNotification } = useNotifications();
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);
  const [typeFilter, setTypeFilter] = useState("all");

  const filtered = useMemo(() => {
    return notifications.filter((n) => {
      if (showUnreadOnly && n.read) return false;
      if (typeFilter !== "all" && n.type !== typeFilter) return false;
      return true;
    });
  }, [notifications, showUnreadOnly, typeFilter]);

  return (
    <div className="settings-page">
      <h2>Notifications</h2>
      <p className="muted">System alerts and tool-cap warnings.</p>
      {error && <p className="error-msg">{error}</p>}
      <div className="row gap">
        <label className="checkbox-label">
          <input type="checkbox" checked={showUnreadOnly} onChange={(e) => setShowUnreadOnly(e.target.checked)} />
          Unread only
        </label>
        <select className="form-input" style={{ maxWidth: 180 }} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="all">All types</option>
          <option value="system">System</option>
          <option value="usage">Usage</option>
          <option value="warning">Warning</option>
        </select>
        <button className="btn btn-secondary" onClick={markAllRead}>Mark all read</button>
      </div>

      <div className="stack" style={{ marginTop: 12 }}>
        {loading && <p className="muted">Loading notifications…</p>}
        {filtered.length === 0 && <p className="muted">No notifications for this filter.</p>}
        {filtered.map((n) => (
          <div key={n.id} className={`notification-item ${n.read ? "" : "notification-item--unread"}`}>
            <div className="row">
              <strong>{n.title}</strong>
              <span className="muted">{new Date(n.created_at).toLocaleString()}</span>
            </div>
            <div>{n.message}</div>
            <div className="row gap">
              {!n.read && <button className="btn btn-sm" onClick={() => markRead(n.id)}>Mark read</button>}
              <button className="btn btn-sm btn-danger" onClick={() => removeNotification(n.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
