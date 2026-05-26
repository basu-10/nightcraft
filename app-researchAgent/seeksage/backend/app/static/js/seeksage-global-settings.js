const errorNode = document.getElementById("gs-error");

const presetForm = document.getElementById("preset-form");
const presetIdInput = document.getElementById("preset-id");
const presetNameInput = document.getElementById("preset-name");
const presetModelInput = document.getElementById("preset-model");
const presetApiKeyInput = document.getElementById("preset-api-key");
const presetTableBody = document.getElementById("preset-table-body");

const policyForm = document.getElementById("policy-form");
const policyIdInput = document.getElementById("policy-id");
const policyNameInput = document.getElementById("policy-name");
const policyThresholdInput = document.getElementById("policy-threshold");
const policyHardCapsInput = document.getElementById("policy-hard-caps");
const policyTableBody = document.getElementById("policy-table-body");

let presets = [];
let policies = [];

function showError(message) {
  if (!message) {
    errorNode.hidden = true;
    errorNode.textContent = "";
    return;
  }
  errorNode.hidden = false;
  errorNode.textContent = message;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const message = typeof body === "object" && body && body.error ? body.error : "Request failed.";
    throw new Error(message);
  }

  return body;
}

function resetPresetForm() {
  presetIdInput.value = "";
  presetNameInput.value = "";
  presetModelInput.value = "";
  presetApiKeyInput.value = "";
}

function resetPolicyForm() {
  policyIdInput.value = "";
  policyNameInput.value = "";
  policyThresholdInput.value = "80";
  policyHardCapsInput.value = "{}";
}

function renderPresets() {
  presetTableBody.innerHTML = "";
  if (!presets.length) {
    presetTableBody.innerHTML = '<tr><td colspan="4">No presets yet.</td></tr>';
    return;
  }

  for (const row of presets) {
    const tr = document.createElement("tr");
    const model = row?.settings?.agent?.model || row?.model || "";
    tr.innerHTML = `
      <td>${escapeHtml(row.name)}</td>
      <td>${escapeHtml(row.provider)}</td>
      <td>${escapeHtml(model)}</td>
      <td>
        <button type="button" data-edit-preset="${row.id}">Edit</button>
        <button type="button" class="danger-btn" data-delete-preset="${row.id}">Delete</button>
      </td>
    `;
    presetTableBody.appendChild(tr);
  }
}

