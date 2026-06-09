import { Children, cloneElement, isValidElement, useEffect, useMemo, useState } from "react";
import Navbar from "./Navbar";
import { useWorkspaces } from "../hooks/useWorkspaces";
import { useNotifications } from "../hooks/useNotifications";

const ACTIVE_WS_KEY = "chotu.activeWorkspaceId";

export default function AuthenticatedShell({ user, onLogout, children }) {
  const { workspaces, createWorkspace, updateWorkspace, deleteWorkspace } = useWorkspaces();
  const { unreadCount } = useNotifications();
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(() => localStorage.getItem(ACTIVE_WS_KEY) || "");

  useEffect(() => {
    if (!activeWorkspaceId && workspaces.length > 0) {
      setActiveWorkspaceId(workspaces[0].id);
      return;
    }
    if (activeWorkspaceId && !workspaces.find((w) => w.id === activeWorkspaceId)) {
      if (workspaces.length > 0) {
        setActiveWorkspaceId(workspaces[0].id);
      } else {
        setActiveWorkspaceId("");
      }
    }
  }, [activeWorkspaceId, workspaces]);

  useEffect(() => {
    if (activeWorkspaceId) {
      localStorage.setItem(ACTIVE_WS_KEY, activeWorkspaceId);
    }
  }, [activeWorkspaceId]);

  const activeWorkspace = useMemo(
    () => workspaces.find((ws) => ws.id === activeWorkspaceId) || null,
    [workspaces, activeWorkspaceId]
  );

  const injectedProps = {
    workspaces,
    activeWorkspace,
    activeWorkspaceId,
    setActiveWorkspaceId,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
  };

  const injectWorkspaceProps = (node) => {
    if (!isValidElement(node)) return node;

    const childNodes = node.props?.children;
    if (childNodes == null) {
      return cloneElement(node, injectedProps);
    }

    const nextChildren = Children.map(childNodes, (child) => injectWorkspaceProps(child));
    return cloneElement(node, { ...injectedProps, children: nextChildren });
  };

  const childWithProps = injectWorkspaceProps(children);

  return (
    <div className="app-shell">
      <Navbar user={user} unreadCount={unreadCount} onLogout={onLogout} />
      <main className="shell-body">{childWithProps}</main>
    </div>
  );
}
