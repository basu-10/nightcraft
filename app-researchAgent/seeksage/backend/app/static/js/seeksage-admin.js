const errorNode = document.getElementById("admin-error");
const usersNode = document.getElementById("admin-users");
const runsNode = document.getElementById("admin-runs");
const runsTodayNode = document.getElementById("admin-runs-today");
const createUserForm = document.getElementById("admin-create-user-form");
const usersTableBody = document.getElementById("admin-users-table-body");

let users = [];

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

async function loadStats() {
  const stats = await request("/admin/stats", { headers: { Accept: "application/json" } });
  usersNode.textContent = String(stats.user_count ?? 0);
  runsNode.textContent = String(stats.run_count ?? 0);
  runsTodayNode.textContent = String(stats.runs_today ?? 0);
}

function renderUsers() {
  usersTableBody.innerHTML = "";

  if (!users.length) {
    usersTableBody.innerHTML = '<tr><td colspan="5">No users found.</td></tr>';
    return;
  }

  for (const row of users) {
    const tr = document.createElement("tr");
    const created = row.created_at ? new Date(row.created_at).toLocaleDateString() : "-";
    tr.innerHTML = `
      <td>${escapeHtml(row.email)}</td>
      <td>${row.is_admin ? "Yes" : "No"}</td>
      <td>${row.active ? "Yes" : "No"}</td>
      <td>${escapeHtml(created)}</td>
      <td>
        <button type="button" data-toggle-admin="${row.id}">${row.is_admin ? "Revoke admin" : "Make admin"}</button>
        <button type="button" data-toggle-active="${row.id}">${row.active ? "Deactivate" : "Activate"}</button>
        <button type="button" data-reset-password="${row.id}">Reset pw</button>
        <button type="button" class="danger-btn" data-delete-user="${row.id}">Delete</button>
      </td>
    `;
    usersTableBody.appendChild(tr);
  }
}

async function loadUsers() {
  users = await request("/admin/users", { headers: { Accept: "application/json" } });
  renderUsers();
}

async function loadAll() {
  showError("");
  try {
    await Promise.all([loadStats(), loadUsers()]);
  } catch (error) {
    showError(error.message || "Failed to load admin data.");
  }
}

createUserForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const email = document.getElementById("admin-create-email").value.trim();
  const password = document.getElementById("admin-create-password").value;
  const isAdmin = document.getElementById("admin-create-is-admin").checked;

  if (!email || password.length < 8) {
    showError("Valid email and password (8+ chars) are required.");
    return;
  }

  try {
    await request("/admin/users", {
      method: "POST",
      body: JSON.stringify({ email, password, is_admin: isAdmin }),
    });
    createUserForm.reset();
    showError("");
    await loadAll();
  } catch (error) {
    showError(error.message || "Failed to create user.");
  }
});

usersTableBody.addEventListener("click", async (event) => {
  const toggleAdmin = event.target.closest("button[data-toggle-admin]");
  const toggleActive = event.target.closest("button[data-toggle-active]");
  const deleteUser = event.target.closest("button[data-delete-user]");
  const resetPassword = event.target.closest("button[data-reset-password]");

  if (!toggleAdmin && !toggleActive && !deleteUser && !resetPassword) {
    return;
  }

  try {
    if (toggleAdmin) {
      const id = toggleAdmin.getAttribute("data-toggle-admin");
      const row = users.find((item) => item.id === id);
      if (row) {
        await request(`/admin/users/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ is_admin: !row.is_admin }),
        });
      }
    }

    if (toggleActive) {
      const id = toggleActive.getAttribute("data-toggle-active");
      const row = users.find((item) => item.id === id);
      if (row) {
        await request(`/admin/users/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ active: !row.active }),
        });
      }
    }

    if (resetPassword) {
      const id = resetPassword.getAttribute("data-reset-password");
      const newPassword = window.prompt("Enter new password (min 8 chars)", "");
      if (newPassword && newPassword.length >= 8) {
        await request(`/admin/users/${id}/password`, {
          method: "POST",
          body: JSON.stringify({ new_password: newPassword }),
        });
      }
    }

    if (deleteUser) {
      const id = deleteUser.getAttribute("data-delete-user");
      const row = users.find((item) => item.id === id);
      if (row) {
        const ok = window.confirm(`Delete user ${row.email}? This cannot be undone.`);
        if (ok) {
          await request(`/admin/users/${id}`, { method: "DELETE" });
        }
      }
    }

    showError("");
    await loadAll();
  } catch (error) {
    showError(error.message || "Admin action failed.");
  }
});

void loadAll();
