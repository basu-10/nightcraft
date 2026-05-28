const emailNode = document.getElementById("account-email");
const totalRunsNode = document.getElementById("account-total-runs");
const runsTodayNode = document.getElementById("account-runs-today");
const passwordForm = document.getElementById("password-form");
const successNode = document.getElementById("account-success");
const errorNode = document.getElementById("account-error");

const API_BASE = window.SEEK_API_BASE || "";

function apiPath(path) {
  return path.startsWith("/") ? `${API_BASE}${path}` : path;
}

async function request(path, options = {}) {
  const response = await fetch(apiPath(path), {
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

function setMessage(type, text) {
  if (type === "success") {
    successNode.hidden = false;
    successNode.textContent = text;
    errorNode.hidden = true;
    errorNode.textContent = "";
    return;
  }

  if (type === "error") {
    errorNode.hidden = false;
    errorNode.textContent = text;
    successNode.hidden = true;
    successNode.textContent = "";
    return;
  }

  successNode.hidden = true;
  successNode.textContent = "";
  errorNode.hidden = true;
  errorNode.textContent = "";
}

async function loadAccountSummary() {
  try {
    const me = await request("/auth/me", { headers: { Accept: "application/json" } });
    emailNode.textContent = me?.user?.email || "Unknown";
  } catch {
    emailNode.textContent = "Unknown";
  }

  try {
    const stats = await request("/api/dashboard/stats", { headers: { Accept: "application/json" } });
    totalRunsNode.textContent = String(stats.total_runs ?? 0);
    runsTodayNode.textContent = String(stats.runs_today ?? 0);
  } catch {
    totalRunsNode.textContent = "-";
    runsTodayNode.textContent = "-";
  }
}

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("", "");

  const currentPassword = passwordForm.currentPassword.value;
  const newPassword = passwordForm.newPassword.value;

  if (newPassword.length < 8) {
    setMessage("error", "Password must be at least 8 characters.");
    return;
  }

  try {
    await request("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    passwordForm.reset();
    setMessage("success", "Password updated.");
  } catch (error) {
    setMessage("error", error.message || "Password update failed.");
  }
});

void loadAccountSummary();
