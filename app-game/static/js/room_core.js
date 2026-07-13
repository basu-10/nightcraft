const RoomCore = (function () {
  let config = null;
  let pollTimer = null;
  let onState = null;
  let gameOverHandled = false;

  const els = {};

  function init(opts) {
    config = opts;
    els.myScore = document.getElementById("myScore");
    els.oppScore = document.getElementById("oppScore");
    els.roundInfo = document.getElementById("roundInfo");
    els.gameOverSection = document.getElementById("gameOverSection");
    els.resultBanner = document.getElementById("resultBanner");
    els.finalScore = document.getElementById("finalScore");
    els.leaveActions = document.getElementById("leaveActions");
    els.leaveBtn = document.getElementById("leaveBtn");
    els.playAgainBtn = document.getElementById("playAgainBtn");

    els.leaveBtn.addEventListener("click", leave);
    els.playAgainBtn.addEventListener("click", playAgain);

    onState = opts.onState || function () {};
    startPolling();
  }

  function stateUrl() {
    return "/game/room/" + config.roomId + "/state";
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(poll, 2000);
    poll();
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function poll() {
    try {
      const res = await fetch(stateUrl());
      if (!res.ok) return;
      const data = await res.json();
      updateScoreboard(data.scores, data.round);
      onState(data);
      if (data.finished && !gameOverHandled) {
        gameOverHandled = true;
        stopPolling();
        showGameOver(data);
      }
    } catch (e) {
      // transient network error; next tick retries
    }
  }

  function updateScoreboard(scores, round) {
    const entries = Object.entries(scores || {});
    let myS = 0;
    let oppS = 0;
    for (const [pid, sc] of entries) {
      if (pid === config.userId) myS = sc;
      else oppS = sc;
    }
    els.myScore.textContent = "You: " + myS;
    els.oppScore.textContent = "Opponent: " + oppS;
    if (round != null) els.roundInfo.textContent = "Round " + (round + 1);
  }

  async function submitMove(moveData) {
    return fetch("/game/room/" + config.roomId + "/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(moveData),
    });
  }

  function scoresFrom(data) {
    const entries = Object.entries(data.scores || {});
    let myS = 0;
    let oppS = 0;
    for (const [pid, sc] of entries) {
      if (pid === config.userId) myS = sc;
      else oppS = sc;
    }
    return { myS, oppS };
  }

  function showGameOver(data) {
    const { myS, oppS } = scoresFrom(data);
    let cls = "draw";
    let text = "DRAW";
    if (data.winner) {
      cls = data.is_winner ? "victory" : "defeat";
      text = data.is_winner ? "VICTORY" : "DEFEAT";
    }
    els.resultBanner.textContent = text;
    els.resultBanner.className = "result-banner " + cls;
    els.finalScore.textContent = "Final Score: " + myS + " - " + oppS;
    els.gameOverSection.classList.remove("hidden");
    els.leaveActions.classList.add("hidden");
  }

  function leave() {
    if (!confirm("Are you sure you want to leave? This will count as a forfeit.")) return;
    stopPolling();
    fetch("/game/room/" + config.roomId + "/leave", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }).finally(function () {
      window.location.href = config.landingUrl;
    });
  }

  function playAgain() {
    window.location.href = config.lobbyUrl + "?game=" + encodeURIComponent(config.gameType);
  }

  return {
    init,
    submitMove,
    updateScoreboard,
    showGameOver,
    getConfig: function () {
      return config;
    },
  };
})();
