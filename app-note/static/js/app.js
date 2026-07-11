/**
 * app.js — NoteStack Web main application logic.
 *
 * Self-contained vanilla JS SPA. No build step required.
 * Uses fetch() for all API calls and manages DOM state directly.
 */

(() => {
  "use strict";

  const IS_GUEST_MODE = Boolean(window.NOTESTACK_IS_GUEST);
  const USER_TIMEZONE = window.NOTESTACK_USER_TIMEZONE || undefined;
  let guestStore = null;

  // ── State ──────────────────────────────────────────────────────────────────
  const state = {
    notes: [],
    folders: [],
    tags: [],
    collapsedFolderIds: new Set(),
    activeNoteId: null,
    activeEditorType: "lexical",
    filter: {
      section: "all",
      folderId: null,
      tagId: null,
      keyword: "",
      sort: "newest",
      dateFilter: null,
    },
    paging: {
      limit: 10,
      offset: 0,
      hasMore: false,
      loading: false,
      pendingReset: false,
    },
    view: "grid", // 'grid' | 'rows'
    editorDirty: false,
    isSaving: false,
    pendingSave: false,
    saveTimer: null,
    autoSaveMs: 1500, // debounce ms for auto-save
  };

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Lexical editor (lazy) ──────────────────────────────────────────────────
  // Created on first use; kept alive for the session (survives note switches).
  let _lexicalEditor = null;

  function _getOrCreateLexicalEditor() {
    if (_lexicalEditor) return _lexicalEditor;
    if (!window.LexicalNoteEditor) {
      console.error(
        "[NoteStack] LexicalNoteEditor not loaded. Is lexical_editor.js included?",
      );
      return null;
    }
    _lexicalEditor = new window.LexicalNoteEditor(
      "lexical-editor-mount",
      onEditorChange,
    );
    _lexicalEditor.init();
    return _lexicalEditor;
  }

  /** Return the correct editor instance for the currently open note. */
  function getActiveEditor() {
    return _getOrCreateLexicalEditor();
  }

  // ── Tag Manager Modal ──────────────────────────────────────────────────────

  const TAG_COLOR_PALETTE = [
    "#4F6EF7",
    "#22C55E",
    "#F59E0B",
    "#EC4899",
    "#06B6D4",
    "#A855F7",
    "#EF4444",
    "#84CC16",
    "#F97316",
    "#14B8A6",
    "#8B5CF6",
    "#3B82F6",
    "#10B981",
    "#EAB308",
    "#D946EF",
  ];

  let _currentTagColor = "#6B7280";
  let _folderDraftColor = "";

  function normalizeTagName(name) {
    return name.trim().toLowerCase().replace(/^#+/, "");
  }

  function _getNextUniqueColor() {
    const usedColors = new Set(
      state.tags.map((t) => t.color?.toUpperCase()).filter(Boolean),
    );
    for (const color of TAG_COLOR_PALETTE) {
      if (!usedColors.has(color.toUpperCase())) return color;
    }
    const hue = (state.tags.length * 0.61803398875) % 1.0;
    const sat = 0.62;
    const val = 0.92;
    const rgb = hsvToRgb(hue, sat, val);
    return rgbToHex(rgb[0], rgb[1], rgb[2]);
  }

  function hsvToRgb(h, s, v) {
    const c = v * s;
    const x = c * (1 - Math.abs(((h * 6) % 2) - 1));
    const m = v - c;
    let r, g, b;
    if (h < 1 / 6) {
      r = c;
      g = x;
      b = 0;
    } else if (h < 2 / 6) {
      r = x;
      g = c;
      b = 0;
    } else if (h < 3 / 6) {
      r = 0;
      g = c;
      b = x;
    } else if (h < 4 / 6) {
      r = 0;
      g = x;
      b = c;
    } else if (h < 5 / 6) {
      r = x;
      g = 0;
      b = c;
    } else {
      r = c;
      g = 0;
      b = x;
    }
    return [
      Math.round((r + m) * 255),
      Math.round((g + m) * 255),
      Math.round((b + m) * 255),
    ];
  }

  function rgbToHex(r, g, b) {
    return (
      "#" +
      [r, g, b]
        .map((x) => x.toString(16).padStart(2, "0").toUpperCase())
        .join("")
    );
  }

  function openTagManagerModal() {
    _currentTagColor = _getNextUniqueColor();
    $("tag-new-input").value = "";
    $("tag-new-input").focus();
    _updateTagColorBtn();
    _refreshTagListManage();
    $("tag-manager-modal").hidden = false;
  }

  function openTagCreateColorPicker() {
    const input = document.createElement("input");
    input.type = "color";
    input.value = (_currentTagColor || "#6B7280").startsWith("#")
      ? _currentTagColor
      : "#6B7280";
    input.addEventListener("change", () => {
      _currentTagColor = input.value;
      _updateTagColorBtn();
    });
    input.click();
  }

  function _updateTagColorBtn() {
    const btn = $("tag-color-btn");
    if (btn) btn.style.backgroundColor = _currentTagColor;
  }

  function _refreshTagListManage() {
    const list = $("tag-list-manage");
    if (!list) return;
    list.innerHTML = "";
    state.tags.forEach((tag) => {
      const row = document.createElement("div");
      row.style.cssText =
        "display: flex; gap: var(--space-2); margin-bottom: var(--space-2); align-items: center;";
      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.className = "form-input";
      nameInput.value = tag.name;
      nameInput.style.flex = "1";
      nameInput.readOnly = true;
      const colorBtn = document.createElement("button");
      colorBtn.type = "button";
      colorBtn.className = "btn";
      colorBtn.style.cssText = `width: 40px; height: 40px; padding: 0; border-radius: 4px; background-color: ${tag.color || "#6B7280"}; border: 1px solid var(--border);`;
      colorBtn.title = "Change color";
      colorBtn.addEventListener("click", () =>
        openColorPicker(tag.id, tag.color || "#6B7280"),
      );
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "btn btn--ghost btn--sm";
      deleteBtn.textContent = "🗑";
      deleteBtn.title = "Delete tag";
      deleteBtn.addEventListener("click", () => deleteTag(tag.id, tag.name));
      row.appendChild(nameInput);
      row.appendChild(colorBtn);
      row.appendChild(deleteBtn);
      list.appendChild(row);
    });
  }

  function openColorPicker(tagId, currentColor) {
    const input = document.createElement("input");
    input.type = "color";
    input.value = currentColor.startsWith("#") ? currentColor : "#6B7280";
    input.addEventListener("change", async () => {
      const newColor = input.value;
      await api("PUT", `/tags/${tagId}`, { color: newColor });
      await loadTags();
      _refreshTagListManage();
    });
    input.click();
  }

  async function createTag() {
    const name = normalizeTagName($("tag-new-input").value);
    if (!name) {
      alert("Please enter a tag name");
      return;
    }
    if (state.tags.some((t) => t.name.toLowerCase() === name.toLowerCase())) {
      alert(`Tag "${name}" already exists`);
      return;
    }
    try {
      await api("POST", "/tags", { name, color: _currentTagColor });
      $("tag-new-input").value = "";
      _currentTagColor = _getNextUniqueColor();
      _updateTagColorBtn();
      await loadTags();
      _refreshTagListManage();
    } catch (err) {
      alert("Failed to create tag");
    }
  }

  async function deleteTag(tagId, tagName) {
    if (!confirm(`Delete tag "${tagName}"?`)) return;
    try {
      await api("DELETE", `/tags/${tagId}`);
      await loadTags();
      _refreshTagListManage();
    } catch (err) {
      alert("Failed to delete tag");
    }
  }

  // ── DOM refs ───────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const noteList = $("note-list");
  const emptyState = $("empty-state");
  const listPagination = $("list-pagination");
  const btnLoadMore = $("btn-load-more");
  const folderList = $("folder-list");
  const tagList = $("tag-list");
  const searchInput = $("search-input");
  const topbarSearchWrap = $("topbar-search-wrap");
  const btnSearchToggle = $("btn-search-toggle");
  const sortSelect = $("sort-select");
  const editorPanel = $("editor-panel");
  const noteTitle = $("note-title");
  const editorTagsDisplay = $("editor-tags-display");
  const saveIndicator = $("save-indicator");
  const btnSaveNote = $("btn-save-note");
  const btnNewNote = $("btn-new-note");
  const btnEmptyNew = $("btn-empty-new");
  const appLayout = $("app");
  const sidebarBackdrop = $("sidebar-backdrop");
  const btnSidebarToggle = $("btn-sidebar-toggle");
  const btnSidebarClose = $("btn-sidebar-close");
  const btnMobileMenu = $("btn-mobile-menu");
  const btnMobileNewNote = $("btn-mobile-new-note");
  const viewTitle = $("view-title");
  const folderNav = $("folder-nav");
  const folderNavBack = $("folder-nav-back");
  const folderNavLabel = $("folder-nav-label");
  const folderNavChips = $("folder-nav-chips");
  const sidebarBody = $("sidebar-body");
  const sidebarFolderSection = $("sidebar-folder-section");
  const sidebarTagSection = $("sidebar-tag-section");
  const sidebarSectionsResizer = $("sidebar-sections-resizer");
  const btnGuestExport = $("btn-guest-export");
  const btnGuestImport = $("btn-guest-import");
  const guestImportFile = $("guest-import-file");
  const guestImportBanner = $("guest-import-banner");
  const guestImportBannerText = $("guest-import-banner-text");
  const btnGuestImportAccept = $("btn-guest-import-accept");
  const btnGuestImportDismiss = $("btn-guest-import-dismiss");

  const guestWarningBanner = $("guest-warning-banner");
  const btnGuestWarningDismiss = $("btn-guest-warning-dismiss");

  const GUEST_IMPORT_DISMISS_KEY = "notestack.guest-import-dismissed-snapshot";
  const GUEST_WARNING_DISMISS_KEY = "notestack.guest-warning-dismissed";
  let guestImportPrompt = null;

  const sectionButtonsDesktop = () =>
    Array.from(document.querySelectorAll(".sidebar__item[data-filter]"));
  const sectionButtonsMobile = () =>
    Array.from(
      document.querySelectorAll(".mobile-nav__item[data-mobile-filter]"),
    );

  // ── Editor ─────────────────────────────────────────────────────────────────
  // Lexical is now the only editor (initialized lazily on first use)

  // ── Boot ───────────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", async () => {
    if (IS_GUEST_MODE) {
      if (
        !window.NoteStackGuestStore ||
        typeof window.NoteStackGuestStore.create !== "function"
      ) {
        alert(
          "Guest mode could not start local storage. Please reload the page.",
        );
        return;
      }
      guestStore = await window.NoteStackGuestStore.create();
      const syncLabel = document.querySelector(
        "#sync-status .sync-badge__label",
      );
      if (syncLabel) syncLabel.textContent = "Local only";
      startGuestWarning();
    }
    restoreFilterFromUrl();
    bindUI();
    if (sortSelect) sortSelect.value = state.filter.sort;
    if (searchInput) searchInput.value = state.filter.keyword;
    await Promise.all([loadFolders(), loadTags()]);
    await loadNotes({ reset: true });
    if (!IS_GUEST_MODE) {
      await maybeImportGuestDataIntoAccount();
    }
  });

  // ── Guest mode warning (periodic flashing notification) ────────────────────
  let _guestWarningTimer = null;

  function startGuestWarning() {
    if (!guestWarningBanner) return;

    let dismissed = false;
    try {
      dismissed = localStorage.getItem(GUEST_WARNING_DISMISS_KEY) === "1";
    } catch {}

    const flash = () => {
      // Brief attention flare, then settle back to the muted resting state.
      guestWarningBanner.classList.remove("guest-warning-banner--muted");
      guestWarningBanner.classList.add("guest-warning-banner--flashing");
      setTimeout(() => {
        if (!guestWarningBanner.hidden) {
          guestWarningBanner.classList.remove(
            "guest-warning-banner--flashing",
          );
          guestWarningBanner.classList.add("guest-warning-banner--muted");
        }
      }, 4500);
    };

    if (dismissed) {
      // Keep the banner visible but calm — no periodic flashing.
      guestWarningBanner.hidden = false;
      guestWarningBanner.classList.add("guest-warning-banner--muted");
    } else {
      guestWarningBanner.hidden = false;
      flash();
      _guestWarningTimer = setInterval(flash, 12000);
    }

    if (btnGuestWarningDismiss) {
      btnGuestWarningDismiss.addEventListener("click", () => {
        guestWarningBanner.hidden = true;
        guestWarningBanner.classList.remove(
          "guest-warning-banner--flashing",
          "guest-warning-banner--muted",
        );
        if (_guestWarningTimer) {
          clearInterval(_guestWarningTimer);
          _guestWarningTimer = null;
        }
        try {
          localStorage.setItem(GUEST_WARNING_DISMISS_KEY, "1");
        } catch {}
      });
    }
  }

  // ── Sync status badge ─────────────────────────────────────────────────────
  const _syncEl = $("sync-status");
  const _syncLabel = _syncEl
    ? _syncEl.querySelector(".sync-badge__label")
    : null;
  let _syncActiveCount = 0;

  function setSyncStatus(state) {
    if (!_syncEl) return;
    _syncEl.className = "sync-badge sync-badge--" + state;
    if (_syncLabel) {
      if (state === "syncing") _syncLabel.textContent = "Syncing…";
      else if (state === "error") _syncLabel.textContent = "Error";
      else _syncLabel.textContent = "Synced";
    }
  }

  function _beginSync() {
    _syncActiveCount++;
    if (_syncActiveCount === 1) setSyncStatus("syncing");
  }

  function _endSync(ok) {
    _syncActiveCount = Math.max(0, _syncActiveCount - 1);
    if (_syncActiveCount === 0) setSyncStatus(ok ? "ok" : "error");
  }

  // ── API helpers ─────────────────────────────────────────────────────────────

  const API_ROOT = window.NOTESTACK_API_ROOT || "/api";

  async function api(method, path, body) {
    if (IS_GUEST_MODE) {
      if (!guestStore) {
        guestStore = await window.NoteStackGuestStore.create();
      }
      const localPath = path.startsWith("/") ? path : `/${path}`;
      return guestStore.request(method, localPath, body);
    }

    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    // Only animate badge for write operations (not plain reads)
    const isWrite = method !== "GET";
    if (isWrite) _beginSync();
    try {
      const res = await fetch(API_ROOT + path, opts);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (isWrite) _endSync(false);
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      const text = await res.text();
      const json = text ? JSON.parse(text) : {};
      if (isWrite) _endSync(true);
      return json;
    } catch (err) {
      if (isWrite) _endSync(false);
      throw err;
    }
  }

  function _isGuestSnapshotEmpty(snapshot) {
    if (!snapshot || typeof snapshot !== "object") return true;
    const notes = Array.isArray(snapshot.notes) ? snapshot.notes : [];
    const folders = Array.isArray(snapshot.folders) ? snapshot.folders : [];
    const tags = Array.isArray(snapshot.tags) ? snapshot.tags : [];
    return notes.length === 0 && folders.length === 0 && tags.length === 0;
  }

  function _guestSnapshotSignature(snapshot) {
    const notes = Array.isArray(snapshot?.notes) ? snapshot.notes : [];
    const folders = Array.isArray(snapshot?.folders) ? snapshot.folders : [];
    const tags = Array.isArray(snapshot?.tags) ? snapshot.tags : [];
    const noteIds = notes
      .map((n) => Number(n?.id || 0))
      .sort((a, b) => a - b)
      .join(",");
    const folderIds = folders
      .map((f) => Number(f?.id || 0))
      .sort((a, b) => a - b)
      .join(",");
    const tagIds = tags
      .map((t) => Number(t?.id || 0))
      .sort((a, b) => a - b)
      .join(",");
    return `${notes.length}:${folders.length}:${tags.length}:${noteIds}:${folderIds}:${tagIds}`;
  }

  function _setGuestImportBannerState({
    message,
    mode = "prompt",
    working = false,
  } = {}) {
    if (!guestImportBanner) return;
    guestImportBanner.classList.remove(
      "guest-import-banner--error",
      "guest-import-banner--success",
      "guest-import-banner--working",
    );
    if (mode === "error")
      guestImportBanner.classList.add("guest-import-banner--error");
    if (mode === "success")
      guestImportBanner.classList.add("guest-import-banner--success");
    if (working)
      guestImportBanner.classList.add("guest-import-banner--working");

    if (guestImportBannerText && message) {
      guestImportBannerText.textContent = message;
    }

    if (btnGuestImportAccept) {
      btnGuestImportAccept.hidden = mode !== "prompt";
      btnGuestImportAccept.disabled = working;
    }
    if (btnGuestImportDismiss) {
      btnGuestImportDismiss.textContent =
        mode === "prompt" ? "Dismiss" : "Close";
      btnGuestImportDismiss.disabled = working;
    }
  }

  function _showGuestImportBanner() {
    if (guestImportBanner) guestImportBanner.hidden = false;
  }

  function _hideGuestImportBanner() {
    if (guestImportBanner) guestImportBanner.hidden = true;
  }

  function _dismissGuestImportPrompt() {
    if (guestImportPrompt?.signature) {
      try {
        localStorage.setItem(
          GUEST_IMPORT_DISMISS_KEY,
          guestImportPrompt.signature,
        );
      } catch {}
    }
    guestImportPrompt = null;
    _hideGuestImportBanner();
  }

  async function _acceptGuestImportPrompt() {
    if (!guestImportPrompt) return;
    _setGuestImportBannerState({
      mode: "prompt",
      working: true,
      message: "Importing guest notes into your account...",
    });

    try {
      const result = await importGuestDataToAccount(guestImportPrompt.snapshot);
      await guestImportPrompt.localStore.clear();
      try {
        localStorage.removeItem(GUEST_IMPORT_DISMISS_KEY);
      } catch {}
      guestImportPrompt = null;
      await Promise.all([loadFolders(), loadTags()]);
      await loadNotes({ reset: true });
      _setGuestImportBannerState({
        mode: "success",
        message: `Imported ${result.notesImported} note(s) into your account.`,
      });
    } catch (err) {
      console.error("Guest import to account failed:", err);
      _setGuestImportBannerState({
        mode: "error",
        message:
          "Could not import guest data right now. You can retry by refreshing this page.",
      });
    }
  }

  function _downloadJsonFile(filename, payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function exportGuestBackup() {
    if (!guestStore) {
      guestStore = await window.NoteStackGuestStore.create();
    }
    const snapshot = await guestStore.dump();
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    _downloadJsonFile(`notestack-guest-backup-${stamp}.json`, {
      version: 1,
      exported_at: new Date().toISOString(),
      app: "notestack",
      mode: "guest",
      data: snapshot,
    });
  }

  async function importGuestBackupFile(file) {
    if (!file) return;
    const text = await file.text();
    let parsed = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error("Invalid JSON file");
    }

    const snapshot =
      parsed && typeof parsed === "object" && parsed.data
        ? parsed.data
        : parsed;
    if (!snapshot || typeof snapshot !== "object") {
      throw new Error("Unsupported backup format");
    }
    if (!guestStore) {
      guestStore = await window.NoteStackGuestStore.create();
    }
    await guestStore.importSnapshot(snapshot, { replace: true });
    state.activeNoteId = null;
    state.editorDirty = false;
    await Promise.all([loadFolders(), loadTags()]);
    await loadNotes({ reset: true });
    alert("Guest backup imported.");
  }

  function _folderDepthLookup(folders) {
    const byId = new Map(folders.map((f) => [f.id, f]));
    const cache = new Map();
    const visit = (id) => {
      if (!id || !byId.has(id)) return 0;
      if (cache.has(id)) return cache.get(id);
      const node = byId.get(id);
      const depth = 1 + visit(node.parent_id);
      cache.set(id, depth);
      return depth;
    };
    folders.forEach((f) => visit(f.id));
    return cache;
  }

  async function importGuestDataToAccount(snapshot) {
    const guestFolders = Array.isArray(snapshot?.folders)
      ? snapshot.folders
      : [];
    const guestTags = Array.isArray(snapshot?.tags) ? snapshot.tags : [];
    const guestNotes = (
      Array.isArray(snapshot?.notes) ? snapshot.notes : []
    ).filter((n) => !n.deleted_at);

    const folderMap = new Map();
    const tagByName = new Map();

    let serverFolders = await api("GET", "/folders");
    let serverTags = await api("GET", "/tags");

    const folderNameToId = new Map(
      (serverFolders || []).map((f) => [
        String(f.name || "").toLowerCase(),
        f.id,
      ]),
    );
    for (const folder of guestFolders) {
      const existing = folderNameToId.get(
        String(folder.name || "").toLowerCase(),
      );
      if (existing) folderMap.set(folder.id, existing);
    }

    const depth = _folderDepthLookup(guestFolders);
    const sortedGuestFolders = [...guestFolders].sort(
      (a, b) => (depth.get(a.id) || 0) - (depth.get(b.id) || 0),
    );

    for (const folder of sortedGuestFolders) {
      if (folderMap.has(folder.id)) continue;
      const parentId = folder.parent_id
        ? folderMap.get(folder.parent_id) || null
        : null;
      try {
        const created = await api("POST", "/folders", {
          name: folder.name,
          parent_id: parentId,
          color: folder.color || null,
        });
        folderMap.set(folder.id, created.id);
      } catch {
        serverFolders = await api("GET", "/folders");
        const fallback = (serverFolders || []).find(
          (f) =>
            String(f.name || "").toLowerCase() ===
            String(folder.name || "").toLowerCase(),
        );
        if (fallback) folderMap.set(folder.id, fallback.id);
      }
    }

    for (const tag of serverTags || []) {
      tagByName.set(String(tag.name || "").toLowerCase(), tag.name);
    }

    for (const tag of guestTags) {
      const key = String(tag.name || "").toLowerCase();
      if (!key || tagByName.has(key)) continue;
      try {
        await api("POST", "/tags", {
          name: tag.name,
          color: tag.color || null,
        });
        tagByName.set(key, String(tag.name || ""));
      } catch {
        // Ignore duplicate failures and rely on name-based matching below.
      }
    }

    serverTags = await api("GET", "/tags");
    const normalizedServerTags = new Map(
      (serverTags || []).map((t) => [
        String(t.name || "").toLowerCase(),
        String(t.name || ""),
      ]),
    );

    let notesImported = 0;
    for (const note of guestNotes) {
      const tags = Array.isArray(note.tags)
        ? note.tags
            .map(
              (t) =>
                normalizedServerTags.get(String(t || "").toLowerCase()) ||
                String(t || "").trim(),
            )
            .filter(Boolean)
        : [];
      await api("POST", "/notes", {
        title: String(note.title || "").trim() || "Untitled",
        content: String(note.content || ""),
        folder_id: note.folder_id
          ? folderMap.get(note.folder_id) || null
          : null,
        is_favorite: note.is_favorite ? 1 : 0,
        tags: tags.join(","),
        editor_type: "lexical",
      });
      notesImported += 1;
    }

    return {
      foldersImported: folderMap.size,
      tagsImported: normalizedServerTags.size,
      notesImported,
    };
  }

  async function maybeImportGuestDataIntoAccount() {
    if (
      !window.NoteStackGuestStore ||
      typeof window.NoteStackGuestStore.create !== "function"
    ) {
      return;
    }
    let localStore = null;
    try {
      localStore = await window.NoteStackGuestStore.create();
      const snapshot = await localStore.dump();
      if (_isGuestSnapshotEmpty(snapshot)) return;

      const signature = _guestSnapshotSignature(snapshot);
      const dismissedSignature = (() => {
        try {
          return localStorage.getItem(GUEST_IMPORT_DISMISS_KEY) || "";
        } catch {
          return "";
        }
      })();
      if (dismissedSignature && dismissedSignature === signature) return;

      guestImportPrompt = { snapshot, localStore, signature };
      _setGuestImportBannerState({
        mode: "prompt",
        message:
          "Guest notes were found in this browser. Import them into your account?",
      });
      _showGuestImportBanner();
    } catch (err) {
      console.error("Guest import prompt setup failed:", err);
    }
  }

  // ── Data loading ───────────────────────────────────────────────────────────
  function restoreFilterFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const section = (params.get("section") || "all").trim();
    const allowedSections = new Set(["all", "favorites", "trash"]);
    state.filter.section = allowedSections.has(section) ? section : "all";

    const folderId = Number.parseInt(params.get("folder_id") || "", 10);
    state.filter.folderId =
      Number.isInteger(folderId) && folderId > 0 ? folderId : null;

    const tagId = Number.parseInt(params.get("tag_id") || "", 10);
    state.filter.tagId = Number.isInteger(tagId) && tagId > 0 ? tagId : null;

    const sort = (params.get("sort") || "newest").trim();
    state.filter.sort = ["newest", "oldest", "alpha"].includes(sort)
      ? sort
      : "newest";
    state.filter.keyword = (params.get("q") || "").trim();
    state.filter.dateFilter = params.get("date") || null;

    if (state.filter.folderId || state.filter.tagId) {
      state.filter.section = "all";
    }
  }

  function syncFilterToUrl() {
    const params = new URLSearchParams();
    if (state.filter.section !== "all")
      params.set("section", state.filter.section);
    if (state.filter.folderId)
      params.set("folder_id", String(state.filter.folderId));
    if (state.filter.tagId) params.set("tag_id", String(state.filter.tagId));
    if (state.filter.sort !== "newest") params.set("sort", state.filter.sort);
    if (state.filter.keyword) params.set("q", state.filter.keyword);
    if (state.filter.dateFilter) params.set("date", state.filter.dateFilter);
    const query = params.toString();
    const nextUrl = query
      ? `${window.location.pathname}?${query}`
      : window.location.pathname;
    window.history.replaceState(null, "", nextUrl);
  }

  function renderLoadMoreButton() {
    if (!listPagination || !btnLoadMore) return;
    const hasNotes = state.notes.length > 0;
    listPagination.hidden = !(hasNotes && state.paging.hasMore);
    btnLoadMore.disabled = state.paging.loading;
    btnLoadMore.textContent = state.paging.loading ? "Loading…" : "Show more";
  }

  async function loadNotes({ reset = false } = {}) {
    if (state.paging.loading) {
      if (reset) state.paging.pendingReset = true;
      return;
    }
    if (reset) {
      state.paging.offset = 0;
      state.paging.hasMore = false;
    }

    state.paging.loading = true;
    renderLoadMoreButton();

    const f = state.filter;
    const params = new URLSearchParams({
      sort: f.sort,
      limit: String(state.paging.limit),
      offset: String(state.paging.offset),
    });
    if (f.folderId) params.set("folder_id", f.folderId);
    if (f.tagId) params.set("tag_id", f.tagId);
    if (f.keyword) params.set("q", f.keyword);
    if (f.section === "favorites") params.set("favorites", "1");
    if (f.dateFilter) params.set("date", f.dateFilter);

    const endpoint = f.section === "trash" ? "/trash" : "/notes";
    try {
      const data = await api("GET", `${endpoint}?${params}`);
      const nextChunk = Array.isArray(data) ? data : [];
      state.notes = reset ? nextChunk : state.notes.concat(nextChunk);
      state.paging.offset = state.notes.length;
      state.paging.hasMore = nextChunk.length === state.paging.limit;
      updateViewTitle();
      renderNoteList();
      updateCounts();
    } finally {
      state.paging.loading = false;
      renderLoadMoreButton();
      if (state.paging.pendingReset) {
        state.paging.pendingReset = false;
        loadNotes({ reset: true });
      }
    }
  }

  async function loadFolders() {
    state.folders = await api("GET", "/folders");
    const validFolderIds = new Set(state.folders.map((f) => f.id));
    state.collapsedFolderIds = new Set(
      [...state.collapsedFolderIds].filter((id) => validFolderIds.has(id)),
    );
    if (state.filter.folderId && !validFolderIds.has(state.filter.folderId)) {
      state.filter.folderId = null;
      state.filter.section = "all";
      syncFilterToUrl();
    }
    updateViewTitle();
    renderFolderTree();
  }

  async function loadTags() {
    state.tags = await api("GET", "/tags");
    const validTagIds = new Set(state.tags.map((t) => t.id));
    if (state.filter.tagId && !validTagIds.has(state.filter.tagId)) {
      state.filter.tagId = null;
      state.filter.section = "all";
      syncFilterToUrl();
    }
    updateViewTitle();
    renderTagPills();
  }

  function getCurrentViewTitle() {
    if (state.filter.folderId) {
      const folder = state.folders.find((f) => f.id === state.filter.folderId);
      return folder ? folder.name : "Folder";
    }
    if (state.filter.tagId) {
      const tag = state.tags.find((t) => t.id === state.filter.tagId);
      return tag ? `#${tag.name}` : "Tag";
    }
    if (state.filter.section === "favorites") return "Favorites";
    if (state.filter.section === "trash") return "Trash";
    let base = "All Notes";
    if (state.filter.dateFilter) {
      const todayStr = _todayDateStr();
      if (state.filter.dateFilter === todayStr) {
        base += " — Today";
      } else {
        const d = new Date(state.filter.dateFilter + "T12:00:00");
        base += ` — ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
      }
    }
    return base;
  }

  function updateViewTitle() {
    const title = getCurrentViewTitle();
    if (viewTitle) viewTitle.textContent = title;
    renderFolderNav();
    document.title = `${title} - NoteStack`;
    // Hide the mobile new-note button on trash (can't create notes in trash)
    const mobileNewWrap = $("mobile-new-wrap");
    if (mobileNewWrap) mobileNewWrap.hidden = state.filter.section === "trash";
  }

  // ── Date filter ────────────────────────────────────────────────────────────

  function _todayDateStr() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function setDateFilter(dateStr) {
    state.filter.dateFilter = dateStr;
    _syncDateFilterUI();
    syncFilterToUrl();
    loadNotes({ reset: true });
  }

  function clearDateFilter() {
    state.filter.dateFilter = null;
    _syncDateFilterUI();
    syncFilterToUrl();
    loadNotes({ reset: true });
  }

  function _syncDateFilterUI() {
    const clearBtn = $("btn-date-clear");
    if (clearBtn) clearBtn.hidden = !state.filter.dateFilter;
  }

  function renderFolderNav() {
    if (!folderNav || !folderNavBack || !folderNavLabel || !folderNavChips)
      return;

    const currentFolderId = state.filter.folderId;
    if (!currentFolderId) {
      folderNav.hidden = true;
      return;
    }

    const currentFolder = state.folders.find((f) => f.id === currentFolderId);
    if (!currentFolder) {
      folderNav.hidden = true;
      return;
    }

    const parentFolder = currentFolder.parent_id
      ? state.folders.find((f) => f.id === currentFolder.parent_id)
      : null;

    folderNavBack.textContent = parentFolder
      ? `← ${parentFolder.name}`
      : "← All Notes";
    folderNavBack.onclick = () => {
      if (parentFolder) setFolderFilterExact(parentFolder.id);
      else setSectionFilter("all");
    };

    const children = state.folders
      .filter((f) => f.parent_id === currentFolderId)
      .sort((a, b) => a.name.localeCompare(b.name));

    folderNavChips.innerHTML = "";
    children.forEach((child) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "folder-nav__chip";
      chip.innerHTML = `
        <span class="folder-nav__chip-dot" style="background:${child.color || "#6B7280"}"></span>
        <span class="folder-nav__chip-name"></span>`;
      const nameEl = chip.querySelector(".folder-nav__chip-name");
      if (nameEl) nameEl.textContent = child.name;
      chip.addEventListener("click", () => setFolderFilterExact(child.id));
      folderNavChips.appendChild(chip);
    });

    const hasChildren = children.length > 0;
    folderNavLabel.hidden = !hasChildren;
    folderNavChips.hidden = !hasChildren;
    folderNav.hidden = false;
  }

  // ── Rendering ─────────────────────────────────────────────────────────────

  function renderNoteList() {
    noteList.className = `note-list${state.view === "rows" ? " note-list--rows" : ""}`;
    noteList.innerHTML = "";
    const isTrashView = state.filter.section === "trash";
    if (btnEmptyNew) btnEmptyNew.hidden = isTrashView;
    if (!state.notes.length) {
      emptyState.hidden = false;
      renderLoadMoreButton();
      return;
    }
    emptyState.hidden = true;
    state.notes.forEach((note) => {
      const card = buildNoteCard(note);
      noteList.appendChild(card);
    });
    renderLoadMoreButton();
  }

  function buildNoteCard(note) {
    const isTrashView = state.filter.section === "trash";
    const div = document.createElement("div");
    div.className = `note-card${note.id === state.activeNoteId ? " note-card--active" : ""}`;
    div.dataset.id = note.id;

    // Apply folder color as left border
    const folderColor = note.folder_color || "";
    if (folderColor) {
      div.style.borderLeftColor = folderColor;
    }

    const tags = (note.tags || "").split(",").filter(Boolean);
    const plainContent = _lexicalPreview(note.content || "");
    const preview = plainContent
      .replace(/[#*`>\-_\[\]!|]/g, "")
      .replace(/\n+/g, " ")
      .trim()
      .slice(0, 160);
    const dateStr = fmtDate(
      (isTrashView ? note.deleted_at : note.updated_at) || note.created_at,
      USER_TIMEZONE,
    );
    const folderName = note.folder_name || "";

    // Tag chips with color from state.tags
    const tagHtml = tags
      .map((t) => {
        const tagData = state.tags.find(
          (st) => st.name.toLowerCase() === t.toLowerCase(),
        );
        const color = tagData?.color || "";
        return `<span class="note-card__tag note-card__tag--clickable" data-tag-name="${esc(t)}" title="Filter by #${esc(t)}" style="${color ? `border-color:${color};color:${color}` : ""}">${esc(t)}</span>`;
      })
      .join("");

    // Footer
    const folderIdAttr =
      Number.isInteger(note.folder_id) && note.folder_id > 0
        ? ` data-folder-id="${note.folder_id}"`
        : "";
    const folderHtml = folderName
      ? `<span class="note-card__folder note-card__folder--clickable"${folderIdAttr} data-folder-name="${esc(folderName)}" title="Filter by folder"><span class="note-card__folder-icon">📁</span>${esc(folderName)}</span><span class="note-card__sep">•</span>`
      : "";

    div.innerHTML = `
      <div class="note-card__header">
        <div class="note-card__title" title="${esc(note.title)}">${esc(note.title)}</div>
        <button class="note-card__star${note.is_favorite ? " note-card__star--on" : ""}${isTrashView ? " note-card__star--hidden" : ""}"
                data-id="${note.id}" title="Favourite">
          ${note.is_favorite ? "★" : "☆"}
        </button>
        <button class="note-card__menu-btn${isTrashView ? " note-card__menu-btn--hidden" : ""}" data-id="${note.id}" title="More options">⋯</button>
      </div>
      <div class="note-card__body">
        <div class="note-card__preview">${esc(preview)}</div>
      </div>
      <div class="note-card__tags">${tagHtml}</div>
      <div class="note-card__footer">
        ${folderHtml}
        <span class="note-card__date"><span class="note-card__date-icon">📅</span>${dateStr}</span>
      </div>`;
    div.addEventListener("click", (e) => {
      const tagPill = e.target.closest(
        ".note-card__tag--clickable[data-tag-name]",
      );
      if (tagPill) {
        const clickedTagName = String(tagPill.dataset.tagName || "")
          .trim()
          .toLowerCase();
        const clickedTag = state.tags.find(
          (t) => t.name.toLowerCase() === clickedTagName,
        );
        if (clickedTag) setTagFilterExact(clickedTag.id);
        return;
      }

      const folderMeta = e.target.closest(".note-card__folder--clickable");
      if (folderMeta) {
        let clickedFolderId = Number.parseInt(
          String(folderMeta.dataset.folderId || ""),
          10,
        );
        if (!Number.isInteger(clickedFolderId) || clickedFolderId <= 0) {
          const clickedFolderName = String(folderMeta.dataset.folderName || "")
            .trim()
            .toLowerCase();
          const clickedFolder = state.folders.find(
            (f) =>
              String(f.name || "")
                .trim()
                .toLowerCase() === clickedFolderName,
          );
          clickedFolderId = clickedFolder ? clickedFolder.id : NaN;
        }
        if (Number.isInteger(clickedFolderId) && clickedFolderId > 0) {
          setFolderFilterExact(clickedFolderId);
        }
        return;
      }

      if (isTrashView) return;
      if (
        e.target.closest(".note-card__star") ||
        e.target.closest(".note-card__menu-btn")
      )
        return;
      openNote(note.id);
    });

    div.querySelector(".note-card__star").addEventListener("click", (e) => {
      if (isTrashView) return;
      e.stopPropagation();
      toggleFavorite(note);
    });

    div.querySelector(".note-card__menu-btn").addEventListener("click", (e) => {
      if (isTrashView) return;
      e.stopPropagation();
      showNoteContextMenu(note.id, e.clientX, e.clientY);
    });

    div.addEventListener("contextmenu", (e) => {
      if (isTrashView) return;
      e.preventDefault();
      showNoteContextMenu(note.id, e.clientX, e.clientY);
    });

    return div;
  }

  function renderFolderTree() {
    folderList.innerHTML = "";
    const byParent = {};
    state.folders.forEach((f) => {
      const key = f.parent_id || 0;
      (byParent[key] = byParent[key] || []).push(f);
    });

    function addFolder(f, depth) {
      const li = document.createElement("li");
      li.dataset.id = f.id;
      li.style.setProperty("--depth", depth);
      if (depth > 0) li.classList.add("folder--child");
      li.classList.toggle("active", state.filter.folderId === f.id);

      const hasChildren = byParent[f.id] && byParent[f.id].length > 0;
      const isExpanded = hasChildren && !state.collapsedFolderIds.has(f.id);
      if (hasChildren) li.classList.add("folder--parent");
      li.innerHTML = `
        <button type="button" class="folder-chevron${hasChildren ? "" : " folder-chevron--empty"}" aria-label="Toggle folder">
          ${hasChildren ? (isExpanded ? "▾" : "▸") : ""}
        </button>
        <span class="folder-dot" style="background:${f.color || "#4F6EF7"}"></span>
        <span class="folder-name">${esc(f.name)}</span>`;

      const chevron = li.querySelector(".folder-chevron");
      if (hasChildren && chevron) {
        chevron.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (state.collapsedFolderIds.has(f.id))
            state.collapsedFolderIds.delete(f.id);
          else state.collapsedFolderIds.add(f.id);
          renderFolderTree();
        });
      }

      li.addEventListener("click", () => setFolderFilter(f.id));
      li.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        showFolderContextMenu(f.id, e.clientX, e.clientY);
      });
      // Long-press for mobile
      addLongPressListener(li, (x, y) => showFolderContextMenu(f.id, x, y));
      folderList.appendChild(li);

      // Recurse into children
      if (isExpanded) {
        (byParent[f.id] || []).forEach((child) => addFolder(child, depth + 1));
      }
    }

    (byParent[0] || []).forEach((f) => addFolder(f, 0));
  }

  function renderTagPills() {
    tagList.innerHTML = "";
    state.tags.forEach((t) => {
      const btn = document.createElement("button");
      btn.className = `tag-pill${state.filter.tagId === t.id ? " active" : ""}`;
      const color = t.color || "#4F6EF7";
      btn.style.cssText = `background:${color}; border-color:${color};`;
      btn.textContent = `#${t.name}`;
      btn.addEventListener("click", () => setTagFilter(t.id));
      tagList.appendChild(btn);
    });
  }

  function updateCounts() {
    const countAll = $("count-all");
    const countFav = $("count-fav");
    if (countAll) countAll.textContent = state.notes.length;
    if (countFav) {
      // Quick count for favorites badge
      const fav = state.notes.filter((n) => n.is_favorite).length;
      countFav.textContent = fav || "";
    }
  }

  // ── Filters ────────────────────────────────────────────────────────────────

  function isMobileLayout() {
    return window.matchMedia("(max-width: 980px)").matches;
  }

  function syncSectionButtons() {
    sectionButtonsDesktop().forEach((el) => {
      el.classList.toggle(
        "sidebar__item--active",
        el.dataset.filter === state.filter.section,
      );
    });
    sectionButtonsMobile().forEach((el) => {
      el.classList.toggle(
        "mobile-nav__item--active",
        el.dataset.mobileFilter === state.filter.section,
      );
    });
  }

  function closeSidebar() {
    if (!isMobileLayout()) return;
    appLayout?.classList.remove("sidebar-open");
    if (sidebarBackdrop) sidebarBackdrop.hidden = true;
  }

  function openSidebar() {
    if (!isMobileLayout()) return;
    appLayout?.classList.add("sidebar-open");
    if (sidebarBackdrop) sidebarBackdrop.hidden = false;
  }

  function toggleSidebar() {
    if (isMobileLayout()) {
      if (appLayout?.classList.contains("sidebar-open")) closeSidebar();
      else openSidebar();
      return;
    }
    appLayout?.classList.toggle("sidebar-collapsed");
  }

  function setSearchVisible(visible) {
    if (!topbarSearchWrap) return;
    topbarSearchWrap.classList.toggle("topbar__search-wrap--visible", visible);
    btnSearchToggle?.setAttribute("aria-expanded", visible ? "true" : "false");
    btnSearchToggle?.classList.toggle("topbar__icon-btn--active", visible);
    if (visible) {
      requestAnimationFrame(() => searchInput?.focus());
    }
  }

  function toggleSearchBar() {
    if (!topbarSearchWrap) return;
    const isVisible = topbarSearchWrap.classList.contains(
      "topbar__search-wrap--visible",
    );
    setSearchVisible(!isVisible);
  }

  function setSectionFilter(section) {
    state.filter.section = section;
    state.filter.folderId = null;
    state.filter.tagId = null;
    syncFilterToUrl();
    syncSectionButtons();
    updateViewTitle();
    renderFolderTree();
    renderTagPills();
    closeSidebar();
    loadNotes({ reset: true });
  }

  function setFolderFilter(folderId) {
    state.filter.folderId =
      state.filter.folderId === folderId ? null : folderId;
    state.filter.tagId = null;
    state.filter.section = "all";
    syncFilterToUrl();
    syncSectionButtons();
    updateViewTitle();
    renderFolderTree();
    renderTagPills();
    closeSidebar();
    loadNotes({ reset: true });
  }

  function setFolderFilterExact(folderId) {
    state.filter.folderId = folderId || null;
    state.filter.tagId = null;
    state.filter.section = "all";
    syncFilterToUrl();
    syncSectionButtons();
    updateViewTitle();
    renderFolderTree();
    renderTagPills();
    closeSidebar();
    loadNotes({ reset: true });
  }

  function setTagFilter(tagId) {
    state.filter.tagId = state.filter.tagId === tagId ? null : tagId;
    state.filter.folderId = null;
    state.filter.section = "all";
    syncFilterToUrl();
    syncSectionButtons();
    updateViewTitle();
    renderFolderTree();
    renderTagPills();
    closeSidebar();
    loadNotes({ reset: true });
  }

  function setTagFilterExact(tagId) {
    state.filter.tagId = tagId || null;
    state.filter.folderId = null;
    state.filter.section = "all";
    syncFilterToUrl();
    syncSectionButtons();
    updateViewTitle();
    renderFolderTree();
    renderTagPills();
    closeSidebar();
    loadNotes({ reset: true });
  }

  // ── Note open / edit ───────────────────────────────────────────────────────

  async function openNote(id) {
    if (state.editorDirty) await saveCurrentNote();
    const note = await api("GET", `/notes/${id}`);
    selectNote(id);

    noteTitle.value = note.title;

    // Web app now uses Lexical only.
    _switchEditorMount();
    state.activeEditorType = "lexical";

    const activeEd = getActiveEditor();
    if (activeEd) activeEd.setContent(note.content);
    renderEditorTags(note.tags);
    updateFavBtn(note.is_favorite);

    editorPanel.classList.remove("editor-panel--closed");
    if (activeEd) activeEd.focus();
    state.editorDirty = false;
    saveIndicator.textContent = "";

    // Highlight active card
    selectNote(id);
  }

  /** Ensure the Lexical editor mount is visible. */
  function _switchEditorMount() {
    const lexMount = $("lexical-editor-mount");
    const badge = $("editor-type-badge");
    if (lexMount) lexMount.hidden = false;
    if (badge) {
      badge.textContent = "";
      badge.hidden = true;
    }
  }

  function selectNote(id) {
    state.activeNoteId = id;
    document.querySelectorAll(".note-card").forEach((el) => {
      el.classList.toggle(
        "note-card--active",
        parseInt(el.dataset.id, 10) === id,
      );
    });
  }

  function closeEditor() {
    if (state.editorDirty) saveCurrentNote();
    editorPanel.classList.add("editor-panel--closed");
    state.activeNoteId = null;
    state.editorDirty = false;
    document
      .querySelectorAll(".note-card--active")
      .forEach((el) => el.classList.remove("note-card--active"));
  }

  function renderEditorTags(tagsStr) {
    const tags = (tagsStr || "").split(",").filter(Boolean);
    editorTagsDisplay.innerHTML = tags
      .map((t) => `<span class="tag-pill">${esc(t)}</span>`)
      .join("");
  }

  function updateFavBtn(isFav) {
    const btn = $("btn-fav");
    if (!btn) return;
    btn.textContent = isFav ? "★" : "☆";
    btn.title = isFav ? "Remove from favourites" : "Add to favourites";
    btn.style.color = isFav ? "var(--star-on)" : "";
  }

  // ── Auto-save ──────────────────────────────────────────────────────────────

  function onEditorChange() {
    if (!state.activeNoteId) return;
    state.editorDirty = true;
    saveIndicator.textContent = "…editing";
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(saveCurrentNote, state.autoSaveMs);
  }

  async function saveCurrentNote(force = false) {
    if (!state.activeNoteId) return;
    if (!force && !state.editorDirty) return;
    if (state.isSaving) {
      state.pendingSave = state.pendingSave || force || state.editorDirty;
      return;
    }

    clearTimeout(state.saveTimer);
    const id = state.activeNoteId;
    state.isSaving = true;
    if (btnSaveNote) btnSaveNote.disabled = true;
    saveIndicator.textContent = "Saving…";

    const tagsStr = Array.from(editorTagsDisplay.querySelectorAll(".tag-pill"))
      .map((el) => el.textContent.trim())
      .join(",");

    const activeEd = getActiveEditor();
    try {
      await api("PUT", `/notes/${id}`, {
        title: noteTitle.value.trim() || "Untitled",
        content: activeEd ? activeEd.getContent() : "",
        tags: tagsStr,
        editor_type: state.activeEditorType,
      });
      state.editorDirty = false;
      saveIndicator.textContent = "Saved";
      setTimeout(() => {
        saveIndicator.textContent = "";
      }, 2000);

      const savedContent = activeEd ? activeEd.getContent() : "";
      const now = new Date();
      const pad = (n) => String(n).padStart(2, "0");
      const updatedAt =
        now.getFullYear() +
        "-" +
        pad(now.getMonth() + 1) +
        "-" +
        pad(now.getDate()) +
        " " +
        pad(now.getHours()) +
        ":" +
        pad(now.getMinutes()) +
        ":" +
        pad(now.getSeconds());

      // Update local state
      const idx = state.notes.findIndex((n) => n.id === id);
      if (idx !== -1) {
        state.notes[idx].title = noteTitle.value.trim() || "Untitled";
        state.notes[idx].content = savedContent;
        state.notes[idx].tags = tagsStr;
        state.notes[idx].updated_at = updatedAt;
        const card = noteList.querySelector(`[data-id="${id}"]`);
        if (card) {
          const updated = buildNoteCard(state.notes[idx]);
          card.replaceWith(updated);
        }
      }
    } catch (err) {
      console.error("Save failed:", err);
      const msg = String(err?.message || "").trim();
      saveIndicator.textContent = msg ? `⚠ ${msg}` : "⚠ Save failed";
    } finally {
      state.isSaving = false;
      if (btnSaveNote) btnSaveNote.disabled = false;
      if (state.pendingSave) {
        state.pendingSave = false;
        // Run exactly one queued save after the current request completes.
        saveCurrentNote(state.editorDirty);
      }
    }
  }

  // ── CRUD actions ───────────────────────────────────────────────────────────

  async function createNote() {
    const body = {
      title: "New note",
      content: "",
      folder_id: state.filter.folderId || null,
      editor_type: "lexical",
    };
    // Mirror desktop behaviour: prefill tag when browsing a tag filter
    if (state.filter.tagId) {
      const tag = state.tags.find((t) => t.id === state.filter.tagId);
      if (tag) body.tags = tag.name;
    }
    const data = await api("POST", "/notes", body);
    await openNote(data.id);
    loadNotes({ reset: true });
    noteTitle.select();
  }

  async function createNoteAtRoot() {
    const data = await api("POST", "/notes", {
      title: "New note",
      content: "",
      folder_id: null,
      editor_type: "lexical",
    });
    await openNote(data.id);
    loadNotes({ reset: true });
    noteTitle.select();
  }

  async function createNoteFromClipboard() {
    let clipContent = "";
    try {
      clipContent = await navigator.clipboard.readText();
    } catch {
      alert(
        "Clipboard access unavailable. Make sure the page is served over HTTPS and you have granted clipboard permission.",
      );
      return;
    }
    const body = {
      title: "New note",
      content: clipContent,
      folder_id: state.filter.folderId || null,
      editor_type: "lexical",
    };
    if (state.filter.tagId) {
      const tag = state.tags.find((t) => t.id === state.filter.tagId);
      if (tag) body.tags = tag.name;
    }
    try {
      const data = await api("POST", "/notes", body);
      await openNote(data.id);
      loadNotes({ reset: true });
      noteTitle.select();
    } catch (err) {
      console.error("Create note from clipboard failed:", err);
      alert("Could not create note. " + (err?.message || "Please try again."));
    }
  }

  async function createNoteWithoutFolderFallback() {
    const previousFolderId = state.filter.folderId;
    state.filter.folderId = null;
    try {
      await createNote();
    } finally {
      state.filter.folderId = previousFolderId;
    }
  }

  async function createNoteSafely() {
    if (btnNewNote) btnNewNote.disabled = true;
    if (btnEmptyNew) btnEmptyNew.disabled = true;
    if (btnMobileNewNote) btnMobileNewNote.disabled = true;
    try {
      await createNote();
    } catch (err) {
      console.error("Failed to create note:", err);
      const message = String(err?.message || "").toLowerCase();
      const shouldRetryWithoutFolder =
        state.filter.folderId != null &&
        (message.includes("folder") ||
          message.includes("constraint") ||
          message.includes("http 500"));
      if (shouldRetryWithoutFolder) {
        try {
          await createNoteWithoutFolderFallback();
          return;
        } catch (retryErr) {
          console.error("Create note retry failed:", retryErr);
          alert(
            "Could not create a new note. " +
              (retryErr?.message || "Please try again."),
          );
          return;
        }
      }
      alert(
        "Could not create a new note. " + (err?.message || "Please try again."),
      );
    } finally {
      if (btnNewNote) btnNewNote.disabled = false;
      if (btnEmptyNew) btnEmptyNew.disabled = false;
      if (btnMobileNewNote) btnMobileNewNote.disabled = false;
    }
  }

  // Long-press helper (mobile) ─────────────────────────────────────────────
  function addLongPressListener(el, callback, duration = 520) {
    if (!el) return;
    let timer = null;
    let moved = false;
    el.addEventListener(
      "touchstart",
      (e) => {
        moved = false;
        timer = setTimeout(() => {
          if (!moved) {
            e.preventDefault();
            const touch = e.touches[0];
            callback(touch.clientX, touch.clientY);
          }
        }, duration);
      },
      { passive: false },
    );
    el.addEventListener("touchmove", () => {
      moved = true;
      clearTimeout(timer);
    });
    el.addEventListener("touchend", () => clearTimeout(timer));
    el.addEventListener("touchcancel", () => clearTimeout(timer));
  }

  // ── Main area context menu ─────────────────────────────────────────────────
  function showMainAreaContextMenu(x, y) {
    const isTrash = state.filter.section === "trash";
    if (isTrash) return;
    showContextMenu(x, y, [
      { label: "📝  New Note", action: () => createNoteSafely() },
      {
        label: "📋  New Note from Clipboard",
        action: () => createNoteFromClipboard(),
      },
      "sep",
      {
        label: "📁  New Folder",
        action: () => openFolderModal(state.filter.folderId || null),
      },
    ]);
  }

  async function toggleFavorite(note) {
    await api("PUT", `/notes/${note.id}`, {
      is_favorite: !note.is_favorite ? 1 : 0,
    });
    const isFav = !note.is_favorite;
    note.is_favorite = isFav ? 1 : 0;
    if (state.activeNoteId === note.id) updateFavBtn(isFav);
    // re-render only the affected card
    const card = noteList.querySelector(`[data-id="${note.id}"]`);
    if (card) card.replaceWith(buildNoteCard(note));
    updateCounts();
  }

  // ── Folder modal ───────────────────────────────────────────────────────────

  let _newFolderParentId = null;
  let _folderModalSnapshot = { name: "", color: "" };

  function _folderLocationLabel(parentId) {
    if (!parentId) return "Root";
    const parent = state.folders.find((f) => f.id === parentId);
    return parent ? parent.name : "Root";
  }

  function _setFolderColor(color) {
    _folderDraftColor = (color || "").trim();
    const colorInput = $("folder-color-input");
    const preview = $("folder-color-preview");
    if (colorInput) colorInput.value = _folderDraftColor || "#6B7280";
    if (preview) preview.style.background = _folderDraftColor || "transparent";
  }

  function _folderModalState() {
    return {
      name: $("folder-name-input")?.value.trim() || "",
      color: _folderDraftColor || "",
    };
  }

  function _folderModalIsDirty() {
    const current = _folderModalState();
    return (
      current.name !== _folderModalSnapshot.name ||
      current.color !== _folderModalSnapshot.color
    );
  }

  function _hideFolderModal() {
    $("folder-modal").hidden = true;
    _newFolderParentId = null;
    _folderModalSnapshot = { name: "", color: "" };
    _folderDraftColor = "";
  }

  async function tryCloseFolderModal() {
    if (!_folderModalIsDirty()) {
      _hideFolderModal();
      return;
    }
    const createBeforeClose = confirm(
      "You have unsaved folder details. Create the folder before closing?\n\nPress OK to create, Cancel for more options.",
    );
    if (createBeforeClose) {
      await saveFolder();
      return;
    }
    const discard = confirm("Discard unsaved folder details?");
    if (discard) _hideFolderModal();
  }

  function openFolderModal(parentId = null) {
    _newFolderParentId = parentId || null;
    const modal = $("folder-modal");
    $("folder-name-input").value = "";
    _setFolderColor("");
    const locationLabel = $("folder-location-label");
    if (locationLabel)
      locationLabel.textContent = _folderLocationLabel(_newFolderParentId);
    _folderModalSnapshot = _folderModalState();
    modal.hidden = false;
    $("folder-name-input").focus();
  }

  async function saveFolder() {
    const name = $("folder-name-input").value.trim();
    if (!name) return;
    try {
      await api("POST", "/folders", {
        name,
        parent_id: _newFolderParentId,
        color: _folderDraftColor || null,
      });
      _hideFolderModal();
      await loadFolders();
      await loadNotes({ reset: true });
    } catch (err) {
      alert(
        "Failed to create folder. " + (err?.message || "Please try again."),
      );
    }
  }

  // ── Rename folder modal ────────────────────────────────────────────────────

  let _renameFolderId = null;

  function openRenameFolderModal(folderId) {
    const folder = state.folders.find((f) => f.id === folderId);
    if (!folder) return;
    _renameFolderId = folderId;
    $("rename-folder-input").value = folder.name;
    $("rename-folder-modal").hidden = false;
    $("rename-folder-input").select();
  }

  async function saveRenameFolder() {
    const name = $("rename-folder-input").value.trim();
    if (!name || !_renameFolderId) return;
    await api("PUT", `/folders/${_renameFolderId}`, { name });
    $("rename-folder-modal").hidden = false;
    $("rename-folder-modal").hidden = true;
    _renameFolderId = null;
    await loadFolders();
    await loadNotes({ reset: true }); // note cards show folder names
  }

  async function deleteFolder(folderId) {
    const folder = state.folders.find((f) => f.id === folderId);
    if (!folder) return;
    if (
      !confirm(
        `Delete folder "${folder.name}"? Notes inside will become unfoldered.`,
      )
    )
      return;
    await api("DELETE", `/folders/${folderId}`);
    if (state.filter.folderId === folderId) {
      state.filter.folderId = null;
      state.filter.section = "all";
      syncFilterToUrl();
    }
    await loadFolders();
    await loadNotes({ reset: true });
  }

  async function createNoteInFolder(folderId) {
    const data = await api("POST", "/notes", {
      title: "New note",
      content: "",
      folder_id: folderId,
      editor_type: "lexical",
    });
    await openNote(data.id);
    loadNotes({ reset: true });
    noteTitle.select();
  }

  // ── Context menu ──────────────────────────────────────────────────────────

  const ctxMenu = $("ctx-menu");
  let _ctxCleanup = null;

  function showContextMenu(x, y, items) {
    hideContextMenu();
    ctxMenu.innerHTML = "";
    items.forEach((item) => {
      if (item === "sep") {
        const sep = document.createElement("div");
        sep.className = "ctx-menu__sep";
        ctxMenu.appendChild(sep);
      } else {
        const el = document.createElement("button");
        el.type = "button";
        el.className = `ctx-menu__item${item.danger ? " ctx-menu__item--danger" : ""}`;
        el.textContent = item.label;
        el.addEventListener("mousedown", (e) => {
          // Keep global dismiss handlers from swallowing the item interaction.
          e.preventDefault();
          e.stopPropagation();
        });
        el.addEventListener("click", async (e) => {
          e.preventDefault();
          e.stopPropagation();
          hideContextMenu();
          try {
            await item.action();
          } catch (err) {
            console.error("Context menu action failed:", err);
          }
        });
        ctxMenu.appendChild(el);
      }
    });

    // Position — keep inside viewport
    ctxMenu.hidden = false;
    const vw = window.innerWidth,
      vh = window.innerHeight;
    const mw = ctxMenu.offsetWidth || 180,
      mh = ctxMenu.offsetHeight || 200;
    ctxMenu.style.left = (x + mw > vw ? vw - mw - 8 : x) + "px";
    ctxMenu.style.top = (y + mh > vh ? vh - mh - 8 : y) + "px";

    const dismiss = (e) => {
      if (!ctxMenu.contains(e.target)) hideContextMenu();
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape") hideContextMenu();
    };
    // Defer global dismiss listeners so the opening right-click event
    // doesn't instantly close the menu while it is still bubbling.
    setTimeout(() => {
      if (ctxMenu.hidden) return;
      document.addEventListener("mousedown", dismiss);
      document.addEventListener("contextmenu", dismiss);
      document.addEventListener("keydown", onKeyDown);
    }, 0);
    _ctxCleanup = () => {
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("contextmenu", dismiss);
      document.removeEventListener("keydown", onKeyDown);
    };
  }

  function hideContextMenu() {
    ctxMenu.hidden = true;
    ctxMenu.innerHTML = "";
    if (_ctxCleanup) {
      _ctxCleanup();
      _ctxCleanup = null;
    }
  }

  function toggleEditorFullscreen() {
    const btn = $("btn-fullscreen-editor");
    const isFullscreen = editorPanel.classList.toggle(
      "editor-panel--fullscreen",
    );
    if (btn) {
      btn.textContent = isFullscreen ? "🗗" : "⤢";
      btn.title = isFullscreen ? "Exit fullscreen" : "Fullscreen editor";
    }
  }

  async   function showMoveToFolderMenu(noteId, x, y) {
    hideContextMenu();

    const note = state.notes.find((n) => n.id === noteId);
    if (!note) return;

    const topLevelFolders = state.folders
      .filter((f) => !f.parent_id)
      .sort((a, b) => (a.name || "").localeCompare(b.name || ""));

    const currentFolderId = note.folder_id;

    const buildSubmenu = () => {
      const sm = document.createElement("div");
      sm.className = "ctx-menu__submenu";
      sm.hidden = false;

      // "No folder" option
      const unfiledBtn = document.createElement("button");
      unfiledBtn.type = "button";
      unfiledBtn.className = "ctx-menu__item";
      unfiledBtn.textContent = "📁  No folder (Unfiled)";
      if (currentFolderId == null || currentFolderId === 0) {
        unfiledBtn.classList.add("ctx-menu__item--active");
      }
      unfiledBtn.addEventListener("mousedown", (e) => e.preventDefault());
      unfiledBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        sm.hidden = true;
        moveNoteToFolder(noteId, null);
      });
      sm.appendChild(unfiledBtn);

      topLevelFolders.forEach((folder) => {
        const folderBtn = document.createElement("button");
        folderBtn.type = "button";
        folderBtn.className = "ctx-menu__item";
        const isActive = currentFolderId === folder.id;
        const colorDot = folder.color
          ? `<span class="ctx-menu__folder-dot" style="background:${folder.color}"></span>`
          : "";
        folderBtn.innerHTML = `${colorDot}${escapeHtml(folder.name)}`;
        if (isActive) {
          folderBtn.classList.add("ctx-menu__item--active");
          folderBtn.style.fontWeight = "700";
        }
        folderBtn.addEventListener("mousedown", (e) => e.preventDefault());
        folderBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          sm.hidden = true;
          moveNoteToFolder(noteId, folder.id);
        });
        sm.appendChild(folderBtn);

        const subfolders = state.folders
          .filter((f) => f.parent_id === folder.id)
          .sort((a, b) => (a.name || "").localeCompare(b.name || ""));

        subfolders.forEach((sub) => {
          const subBtn = document.createElement("button");
          subBtn.type = "button";
          subBtn.className = "ctx-menu__item ctx-menu__item--indent-2";
          const subActive = currentFolderId === sub.id;
          const subDot = sub.color
            ? `<span class="ctx-menu__folder-dot" style="background:${sub.color}"></span>`
            : "";
          subBtn.innerHTML = `${subDot}${escapeHtml(sub.name)}`;
          if (subActive) {
            subBtn.classList.add("ctx-menu__item--active");
            subBtn.style.fontWeight = "700";
          }
          subBtn.addEventListener("mousedown", (e) => e.preventDefault());
          subBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            sm.hidden = true;
            moveNoteToFolder(noteId, sub.id);
          });
          sm.appendChild(subBtn);
        });
      });

      const sepBefore = document.createElement("div");
      sepBefore.className = "ctx-menu__sep";
      sm.insertBefore(sepBefore, sm.firstChild);

      return sm;
    };

    const submenu = buildSubmenu();
    document.body.appendChild(submenu);
    positionCtxMenu(submenu, x, y);

    const dismiss = (e) => {
      if (submenu.contains(e.target)) return;
      submenu.remove();
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("contextmenu", dismiss);
      document.removeEventListener("keydown", onKeyDown);
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        submenu.remove();
        document.removeEventListener("mousedown", dismiss);
        document.removeEventListener("contextmenu", dismiss);
        document.removeEventListener("keydown", onKeyDown);
      }
    };
    setTimeout(() => {
      document.addEventListener("mousedown", dismiss);
      document.addEventListener("contextmenu", dismiss);
      document.addEventListener("keydown", onKeyDown);
    }, 0);

    function positionCtxMenu(el, x, y) {
      el.hidden = false;
      const vw = window.innerWidth,
        vh = window.innerHeight;
      const mw = el.offsetWidth || 180,
        mh = el.offsetHeight || 200;
      el.style.left = (x + mw > vw ? x - mw - 8 : x) + "px";
      el.style.top = (y + mh > vh ? vh - mh - 8 : y) + "px";
    }
  }

  async function moveNoteToFolder(noteId, folderId) {
    try {
      const folderIdPayload = folderId === null ? null : String(folderId);
      const payload = {
        folder_id: folderIdPayload,
        append_tags: null,
      };
      await api("PUT", `/notes/${noteId}`, payload);
      await loadNotes({ reset: true });
      if (state.activeNoteId === noteId) {
        const saved = state.notes.find((n) => n.id === noteId);
        if (saved) {
          state.notes = state.notes.map((n) =>
            n.id === noteId ? { ...n, folder_id: folderId } : n,
          );
          openNote(noteId);
        }
      }
    } catch (err) {
      console.error("Move to folder failed:", err);
    }
  }

  function showNoteContextMenu(noteId, x, y) {
    const note = state.notes.find((n) => n.id === noteId);
    if (!note) return;
    const isTrash = state.filter.section === "trash";

    showContextMenu(x, y, [
      { label: "📝  Open Note", action: () => openNote(noteId) },
      {
        label: note.is_favorite ? "⭐  Unfavorite" : "☆  Favorite",
        action: () => toggleFavorite(note),
      },
      { label: "📁  Move to Folder", action: () => showMoveToFolderMenu(noteId, x, y) },
      { label: "📋  Copy Content", action: () => copyNoteContent(noteId) },
      { label: "🏷️  Add Tag", action: () => openTagsModal() },
      ...(isTrash
        ? []
        : ["sep", { label: "🗑️  Delete", danger: true, action: () => deleteSingleNote(noteId) }]),
    ]);
  }

  function showFolderContextMenu(folderId, x, y) {
    showContextMenu(x, y, [
      {
        label: "📝  Create Note Here",
        action: () => createNoteInFolder(folderId),
      },
      {
        label: "📁  Create Subfolder",
        action: () => openFolderModal(folderId),
      },
      "sep",
      {
        label: "✏️  Rename Folder",
        action: () => openRenameFolderModal(folderId),
      },
      {
        label: "🗑️  Delete Folder",
        danger: true,
        action: () => deleteFolder(folderId),
      },
    ]);
  }

  async function copyNoteContent(noteId) {
    try {
      const note = await api("GET", `/notes/${noteId}`);
      await navigator.clipboard.writeText(note.content || "");
    } catch {
      // Fallback for non-HTTPS
      const note = state.notes.find((n) => n.id === noteId);
      const ta = document.createElement("textarea");
      ta.value = note?.content || "";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
  }

  async function deleteSingleNote(noteId) {
    if (!confirm("Move this note to trash?")) return;
    await api("DELETE", `/notes/${noteId}`);
    if (state.activeNoteId === noteId) closeEditor();
    await loadNotes({ reset: true });
  }

  // ── Tags modal ─────────────────────────────────────────────────────────────

  function openTagsModal() {
    const current = Array.from(editorTagsDisplay.querySelectorAll(".tag-pill"))
      .map((el) => el.textContent.trim())
      .join(", ");
    $("tags-input").value = current;
    populateTagDropdown();
    $("tags-modal").hidden = false;
    $("tags-input").focus();
  }

  function populateTagDropdown() {
    const select = $("tags-select");
    if (!select) return;

    const selected = new Set(
      $("tags-input")
        .value.split(",")
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean),
    );

    select.innerHTML = '<option value="">Choose existing tag</option>';
    state.tags
      .filter((tag) => !selected.has(tag.name.toLowerCase()))
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach((tag) => {
        const opt = document.createElement("option");
        opt.value = tag.name;
        opt.textContent = tag.name;
        select.appendChild(opt);
      });
  }

  function addSelectedTag() {
    const select = $("tags-select");
    const input = $("tags-input");
    if (!select || !input || !select.value) return;

    const tags = input.value
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const seen = new Set(tags.map((t) => t.toLowerCase()));
    if (!seen.has(select.value.toLowerCase())) tags.push(select.value);
    input.value = tags.join(", ");
    select.value = "";
    populateTagDropdown();
  }

  async function saveTags() {
    const raw = $("tags-input").value;
    const tags = raw
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    renderEditorTags(tags.join(","));
    $("tags-modal").hidden = true;
    // Persist immediately
    if (state.activeNoteId) {
      await api("PUT", `/notes/${state.activeNoteId}`, {
        tags: tags.join(","),
      });
      await loadTags(); // refresh sidebar tag list
    }
  }

  // ── UI bindings ────────────────────────────────────────────────────────────

  function bindUI() {
    if (!IS_GUEST_MODE) {
      btnGuestImportAccept?.addEventListener("click", () => {
        _acceptGuestImportPrompt();
      });
      btnGuestImportDismiss?.addEventListener("click", () => {
        _dismissGuestImportPrompt();
      });
    }

    if (IS_GUEST_MODE) {
      btnGuestExport?.addEventListener("click", async () => {
        try {
          await exportGuestBackup();
        } catch (err) {
          alert("Failed to export guest backup.");
        }
      });
      btnGuestImport?.addEventListener("click", () => {
        guestImportFile?.click();
      });
      guestImportFile?.addEventListener("change", async (event) => {
        const file = event?.target?.files?.[0] || null;
        if (!file) return;
        try {
          await importGuestBackupFile(file);
        } catch (err) {
          alert(String(err?.message || "Failed to import backup"));
        } finally {
          event.target.value = "";
        }
      });
    }

    // New note
    btnNewNote?.addEventListener("click", () => {
      createNoteSafely();
    });
    btnEmptyNew?.addEventListener("click", () => {
      createNoteSafely();
    });

    // Keyboard shortcut Ctrl+N
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "n") {
        e.preventDefault();
        createNoteSafely();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        saveCurrentNote(true);
      }
      if (e.key === "Escape") {
        closeSidebar();
        closeEditor();
      }
    });

    // Sidebar nav
    document.querySelectorAll(".sidebar__item[data-filter]").forEach((el) => {
      el.addEventListener("click", () => setSectionFilter(el.dataset.filter));
    });
    document
      .querySelectorAll(".mobile-nav__item[data-mobile-filter]")
      .forEach((el) => {
        el.addEventListener("click", () =>
          setSectionFilter(el.dataset.mobileFilter),
        );
      });

    btnSidebarToggle?.addEventListener("click", toggleSidebar);
    btnSidebarClose?.addEventListener("click", closeSidebar);
    btnSearchToggle?.addEventListener("click", toggleSearchBar);
    btnMobileMenu?.addEventListener("click", toggleSidebar);
    btnMobileNewNote?.addEventListener("click", () => {
      createNoteSafely();
    });
    $("btn-mobile-new-caret")?.addEventListener("click", (e) => {
      e.stopPropagation();
      const rect = e.currentTarget.getBoundingClientRect();
      showContextMenu(rect.left, rect.top, [
        { label: "📝  New Note", action: () => createNoteSafely() },
        {
          label: "📁  New Folder",
          action: () => openFolderModal(state.filter.folderId || null),
        },
        {
          label: "📋  New Note from Clipboard",
          action: () => createNoteFromClipboard(),
        },
      ]);
    });
    sidebarBackdrop?.addEventListener("click", closeSidebar);

    // Right-click on folder section (empty area / header) → root folder operations
    const folderSection = folderList?.closest(".sidebar__section");
    folderSection?.addEventListener("contextmenu", (e) => {
      if (e.target.closest("li[data-id]")) return; // folder items handle their own
      e.preventDefault();
      showContextMenu(e.clientX, e.clientY, [
        { label: "📁  New Root Folder", action: () => openFolderModal(null) },
        { label: "📝  New Note at Root", action: () => createNoteAtRoot() },
      ]);
    });
    addLongPressListener(
      folderSection?.querySelector(".sidebar__section-header") || folderSection,
      (x, y) =>
        showContextMenu(x, y, [
          { label: "📁  New Root Folder", action: () => openFolderModal(null) },
          { label: "📝  New Note at Root", action: () => createNoteAtRoot() },
        ]),
    );

    // Right-click on main content area (not on a note card) → quick create menu
    document
      .querySelector(".main-content")
      ?.addEventListener("contextmenu", (e) => {
        if (e.target.closest(".note-card")) return; // note cards have their own handler
        if (e.target.closest(".editor-panel")) return;
        if (e.target.closest(".topbar")) return;
        if (state.filter.section === "trash") return;
        e.preventDefault();
        showMainAreaContextMenu(e.clientX, e.clientY);
      });

    window.addEventListener("resize", () => {
      if (!isMobileLayout()) closeSidebar();
    });

    // Add folder
    $("btn-add-folder").addEventListener("click", () => openFolderModal(null));
    $("btn-folder-cancel").addEventListener("click", () => {
      tryCloseFolderModal();
    });
    $("btn-folder-save").addEventListener("click", () => {
      saveFolder();
    });
    $("folder-name-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") saveFolder();
    });
    $("btn-folder-color")?.addEventListener("click", () =>
      $("folder-color-input")?.click(),
    );
    $("folder-color-input")?.addEventListener("input", (e) => {
      _setFolderColor(e?.target?.value || "");
    });

    // Rename folder
    $("btn-rename-folder-cancel").addEventListener("click", () => {
      $("rename-folder-modal").hidden = true;
    });
    $("btn-rename-folder-save").addEventListener("click", saveRenameFolder);
    $("rename-folder-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") saveRenameFolder();
    });

    // Editor controls
    $("btn-close-editor").addEventListener("click", closeEditor);
    $("btn-fullscreen-editor")?.addEventListener(
      "click",
      toggleEditorFullscreen,
    );
    $("btn-save-note")?.addEventListener("click", () => saveCurrentNote(true));
    $("btn-delete-note").addEventListener("click", () => {
      if (state.activeNoteId) deleteSingleNote(state.activeNoteId);
    });
    $("btn-fav").addEventListener("click", async () => {
      if (!state.activeNoteId) return;
      const note = state.notes.find((n) => n.id === state.activeNoteId);
      if (note) await toggleFavorite(note);
    });

    // Note title auto-save on blur / enter
    noteTitle.addEventListener("input", () => {
      if (!state.activeNoteId) return;
      state.editorDirty = true;
      clearTimeout(state.saveTimer);
      state.saveTimer = setTimeout(saveCurrentNote, state.autoSaveMs);
    });

    // Tags modal
    $("btn-edit-tags").addEventListener("click", openTagsModal);
    $("btn-tags-cancel").addEventListener("click", () => {
      $("tags-modal").hidden = true;
    });
    $("btn-tags-save").addEventListener("click", saveTags);
    $("btn-tags-add")?.addEventListener("click", addSelectedTag);
    $("tags-select")?.addEventListener("change", addSelectedTag);
    $("tags-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") saveTags();
    });
    $("tags-input").addEventListener("input", populateTagDropdown);

    // Tag manager modal (create/edit/delete tags)
    $("btn-add-tag")?.addEventListener("click", openTagManagerModal);
    $("btn-tag-add")?.addEventListener("click", createTag);
    $("btn-tag-manager-close")?.addEventListener("click", () => {
      $("tag-manager-modal").hidden = true;
    });
    $("tag-color-btn")?.addEventListener("click", openTagCreateColorPicker);
    $("tag-new-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") createTag();
    });

    // Close modals on overlay click
    [
      $("rename-folder-modal"),
      $("tags-modal"),
      $("tag-manager-modal"),
      $("conflicts-modal"),
    ].forEach((overlay) => {
      overlay?.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.hidden = true;
      });
    });
    $("folder-modal")?.addEventListener("click", (e) => {
      if (e.target === $("folder-modal")) {
        tryCloseFolderModal();
      }
    });

    // Search
    setSearchVisible(false);

    initSidebarSectionResizer();

    let searchTimer;
    searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.filter.keyword = searchInput.value.trim();
        syncFilterToUrl();
        loadNotes({ reset: true });
      }, 280);
    });

    // Sort
    sortSelect.addEventListener("change", () => {
      state.filter.sort = sortSelect.value;
      syncFilterToUrl();
      loadNotes({ reset: true });
    });

    // Date filter
    $("btn-date-today")?.addEventListener("click", () =>
      setDateFilter(_todayDateStr()),
    );
    $("btn-date-pick")?.addEventListener("click", () => {
      const input = $("date-filter-input");
      if (!input) return;
      if (state.filter.dateFilter) input.value = state.filter.dateFilter;
      input.showPicker ? input.showPicker() : input.click();
    });
    $("date-filter-input")?.addEventListener("change", (e) => {
      if (e.target.value) setDateFilter(e.target.value);
    });
    $("btn-date-clear")?.addEventListener("click", () => clearDateFilter());
    _syncDateFilterUI();

    btnLoadMore?.addEventListener("click", () => {
      if (!state.paging.hasMore || state.paging.loading) return;
      loadNotes({ reset: false });
    });

    // View toggle
    $("btn-toggle-view").addEventListener("click", () => {
      state.view = state.view === "grid" ? "rows" : "grid";
      syncViewToggleButton();
      renderNoteList();
    });

    // Conflict resolution callback (called by conflicts.js after resolving)
    window._onConflictResolved = () => {
      ConflictUI.loadConflicts().then((conflicts) => {
        const banner = $("conflict-banner");
        const countEl = $("conflict-count");
        if (countEl) countEl.textContent = conflicts.length;
        if (banner) banner.hidden = conflicts.length === 0;
      });
      loadNotes({ reset: true });
    };

    syncSectionButtons();
    syncViewToggleButton();
    updateViewTitle();
    syncFilterToUrl();
    renderLoadMoreButton();
  }

  function initSidebarSectionResizer() {
    if (
      !sidebarBody ||
      !sidebarFolderSection ||
      !sidebarTagSection ||
      !sidebarSectionsResizer
    )
      return;

    const minPaneHeight = 90;
    const storageKey = "notestack.sidebar.folderPaneHeight";
    let dragging = false;

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function maxFolderHeight() {
      const total = sidebarBody.clientHeight;
      const handle = sidebarSectionsResizer.offsetHeight || 14;
      return Math.max(minPaneHeight, total - handle - minPaneHeight);
    }

    function applyFolderHeight(px, { persist = false } = {}) {
      const next = clamp(Math.round(px), minPaneHeight, maxFolderHeight());
      sidebarFolderSection.style.flex = `0 0 ${next}px`;
      sidebarTagSection.style.flex = "1 1 auto";
      sidebarSectionsResizer.setAttribute("aria-valuenow", String(next));
      if (persist) {
        try {
          localStorage.setItem(storageKey, String(next));
        } catch {}
      }
    }

    function yToFolderHeight(clientY) {
      const bodyRect = sidebarBody.getBoundingClientRect();
      const handleHalf = (sidebarSectionsResizer.offsetHeight || 14) / 2;
      return clientY - bodyRect.top - handleHalf;
    }

    sidebarSectionsResizer.setAttribute("role", "separator");
    sidebarSectionsResizer.setAttribute("aria-orientation", "horizontal");
    sidebarSectionsResizer.setAttribute("aria-valuemin", String(minPaneHeight));

    let initial = sidebarFolderSection.getBoundingClientRect().height;
    try {
      const saved = Number.parseInt(localStorage.getItem(storageKey) || "", 10);
      if (Number.isInteger(saved) && saved > 0) initial = saved;
    } catch {}
    applyFolderHeight(initial);

    sidebarSectionsResizer.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      dragging = true;
      e.preventDefault();
      sidebarSectionsResizer.setPointerCapture(e.pointerId);
    });

    sidebarSectionsResizer.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      applyFolderHeight(yToFolderHeight(e.clientY));
    });

    sidebarSectionsResizer.addEventListener("pointerup", (e) => {
      if (!dragging) return;
      dragging = false;
      applyFolderHeight(yToFolderHeight(e.clientY), { persist: true });
      if (sidebarSectionsResizer.hasPointerCapture(e.pointerId)) {
        sidebarSectionsResizer.releasePointerCapture(e.pointerId);
      }
    });

    sidebarSectionsResizer.addEventListener("pointercancel", () => {
      dragging = false;
    });

    sidebarSectionsResizer.addEventListener("keydown", (e) => {
      if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const current = sidebarFolderSection.getBoundingClientRect().height;
      if (e.key === "ArrowUp")
        applyFolderHeight(current - 24, { persist: true });
      if (e.key === "ArrowDown")
        applyFolderHeight(current + 24, { persist: true });
      if (e.key === "Home") applyFolderHeight(minPaneHeight, { persist: true });
      if (e.key === "End")
        applyFolderHeight(maxFolderHeight(), { persist: true });
    });

    window.addEventListener("resize", () => {
      if (!sidebarFolderSection.style.flexBasis) return;
      const current = sidebarFolderSection.getBoundingClientRect().height;
      applyFolderHeight(current);
    });
  }

  function syncViewToggleButton() {
    const btn = $("btn-toggle-view");
    if (!btn) return;
    const isGrid = state.view === "grid";
    btn.textContent = isGrid ? "⊞" : "☰";
    btn.title = isGrid ? "Switch to list view" : "Switch to grid view";
    btn.setAttribute("aria-label", btn.title);
  }

  function esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Extract plain-text preview from a Lexical JSON state string.
  // Returns '' if parsing fails (graceful fallback for truncated/empty states).
  function _lexicalPreview(content) {
    if (!content) return "";
    try {
      const parsed = JSON.parse(content);
      const texts = [];
      function walk(node) {
        if (!node) return;
        if (node.type === "text") {
          texts.push(node.text || "");
          return;
        }
        (node.children || []).forEach(walk);
      }
      walk(parsed.root);
      return texts.join(" ");
    } catch {
      return content.slice(0, 160);
    }
  }

  function fmtDate(iso, timezone) {
    if (!iso) return "";
    try {
      let normalized = iso.replace(" ", "T");
      normalized = normalized.replace(/([+\-]\d{2})$/, "$1:00");
      if (!/[Zz]$/.test(normalized) && !/[\+\-]\d{2}:\d{2}$/.test(normalized)) {
        normalized += "Z";
      }
      const d = new Date(normalized);
      const now = new Date();
      const diff = now - d;
      if (diff < 60000) return "just now";
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
      return d.toLocaleDateString(timezone || undefined, {
        month: "short",
        day: "numeric",
      });
    } catch {
      return iso.slice(0, 10);
    }
  }
})();
