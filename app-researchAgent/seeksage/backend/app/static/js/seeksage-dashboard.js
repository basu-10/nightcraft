function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
  }
}

function renderList(id, items) {
  const node = document.getElementById(id);
  if (!node) {
    return;
  }
  node.innerHTML = "";
  if (!items.length) {
    const li = document.createElement("li");
    li.textContent = "No data yet.";
    node.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    node.appendChild(li);
  }
}

const API_BASE = window.SEEK_API_BASE || "";

async function loadStats() {
  try {
    const response = await fetch(`${API_BASE}/api/dashboard/stats`, {
      credentials: "include",
      headers: { "Accept": "application/json" },
    });

    if (!response.ok) {
      throw new Error("Failed to load dashboard stats.");
    }

    const data = await response.json();
    setText("total-runs", String(data.total_runs ?? 0));
    setText("runs-today", String(data.runs_today ?? 0));

    const workspaceRows = (data.workspace_stats || []).map((item) => {
      const runs = item.run_count ?? 0;
      const sessions = item.session_count ?? 0;
      return `${item.name}: ${runs} runs, ${sessions} sessions`;
    });
    renderList("workspace-stats", workspaceRows);

    const toolCounts = Object.entries(data.tool_counts || {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, count]) => `${name}: ${count}`);
    renderList("tool-counts", toolCounts);
  } catch (error) {
    renderList("workspace-stats", [error.message || "Failed to load stats."]);
    renderList("tool-counts", ["Unavailable"]);
  }
}

void loadStats();
