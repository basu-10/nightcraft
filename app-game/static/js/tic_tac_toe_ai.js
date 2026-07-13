const TTT_AI = (function () {
  const TIERS = {
    1: "Recruit",
    2: "Rookie",
    3: "Grunt",
    4: "Veteran",
    5: "Commander",
  };

  function empties(board) {
    const out = [];
    board.forEach(function (c, i) {
      if (c === null) out.push(i);
    });
    return out;
  }

  function winner(board) {
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
    for (const [a, b, c] of lines) {
      if (board[a] && board[a] === board[b] && board[a] === board[c]) return board[a];
    }
    return null;
  }

  function randomChoice(list) {
    return list[Math.floor(Math.random() * list.length)];
  }

  function findWinningMove(board, symbol) {
    const empty = empties(board);
    for (const i of empty) {
      board[i] = symbol;
      const w = winner(board);
      board[i] = null;
      if (w === symbol) return i;
    }
    return -1;
  }

  function minimax(board, ai, human, current, depth) {
    const w = winner(board);
    if (w === ai) return { score: 10 - depth };
    if (w === human) return { score: depth - 10 };
    const empty = empties(board);
    if (empty.length === 0) return { score: 0 };

    let best = current === ai ? { score: -Infinity } : { score: Infinity };
    for (const i of empty) {
      board[i] = current;
      const res = minimax(board, ai, human, current === ai ? human : ai, depth + 1);
      board[i] = null;
      if (current === ai) {
        if (res.score > best.score) best = { score: res.score, move: i };
      } else {
        if (res.score < best.score) best = { score: res.score, move: i };
      }
    }
    return best;
  }

  function chooseMove(board, tier, mySymbol) {
    const opp = mySymbol === "X" ? "O" : "X";
    const empty = empties(board);
    if (empty.length === 0) return -1;

    switch (tier) {
      case 1:
        return randomChoice(empty);
      case 2: {
        const win = findWinningMove(board, mySymbol);
        if (win !== -1) return win;
        if (Math.random() < 0.6) {
          const blk = findWinningMove(board, opp);
          if (blk !== -1) return blk;
        }
        return randomChoice(empty);
      }
      case 3: {
        const win = findWinningMove(board, mySymbol);
        if (win !== -1) return win;
        const blk = findWinningMove(board, opp);
        if (blk !== -1) return blk;
        return randomChoice(empty);
      }
      case 4: {
        if (Math.random() < 0.25) return randomChoice(empty);
        return minimax(board, mySymbol, opp, mySymbol, 0).move;
      }
      case 5:
      default:
        return minimax(board, mySymbol, opp, mySymbol, 0).move;
    }
  }

  return { TIERS, chooseMove, winner };
})();
