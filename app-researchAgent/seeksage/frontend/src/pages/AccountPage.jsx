import { useEffect, useState } from "react";
import { api } from "../api";

export default function AccountPage({ user }) {
  const [name, setName] = useState(user?.email?.split("@")[0] || "");
  const [email, setEmail] = useState(user?.email || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.getDashboardStats().then(setStats).catch(() => setStats(null));
  }, []);

  const changePassword = async () => {
    setError("");
    setMessage("");
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setMessage("Password updated.");
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="settings-page">
      <h2>Account</h2>
      <p className="muted">Profile management, subscription summary, and usage.</p>

      <div className="form-section">
        <label className="form-label">Display name</label>
        <input className="form-input" value={name} onChange={(e) => setName(e.target.value)} />
        <label className="form-label">Email</label>
        <input className="form-input" value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>

      <div className="stats-cards" style={{ marginTop: 16 }}>
        <div className="stat-card"><span className="stat-value">Free</span><span className="stat-label">Plan</span></div>
        <div className="stat-card"><span className="stat-value">{stats?.total_runs ?? "-"}</span><span className="stat-label">Total Runs</span></div>
        <div className="stat-card"><span className="stat-value">{stats?.runs_today ?? "-"}</span><span className="stat-label">Runs Today</span></div>
      </div>

      <div className="form-section" style={{ marginTop: 16 }}>
        <h3>Change Password</h3>
        {message && <p className="success-msg">{message}</p>}
        {error && <p className="error-msg">{error}</p>}
        <label className="form-label">Current password</label>
        <input className="form-input" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
        <label className="form-label">New password</label>
        <input className="form-input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        <button className="btn btn-primary" onClick={changePassword}>Update Password</button>
      </div>
    </div>
  );
}
