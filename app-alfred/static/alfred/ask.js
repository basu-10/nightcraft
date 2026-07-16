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

  function addMessage(role, text, refs) {
    const div = document.createElement("div");
    div.className = "msg msg-" + role;
    const roleEl = document.createElement("div");
    roleEl.className = "msg-role";
    roleEl.textContent = role;
    const body = document.createElement("div");
    body.className = "msg-body";
    body.textContent = text;
    div.appendChild(roleEl);
    div.appendChild(body);
    if (refs && refs.length) {
      const refsEl = document.createElement("div");
      refsEl.className = "msg-refs";
      refs.forEach(function (id) {
        const c = document.createElement("span");
        c.className = "chip";
        c.textContent = "Asset #" + id;
        refsEl.appendChild(c);
      });
      div.appendChild(refsEl);
    }
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addAgentEvent(ev) {
    if (logEl.hidden) logEl.hidden = false;
    const line = document.createElement("div");
    line.className = "ev-" + ev.type;
    let text = "[" + ev.type + "]";
    if (ev.type === "plan" && ev.payload.plan) {
      text += " " + JSON.stringify(ev.payload.plan.phases);
    } else if (ev.payload && ev.payload.message) {
      text += " " + ev.payload.message;
    } else if (ev.type === "artifact" && ev.payload.title) {
      text += " " + ev.payload.title + " (Asset #" + ev.payload.asset_id + ")";
    } else if (ev.type === "llm_message" && ev.payload.content) {
      text = ev.payload.content;
    } else if (ev.type === "tool_call" && ev.payload.name) {
      text += " " + ev.payload.name + " " + JSON.stringify(ev.payload.args || {});
    } else if (ev.type === "tool_result" && ev.payload.name) {
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

  // Drag and drop a file -> ingest -> attach chip.
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
        (data.events || []).forEach(function (ev) {
          if (ev.seq > lastSeq) lastSeq = ev.seq;
          if (ev.type === "llm_message" && ev.payload && ev.payload.content && !ev.payload.final) {
            // live thinking; shown in log only
          }
          if (ev.type === "artifact") {
            addMessage("assistant", "Created report: " + ev.payload.title + " (Asset #" + ev.payload.asset_id + ")");
          }
          if (ev.type === "status" && ev.payload.status === "done") {
            addMessage("assistant", ev.payload.summary || "Done.");
          }
          addAgentEvent(ev);
        });
        if (data.status === "done" || data.status === "error") {
          stopPolling();
          sendBtn.disabled = false;
        }
      })
      .catch(function () { /* keep polling; heartbeat protects liveness */ });
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollEvents, 1500);
  }
  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  // Heartbeat every ~15s while tab open (§11).
  startPolling();
  setInterval(function () {
    fetch("/alfred/api/heartbeat", { method: "GET" }).catch(function () {});
  }, 15000);

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const goal = input.value.trim();
      if (!goal) return;
      addMessage("user", goal, Array.from(attached));
      input.value = "";
      sendBtn.disabled = true;

      const payload = {
        goal: goal,
        session_id: sessionId,
        referenced_asset_ids: Array.from(attached),
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
})();
