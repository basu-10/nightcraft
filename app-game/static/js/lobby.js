const Lobby = (function () {
  let opts = null;
  let startTs = 0;
  let timer = null;

  const waitingSection = document.getElementById("waitingSection");
  const foundSection = document.getElementById("foundSection");
  const timeoutSection = document.getElementById("timeoutSection");
  const statusText = document.getElementById("statusText");
  const cancelBtn = document.getElementById("cancelBtn");
  const retryBtn = document.getElementById("retryBtn");

  function init(o) {
    opts = o;
    startTs = Date.now();
    cancelBtn.addEventListener("click", cancel);
    retryBtn.addEventListener("click", function () {
      window.location.reload();
    });
    join();
    startPolling();
  }

  function join() {
    return fetch(opts.joinUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game: opts.gameType }),
    });
  }

  function startPolling() {
    stop();
    timer = setInterval(poll, 2000);
    poll();
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function poll() {
    fetch(opts.pollUrl)
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.matched) {
          stop();
          showFound(data.room_id);
        } else if (Date.now() - startTs > opts.timeoutMs) {
          stop();
          showTimeout();
        }
      })
      .catch(function () {});
  }

  function showFound(roomId) {
    waitingSection.classList.add("hidden");
    foundSection.classList.remove("hidden");
    setTimeout(function () {
      window.location.href = "/game/room/" + roomId;
    }, 500);
  }

  function showTimeout() {
    waitingSection.classList.add("hidden");
    timeoutSection.classList.remove("hidden");
  }

  function cancel() {
    stop();
    fetch(opts.cancelUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game: opts.gameType }),
    }).finally(function () {
      window.location.href = opts.landingUrl;
    });
  }

  return { init };
})();
