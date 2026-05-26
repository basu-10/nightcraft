const errorNode = document.getElementById("notifications-error");
const listNode = document.getElementById("notifications-list");
const unreadOnlyNode = document.getElementById("unread-only");
const typeNode = document.getElementById("notification-type");
const markAllButton = document.getElementById("mark-all-read");

let notifications = [];

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

function filteredRows() {
  const unreadOnly = unreadOnlyNode.checked;
  const type = typeNode.value;
  return notifications.filter((item) => {
    if (unreadOnly && item.read) {
      return false;
    }
    if (type !== "all" && item.type !== type) {
      return false;
    }
    return true;
  });
}

function render() {
  const rows = filteredRows();
  listNode.innerHTML = "";

  if (!rows.length) {
    listNode.innerHTML = '<p class="muted">No notifications for this filter.</p>';
    return;
  }

  for (const item of rows) {
    const node = document.createElement("article");
    node.className = `notification-item${item.read ? "" : " notification-item--unread"}`;
    node.innerHTML = `
      <div class="notification-row">
        <strong>${escapeHtml(item.title)}</strong>
        <span class="muted">${escapeHtml(new Date(item.created_at).toLocaleString())}</span>
      </div>
      <p>${escapeHtml(item.message || "")}</p>
      <div class="notification-actions">
        ${item.read ? "" : `<button type="button" data-mark-read="${item.id}">Mark read</button>`}
        <button type="button" class="danger-btn" data-delete-notification="${item.id}">Delete</button>
      </div>
    `;
    listNode.appendChild(node);
  }
}

async function loadNotifications() {
  showError("");
  try {
    notifications = await request("/api/notifications", { headers: { Accept: "application/json" } });
    render();
  } catch (error) {
    showError(error.message || "Failed to load notifications.");
    listNode.innerHTML = '<p class="muted">Could not load notifications.</p>';
  }
}

listNode.addEventListener("click", async (event) => {
  const markReadBtn = event.target.closest("button[data-mark-read]");
  const deleteBtn = event.target.closest("button[data-delete-notification]");

  if (!markReadBtn && !deleteBtn) {
    return;
  }

  try {
    if (markReadBtn) {
      const id = markReadBtn.getAttribute("data-mark-read");
      const updated = await request(`/api/notifications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ read: true }),
      });
      notifications = notifications.map((item) => (item.id === updated.id ? updated : item));
    }

    if (deleteBtn) {
      const id = deleteBtn.getAttribute("data-delete-notification");
      await request(`/api/notifications/${id}`, { method: "DELETE" });
      notifications = notifications.filter((item) => item.id !== id);
    }

    showError("");
    render();
  } catch (error) {
    showError(error.message || "Notification update failed.");
  }
});

markAllButton.addEventListener("click", async () => {
  try {
    await request("/api/notifications/mark-all-read", { method: "POST" });
    notifications = notifications.map((item) => ({ ...item, read: true }));
    showError("");
    render();
  } catch (error) {
    showError(error.message || "Failed to mark notifications as read.");
  }
});

unreadOnlyNode.addEventListener("change", render);
typeNode.addEventListener("change", render);

void loadNotifications();
