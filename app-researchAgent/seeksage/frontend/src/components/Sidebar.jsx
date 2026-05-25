import { useState } from "react";
import { useNavigate } from "react-router-dom";

const COLORS = ["#4A90D9", "#7B68EE", "#50C878", "#FF7F50", "#FFD700", "#20B2AA"];

function ProjectNode({ project, workspace, sessions, activeSessionId, onSelect, onDeleteSession, onNewSession }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="sidebar-project">
      <div
        className="sidebar-proj-header"
        onClick={() => setExpanded((p) => !p)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && setExpanded((p) => !p)}
      >
        <span className="proj-icon">[P]</span>
        <span className="proj-name">{project.name}</span>
        <span className="proj-chevron">{expanded ? "▾" : "▸"}</span>
      </div>
      {expanded && (
        <div className="sidebar-proj-body">
          {sessions.map((s) => (
            <SessionItem
              key={s.id}
              session={s}
              active={s.id === activeSessionId}
              onSelect={() => onSelect(workspace, s)}
              onDelete={() => onDeleteSession(s.id)}
            />
          ))}
          <button
            className="sidebar-new-btn"
            onClick={() => onNewSession(project.id)}
          >
            + New Session
          </button>
        </div>
      )}
    </div>
  );
}

function SessionItem({ session, active, onSelect, onDelete }) {
  return (
    <div
      className={`sidebar-session ${active ? "sidebar-session--active" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
    >
      <span className="session-title">{session.title || "Untitled"}</span>
      <button
        className="icon-btn session-del-btn"
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        title="Delete session"
        aria-label="Delete session"
      >
        ×
      </button>
    </div>
  );
}

export default function Sidebar({
  user,
  activeWorkspace,
  sessions,
  projects,
  activeSession,
  onSelectSession,
  onNewProject,
  onNewSession,
  onDeleteSession,
  onLogout,
  isOpen = false,
  onClose,
}) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const displayName = user?.email ? user.email.split("@")[0] : "User";

  const handleLogout = async () => {
    setMenuOpen(false);
    onLogout?.();
  };

  return (
    <aside className={`sidebar${isOpen ? " sidebar--open" : ""}`}>
      {/* Close button — only visible on mobile */}
      {onClose && (
        <button
          className="icon-btn sidebar-close-btn"
          style={{ display: isOpen ? "block" : undefined }}
          onClick={onClose}
          aria-label="Close navigation"
          title="Close"
        >
          ✕
        </button>
      )}
      {/* User info */}
      <div className="sidebar-user">
        <span className="sidebar-user-email" onClick={() => navigate("/account")} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && navigate("/account")} style={{ cursor: "pointer" }}>{displayName}</span>
        <div className="sidebar-user-menu-wrapper">
          <button className="icon-btn sidebar-menu-trigger" onClick={() => setMenuOpen((p) => !p)} title="Menu" aria-label="Menu">
            ⋮
          </button>
          {menuOpen && (
            <>
              <div className="sidebar-menu-backdrop" onClick={() => setMenuOpen(false)} />
              <div className="sidebar-menu-dropdown">
                <button className="sidebar-menu-item" onClick={() => { setMenuOpen(false); navigate("/dashboard"); }}>Dashboard</button>
                <button className="sidebar-menu-item" onClick={() => { setMenuOpen(false); navigate("/global-settings"); }}>Global Settings</button>
                <div className="sidebar-menu-divider" />
                <button className="sidebar-menu-item sidebar-menu-item--danger" onClick={handleLogout}>Logout</button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Projects and sessions for active workspace */}
      <div className="sidebar-workspaces">
        {activeWorkspace && (
          <>
            {(projects || []).map((proj) => (
              <ProjectNode
                key={proj.id}
                project={proj}
                workspace={activeWorkspace}
                sessions={(sessions || []).filter((s) => s.project_id === proj.id)}
                activeSessionId={activeSession?.id}
                onSelect={onSelectSession}
                onDeleteSession={onDeleteSession}
                onNewSession={(projId) => onNewSession(activeWorkspace.id, projId)}
              />
            ))}

            <button
              className="sidebar-new-btn"
              onClick={() => onNewProject?.(activeWorkspace.id)}
            >
              + New Project
            </button>

            {(sessions || []).filter((s) => !s.project_id).map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                active={s.id === activeSession?.id}
                onSelect={() => onSelectSession(activeWorkspace, s)}
                onDelete={() => onDeleteSession(s.id)}
              />
            ))}

            <button
              className="sidebar-new-btn"
              onClick={() => onNewSession(activeWorkspace.id, null)}
            >
              + New Session
            </button>
          </>
        )}
      </div>
    </aside>
  );
}
