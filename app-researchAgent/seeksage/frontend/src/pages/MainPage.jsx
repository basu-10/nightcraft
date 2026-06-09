import { useState, useCallback, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import ChatArea from "../components/ChatArea";
import SessionInfoPanel from "../components/SessionInfoPanel";
import LeftSidebarTabs from "../components/LeftSidebarTabs";
import WorkspaceTabs from "../components/WorkspaceTabs";
import { useRunPoller } from "../hooks/useRunPoller";
import { useWorkspaceSettings } from "../hooks/useWorkspaceSettings";
import { api } from "../api";

/**
 * MainPage — 3-column layout: LeftSidebarTabs | ChatArea | SessionInfoPanel
 */

export default function MainPage({ user, onLogout, workspaces = [], activeWorkspace, activeWorkspaceId, setActiveWorkspaceId, createWorkspace, updateWorkspace, deleteWorkspace }) {
  const navigate = useNavigate();

  // All sessions and projects keyed by workspace_id
  const [sessions, setSessions] = useState([]);
  const [projects, setProjects] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [activeRunId, setActiveRunId] = useState(null);
  const [pendingBySession, setPendingBySession] = useState({});
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [profiles, setProfiles] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [notes, setNotes] = useState([]);
  const [filesBySession, setFilesBySession] = useState({});

  const { run, events, polling } = useRunPoller(activeRunId);
  const { settings, updateSettings } = useWorkspaceSettings(activeWorkspaceId);

  // Load sessions + projects for all workspaces
  useEffect(() => {
    if (workspaces.length === 0) return;
    Promise.all(
      workspaces.map(async (ws) => {
        const [slist, plist] = await Promise.all([
          api.listSessions(ws.id),
          api.listProjects(ws.id),
        ]);
        return { ws, sessions: slist, projects: plist };
      })
    ).then((results) => {
      const allSessions = results.flatMap((r) => r.sessions);
      const allProjects = results.flatMap((r) => r.projects);
      setSessions(allSessions);
      setProjects(allProjects);
    });
  }, [workspaces]);

  useEffect(() => {
    api.listProfiles().then(setProfiles).catch(() => setProfiles([]));
    api.listToolPolicies().then(setPolicies).catch(() => setPolicies([]));
  }, []);

  useEffect(() => {
    api.listNotes().then(setNotes).catch(() => setNotes([]));
  }, []);

  useEffect(() => {
    if (!activeWorkspaceId && workspaces.length > 0) {
      setActiveWorkspaceId(workspaces[0].id);
    }
  }, [activeWorkspaceId, workspaces, setActiveWorkspaceId]);

  useEffect(() => {
    if (!activeWorkspaceId) {
      setActiveSession(null);
      return;
    }
    setActiveSession((cur) => {
      if (cur?.workspace_id === activeWorkspaceId) return cur;
      return sessions.find((s) => s.workspace_id === activeWorkspaceId) || null;
    });
  }, [activeWorkspaceId, sessions]);

  useEffect(() => {
    if (!activeSession?.id) {
      return;
    }
    api.listSessionFiles(activeSession.id)
      .then((rows) => {
        setFilesBySession((prev) => ({ ...prev, [activeSession.id]: rows }));
      })
      .catch(() => {
        setFilesBySession((prev) => ({ ...prev, [activeSession.id]: [] }));
      });
  }, [activeSession?.id, run?.id]);

  useEffect(() => {
    if (!activeSession?.id) {
      setActiveRunId(null);
      return;
    }
    api.listSessionRuns(activeSession.id)
      .then((runs) => {
        const latest = runs?.[0] || null;
        if (!latest) {
          setActiveRunId(null);
          return;
        }
        if (latest.status === "done" || latest.status === "error") {
          setActiveRunId(latest.id);
          return;
        }
        setActiveRunId(latest.id);
      })
      .catch(() => {
        setActiveRunId(null);
      });
  }, [activeSession?.id]);

  const handleSelectSession = useCallback((workspace, session) => {
    if (workspace?.id) setActiveWorkspaceId(workspace.id);
    setActiveSession(session);
  }, [setActiveWorkspaceId]);

  const handleNewSession = useCallback(
    async (workspaceId, projectId) => {
      const session = await api.createSession(workspaceId, "New Chat", projectId);
      setSessions((prev) => [session, ...prev]);
      setActiveWorkspaceId(workspaceId);
      setActiveSession(session);
      setActiveRunId(null);
    },
    [setActiveWorkspaceId]
  );

  const handleNewProject = useCallback(async (workspaceId) => {
    const name = window.prompt("Project name:", "New Project");
    if (!name?.trim()) return;
    const project = await api.createProject(workspaceId, name.trim(), "");
    setProjects((prev) => [project, ...prev]);
  }, []);

  const handleDeleteSession = useCallback(async (sessionId) => {
    await api.deleteSession(sessionId);
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    setPendingBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
    if (activeSession?.id === sessionId) setActiveSession(null);
  }, [activeSession]);

  const handlePendingStateChange = useCallback((sessionId, pendingState) => {
    if (!sessionId) return;
    setPendingBySession((prev) => {
      if (!pendingState) {
        if (!prev[sessionId]) return prev;
        const next = { ...prev };
        delete next[sessionId];
        return next;
      }
      return { ...prev, [sessionId]: pendingState };
    });
  }, []);

  const handleRenameSession = useCallback(async (sessionId, title) => {
    const updated = await api.updateSession(sessionId, { title });
    setSessions((prev) => prev.map((s) => (s.id === sessionId ? updated : s)));
    setActiveSession((prev) => (prev?.id === sessionId ? updated : prev));
  }, []);

  const handleUpdateWorkspaceSettings = useCallback(async (patch) => {
    const next = { ...patch };
    if (patch.tool_policy_id) {
      const policy = policies.find((p) => p.id === patch.tool_policy_id);
      if (policy?.hard_caps) {
        next.tool_caps = policy.hard_caps;
      }
    }
    try {
      await updateSettings(next);
    } catch {
      // Settings update failed silently — state remains unchanged
    }
  }, [policies, updateSettings]);

  const toolUsage = useMemo(() => {
    const counts = {};
    (events || []).forEach((ev) => {
      const payload = ev.payload_json || {};
      const toolName = payload.tool_name || payload.tool || payload?.metadata?.tool_name;
      if (toolName) counts[toolName] = (counts[toolName] || 0) + 1;
    });
    return counts;
  }, [events]);

  const currentNotes = useMemo(
    () => (activeSession ? notes.filter((n) => n.chat_session_id === activeSession.id) : []),
    [notes, activeSession]
  );

  const currentFiles = useMemo(
    () => (activeSession ? (filesBySession[activeSession.id] || []) : []),
    [activeSession, filesBySession]
  );

  const handleSaveNote = useCallback((note) => {
    return api.createNote({
      title: note.title,
      body: note.body,
      tags: note.tags,
      workspace_id: activeWorkspace?.id || null,
      project_id: activeSession?.project_id || null,
      chat_session_id: activeSession?.id || null,
    }).then((created) => {
      setNotes((prev) => [created, ...prev]);
      return created;
    });
  }, [activeWorkspace, activeSession]);

  const handleDeleteNote = useCallback((noteId) => {
    return api.deleteNote(noteId).then(() => {
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    });
  }, []);

  const handleFilesAdded = useCallback((files) => {
    if (!activeSession?.id || !files?.length) return;
    api.uploadSessionFiles(activeSession.id, files).then((rows) => {
      setFilesBySession((prev) => ({
        ...prev,
        [activeSession.id]: [...rows, ...(prev[activeSession.id] || [])],
      }));
    });
  }, [activeSession]);

  const handleDeleteFile = useCallback((fileId) => {
    if (!activeSession?.id) return Promise.resolve();
    return api.deleteSessionFile(fileId).then(() => {
      setFilesBySession((prev) => ({
        ...prev,
        [activeSession.id]: (prev[activeSession.id] || []).filter((f) => f.id !== fileId),
      }));
    });
  }, [activeSession]);

  const sessionsForActiveWorkspace = activeWorkspaceId
    ? sessions.filter((s) => s.workspace_id === activeWorkspaceId)
    : [];
  const projectsForActiveWorkspace = activeWorkspaceId
    ? projects.filter((p) => p.workspace_id === activeWorkspaceId)
    : [];

  const chatHistorySidebar = (
    <Sidebar
      user={user}
      activeWorkspace={activeWorkspace}
      sessions={sessionsForActiveWorkspace}
      projects={projectsForActiveWorkspace}
      activeSession={activeSession}
      onSelectSession={(ws, s) => { handleSelectSession(ws, s); setSidebarOpen(false); }}
      onNewProject={handleNewProject}
      onNewSession={handleNewSession}
      onDeleteSession={handleDeleteSession}
      onLogout={onLogout}
      isOpen={sidebarOpen}
      onClose={() => setSidebarOpen(false)}
    />
  );

  const displayName = user?.email ? user.email.split("@")[0] : "User";
  const centralAdminUrl = import.meta.env.VITE_LANDING_ADMIN_URL || "/platform-admin";

  return (
    <div className="main-page-shell">
      <WorkspaceTabs
        workspaces={workspaces}
        activeWorkspaceId={activeWorkspaceId}
        onSelectWorkspace={setActiveWorkspaceId}
        onCreateWorkspace={createWorkspace}
        onRenameWorkspace={updateWorkspace}
        onDeleteWorkspace={deleteWorkspace}
      />
      <section className="main-home-banner">
        <p>Hi, {displayName} welcome</p>
        {user?.is_admin && (
          <div className="main-banner-actions">
            <button className="main-admin-btn" onClick={() => navigate("/admin")}>Open Admin</button>
            <button className="main-admin-btn" onClick={() => window.location.assign(centralAdminUrl)}>Central Admin Hub</button>
          </div>
        )}
      </section>

      <div className="main-layout">
        {/* Mobile hamburger */}
        <button
          className="sidebar-hamburger"
          aria-label="Open navigation"
          onClick={() => setSidebarOpen(true)}
        >
          &#9776;
        </button>

        {/* Dimming backdrop behind sidebar on mobile */}
        <div
          className={`sidebar-backdrop${sidebarOpen ? " sidebar-backdrop--visible" : ""}`}
          onClick={() => setSidebarOpen(false)}
        />

        <div className="left-column">
          <LeftSidebarTabs
            chatHistory={chatHistorySidebar}
            settings={settings}
            onUpdateSettings={handleUpdateWorkspaceSettings}
            profiles={profiles}
            policies={policies}
            usage={toolUsage}
            workspaceId={activeWorkspaceId}
          />
        </div>

        <ChatArea
          session={activeSession}
          workspace={activeWorkspace}
          run={run}
          polling={polling}
          pendingState={activeSession ? pendingBySession[activeSession.id] : null}
          onRunStart={setActiveRunId}
          onPendingStateChange={handlePendingStateChange}
          onSessionRename={handleRenameSession}
          onFilesAdded={handleFilesAdded}
          onCreateSession={
            activeWorkspaceId
              ? () => handleNewSession(activeWorkspaceId, null)
              : null
          }
        />

        {activeSession && (
          <SessionInfoPanel
            session={activeSession}
            run={run}
            events={events}
            workspaceSettings={settings}
            notes={currentNotes}
            onSaveNote={handleSaveNote}
            onDeleteNote={handleDeleteNote}
            files={currentFiles}
            onDeleteFile={handleDeleteFile}
          />
        )}
      </div>
    </div>
  );
}
