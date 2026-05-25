import { useState, useEffect } from "react";
import { api } from "../api";
import ModalDialog from "../components/ModalDialog";
import Spinner from "../components/Spinner";

const _LOCAL_DEFAULT_BASE = {
  lm_studio: "http://localhost:1234/v1",
  ollama: "http://localhost:11434/v1",
};

function _toAdvancedSettings(profile) {
  const settings = profile?.settings && typeof profile.settings === "object" ? profile.settings : {};
  if (profile?.provider === "advanced") {
    return settings;
  }

  const provider = ["lm_studio", "ollama", "openrouter"].includes(profile?.provider)
    ? profile.provider
    : "openrouter";
  const model = (
    settings.model
    || settings.agent_model
    || profile?.model
    || "openai/gpt-4o-mini"
  );

  const advanced = {
    or_api_key: provider === "openrouter" ? (settings.api_key || "") : "",
    agent: {
      provider,
      model,
    },
  };

  if (provider !== "openrouter") {
    advanced.agent.api_base = settings.api_base || _LOCAL_DEFAULT_BASE[provider] || "";
  }
  return advanced;
}

// ── Provider Setup Tab ────────────────────────────────────────────────────────
function ProviderSetupTab() {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [form, setForm] = useState({ name: "", provider: "advanced", settings_text: "{}" });

  const load = async () => {
    setLoading(true);
    try {
      setProfiles(await api.listProfiles());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openAdd = () => {
    setForm({ name: "", provider: "advanced", settings_text: JSON.stringify({
      or_api_key: "",
      agent: { provider: "openrouter", model: "openai/gpt-4o-mini" }
    }, null, 2) });
    setEditTarget(null);
    setShowAdd(true);
  };

  const openEdit = (p) => {
    setForm({
      name: p.name,
      provider: "advanced",
      settings_text: JSON.stringify(_toAdvancedSettings(p), null, 2),
    });
    setEditTarget(p);
    setShowAdd(true);
  };

  const handleSave = async () => {
    let settings;
    try { settings = JSON.parse(form.settings_text); } catch { setError("Invalid JSON"); return; }
    try {
      if (editTarget) {
        await api.updateProfile(editTarget.id, { name: form.name, provider: "advanced", settings });
      } else {
        await api.createProfile({ name: form.name, provider: "advanced", settings });
      }
      setShowAdd(false);
      load();
    } catch (e) { setError(e.message); }
  };

  const handleActivate = async (id) => {
    await api.activateProfile(id); load();
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this profile?")) return;
    await api.deleteProfile(id); load();
  };

  return (
    <div className="settings-tab">
      {error && <p className="error-msg">{error}</p>}
      <div className="settings-tab-header">
        <h3>LLM Profiles</h3>
        <button className="btn btn-primary" onClick={openAdd}>+ Add Profile</button>
      </div>
      {loading ? <Spinner /> : (
        <table className="data-table">
          <thead><tr><th>Name</th><th>Provider</th><th>Active</th><th>Actions</th></tr></thead>
          <tbody>
            {profiles.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>{p.provider}</td>
                <td>{p.is_active ? "✅" : ""}</td>
                <td>
                  {!p.is_active && <button className="btn btn-sm" onClick={() => handleActivate(p.id)}>Activate</button>}
                  {" "}
                  <button className="btn btn-sm" onClick={() => openEdit(p)}>Edit</button>
                  {" "}
                  <button className="btn btn-sm btn-danger" onClick={() => handleDelete(p.id)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showAdd && (
        <ModalDialog
          title={editTarget ? "Edit Profile" : "Add Profile"}
          onClose={() => setShowAdd(false)}
          footer={
            <>
              <button className="btn btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSave}>Save</button>
            </>
          }
        >
          <label className="form-label">Name</label>
          <input className="form-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <label className="form-label">Provider type</label>
          <input className="form-input" value="advanced" disabled />
          <label className="form-label">Settings (JSON)</label>
          <textarea
            className="form-input mono"
            rows={12}
            value={form.settings_text}
            onChange={(e) => setForm({ ...form, settings_text: e.target.value })}
          />
        </ModalDialog>
      )}
    </div>
  );
}

// ── Tool Settings Tab ─────────────────────────────────────────────────────────
function ToolSettingsTab() {
  const [text, setText] = useState("{}");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getToolSettings().then((d) => { setText(JSON.stringify(d, null, 2)); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  const handleSave = async () => {
    let parsed;
    try { parsed = JSON.parse(text); } catch { setError("Invalid JSON"); return; }
    setSaving(true);
    try {
      await api.updateToolSettings(parsed);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) { setError(e.message); } finally { setSaving(false); }
  };

  return (
    <div className="settings-tab">
      {error && <p className="error-msg">{error}</p>}
      <div className="settings-tab-header">
        <h3>Tool Settings</h3>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? <Spinner size={14} /> : saved ? "Saved ✓" : "Save"}
        </button>
      </div>
      {loading ? <Spinner /> : (
        <textarea
          className="form-input mono"
          rows={20}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      )}
    </div>
  );
}

// ── Account Tab ───────────────────────────────────────────────────────────────
function AccountTab({ user }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const handleChange = async () => {
    setMsg(""); setError("");
    if (newPassword !== confirm) { setError("Passwords do not match"); return; }
    if (newPassword.length < 8) { setError("Password must be at least 8 characters"); return; }
    try {
      await api.changePassword(currentPassword, newPassword);
      setMsg("Password changed successfully.");
      setCurrentPassword(""); setNewPassword(""); setConfirm("");
    } catch (e) { setError(e.message); }
  };

  return (
    <div className="settings-tab">
      <h3>Account</h3>
      <p className="account-email">Signed in as <strong>{user?.email}</strong></p>
      <div className="form-section">
        <h4>Change Password</h4>
        {msg && <p className="success-msg">{msg}</p>}
        {error && <p className="error-msg">{error}</p>}
        <label className="form-label">Current password</label>
        <input className="form-input" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
        <label className="form-label">New password</label>
        <input className="form-input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        <label className="form-label">Confirm new password</label>
        <input className="form-input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        <button className="btn btn-primary" onClick={handleChange}>Change Password</button>
      </div>
    </div>
  );
}

// ── SettingsPage ──────────────────────────────────────────────────────────────
const TABS = [
  { id: "provider", label: "Provider Setup" },
  { id: "tools", label: "Tool Settings" },
  { id: "account", label: "Account" },
];

export default function SettingsPage({ user }) {
  const [tab, setTab] = useState("provider");

  return (
    <div className="settings-page">
      <h2>Settings</h2>
      <div className="tab-bar">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab-btn ${tab === t.id ? "tab-btn--active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="tab-content">
        {tab === "provider" && <ProviderSetupTab />}
        {tab === "tools" && <ToolSettingsTab />}
        {tab === "account" && <AccountTab user={user} />}
      </div>
    </div>
  );
}
