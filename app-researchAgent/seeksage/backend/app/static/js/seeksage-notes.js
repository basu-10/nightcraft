const errorNode = document.getElementById("notes-error");
const tableBody = document.getElementById("notes-table-body");
const form = document.getElementById("note-form");
const queryInput = document.getElementById("notes-query");
const tagInput = document.getElementById("notes-tag-filter");

let allNotes = [];

function showError(message) {
  if (!message) {
    errorNode.hidden = true;
    errorNode.textContent = "";
    return;
  }
  errorNode.hidden = false;
  errorNode.textContent = message;
}

function normalizeText(value) {
  return String(value || "").toLowerCase();
}

function filteredNotes() {
  const query = normalizeText(queryInput.value.trim());
  const tagFilter = normalizeText(tagInput.value.trim());

  return allNotes
    .filter((item) => {
      if (!query) {
        return true;
      }
      const haystack = `${item.title || ""} ${item.body || ""}`.toLowerCase();
      return haystack.includes(query);
    })
    .filter((item) => {
      if (!tagFilter) {
        return true;
      }
      return (item.tags || []).some((tag) => normalizeText(tag).includes(tagFilter));
    })
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
}

function locationLabel(note) {
  return [note.workspace_id, note.project_id, note.chat_session_id].filter(Boolean).join(" / ") || "-";
}

function renderTable() {
  const rows = filteredNotes();
  tableBody.innerHTML = "";

  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="5">No notes found.</td>';
    tableBody.appendChild(tr);
    return;
  }

  for (const note of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(note.title)}</td>
      <td>${escapeHtml((note.tags || []).join(", "))}</td>
      <td>${escapeHtml(locationLabel(note))}</td>
      <td>${escapeHtml(new Date(note.created_at).toLocaleString())}</td>
      <td><button data-note-id="${note.id}" class="danger-btn" type="button">Delete</button></td>
    `;
    tableBody.appendChild(tr);
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

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
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof body === "object" && body && body.error ? body.error : "Request failed.";
    throw new Error(message);
  }

  return body;
}

async function loadNotes() {
  showError("");
  try {
    allNotes = await request("/api/notes");
    renderTable();
  } catch (error) {
    showError(error.message || "Failed to load notes.");
    tableBody.innerHTML = '<tr><td colspan="5">Could not load notes.</td></tr>';
  }
}

function formPayload() {
  return {
    title: form.title.value.trim(),
    body: form.body.value.trim(),
    tags: form.tags.value
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
    workspace_id: form.workspace.value.trim() || null,
    project_id: form.project.value.trim() || null,
    chat_session_id: form.session.value.trim() || null,
  };
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formPayload();
  if (!payload.title) {
    showError("Title is required.");
    return;
  }

  try {
    const created = await request("/api/notes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    allNotes = [created, ...allNotes];
    form.reset();
    showError("");
    renderTable();
  } catch (error) {
    showError(error.message || "Failed to create note.");
  }
});

tableBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-note-id]");
  if (!button) {
    return;
  }

  const noteId = button.getAttribute("data-note-id");
  if (!noteId) {
    return;
  }

  try {
    await request(`/api/notes/${noteId}`, { method: "DELETE" });
    allNotes = allNotes.filter((note) => note.id !== noteId);
    showError("");
    renderTable();
  } catch (error) {
    showError(error.message || "Failed to delete note.");
  }
});

queryInput.addEventListener("input", renderTable);
tagInput.addEventListener("input", renderTable);

void loadNotes();
