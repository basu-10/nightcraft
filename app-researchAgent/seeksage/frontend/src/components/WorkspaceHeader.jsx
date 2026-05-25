export default function WorkspaceHeader({ workspace, onSettings }) {
  if (!workspace) return null;
  return (
    <div className="workspace-header">
      <span
        className="workspace-color-dot"
        style={{ background: workspace.color || "#4A90D9" }}
      />
      <span className="workspace-name">{workspace.name}</span>
      {onSettings && (
        <button
          className="icon-btn"
          onClick={onSettings}
          aria-label="Workspace settings"
          title="Workspace settings"
        >
          ⚙
        </button>
      )}
    </div>
  );
}
