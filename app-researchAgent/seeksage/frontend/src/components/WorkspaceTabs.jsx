import { useMemo, useState } from "react";

const COLORS = ["#4A90D9", "#7B68EE", "#50C878", "#FF7F50", "#FFD700", "#20B2AA"];

function nextColor(existingCount) {
  return COLORS[existingCount % COLORS.length];
}

export default function WorkspaceTabs({
  workspaces,
  activeWorkspaceId,
  onSelectWorkspace,
  onCreateWorkspace,
  onRenameWorkspace,
  onDeleteWorkspace,
}) {
  const sorted = useMemo(() => [...(workspaces || [])], [workspaces]);
  const [menuState, setMenuState] = useState({ open: false, x: 0, y: 0, workspace: null });

  const createWorkspace = async () => {
    const name = window.prompt("New workspace name:", "New Workspace");
    if (!name?.trim()) return;
    await onCreateWorkspace({
      name: name.trim(),
      color: nextColor(sorted.length),
    });
  };

  const renameWorkspace = async (workspace) => {
    const name = window.prompt("Rename workspace:", workspace.name || "");
    if (!name?.trim() || name.trim() === workspace.name) return;
    await onRenameWorkspace(workspace.id, { name: name.trim() });
  };

  const deleteWorkspace = async (workspace) => {
    if (!window.confirm(`Delete workspace ${workspace.name}?`)) return;
    await onDeleteWorkspace(workspace.id);
  };

  const openContextMenu = (e, workspace) => {
    e.preventDefault();
    setMenuState({ open: true, x: e.clientX, y: e.clientY, workspace });
  };

  const closeContextMenu = () => {
    setMenuState((prev) => ({ ...prev, open: false }));
  };

  const handleRenameFromMenu = async () => {
    if (!menuState.workspace) return;
    await renameWorkspace(menuState.workspace);
    closeContextMenu();
  };

  const handleCloseFromMenu = async () => {
    if (!menuState.workspace) return;
    await deleteWorkspace(menuState.workspace);
    closeContextMenu();
  };

  return (
    <div className="workspace-tabs-row">
      <div className="workspace-tabs-scroll">
        {sorted.map((ws) => (
          <div
            key={ws.id}
            className={`workspace-tab ${activeWorkspaceId === ws.id ? "workspace-tab--active" : ""}`}
            onClick={() => onSelectWorkspace(ws.id)}
            onContextMenu={(e) => openContextMenu(e, ws)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && onSelectWorkspace(ws.id)}
            title="Right-click for workspace actions"
          >
            <span className="workspace-tab-dot" style={{ background: ws.color || COLORS[0] }} />
            <span className="workspace-tab-name">{ws.name}</span>
          </div>
        ))}
      </div>
      <button className="workspace-tab workspace-tab--new" onClick={createWorkspace}>+ Workspace</button>

      {menuState.open && (
        <>
          <div className="workspace-menu-backdrop" onClick={closeContextMenu} />
          <div
            className="workspace-context-menu"
            style={{ left: menuState.x, top: menuState.y }}
            role="menu"
            aria-label="Workspace actions"
          >
            <button className="workspace-context-item" onClick={handleRenameFromMenu}>Rename workspace</button>
            <button className="workspace-context-item workspace-context-item--danger" onClick={handleCloseFromMenu}>Close workspace</button>
          </div>
        </>
      )}
    </div>
  );
}
