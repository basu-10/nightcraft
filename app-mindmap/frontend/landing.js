import { getAllBooks, createNewBook, saveBook, deleteBook } from "./db.js";

const bookListEl = document.getElementById("book-list");
const emptyStateEl = document.getElementById("book-list-empty");
const btnCreate = document.getElementById("btn-create-book");
const btnImport = document.getElementById("btn-import-book");
const importInput = document.getElementById("import-input");

function formatTime(iso) {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m ago";
  const hours = Math.floor(mins / 60);
  if (hours < 24) return hours + "h ago";
  const days = Math.floor(hours / 24);
  if (days < 30) return days + "d ago";
  return new Date(iso).toLocaleDateString();
}

function renderBooks(books) {
  const existing = bookListEl.querySelectorAll(".book-card");
  existing.forEach((el) => el.remove());

  if (!books || books.length === 0) {
    emptyStateEl.style.display = "block";
    return;
  }
  emptyStateEl.style.display = "none";

  books.forEach((book) => {
    const card = document.createElement("div");
    card.className = "book-card";
    card.dataset.bookId = book.id;
    card.innerHTML = `
      <div class="book-card-header">
        <h3 class="book-card-title">${escapeHtml(book.title || "Untitled")}</h3>
        <button class="book-card-delete" title="Delete book">&times;</button>
      </div>
      <div class="book-card-meta">
        <span>${book.canvasCount} canvas${book.canvasCount !== 1 ? "es" : ""}</span>
        <span>&middot;</span>
        <span>${book.cardCount} card${book.cardCount !== 1 ? "s" : ""}</span>
      </div>
      <div class="book-card-time">Last opened ${formatTime(book.updatedAt)}</div>
    `;

    card.addEventListener("click", (e) => {
      if (e.target.closest(".book-card-delete")) return;
      openBook(book.id);
    });

    const deleteBtn = card.querySelector(".book-card-delete");
    deleteBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (confirm('Delete "' + (book.title || "Untitled") + '" and all its canvases?')) {
        await deleteBook(book.id);
        renderBooks(await getAllBooks());
      }
    });

    bookListEl.appendChild(card);
  });
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function openBook(id) {
  window.location.href = "/?bookId=" + encodeURIComponent(id);
}

btnCreate.addEventListener("click", async () => {
  const title = prompt("Book name:", "Research Workspace");
  if (!title) return;
  const id = await createNewBook(title.trim());
  openBook(id);
});

btnImport.addEventListener("click", () => {
  importInput.click();
});

importInput.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    delete data.id;
    const id = await saveBook(data);
    openBook(id);
  } catch (err) {
    alert("Failed to import book: " + err.message);
  }
  e.target.value = "";
});

getAllBooks().then(renderBooks);