/*
 * guest_store.js
 * IndexedDB-backed local API adapter used when NoteStack runs in guest mode.
 */

(function () {
  "use strict";

  const DB_NAME = "notestack-guest";
  const DB_VERSION = 1;
  const STATE_STORE = "state";
  const STATE_KEY = "guest-state-v1";

  function nowIso() {
    return new Date().toISOString();
  }

  function toIntOrNull(value) {
    const n = Number.parseInt(String(value), 10);
    return Number.isInteger(n) ? n : null;
  }

  function parseTags(raw) {
    return String(raw || "")
      .split(",")
      .map((t) => t.trim().toLowerCase().replace(/^#+/, ""))
      .filter(Boolean);
  }

  function uniq(list) {
    const seen = new Set();
    const out = [];
    for (const item of list) {
      const key = String(item).toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  }

  function defaultState() {
    return {
      counters: {
        notes: 1,
        folders: 1,
        tags: 1,
      },
      notes: [],
      folders: [],
      tags: [],
    };
  }

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STATE_STORE)) {
          db.createObjectStore(STATE_STORE);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () =>
        reject(req.error || new Error("IndexedDB open failed"));
    });
  }

  function txPromise(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(request.error || new Error("IndexedDB request failed"));
    });
  }

  function loadState(db) {
    const tx = db.transaction(STATE_STORE, "readonly");
    const store = tx.objectStore(STATE_STORE);
    return txPromise(store.get(STATE_KEY)).then(
      (value) => value || defaultState(),
    );
  }

  function saveState(db, state) {
    const tx = db.transaction(STATE_STORE, "readwrite");
    const store = tx.objectStore(STATE_STORE);
    return txPromise(store.put(state, STATE_KEY));
  }

  function byName(a, b) {
    return String(a.name || "").localeCompare(String(b.name || ""));
  }

  function notesForList(state, includeTrash) {
    const folderById = new Map(state.folders.map((f) => [f.id, f]));
    return state.notes
      .filter((n) => (includeTrash ? !!n.deleted_at : !n.deleted_at))
      .map((n) => {
        const folder = n.folder_id ? folderById.get(n.folder_id) : null;
        return {
          ...n,
          folder_name: folder ? folder.name : null,
          folder_color: folder ? folder.color : null,
          tags: (n.tags || []).join(","),
        };
      });
  }

  function applySort(notes, sort) {
    if (sort === "alpha") {
      notes.sort((a, b) =>
        String(a.title || "").localeCompare(String(b.title || "")),
      );
      return;
    }
    const key = (n) => String(n.updated_at || n.created_at || "");
    notes.sort((a, b) => {
      const av = key(a);
      const bv = key(b);
      if (sort === "oldest") return av.localeCompare(bv);
      return bv.localeCompare(av);
    });
  }

  function ensureTagsExist(state, tagNames) {
    const existingByName = new Map(
      state.tags.map((t) => [String(t.name).toLowerCase(), t]),
    );
    for (const name of tagNames) {
      const normalized = String(name).toLowerCase().replace(/^#+/, "");
      if (!normalized || existingByName.has(normalized)) continue;
      const tag = {
        id: state.counters.tags++,
        name: normalized,
        color: null,
        created_at: nowIso(),
      };
      state.tags.push(tag);
      existingByName.set(normalized, tag);
    }
  }

  function normalizeColor(raw) {
    const value = String(raw || "").trim();
    if (!value.startsWith("#")) return null;
    return value.slice(0, 7).toUpperCase();
  }

  function recursiveFolderIds(state, folderId) {
    const out = new Set([folderId]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const folder of state.folders) {
        if (
          folder.parent_id &&
          out.has(folder.parent_id) &&
          !out.has(folder.id)
        ) {
          out.add(folder.id);
          changed = true;
        }
      }
    }
    return out;
  }

  function deepClone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function normalizeSnapshot(raw) {
    const fallback = defaultState();
    if (!raw || typeof raw !== "object") return fallback;
    const notes = Array.isArray(raw.notes) ? raw.notes : [];
    const folders = Array.isArray(raw.folders) ? raw.folders : [];
    const tags = Array.isArray(raw.tags) ? raw.tags : [];
    const maxNoteId = notes.reduce(
      (m, n) => Math.max(m, Number(n?.id || 0)),
      0,
    );
    const maxFolderId = folders.reduce(
      (m, f) => Math.max(m, Number(f?.id || 0)),
      0,
    );
    const maxTagId = tags.reduce((m, t) => Math.max(m, Number(t?.id || 0)), 0);
    return {
      counters: {
        notes: Math.max(Number(raw?.counters?.notes || 0), maxNoteId + 1, 1),
        folders: Math.max(
          Number(raw?.counters?.folders || 0),
          maxFolderId + 1,
          1,
        ),
        tags: Math.max(Number(raw?.counters?.tags || 0), maxTagId + 1, 1),
      },
      notes,
      folders,
      tags,
    };
  }

  async function createGuestStore() {
    const db = await openDb();

    async function withState(mutator) {
      const state = await loadState(db);
      const result = await mutator(state);
      await saveState(db, state);
      return result;
    }

    return {
      async dump() {
        const state = await loadState(db);
        return deepClone(state);
      },

      async clear() {
        await saveState(db, defaultState());
        return { ok: true };
      },

      async importSnapshot(snapshot, options = {}) {
        const replace = options.replace !== false;
        if (replace) {
          await saveState(db, normalizeSnapshot(snapshot));
          return { ok: true };
        }
        return withState((state) => {
          const incoming = normalizeSnapshot(snapshot);
          state.notes = [...state.notes, ...incoming.notes];
          state.folders = [...state.folders, ...incoming.folders];
          state.tags = [...state.tags, ...incoming.tags];
          state.counters.notes = Math.max(
            state.counters.notes,
            incoming.counters.notes,
          );
          state.counters.folders = Math.max(
            state.counters.folders,
            incoming.counters.folders,
          );
          state.counters.tags = Math.max(
            state.counters.tags,
            incoming.counters.tags,
          );
          return { ok: true };
        });
      },

      async request(method, fullPath, body) {
        const parsed = new URL(fullPath, window.location.origin);
        const path = parsed.pathname;

        if (method === "GET" && path === "/sync/conflicts") {
          return [];
        }

        if (
          method === "POST" &&
          /^\/sync\/conflicts\/\d+\/resolve$/.test(path)
        ) {
          return { resolved: true };
        }

        if (method === "GET" && path === "/folders") {
          return withState((state) => [...state.folders].sort(byName));
        }

        if (method === "POST" && path === "/folders") {
          return withState((state) => {
            const name = String(body?.name || "").trim();
            if (!name) throw new Error("name is required");
            const duplicate = state.folders.some(
              (f) => String(f.name).toLowerCase() === name.toLowerCase(),
            );
            if (duplicate) throw new Error("Folder name already exists");
            const folder = {
              id: state.counters.folders++,
              name,
              parent_id: toIntOrNull(body?.parent_id),
              color: normalizeColor(body?.color),
              sync_id: null,
              created_at: nowIso(),
            };
            state.folders.push(folder);
            return { id: folder.id };
          });
        }

        if (method === "PUT" && /^\/folders\/\d+$/.test(path)) {
          return withState((state) => {
            const folderId = Number(path.split("/").pop());
            const folder = state.folders.find((f) => f.id === folderId);
            if (!folder) throw new Error("Not found");
            if (body && Object.prototype.hasOwnProperty.call(body, "name")) {
              const name = String(body.name || "").trim();
              if (!name) throw new Error("name is required");
              const duplicate = state.folders.some(
                (f) =>
                  f.id !== folderId &&
                  String(f.name).toLowerCase() === name.toLowerCase(),
              );
              if (duplicate) throw new Error("Folder name already exists");
              folder.name = name;
            }
            if (
              body &&
              Object.prototype.hasOwnProperty.call(body, "parent_id")
            ) {
              folder.parent_id = toIntOrNull(body.parent_id);
            }
            if (body && Object.prototype.hasOwnProperty.call(body, "color")) {
              folder.color = normalizeColor(body.color);
            }
            return { ok: true };
          });
        }

        if (method === "DELETE" && /^\/folders\/\d+$/.test(path)) {
          return withState((state) => {
            const folderId = Number(path.split("/").pop());
            const folder = state.folders.find((f) => f.id === folderId);
            if (!folder) throw new Error("Not found");
            const doomed = recursiveFolderIds(state, folderId);
            state.folders = state.folders.filter((f) => !doomed.has(f.id));
            for (const note of state.notes) {
              if (note.folder_id && doomed.has(note.folder_id))
                note.folder_id = null;
            }
            return { ok: true };
          });
        }

        if (method === "GET" && path === "/tags") {
          return withState((state) => [...state.tags].sort(byName));
        }

        if (method === "POST" && path === "/tags") {
          return withState((state) => {
            const name = String(body?.name || "")
              .trim()
              .toLowerCase()
              .replace(/^#+/, "");
            if (!name) throw new Error("name is required");
            const duplicate = state.tags.some(
              (t) => String(t.name).toLowerCase() === name,
            );
            if (duplicate) throw new Error("Tag already exists");
            const tag = {
              id: state.counters.tags++,
              name,
              color: normalizeColor(body?.color),
              created_at: nowIso(),
            };
            state.tags.push(tag);
            return { id: tag.id };
          });
        }

        if (method === "PUT" && /^\/tags\/\d+$/.test(path)) {
          return withState((state) => {
            const tagId = Number(path.split("/").pop());
            const tag = state.tags.find((t) => t.id === tagId);
            if (!tag) throw new Error("Not found");
            const prevName = tag.name;
            if (body && Object.prototype.hasOwnProperty.call(body, "name")) {
              const nextName = String(body.name || "")
                .trim()
                .toLowerCase()
                .replace(/^#+/, "");
              if (!nextName) throw new Error("name is required");
              const duplicate = state.tags.some(
                (t) =>
                  t.id !== tagId && String(t.name).toLowerCase() === nextName,
              );
              if (duplicate) throw new Error("Tag already exists");
              tag.name = nextName;
            }
            if (body && Object.prototype.hasOwnProperty.call(body, "color")) {
              tag.color = normalizeColor(body.color);
            }
            if (tag.name !== prevName) {
              for (const note of state.notes) {
                note.tags = (note.tags || []).map((t) =>
                  t.toLowerCase() === prevName.toLowerCase() ? tag.name : t,
                );
                note.tags = uniq(note.tags);
              }
            }
            return { ok: true };
          });
        }

        if (method === "DELETE" && /^\/tags\/\d+$/.test(path)) {
          return withState((state) => {
            const tagId = Number(path.split("/").pop());
            const tag = state.tags.find((t) => t.id === tagId);
            if (!tag) throw new Error("Not found");
            state.tags = state.tags.filter((t) => t.id !== tagId);
            for (const note of state.notes) {
              note.tags = (note.tags || []).filter(
                (t) => t.toLowerCase() !== tag.name.toLowerCase(),
              );
            }
            return { ok: true };
          });
        }

        if (method === "GET" && path === "/notes") {
          return withState((state) => {
            const params = parsed.searchParams;
            const folderId = toIntOrNull(params.get("folder_id"));
            const keyword = String(params.get("q") || "")
              .trim()
              .toLowerCase();
            const favoritesOnly = params.get("favorites") === "1";
            const sort = String(params.get("sort") || "newest").trim();
            const limit = Math.max(
              1,
              Number.parseInt(params.get("limit") || "200", 10) || 200,
            );
            const offset = Math.max(
              0,
              Number.parseInt(params.get("offset") || "0", 10) || 0,
            );
            const dateFilter = String(params.get("date") || "").trim();
            const tagId = toIntOrNull(params.get("tag_id"));
            const tag = tagId ? state.tags.find((t) => t.id === tagId) : null;

            let notes = notesForList(state, false);
            if (folderId) notes = notes.filter((n) => n.folder_id === folderId);
            if (tag)
              notes = notes.filter((n) =>
                (n.tags || "")
                  .split(",")
                  .map((x) => x.toLowerCase())
                  .includes(tag.name.toLowerCase()),
              );
            if (favoritesOnly) notes = notes.filter((n) => !!n.is_favorite);
            if (keyword) {
              notes = notes.filter((n) => {
                const text =
                  `${n.title || ""} ${n.content || ""} ${n.tags || ""}`.toLowerCase();
                return text.includes(keyword);
              });
            }
            if (dateFilter) {
              notes = notes.filter((n) =>
                String(n.updated_at || n.created_at || "").startsWith(
                  dateFilter,
                ),
              );
            }
            applySort(notes, sort);
            return notes.slice(offset, offset + limit);
          });
        }

        if (method === "GET" && path === "/trash") {
          return withState((state) => {
            const params = parsed.searchParams;
            const keyword = String(params.get("q") || "")
              .trim()
              .toLowerCase();
            const sort = String(params.get("sort") || "newest").trim();
            const limit = Math.max(
              1,
              Number.parseInt(params.get("limit") || "200", 10) || 200,
            );
            const offset = Math.max(
              0,
              Number.parseInt(params.get("offset") || "0", 10) || 0,
            );
            let notes = notesForList(state, true);
            if (keyword) {
              notes = notes.filter((n) => {
                const text =
                  `${n.title || ""} ${n.content || ""} ${n.tags || ""}`.toLowerCase();
                return text.includes(keyword);
              });
            }
            applySort(notes, sort);
            return notes.slice(offset, offset + limit);
          });
        }

        if (method === "GET" && /^\/notes\/\d+$/.test(path)) {
          return withState((state) => {
            const noteId = Number(path.split("/").pop());
            const note = state.notes.find(
              (n) => n.id === noteId && !n.deleted_at,
            );
            if (!note) throw new Error("Not found");
            return {
              ...note,
              tags: (note.tags || []).join(","),
            };
          });
        }

        if (method === "POST" && path === "/notes") {
          return withState((state) => {
            const title = String(body?.title || "").trim() || "Untitled";
            const noteTags = uniq(parseTags(body?.tags));
            ensureTagsExist(state, noteTags);
            const now = nowIso();
            const note = {
              id: state.counters.notes++,
              title,
              content: String(body?.content || ""),
              folder_id: toIntOrNull(body?.folder_id),
              is_favorite: body?.is_favorite ? 1 : 0,
              tags: noteTags,
              editor_type: "lexical",
              created_at: now,
              updated_at: now,
              deleted_at: null,
            };
            state.notes.push(note);
            return { id: note.id };
          });
        }

        if (method === "PUT" && /^\/notes\/\d+$/.test(path)) {
          return withState((state) => {
            const noteId = Number(path.split("/").pop());
            const note = state.notes.find(
              (n) => n.id === noteId && !n.deleted_at,
            );
            if (!note) throw new Error("Not found");

            if (body && Object.prototype.hasOwnProperty.call(body, "title")) {
              note.title = String(body.title || "").trim() || "Untitled";
            }
            if (body && Object.prototype.hasOwnProperty.call(body, "content")) {
              note.content = String(body.content || "");
            }
            if (
              body &&
              Object.prototype.hasOwnProperty.call(body, "folder_id")
            ) {
              note.folder_id = toIntOrNull(body.folder_id);
            }
            if (
              body &&
              Object.prototype.hasOwnProperty.call(body, "is_favorite")
            ) {
              note.is_favorite = body.is_favorite ? 1 : 0;
            }
            if (body && Object.prototype.hasOwnProperty.call(body, "tags")) {
              const nextTags = uniq(parseTags(body.tags));
              ensureTagsExist(state, nextTags);
              note.tags = nextTags;
            }
            note.updated_at = nowIso();
            return { ok: true };
          });
        }

        if (method === "DELETE" && /^\/notes\/\d+$/.test(path)) {
          return withState((state) => {
            const noteId = Number(path.split("/").pop());
            const note = state.notes.find(
              (n) => n.id === noteId && !n.deleted_at,
            );
            if (!note) throw new Error("Not found");
            const now = nowIso();
            note.deleted_at = now;
            note.updated_at = now;
            return { ok: true };
          });
        }

        throw new Error("Unsupported guest route: " + method + " " + path);
      },
    };
  }

  window.NoteStackGuestStore = {
    create: createGuestStore,
  };
})();
