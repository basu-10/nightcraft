import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

export function useWorkspaceSettings(workspaceId) {
  const [settings, setSettings] = useState({ profile_id: "", tool_policy_id: "", tool_caps: {} });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.getWorkspaceSettings(workspaceId);
      setSettings({
        profile_id: data?.profile_id || "",
        tool_policy_id: data?.tool_policy_id || "",
        tool_caps: data?.tool_caps || {},
      });
    } catch {
      // Graceful fallback when dedicated settings endpoint is not yet available.
      try {
        const workspace = await api.getWorkspace(workspaceId);
        setSettings({
          profile_id: workspace?.profile_id || "",
          tool_policy_id: workspace?.tool_policy_id || "",
          tool_caps: workspace?.tool_caps || {},
        });
      } catch (err) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const updateSettings = useCallback(async (patch) => {
    if (!workspaceId) return null;
    try {
      const data = await api.updateWorkspaceSettings(workspaceId, patch);
      setSettings((prev) => ({ ...prev, ...data }));
      return data;
    } catch {
      const data = await api.updateWorkspace(workspaceId, patch);
      setSettings((prev) => ({
        ...prev,
        profile_id: data?.profile_id || prev.profile_id,
        tool_policy_id: data?.tool_policy_id || prev.tool_policy_id,
        tool_caps: data?.tool_caps || prev.tool_caps,
      }));
      return data;
    }
  }, [workspaceId]);

  return { settings, loading, error, reload: load, updateSettings };
}
