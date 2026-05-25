import { useState, useEffect, useCallback } from "react";
import { api } from "../api";

export function useSessions(workspaceId) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listSessions(workspaceId);
      setSessions(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const createSession = useCallback(
    async (title = "New Chat", projectId = null) => {
      const session = await api.createSession(workspaceId, title, projectId);
      setSessions((prev) => [session, ...prev]);
      return session;
    },
    [workspaceId]
  );

  const updateSession = useCallback(async (sessionId, payload) => {
    const session = await api.updateSession(sessionId, payload);
    setSessions((prev) => prev.map((s) => (s.id === sessionId ? session : s)));
    return session;
  }, []);

  const deleteSession = useCallback(async (sessionId) => {
    await api.deleteSession(sessionId);
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
  }, []);

  return { sessions, loading, error, reload: load, createSession, updateSession, deleteSession };
}
