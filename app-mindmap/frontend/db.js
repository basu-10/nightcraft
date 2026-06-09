const DB_NAME = "research_workspace_db";
const DB_VERSION = 1;
const STORE_NAME = "books";

function uid() {
  return "id_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
}

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = (e) => reject(e.target.error);
  });
}

function exec(mode, cb) {
  return openDB().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      const store = tx.objectStore(STORE_NAME);
      let result;
      try {
        result = cb(store);
      } catch (err) {
        reject(err);
        return;
      }
      tx.oncomplete = () => {
        if (result && typeof result === "object" && "result" in result) {
          resolve(result.result);
        } else {
          resolve(result);
        }
      };
      tx.onerror = (e) => reject(e.target.error);
    });
  });
}

export async function getAllBooks() {
  const records = await exec("readonly", (store) => store.getAll());
  return (records || [])
    .map((r) => ({
      id: r.id,
      title: r.bookTitle || "Untitled",
      canvasCount: (r.canvases || []).length,
      cardCount: (r.canvases || []).reduce(
        (sum, c) => sum + (c.cards || []).length,
        0,
      ),
      createdAt: r.createdAt,
      updatedAt: r.updatedAt,
    }))
    .sort((a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0));
}

export async function getBook(id) {
  const record = await exec("readonly", (store) => store.get(id));
  return record || null;
}

export async function saveBook(bookData) {
  const record = JSON.parse(JSON.stringify(bookData));
  record.updatedAt = new Date().toISOString();
  if (!record.id) {
    record.id = uid();
    record.createdAt = record.updatedAt;
  }
  const result = await exec("readwrite", (store) => store.put(record));
  return record.id;
}

export async function deleteBook(id) {
  await exec("readwrite", (store) => store.delete(id));
}

export async function createNewBook(title) {
  const id = uid();
  const canvasId = uid();
  const now = new Date().toISOString();
  const record = {
    id,
    version: 2,
    bookTitle: title || "Untitled Book",
    activeCanvasId: canvasId,
    canvases: [
      {
        id: canvasId,
        name: "Canvas 1",
        cards: [],
        edges: [],
        tagDefinitions: [],
        savedViews: [],
        activeQuickView: "all",
        panX: 0,
        panY: 0,
        zoom: 1,
      },
    ],
    createdAt: now,
    updatedAt: now,
  };
  await exec("readwrite", (store) => store.put(record));
  return id;
}