(function () {
  "use strict";

  const messagesEl = document.getElementById("messages");
  const logEl = document.getElementById("agent-log");
  const form = document.getElementById("composer");
  const input = document.getElementById("goal-input");
  const dropzone = document.getElementById("dropzone");
  const attachmentsEl = document.getElementById("attachments");
  const sendBtn = document.getElementById("send-btn");
  const assetList = document.getElementById("asset-list");

  const attached = new Set();
  let sessionId = form ? form.dataset.session || "" : "";
  let pollTimer = null;
  let currentRunId = null;
  let lastSeq = -1;
  let currentRunTools = [];
  let currentRunPlan = null;

  function formatTime(date) {
    if (!date) return "";
    const d = new Date(date);
    let hours = d.getHours();
    const minutes = d.getMinutes();
    const ampm = hours >= 12 ? "PM" : "AM";
    hours = hours % 12;
    if (hours === 0) hours = 12;
    const minStr = minutes < 10 ? "0" + minutes : minutes;
    return hours + ":" + minStr + " " + ampm;
  }

  function formatTimestamp(iso) {
    if (!iso) return formatTime(new Date());
    return formatTime(iso);
  }

  function renderMessage(el) {
    const timeEl = el.querySelector(".msg-time");
    if (timeEl && !timeEl.textContent) {
      const ts = timeEl.dataset.timestamp;
      timeEl.textContent = formatTimestamp(ts);
    }
  }

  function addMessage(role, text, refs, runContext) {
    const div = document.createElement("div");
    div.className = "msg msg-" + role;
    div.dataset.role = role;

    if (role === "assistant") {
      const avatar = document.createElement("div");
      avatar.className = "msg-avatar";
      avatar.textContent = "A";
      div.appendChild(avatar);
    }

    const content = document.createElement("div");
    content.className = "msg-content";

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const name = document.createElement("span");
    name.className = "msg-name";
    name.textContent = role === "user" ? "You" : "Alfred";
    const time = document.createElement("span");
    time.className = "msg-time";
    time.textContent = formatTime(new Date());
    if (role === "user") {
      const check = document.createElement("span");
      check.className = "msg-check";
      check.textContent = " ✓";
      time.appendChild(check);
    }
    meta.appendChild(name);
    meta.appendChild(time);
    content.appendChild(meta);

    const body = document.createElement("div");
    body.className = "msg-body";
    body.textContent = text;
    content.appendChild(body);

    if (runContext && runContext.tools && runContext.tools.length) {
      const toolsSection = buildToolsSection(runContext.tools);
      content.appendChild(toolsSection);
    }

    if (runContext && runContext.plan) {
      const planSection = buildPlanSection(runContext.plan);
      content.appendChild(planSection);
    }

    if (refs && refs.length) {
      const refsEl = document.createElement("div");
      refsEl.className = "msg-refs";
      refs.forEach(function (id) {
        const c = document.createElement("span");
        c.className = "chip";
        c.textContent = "Asset #" + id;
        refsEl.appendChild(c);
      });
      content.appendChild(refsEl);
    }

    div.appendChild(content);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function buildToolsSection(tools) {
    const section = document.createElement("div");
    section.className = "section-toggle open";

    const header = document.createElement("div");
    header.className = "section-toggle-header";
    header.innerHTML = '<span>Using tools</span><span class="section-toggle-chevron">&#9662;</span>';
    header.addEventListener("click", function () {
      section.classList.toggle("open");
    });

    const body = document.createElement("div");
    body.className = "section-toggle-body";

    tools.forEach(function (tool) {
      const card = document.createElement("div");
      card.className = "tool-card";

      const icon = document.createElement("div");
      icon.className = "tool-icon";
      icon.textContent = tool.icon || "&#128736;";

      const info = document.createElement("div");
      info.className = "tool-info";
      const name = document.createElement("div");
      name.className = "tool-name";
      name.textContent = tool.name;
      const query = document.createElement("div");
      query.className = "tool-query";
      query.textContent = tool.query || "";
      info.appendChild(name);
      info.appendChild(query);

      const status = document.createElement("div");
      status.className = "tool-status " + (tool.status || "completed");
      const dot = document.createElement("span");
      dot.className = "tool-status-dot";
      const label = document.createElement("span");
      label.textContent = tool.statusLabel || "Completed";
      status.appendChild(dot);
      status.appendChild(label);

      card.appendChild(icon);
      card.appendChild(info);
      card.appendChild(status);
      body.appendChild(card);
    });

    section.appendChild(header);
    section.appendChild(body);
    return section;
  }

  function buildPlanSection(plan) {
    const section = document.createElement("div");
    section.className = "section-toggle";

    const header = document.createElement("div");
    header.className = "section-toggle-header";
    header.innerHTML = '<span>Planning</span><span class="section-toggle-chevron">&#9662;</span>';
    header.addEventListener("click", function () {
      section.classList.toggle("open");
    });

    const body = document.createElement("div");
    body.className = "section-toggle-body";
    body.textContent = plan || "Analyzing goal and selecting tools...";

    section.appendChild(header);
    section.appendChild(body);
    return section;
  }

  function getToolIcon(name) {
    const n = (name || "").toLowerCase();
    if (n.includes("search") && n.includes("web")) return "&#127760;";
    if (n.includes("search") && n.includes("paper")) return "&#128196;";
    if (n.includes("read")) return "&#128212;";
    if (n.includes("summar")) return "&#128220;";
    if (n.includes("write")) return "&#9997;";
    return "&#128736;";
  }

  function addAgentEvent(ev) {
    if (logEl.hidden) logEl.hidden = false;
    const line = document.createElement("div");
    line.className = "ev-" + ev.type;
    let text = "[" + ev.type + "]";
    if (ev.type === "plan" && ev.payload.plan) {
      currentRunPlan = ev.payload.plan.phases ? ev.payload.plan.phases.join(", ") : JSON.stringify(ev.payload.plan);
    } else if (ev.payload && ev.payload.message) {
      text += " " + ev.payload.message;
    } else if (ev.type === "artifact" && ev.payload.title) {
      text += " " + ev.payload.title + " (Asset #" + ev.payload.asset_id + ")";
    } else if (ev.type === "llm_message" && ev.payload.content) {
      text = ev.payload.content;
    } else if (ev.type === "tool_call" && ev.payload.name) {
      const toolName = ev.payload.name;
      const toolQuery = ev.payload.args && ev.payload.args.query ? ev.payload.args.query : "";
      currentRunTools.push({
        name: toolName,
        query: toolQuery,
        status: "in-progress",
        statusLabel: "In progress",
        icon: getToolIcon(toolName),
      });
      text += " " + toolName + " " + JSON.stringify(ev.payload.args || {});
    } else if (ev.type === "tool_result" && ev.payload.name) {
      const tool = currentRunTools.find(function (t) { return t.name === ev.payload.name && t.status === "in-progress"; });
      if (tool) {
        tool.status = "completed";
        tool.statusLabel = "Completed";
      }
      text += " " + ev.payload.name + " → " + JSON.stringify(ev.payload.result || {}).slice(0, 200);
    }
    line.textContent = text;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function attachChip(id, title) {
    if (attached.has(id)) return;
    attached.add(id);
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.dataset.id = id;
    chip.textContent = title + " #" + id;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "×";
    btn.addEventListener("click", function () {
      attached.delete(id);
      chip.remove();
    });
    chip.appendChild(btn);
    attachmentsEl.appendChild(chip);
  }

  if (assetList) {
    assetList.querySelectorAll(".asset-attach").forEach(function (btn) {
      btn.addEventListener("click", function () {
        attachChip(btn.dataset.id, btn.dataset.title);
      });
    });
  }

  ["dragenter", "dragover"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", function (e) {
    const files = e.dataTransfer.files;
    if (files && files.length) {
      for (let i = 0; i < files.length; i++) uploadFile(files[i]);
    }
  });

  function uploadFile(file) {
    const fd = new FormData();
    fd.append("file", file);
    fetch("/alfred/api/ingest", { method: "POST", body: fd })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.asset_id) {
          attachChip(String(data.asset_id), data.title);
          input.placeholder = "Ask Alfred to change/reformat the attached file…";
        } else if (data.error) {
          alert("Ingest failed: " + data.error);
        }
      })
      .catch(function (err) { alert("Upload failed: " + err); });
  }

  function pollEvents() {
    if (!currentRunId) return;
    fetch("/alfred/api/runs/" + currentRunId + "/events?after=" + lastSeq)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        const prevStatus = document.getElementById("run-status-banner").dataset.status;
        (data.events || []).forEach(function (ev) {
          if (ev.seq > lastSeq) lastSeq = ev.seq;
          if (ev.type === "llm_message" && ev.payload && ev.payload.content && !ev.payload.final) {
            // live thinking; shown in log only
          }
          if (ev.type === "artifact") {
            addMessage("assistant", "Created report: " + ev.payload.title + " (Asset #" + ev.payload.asset_id + ")");
          }
          if (ev.type === "status" && ev.payload.status === "done") {
            const runContext = {
              tools: currentRunTools.slice(),
              plan: currentRunPlan,
            };
            addMessage("assistant", ev.payload.summary || "Done.", [], runContext);
            currentRunTools = [];
            currentRunPlan = null;
          }
          addAgentEvent(ev);
        });
        if (data.status && data.status !== prevStatus) {
          showRunStatus(data.status, currentRunId);
        }
        if (data.status === "done" || data.status === "error" || data.status === "fatal") {
          stopPolling();
          sendBtn.disabled = false;
        }
      })
      .catch(function () { /* keep polling; heartbeat protects liveness */ });
  }

  function showRunStatus(status, runId) {
    const banner = document.getElementById("run-status-banner");
    if (!banner) return;
    banner.dataset.status = status;
    banner.className = "run-status-banner status-" + status;
    banner.hidden = false;
    let label = status;
    if (status === "running") label = "Running…";
    else if (status === "queued") label = "Queued…";
    else if (status === "done") label = "Run completed";
    else if (status === "error") label = "Run ended with an error";
    else if (status === "fatal") label = "Run aborted: policy limit reached";
    let html = '<span class="run-status-dot"></span><span class="run-status-label">' + label + "</span>";
    if (status === "fatal") {
      html += '<a class="run-status-action" href="/alfred/ask?rerun=' + encodeURIComponent(runId || "") + '">Re-run with looser limits</a>';
    } else if (status === "error") {
      html += '<a class="run-status-action" href="/alfred/ask?rerun=' + encodeURIComponent(runId || "") + '">Re-run</a>';
    }
    banner.innerHTML = html;
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollEvents, 1500);
  }
  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  startPolling();
  setInterval(function () {
    fetch("/alfred/api/heartbeat", { method: "GET" }).catch(function () {});
  }, 15000);

  messagesEl.querySelectorAll(".msg").forEach(function (el) {
    renderMessage(el);
  });

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const goal = input.value.trim();
      if (!goal) return;
      addMessage("user", goal, Array.from(attached));
      input.value = "";
      sendBtn.disabled = true;
      currentRunTools = [];
      currentRunPlan = null;

      const payload = {
        goal: goal,
        session_id: sessionId,
        referenced_asset_ids: Array.from(attached),
        relax_bounds: form.dataset.relaxBounds === "1",
      };
      fetch("/alfred/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.run_id) {
            currentRunId = data.run_id;
            sessionId = data.session_id || sessionId;
            lastSeq = -1;
            startPolling();
          } else {
            addMessage("assistant", "Error: " + (data.error || "could not start run"));
            sendBtn.disabled = false;
          }
        })
        .catch(function (err) {
          addMessage("assistant", "Error: " + err);
          sendBtn.disabled = false;
        });
    });
  }

  document.querySelectorAll(".tool-btn[data-tool]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const tool = btn.dataset.tool;
      if (tool === "attach") {
        input.click();
      } else {
        input.placeholder = "Use " + btn.textContent.trim() + " to find information...";
        input.focus();
      }
    });
  });
})();
