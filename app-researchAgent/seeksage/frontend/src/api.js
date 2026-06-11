const inferredApiBase = window.location.pathname.startsWith("/seeksage") ? "/seeksage" : "";
const API_BASE = (import.meta.env.VITE_API_BASE || inferredApiBase).replace(/\/$/, "");

async function request(url, options = {}) {
  const response = await fetch(`${API_BASE}${url}`, {
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
    const message =
      typeof body === "object" && body?.error ? body.error : "Request failed";
    throw new Error(message);
  }

  return body;
}

async function requestForm(url, formData, options = {}) {
  const response = await fetch(`${API_BASE}${url}`, {
    credentials: "include",
    method: options.method || "POST",
    body: formData,
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof body === "object" && body?.error ? body.error : "Request failed";
    throw new Error(message);
  }

  return body;
}

export const api = {
  // ── Auth ──────────────────────────────────────────────────────────────────
  me: () => request("/auth/me"),
  register: (email, password) =>
    request("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request("/auth/logout", { method: "POST" }),
  changePassword: (currentPassword, newPassword) =>
    request("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  // ── Workspaces ────────────────────────────────────────────────────────────
  listWorkspaces: () => request("/api/workspaces"),
  createWorkspace: (payload) =>
    request("/api/workspaces", { method: "POST", body: JSON.stringify(payload) }),
  getWorkspace: (workspaceId) => request(`/api/workspaces/${workspaceId}`),
  updateWorkspace: (workspaceId, payload) =>
    request(`/api/workspaces/${workspaceId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteWorkspace: (workspaceId) =>
    request(`/api/workspaces/${workspaceId}`, { method: "DELETE" }),
  getWorkspaceSettings: (workspaceId) => request(`/api/workspaces/${workspaceId}/settings`),
  updateWorkspaceSettings: (workspaceId, payload) =>
    request(`/api/workspaces/${workspaceId}/settings`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  // ── Projects ──────────────────────────────────────────────────────────────
  listProjects: (workspaceId, includeArchived = false) =>
    request(`/api/workspaces/${workspaceId}/projects${includeArchived ? "?archived=true" : ""}`),
  createProject: (workspaceId, name, description = "") =>
    request(`/api/workspaces/${workspaceId}/projects`, {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),
  getProject: (projectId) => request(`/api/projects/${projectId}`),
  updateProject: (projectId, payload) =>
    request(`/api/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteProject: (projectId) =>
    request(`/api/projects/${projectId}`, { method: "DELETE" }),
  getProjectMemory: (projectId) => request(`/api/projects/${projectId}/memory`),
  updateProjectMemory: (projectId, memoryText) =>
    request(`/api/projects/${projectId}/memory`, {
      method: "PUT",
      body: JSON.stringify({ memory_text: memoryText }),
    }),

  // ── Sessions ──────────────────────────────────────────────────────────────
  listSessions: (workspaceId, projectId = null) => {
    const base = `/api/workspaces/${workspaceId}/sessions`;
    return request(base);
  },
  listProjectSessions: (projectId) => request(`/api/projects/${projectId}/sessions`),
  createSession: (workspaceId, title = "New Chat", projectId = null) =>
    request(`/api/workspaces/${workspaceId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ title, ...(projectId ? { project_id: projectId } : {}) }),
    }),
  createProjectSession: (projectId, title = "New Chat") =>
    request(`/api/projects/${projectId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  getSession: (sessionId) => request(`/api/sessions/${sessionId}`),
  updateSession: (sessionId, payload) =>
    request(`/api/sessions/${sessionId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteSession: (sessionId) =>
    request(`/api/sessions/${sessionId}`, { method: "DELETE" }),

  // ── Messages ──────────────────────────────────────────────────────────────
  listMessages: (sessionId) => request(`/api/sessions/${sessionId}/messages`),

  // ── Notes ─────────────────────────────────────────────────────────────────
  listNotes: (params = {}) => {
    const search = new URLSearchParams();
    if (params.workspaceId) search.set("workspace_id", params.workspaceId);
    if (params.projectId) search.set("project_id", params.projectId);
    if (params.sessionId) search.set("session_id", params.sessionId);
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return request(`/api/notes${suffix}`);
  },
  createNote: (payload) => request("/api/notes", { method: "POST", body: JSON.stringify(payload) }),
  updateNote: (noteId, payload) => request(`/api/notes/${noteId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteNote: (noteId) => request(`/api/notes/${noteId}`, { method: "DELETE" }),

  // ── Notifications ─────────────────────────────────────────────────────────
  listNotifications: () => request("/api/notifications"),
  createNotification: (payload) => request("/api/notifications", { method: "POST", body: JSON.stringify(payload) }),
  updateNotification: (notificationId, payload) =>
    request(`/api/notifications/${notificationId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteNotification: (notificationId) => request(`/api/notifications/${notificationId}`, { method: "DELETE" }),
  markAllNotificationsRead: () => request("/api/notifications/mark-all-read", { method: "POST" }),

  // ── Files ─────────────────────────────────────────────────────────────────
  listSessionFiles: (sessionId) => request(`/api/sessions/${sessionId}/files`),
  uploadSessionFiles: (sessionId, files) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    return requestForm(`/api/sessions/${sessionId}/files`, formData);
  },
  deleteSessionFile: (fileId) => request(`/api/files/${fileId}`, { method: "DELETE" }),
  getSessionFileDownloadUrl: (fileId) => `/api/files/${fileId}/download`,

  // ── Runs ──────────────────────────────────────────────────────────────────
  enqueueRun: (sessionId, query) =>
    request(`/api/sessions/${sessionId}/runs`, {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  getRun: (runId) => request(`/api/runs/${runId}`),
  listRunEvents: (runId) => request(`/api/runs/${runId}/events`),
  listRunActivityLogs: (runId) => request(`/api/runs/${runId}/activity-logs`),
  listSessionRuns: (sessionId) => request(`/api/sessions/${sessionId}/runs`),

  // ── Profiles ──────────────────────────────────────────────────────────────
  listProfiles: () => request("/api/profiles"),
  createProfile: (payload) =>
    request("/api/profiles", { method: "POST", body: JSON.stringify(payload) }),
  updateProfile: (profileId, payload) =>
    request(`/api/profiles/${profileId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  activateProfile: (profileId) =>
    request(`/api/profiles/${profileId}/activate`, { method: "POST" }),
  deleteProfile: (profileId) =>
    request(`/api/profiles/${profileId}`, { method: "DELETE" }),

  // ── Tool Settings ─────────────────────────────────────────────────────────
  getToolSettings: () => request("/api/settings/tools"),
  updateToolSettings: (payload) =>
    request("/api/settings/tools", { method: "PATCH", body: JSON.stringify(payload) }),
  listProviderPresets: () => request("/api/settings/provider-presets"),
  createProviderPreset: (payload) =>
    request("/api/settings/provider-presets", { method: "POST", body: JSON.stringify(payload) }),
  updateProviderPreset: (presetId, payload) =>
    request(`/api/settings/provider-presets/${presetId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteProviderPreset: (presetId) =>
    request(`/api/settings/provider-presets/${presetId}`, { method: "DELETE" }),
  listToolPolicies: () => request("/api/settings/tool-policies"),
  createToolPolicy: (payload) =>
    request("/api/settings/tool-policies", { method: "POST", body: JSON.stringify(payload) }),
  updateToolPolicy: (policyId, payload) =>
    request(`/api/settings/tool-policies/${policyId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteToolPolicy: (policyId) =>
    request(`/api/settings/tool-policies/${policyId}`, { method: "DELETE" }),

  // ── Dashboard ─────────────────────────────────────────────────────────────
  getDashboardStats: () => request("/api/dashboard/stats"),

  // ── Admin ─────────────────────────────────────────────────────────────────
  adminListUsers: () => request("/admin/users"),
  adminCreateUser: (payload) =>
    request("/admin/users", { method: "POST", body: JSON.stringify(payload) }),
  adminUpdateUser: (userId, payload) =>
    request(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  adminResetPassword: (userId, newPassword) =>
    request(`/admin/users/${userId}/password`, {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword }),
    }),
  adminDeleteUser: (userId) =>
    request(`/admin/users/${userId}`, { method: "DELETE" }),
  adminGetStats: () => request("/admin/stats"),
};