function renderPolicies() {
  policyTableBody.innerHTML = "";
  if (!policies.length) {
    policyTableBody.innerHTML = '<tr><td colspan="4">No policies yet.</td></tr>';
    return;
  }

  for (const row of policies) {
    const toolCount = Object.keys(row.hard_caps || {}).length;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.name)}</td>
      <td>${escapeHtml(String(row.warning_threshold ?? ""))}</td>
      <td>${escapeHtml(String(toolCount))}</td>
      <td>
        <button type="button" data-edit-policy="${row.id}">Edit</button>
        <button type="button" class="danger-btn" data-delete-policy="${row.id}">Delete</button>
      </td>
    `;
    policyTableBody.appendChild(tr);
  }
}

async function loadAll() {
  showError("");
  try {
    const [presetRows, policyRows] = await Promise.all([
      request("/api/settings/provider-presets", { headers: { Accept: "application/json" } }),
      request("/api/settings/tool-policies", { headers: { Accept: "application/json" } }),
    ]);
    presets = presetRows;
    policies = policyRows;
    renderPresets();
    renderPolicies();
  } catch (error) {
    showError(error.message || "Failed to load settings.");
  }
}

presetForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = presetIdInput.value.trim();
  const name = presetNameInput.value.trim();
  const model = presetModelInput.value.trim();
  const apiKey = presetApiKeyInput.value.trim();

  if (!name || !model) {
    showError("Preset name and agent model are required.");
    return;
  }

  const payload = {
    name,
    provider: "advanced",
    model,
    settings: {
      or_api_key: apiKey,
      agent: { provider: "openrouter", model },
      agent_fallback: { provider: "openrouter", model: "" },
      code: { provider: "openrouter", model: "" },
      code_fallback: { provider: "openrouter", model: "" },
      summarization: { provider: "openrouter", model: "" },
      summarization_fallback: { provider: "openrouter", model: "" },
    },
  };

  try {
    const saved = id
      ? await request(`/api/settings/provider-presets/${id}`, { method: "PATCH", body: JSON.stringify(payload) })
      : await request("/api/settings/provider-presets", { method: "POST", body: JSON.stringify(payload) });

    if (id) {
      presets = presets.map((row) => (row.id === id ? saved : row));
    } else {
      presets = [saved, ...presets];
    }

    resetPresetForm();
    showError("");
    renderPresets();
  } catch (error) {
    showError(error.message || "Failed to save preset.");
  }
});

presetTableBody.addEventListener("click", async (event) => {
  const editButton = event.target.closest("button[data-edit-preset]");
  const deleteButton = event.target.closest("button[data-delete-preset]");

  if (editButton) {
    const id = editButton.getAttribute("data-edit-preset");
    const row = presets.find((item) => item.id === id);
    if (!row) {
      return;
    }

    presetIdInput.value = row.id;
    presetNameInput.value = row.name || "";
    presetModelInput.value = row?.settings?.agent?.model || row.model || "";
    presetApiKeyInput.value = row?.settings?.or_api_key || "";
    return;
  }

  if (deleteButton) {
    const id = deleteButton.getAttribute("data-delete-preset");
    try {
      await request(`/api/settings/provider-presets/${id}`, { method: "DELETE" });
      presets = presets.filter((row) => row.id !== id);
      renderPresets();
      showError("");
    } catch (error) {
      showError(error.message || "Failed to delete preset.");
    }
  }
});

policyForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const id = policyIdInput.value.trim();
  const name = policyNameInput.value.trim();
  const warningThreshold = Number(policyThresholdInput.value || 80);

  let hardCaps;
  try {
    hardCaps = JSON.parse(policyHardCapsInput.value || "{}");
  } catch {
    showError("Hard caps must be valid JSON.");
    return;
  }

  const payload = {
    name,
    warning_threshold: warningThreshold,
    hard_caps: hardCaps,
  };

  if (!name) {
    showError("Policy name is required.");
    return;
  }

  try {
    const saved = id
      ? await request(`/api/settings/tool-policies/${id}`, { method: "PATCH", body: JSON.stringify(payload) })
      : await request("/api/settings/tool-policies", { method: "POST", body: JSON.stringify(payload) });

    if (id) {
      policies = policies.map((row) => (row.id === id ? saved : row));
    } else {
      policies = [saved, ...policies];
    }

    resetPolicyForm();
    showError("");
    renderPolicies();
  } catch (error) {
    showError(error.message || "Failed to save policy.");
  }
});

policyTableBody.addEventListener("click", async (event) => {
  const editButton = event.target.closest("button[data-edit-policy]");
  const deleteButton = event.target.closest("button[data-delete-policy]");

  if (editButton) {
    const id = editButton.getAttribute("data-edit-policy");
    const row = policies.find((item) => item.id === id);
    if (!row) {
      return;
    }

    policyIdInput.value = row.id;
    policyNameInput.value = row.name || "";
    policyThresholdInput.value = String(row.warning_threshold ?? 80);
    policyHardCapsInput.value = JSON.stringify(row.hard_caps || {}, null, 2);
    return;
  }

  if (deleteButton) {
    const id = deleteButton.getAttribute("data-delete-policy");
    try {
      await request(`/api/settings/tool-policies/${id}`, { method: "DELETE" });
      policies = policies.filter((row) => row.id !== id);
      renderPolicies();
      showError("");
    } catch (error) {
      showError(error.message || "Failed to delete policy.");
    }
  }
});

void loadAll();
