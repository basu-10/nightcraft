function renderTttBoard(container, board, opts) {
  opts = opts || {};
  container.innerHTML = "";
  board.forEach(function (cell, i) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ttt-cell";
    if (cell === "X") btn.classList.add("cell-x");
    if (cell === "O") btn.classList.add("cell-o");
    btn.textContent = cell || "";
    if (cell || !opts.enabled) btn.disabled = true;
    if (opts.winningLine && opts.winningLine.indexOf(i) !== -1) {
      btn.classList.add("win");
    }
    btn.addEventListener("click", function () {
      if (opts.enabled && !cell && opts.onClick) opts.onClick(i);
    });
    container.appendChild(btn);
  });
}

function findTttWinningLine(board) {
  const lines = [
    [0, 1, 2],
    [3, 4, 5],
    [6, 7, 8],
    [0, 3, 6],
    [1, 4, 7],
    [2, 5, 8],
    [0, 4, 8],
    [2, 4, 6],
  ];
  for (const line of lines) {
    const [a, b, c] = line;
    if (board[a] && board[a] === board[b] && board[a] === board[c]) {
      return line;
    }
  }
  return null;
}
