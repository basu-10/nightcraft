import { useState, useEffect, useCallback } from "react";
import { api } from "../api";

export function useWorkspaces() {
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listWorkspaces();
      setWorkspaces(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createWorkspace = useCallback(async (payload) => {
    const ws = await api.createWorkspace(payload);
    setWorkspaces((prev) => [...prev, ws]);
    return ws;
  }, []);

  const updateWorkspace = useCallback(async (workspaceId, payload) => {
    const ws = await api.updateWorkspace(workspaceId, payload);
    setWorkspaces((prev) => prev.map((w) => (w.id === workspaceId ? ws : w)));
    return ws;
  }, []);

  const deleteWorkspace = useCallback(async (workspaceId) => {
    await api.deleteWorkspace(workspaceId);
    setWorkspaces((prev) => prev.filter((w) => w.id !== workspaceId));
  }, []);

  return { workspaces, loading, error, reload: load, createWorkspace, updateWorkspace, deleteWorkspace };
}
