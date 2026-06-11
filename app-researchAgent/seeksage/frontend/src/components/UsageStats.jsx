import { useMemo } from "react";

const USAGE_STATS_HEADER = "### Usage Stats";
const TOOLS_MARKER = "- **Tools:**";

const METRIC_GROUPS = [
  {
    title: "Work",
    items: [
      { label: "Searches", value: "searches" },
      { label: "Tool calls", value: "tool_calls" },
      { label: "Tool results", value: "tool_results" },
      { label: "Cache hits", value: "tool_cache_hits" },
    ],
  },
  {
    title: "LLM",
    items: [
      { label: "LLM calls", value: "llm_calls" },
      { label: "LLM replies", value: "llm_replies" },
      { label: "LLM retries", value: "llm_retries" },
      { label: "LLM errors", value: "llm_errors" },
    ],
  },
  {
    title: "Reliability",
    items: [
      { label: "Tool errors", value: "tool_errors" },
      { label: "Tool timeouts", value: "tool_timeouts" },
      { label: "Run time", value: "duration_ms", format: "duration" },
      { label: "Model", value: "used_model", format: "text" },
    ],
  },
];

function toNumber(value) {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number : 0;
}

function formatDuration(value) {
  if (value === null || value === undefined || value === "") return "n/a";
  const ms = Number(value);
  if (!Number.isFinite(ms)) return String(value);
  if (ms < 1000) return "<1s";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) return `${(ms / 1000).toFixed(1)}s`;
  if (seconds === 0) return `${minutes}m`;
  return `${minutes}m ${seconds}s`;
}

function formatValue(metric, stats) {
  const raw = stats[metric.value];
  if (metric.format === "duration") return formatDuration(raw);
  if (metric.format === "text") return raw || "n/a";
  return toNumber(raw);
}

function entriesFromCounts(counts) {
  if (!counts || typeof counts !== "object" || Array.isArray(counts)) return [];
  return Object.entries(counts)
    .filter(([name, count]) => name && count)
    .sort((a, b) => String(a[0]).localeCompare(String(b[0])));
}

function CountChips({ title, entries, emptyText }) {
  const hasEntries = entries.length > 0;

  return (
    <div className="usage-stats-breakdown">
      <div className="usage-stats-breakdown-title">{title}</div>
      {hasEntries ? (
        <div className="usage-stats-chips">
          {entries.map(([name, count]) => (
            <span className="usage-stats-chip" key={name}>
              {name} <strong>{count}</strong>
            </span>
          ))}
        </div>
      ) : (
        <div className="usage-stats-empty">{emptyText}</div>
      )}
    </div>
  );
}

export function splitUsageStatsMarkdown(content, stats) {
  const text = content || "";
  if (!stats || !text.includes(USAGE_STATS_HEADER)) {
    return { hasUsageStats: false, markdown: text };
  }

  const start = text.indexOf(USAGE_STATS_HEADER);
  let end = -1;
  const markerIndex = text.indexOf(TOOLS_MARKER, start);

  if (markerIndex !== -1) {
    const blankAfterTools = text.indexOf("\n\n", markerIndex);
    end = blankAfterTools === -1 ? text.length : blankAfterTools;
  } else {
    const blankAfterHeader = text.indexOf("\n\n", start);
    end = blankAfterHeader === -1 ? text.length : blankAfterHeader;
  }

  const before = text.slice(0, start).trimEnd();
  const after = end === -1 ? "" : text.slice(end).trimStart();
  const markdown = [before, after].filter(Boolean).join("\n\n");

  return { hasUsageStats: true, markdown };
}

export default function UsageStats({ stats }) {
  const normalizedStats = useMemo(() => ({ ...(stats || {}) }), [stats]);
  const llmModels = entriesFromCounts(normalizedStats.llm_model_counts);
  const tools = entriesFromCounts(normalizedStats.tool_counts);
  const model = normalizedStats.used_model || "n/a";
  const duration = formatDuration(normalizedStats.duration_ms);

  return (
    <section className="usage-stats-card" aria-label="Usage stats">
      <div className="usage-stats-header">
        <div>
          <p className="usage-stats-kicker">Run summary</p>
          <h3 className="usage-stats-title">Usage Stats</h3>
        </div>
        <div className="usage-stats-pills" aria-label="Run metadata">
          <span className="usage-stats-pill">{duration}</span>
          <span className="usage-stats-pill">{model}</span>
        </div>
      </div>

      <div className="usage-stats-grid">
        {METRIC_GROUPS.map((group) => (
          <div className="usage-stats-group" key={group.title}>
            <div className="usage-stats-group-title">{group.title}</div>
            <div className="usage-stats-group-grid">
              {group.items.map((metric) => (
                <div className="usage-stat-tile" key={metric.value}>
                  <div className="usage-stat-label">{metric.label}</div>
                  <div className="usage-stat-value">{formatValue(metric, normalizedStats)}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="usage-stats-detail-row">
        <CountChips title="LLM models" entries={llmModels} emptyText="No LLM model breakdown recorded." />
        <CountChips title="Tools" entries={tools} emptyText="No tool breakdown recorded." />
      </div>
    </section>
  );
}
