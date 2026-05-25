import { useEffect, useState } from "react";
import Spinner from "../components/Spinner";
import { api } from "../api";

function StatCard({ label, value }) {
  return (
    <div className="stat-card">
      <span className="stat-value">{value ?? "—"}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

function ToolCountsTable({ toolCounts }) {
  if (!toolCounts || Object.keys(toolCounts).length === 0) return <p className="muted">No tool data.</p>;
  return (
    <table className="data-table">
      <thead><tr><th>Tool</th><th>Calls</th></tr></thead>
      <tbody>
        {Object.entries(toolCounts)
          .sort((a, b) => b[1] - a[1])
          .map(([tool, count]) => (
            <tr key={tool}><td>{tool}</td><td>{count}</td></tr>
          ))}
      </tbody>
    </table>
  );
}

function WorkspaceTable({ workspaceStats }) {
  if (!workspaceStats || workspaceStats.length === 0) return <p className="muted">No workspaces yet.</p>;
  return (
    <table className="data-table">
      <thead><tr><th>Workspace</th><th>Sessions</th><th>Runs</th></tr></thead>
      <tbody>
        {workspaceStats.map((ws) => (
          <tr key={ws.id}>
            <td>{ws.name}</td>
            <td>{ws.session_count}</td>
            <td>{ws.run_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getDashboardStats()
      .then((d) => { setStats(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <div className="page-shell"><Spinner /></div>;

  return (
    <div className="dashboard-page">
      <h2>Dashboard</h2>
      {error && <p className="error-msg">{error}</p>}

      <div className="stats-cards">
        <StatCard label="Total Runs" value={stats?.total_runs} />
        <StatCard label="Runs Today" value={stats?.runs_today} />
      </div>

      <div className="dashboard-sections">
        <section className="dashboard-section">
          <h3>Tool Calls</h3>
          <ToolCountsTable toolCounts={stats?.tool_counts} />
        </section>
        <section className="dashboard-section">
          <h3>Workspaces</h3>
          <WorkspaceTable workspaceStats={stats?.workspace_stats} />
        </section>
      </div>
    </div>
  );
}

