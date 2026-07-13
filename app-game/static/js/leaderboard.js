const Leaderboard = (function () {
  let opts = null;
  let currentGame = null;

  const body = document.getElementById("lbBody");
  const meEl = document.getElementById("lbMe");
  const tabs = document.querySelectorAll(".lb-tab");

  function init(o) {
    opts = o;
    currentGame = o.initialGame;
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        currentGame = tab.dataset.game;
        load();
      });
    });
    load();
  }

  function load() {
    tabs.forEach(function (tab) {
      tab.classList.toggle("active", tab.dataset.game === currentGame);
    });
    fetch(opts.dataUrl + encodeURIComponent(currentGame))
      .then(function (r) {
        return r.json();
      })
      .then(render)
      .catch(function () {
        body.innerHTML = '<tr><td colspan="6" class="lb-empty">Failed to load.</td></tr>';
      });
  }

  function shortId(id) {
    if (!id) return "—";
    if (id.length > 18) return id.slice(0, 16) + "…";
    return id;
  }

  function render(data) {
    const rows = data.leaderboard || [];
    body.innerHTML = "";
    if (rows.length === 0) {
      body.innerHTML =
        '<tr><td colspan="6" class="lb-empty">No ranked players yet. Go win some games!</td></tr>';
    } else {
      rows.forEach(function (row, idx) {
        const tr = document.createElement("tr");
        if (data.me && data.me.rank === idx + 1) tr.className = "lb-me";
        tr.innerHTML =
          '<td class="rank">' + (idx + 1) + "</td>" +
          "<td>" + shortId(row.user_id) + "</td>" +
          '<td class="elo">' + row.elo + "</td>" +
          "<td>" + row.wins + "</td>" +
          "<td>" + row.losses + "</td>" +
          "<td>" + row.draws + "</td>";
        body.appendChild(tr);
      });
    }

    if (data.me) {
      const s = data.me.stats;
      meEl.classList.remove("hidden");
      meEl.innerHTML =
        "Your rank: <strong>#" + data.me.rank + "</strong> · ELO " + data.me.elo +
        " · W " + s.wins + " / L " + s.losses + " / D " + s.draws;
    } else {
      meEl.classList.remove("hidden");
      meEl.textContent = "Log in to be ranked. Guests play unranked.";
    }
  }

  return { init };
})();
