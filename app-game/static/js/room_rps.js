(function () {
  const rpsEl = document.getElementById("rpsSection");
  const boardEl = document.getElementById("tttBoard");
  const promptEl = document.getElementById("prompt");
  const roundResultEl = document.getElementById("roundResult");
  const choiceBtns = document.querySelectorAll(".choice-btn");

  boardEl.classList.add("hidden");
  rpsEl.classList.remove("hidden");

  let myMove = null;
  let locked = false;

  function setDisabled(disabled) {
    choiceBtns.forEach(function (b) {
      b.disabled = disabled;
    });
  }

  function clearSelected() {
    choiceBtns.forEach(function (b) {
      b.classList.remove("selected");
    });
  }

  choiceBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (locked || myMove) return;
      myMove = btn.dataset.choice;
      clearSelected();
      btn.classList.add("selected");
      locked = true;
      setDisabled(true);
      promptEl.textContent = "Waiting for opponent…";
      RoomCore.submitMove({ choice: myMove }).catch(function () {
        locked = false;
        myMove = null;
        clearSelected();
        setDisabled(false);
        promptEl.textContent = "Network error — try again.";
      });
    });
  });

  function renderState(data) {
    if (data.finished) {
      rpsEl.classList.add("hidden");
      return;
    }

    myMove = data.my_move ? data.my_move.choice : null;
    const bothMoved = data.my_move && data.opponent_moved;

    if (bothMoved && data.results && data.results[RoomConfig.userId]) {
      const myR = data.results[RoomConfig.userId];
      let text =
        "You chose " + myR.choice + ". Opponent chose " + myR.opponent_choice + ". ";
      text += myR.result === "win" ? "You Win!" : myR.result === "lose" ? "You Lose!" : "Tie!";
      roundResultEl.textContent = text;
      roundResultEl.className = "result " + (myR.result === "win" ? "success" : myR.result === "lose" ? "failure" : "");
      roundResultEl.classList.remove("hidden");
      setDisabled(true);
      promptEl.classList.add("hidden");
      return;
    }

    roundResultEl.classList.add("hidden");
    if (myMove) {
      locked = true;
      clearSelected();
      choiceBtns.forEach(function (b) {
        if (b.dataset.choice === myMove) b.classList.add("selected");
      });
      setDisabled(true);
      promptEl.classList.remove("hidden");
      promptEl.textContent = "Waiting for opponent…";
    } else {
      locked = false;
      clearSelected();
      setDisabled(false);
      promptEl.classList.remove("hidden");
      promptEl.textContent = "Make your move!";
    }
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
