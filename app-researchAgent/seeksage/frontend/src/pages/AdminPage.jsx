import { useState, useEffect, useCallback } from "react";
import { api } from "../api";
import ModalDialog from "../components/ModalDialog";
import Spinner from "../components/Spinner";

function StatsCards({ stats }) {
  if (!stats) return null;
  return (
    <div className="stats-cards">
      <div className="stat-card">
        <span className="stat-value">{stats.total_users}</span>
        <span className="stat-label">Total Users</span>
      </div>
      <div className="stat-card">
        <span className="stat-value">{stats.active_users}</span>
        <span className="stat-label">Active Users</span>
      </div>
      <div className="stat-card">
        <span className="stat-value">{stats.total_workspaces}</span>
        <span className="stat-label">Workspaces</span>
      </div>
      <div className="stat-card">
        <span className="stat-value">{stats.total_sessions}</span>
        <span className="stat-label">Sessions</span>
      </div>
      <div className="stat-card">
        <span className="stat-value">{stats.total_runs}</span>
        <span className="stat-label">Total Runs</span>
      </div>
    </div>
  );
}

export default function AdminPage() {
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ email: "", password: "", is_admin: false });
  const [createError, setCreateError] = useState("");

  const [showReset, setShowReset] = useState(null); // userId
  const [newPw, setNewPw] = useState("");
  const [resetError, setResetError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [userRows, statsData] = await Promise.all([
        api.adminListUsers(),
        api.adminGetStats(),
      ]);
      setUsers(userRows);
      setStats(statsData);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggleAdmin = async (u) => {
    try {
      await api.adminUpdateUser(u.id, { is_admin: !u.is_admin });
      load();
    } catch (e) { setError(e.message); }
  };

  const handleToggleActive = async (u) => {
    try {
      await api.adminUpdateUser(u.id, { active: !u.active });
      load();
    } catch (e) { setError(e.message); }
  };

  const handleDelete = async (u) => {
    if (!confirm(`Delete user ${u.email}? This cannot be undone.`)) return;
    try {
      await api.adminDeleteUser(u.id);
      load();
    } catch (e) { setError(e.message); }
  };

  const handleCreate = async () => {
    setCreateError("");
    try {
      await api.adminCreateUser(createForm);
      setShowCreate(false);
      load();
    } catch (e) { setCreateError(e.message); }
  };

  const handleReset = async () => {
    setResetError("");
    if (newPw.length < 8) { setResetError("Password must be at least 8 characters"); return; }
    try {
      await api.adminResetPassword(showReset, newPw);
      setShowReset(null);
      setNewPw("");
    } catch (e) { setResetError(e.message); }
  };

  return (
    <div className="admin-page">
      <h2>Admin</h2>
      {error && <p className="error-msg">{error}</p>}
      <StatsCards stats={stats} />

      <div className="admin-section">
        <div className="admin-section-header">
          <h3>Users</h3>
          <button className="btn btn-primary" onClick={() => { setCreateForm({ email: "", password: "", is_admin: false }); setShowCreate(true); }}>
            + Create User
          </button>
        </div>
        {loading ? <Spinner /> : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Admin</th>
                <th>Active</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.is_admin ? "✅" : "—"}</td>
                  <td>{u.active ? "✅" : "❌"}</td>
                  <td>{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="table-actions">
                    <button className="btn btn-sm" onClick={() => handleToggleAdmin(u)}>
                      {u.is_admin ? "Revoke admin" : "Make admin"}
                    </button>
                    <button className="btn btn-sm" onClick={() => handleToggleActive(u)}>
                      {u.active ? "Deactivate" : "Activate"}
                    </button>
                    <button className="btn btn-sm" onClick={() => { setNewPw(""); setResetError(""); setShowReset(u.id); }}>
                      Reset pw
                    </button>
                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(u)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && (
        <ModalDialog
          title="Create User"
          onClose={() => setShowCreate(false)}
          footer={
            <>
              <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate}>Create</button>
            </>
          }
        >
          {createError && <p className="error-msg">{createError}</p>}
          <label className="form-label">Email</label>
          <input className="form-input" type="email" value={createForm.email}
            onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })} />
          <label className="form-label">Password</label>
          <input className="form-input" type="password" value={createForm.password}
            onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} />
          <label className="form-label checkbox-label">
            <input type="checkbox" checked={createForm.is_admin}
              onChange={(e) => setCreateForm({ ...createForm, is_admin: e.target.checked })} />
            {" "}Admin
          </label>
        </ModalDialog>
      )}

      {showReset && (
        <ModalDialog
          title="Reset Password"
          onClose={() => setShowReset(null)}
          footer={
            <>
              <button className="btn btn-secondary" onClick={() => setShowReset(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleReset}>Reset</button>
            </>
          }
        >
          {resetError && <p className="error-msg">{resetError}</p>}
          <label className="form-label">New password</label>
          <input className="form-input" type="password" value={newPw}
            onChange={(e) => setNewPw(e.target.value)} />
        </ModalDialog>
      )}
    </div>
  );
}
