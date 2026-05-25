import { useEffect, useState } from "react";
import { api } from "../api";

const ROLE_FIELDS = [
  { key: "agent", label: "Agent" },
  { key: "agent_fallback", label: "Agent Fallback" },
  { key: "code", label: "Code Generation" },
  { key: "code_fallback", label: "Code Fallback" },
  { key: "summarization", label: "Summarization" },
  { key: "summarization_fallback", label: "Summarization Fallback" },
];

const LOCAL_DEFAULT_BASE = {
  lm_studio: "http://localhost:1234/v1",
  ollama: "http://localhost:11434/v1",
};

function defaultRoleConfig(roleKey) {
  if (roleKey === "agent") {
    return { provider: "openrouter", api_base: "", model: "openai/gpt-4o-mini" };
  }
  return { provider: "openrouter", api_base: "", model: "" };
}

function createDefaultForm() {
  const roles = {};
  ROLE_FIELDS.forEach(({ key }) => {
    roles[key] = defaultRoleConfig(key);
  });
  return {
    id: "",
    name: "",
    provider: "advanced",
    or_api_key: "",
    roles,
  };
}

function toRoleConfig(rawCfg, roleKey) {
  const cfg = rawCfg && typeof rawCfg === "object" ? rawCfg : {};
  const provider = ["lm_studio", "ollama", "openrouter"].includes(cfg.provider)
    ? cfg.provider
    : "openrouter";
  const api_base = provider === "openrouter"
    ? ""
    : (cfg.api_base || LOCAL_DEFAULT_BASE[provider] || "");
  const model = typeof cfg.model === "string" ? cfg.model : "";

  if (roleKey === "agent" && !model) {
    return { provider, api_base, model: "openai/gpt-4o-mini" };
  }
  return { provider, api_base, model };
}

function presetToForm(row) {
  const settings = row?.settings && typeof row.settings === "object" ? row.settings : {};
  const next = createDefaultForm();
  next.id = row?.id || "";
  next.name = row?.name || "";
  next.provider = "advanced";

  if (row?.provider === "advanced") {
    next.or_api_key = typeof settings.or_api_key === "string" ? settings.or_api_key : "";
    ROLE_FIELDS.forEach(({ key }) => {
      next.roles[key] = toRoleConfig(settings[key], key);
    });
    return next;
  }

  const legacyProvider = ["lm_studio", "ollama", "openrouter"].includes(row?.provider)
    ? row.provider
    : "openrouter";
  const legacyModel = typeof row?.model === "string" ? row.model : "";
  const roleCfg = {
    provider: legacyProvider,
    api_base: legacyProvider === "openrouter"
      ? ""
      : (settings.api_base || LOCAL_DEFAULT_BASE[legacyProvider] || ""),
    model: legacyModel,
  };
  next.roles.agent = roleCfg;
  if (legacyProvider === "openrouter") {
    next.or_api_key = typeof settings.api_key === "string" ? settings.api_key : "";
  }
  return next;
}

function formToPayload(form) {
  const settings = {
    or_api_key: (form.or_api_key || "").trim(),
  };

  ROLE_FIELDS.forEach(({ key }) => {
    const role = form.roles[key] || defaultRoleConfig(key);
    const provider = ["lm_studio", "ollama", "openrouter"].includes(role.provider)
      ? role.provider
      : "openrouter";
    const roleCfg = {
      provider,
      model: (role.model || "").trim(),
    };
    if (provider !== "openrouter") {
      roleCfg.api_base = (role.api_base || LOCAL_DEFAULT_BASE[provider] || "").trim();
    }
    settings[key] = roleCfg;
  });

  return {
    name: (form.name || "").trim(),
    provider: "advanced",
    model: settings.agent?.model || "",
    settings,
  };
}

function agentModelLabel(row) {
  if (row?.provider === "advanced") {
    return row?.settings?.agent?.model || "";
  }
  return row?.model || "";
}

