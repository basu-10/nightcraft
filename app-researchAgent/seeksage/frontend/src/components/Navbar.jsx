import { NavLink, useNavigate } from "react-router-dom";

export default function Navbar({ user, unreadCount = 0 }) {
  const navigate = useNavigate();

  return (
    <header className="global-navbar">
      <div className="navbar-brand" onClick={() => navigate("/")} role="button" tabIndex={0}>
        SeekSage Web
      </div>
      <div className="navbar-right">
        <NavLink to="/notes" className="nav-link nav-icon-link" title="Notes" aria-label="Notes">
          <span className="nav-icon" aria-hidden="true">📝</span>
        </NavLink>
        <NavLink to="/notifications" className="nav-link nav-icon-link" title="Notifications" aria-label="Notifications">
          <span className="nav-icon" aria-hidden="true">🔔</span>
          {unreadCount > 0 && <span className="nav-badge">{unreadCount}</span>}
        </NavLink>
      </div>
    </header>
  );
}
