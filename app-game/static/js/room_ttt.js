(function () {
  const boardEl = document.getElementById("tttBoard");
  const promptEl = document.getElementById("prompt");
  const rpsEl = document.getElementById("rpsSection");
  const roundResultEl = document.getElementById("roundResult");

  rpsEl.classList.add("hidden");
  boardEl.classList.remove("hidden");

  let busy = false;

  function renderState(data) {
    if (data.finished) {
      const line = findTttWinningLine(data.current_round.board);
      renderTttBoard(boardEl, data.current_round.board, {
        enabled: false,
        winningLine: line,
      });
      promptEl.classList.add("hidden");
      return;
    }

    const board = data.current_round.board;
    const myTurn = data.my_turn;

    renderTttBoard(boardEl, board, {
      enabled: myTurn && !busy,
      onClick: function (cell) {
        busy = true;
        promptEl.textContent = "Move sent…";
        RoomCore.submitMove({ cell: cell }).catch(function () {
          busy = false;
          promptEl.textContent = "Network error — try again.";
        });
      },
    });

    promptEl.classList.remove("hidden");
    promptEl.textContent = myTurn ? "Your move!" : "Opponent is thinking…";
  }

  RoomCore.init({
    roomId: RoomConfig.roomId,
    gameType: RoomConfig.gameType,
    userId: RoomConfig.userId,
    landingUrl: RoomConfig.landingUrl,
    lobbyUrl: RoomConfig.lobbyUrl,
    onState: renderState,
  });
})();