function ProviderPresetsTab({ onCountChange }) {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(createDefaultForm);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listProviderPresets()
      .then((loaded) => {
        setRows(loaded);
        onCountChange?.(loaded.length);
      })
      .catch((err) => setError(err.message));
  }, [onCountChange]);

  const save = async () => {
    const entry = formToPayload(form);
    if (!entry.name) {
      window.alert("Preset name is required");
      return;
    }
    if (!entry.model) {
      window.alert("Agent model is required");
      return;
    }
    try {
      const saved = form.id
        ? await api.updateProviderPreset(form.id, entry)
        : await api.createProviderPreset(entry);
      setRows((prev) => {
        const next = form.id ? prev.map((r) => (r.id === form.id ? saved : r)) : [saved, ...prev];
        onCountChange?.(next.length);
        return next;
      });
      setError("");
    } catch (err) {
      setError(err.message);
      return;
    }
    setForm(createDefaultForm());
  };

  const setRole = (roleKey, patch) => {
    setForm((prev) => ({
      ...prev,
      roles: {
        ...prev.roles,
        [roleKey]: {
          ...(prev.roles[roleKey] || defaultRoleConfig(roleKey)),
          ...patch,
        },
      },
    }));
  };

  const edit = (row) => setForm(presetToForm(row));

  const remove = async (id) => {
    try {
      await api.deleteProviderPreset(id);
      setRows((prev) => {
        const next = prev.filter((r) => r.id !== id);
        onCountChange?.(next.length);
        return next;
      });
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="settings-tab">
      <h3>Provider Presets</h3>
      {error && <p className="error-msg">{error}</p>}
      <div className="form-section form-section--wide">
        <label className="form-label">Preset name</label>
        <input className="form-input" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
        <div className="muted">Provider mode is fixed to advanced. Each role can use a different provider and model.</div>

        <label className="form-label">Shared OpenRouter API key</label>
        <input
          className="form-input"
          type="password"
          value={form.or_api_key}
          onChange={(e) => setForm((p) => ({ ...p, or_api_key: e.target.value }))}
          placeholder="sk-or-..."
        />

        <div className="provider-roles-grid">
          <div className="provider-roles-grid__header">Role</div>
          <div className="provider-roles-grid__header">Provider</div>
          <div className="provider-roles-grid__header">API Base URL</div>
          <div className="provider-roles-grid__header">Model</div>
          {ROLE_FIELDS.map(({ key, label }) => {
            const role = form.roles[key] || defaultRoleConfig(key);
            return (
              <div className="provider-roles-grid__row" key={key}>
                <div className="provider-roles-grid__cell provider-roles-grid__label">{label}</div>
                <div className="provider-roles-grid__cell">
                  <select
                    className="form-input"
                    value={role.provider}
                    onChange={(e) => {
                      const provider = e.target.value;
                      setRole(key, {
                        provider,
                        api_base: provider === "openrouter"
                          ? ""
                          : (role.api_base || LOCAL_DEFAULT_BASE[provider] || ""),
                      });
                    }}
                  >
                    <option value="openrouter">openrouter</option>
                    <option value="lm_studio">lm_studio</option>
                    <option value="ollama">ollama</option>
                  </select>
                </div>
                <div className="provider-roles-grid__cell">
                  <input
                    className="form-input"
                    value={role.provider === "openrouter" ? "" : (role.api_base || "")}
                    onChange={(e) => setRole(key, { api_base: e.target.value })}
                    placeholder={role.provider === "openrouter" ? "Not used for OpenRouter" : (LOCAL_DEFAULT_BASE[role.provider] || "")}
                    disabled={role.provider === "openrouter"}
                  />
                </div>
                <div className="provider-roles-grid__cell">
                  <input
                    className="form-input"
                    value={role.model || ""}
                    onChange={(e) => setRole(key, { model: e.target.value })}
                    placeholder={key === "agent" ? "openai/gpt-4o-mini" : "optional"}
                  />
                </div>
              </div>
            );
          })}
        </div>

        <button className="btn btn-primary" onClick={save}>{form.id ? "Update Preset" : "Create Preset"}</button>
      </div>

      <table className="data-table">
        <thead><tr><th>Name</th><th>Provider</th><th>Agent Model</th><th>Configured Roles</th><th>Actions</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td>{r.provider}</td>
              <td>{agentModelLabel(r)}</td>
              <td>{ROLE_FIELDS.filter(({ key }) => (r.settings?.[key]?.model || "").trim()).length}</td>
              <td className="table-actions">
                <button className="btn btn-sm" onClick={() => edit(r)}>Edit</button>
                <button className="btn btn-sm btn-danger" onClick={() => remove(r.id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PoliciesTab({ onCountChange }) {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ id: "", name: "", warning_threshold: 80, hard_caps: "{}" });
  const [error, setError] = useState("");

  useEffect(() => {
    api.listToolPolicies()
      .then((loaded) => {
        setRows(loaded);
        onCountChange?.(loaded.length);
      })
      .catch((err) => setError(err.message));
  }, [onCountChange]);

  const save = async () => {
    let caps;
    try {
      caps = JSON.parse(form.hard_caps || "{}");
    } catch {
      window.alert("Hard caps must be valid JSON");
      return;
    }
    const entry = {
      name: form.name.trim(),
      warning_threshold: Number(form.warning_threshold) || 80,
      hard_caps: caps,
    };
    if (!entry.name) return;
    try {
      const saved = form.id
        ? await api.updateToolPolicy(form.id, entry)
        : await api.createToolPolicy(entry);
      setRows((prev) => {
        const next = form.id ? prev.map((r) => (r.id === form.id ? saved : r)) : [saved, ...prev];
        onCountChange?.(next.length);
        return next;
      });
      setError("");
    } catch (err) {
      setError(err.message);
      return;
    }
    setForm({ id: "", name: "", warning_threshold: 80, hard_caps: "{}" });
  };

  const edit = (row) => setForm({ ...row, hard_caps: JSON.stringify(row.hard_caps || {}, null, 2) });
  const remove = async (id) => {
    try {
      await api.deleteToolPolicy(id);
      setRows((prev) => {
        const next = prev.filter((r) => r.id !== id);
        onCountChange?.(next.length);
        return next;
      });
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="settings-tab">
      <h3>Tool Hard Cap Policies</h3>
      {error && <p className="error-msg">{error}</p>}
      <div className="form-section">
        <label className="form-label">Policy name</label>
        <input className="form-input" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
        <label className="form-label">Warning threshold (%)</label>
        <input className="form-input" type="number" min={1} max={100} value={form.warning_threshold} onChange={(e) => setForm((p) => ({ ...p, warning_threshold: e.target.value }))} />
        <label className="form-label">Hard caps by tool (JSON)</label>
        <textarea className="form-input mono" rows={8} value={form.hard_caps} onChange={(e) => setForm((p) => ({ ...p, hard_caps: e.target.value }))} />
        <button className="btn btn-primary" onClick={save}>{form.id ? "Update Policy" : "Create Policy"}</button>
      </div>
      <table className="data-table">
        <thead><tr><th>Name</th><th>Warn %</th><th>Tools</th><th>Actions</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td>{r.warning_threshold}</td>
              <td>{Object.keys(r.hard_caps || {}).length}</td>
              <td className="table-actions">
                <button className="btn btn-sm" onClick={() => edit(r)}>Edit</button>
                <button className="btn btn-sm btn-danger" onClick={() => remove(r.id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function GlobalSettingsPage() {
  const [tab, setTab] = useState("presets");
  const [presetCount, setPresetCount] = useState(0);
  const [policyCount, setPolicyCount] = useState(0);

  return (
    <div className="settings-page">
      <h2>Global Settings</h2>
      <p className="muted">Provider presets: {presetCount} | Tool policies: {policyCount}</p>
      <div className="tab-bar">
        <button className={`tab-btn ${tab === "presets" ? "tab-btn--active" : ""}`} onClick={() => setTab("presets")}>Provider Presets</button>
        <button className={`tab-btn ${tab === "policies" ? "tab-btn--active" : ""}`} onClick={() => setTab("policies")}>Tool Hard Cap Policies</button>
      </div>
      <div className="tab-content">
        {tab === "presets" ? <ProviderPresetsTab onCountChange={setPresetCount} /> : <PoliciesTab onCountChange={setPolicyCount} />}
      </div>
    </div>
  );
}
