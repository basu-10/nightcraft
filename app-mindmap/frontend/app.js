import {
  createEditor,
  $getRoot,
  $getSelection,
  $isRangeSelection,
  $isNodeSelection,
  $createParagraphNode,
  $createTextNode,
  FORMAT_TEXT_COMMAND,
} from "lexical";
import { HeadingNode, QuoteNode, registerRichText } from "@lexical/rich-text";
import { LinkNode, $createLinkNode } from "@lexical/link";
import {
  ListNode,
  ListItemNode,
  INSERT_UNORDERED_LIST_COMMAND,
  REMOVE_LIST_COMMAND,
} from "@lexical/list";
import { $generateHtmlFromNodes, $generateNodesFromDOM } from "@lexical/html";
import {
  $patchStyleText,
  $getSelectionStyleValueForProperty,
} from "@lexical/selection";
import { TableNode, TableCellNode, TableRowNode } from "@lexical/table";
import * as XLSX from "xlsx";
import { getBook, saveBook } from "./db.js";

const CARD_TYPES = {
  text: { color: "#6c63ff", label: "Text" },
  image: { color: "#ce93d8", label: "Image" },
  table: { color: "#ffb74d", label: "Table" },
};
// ── State ──
const board = {
  boardTitle: "Research Workspace",
  cards: [],
  edges: [],
  tagDefinitions: [],
  savedViews: [],
  activeQuickView: "all",
  panX: 0,
  panY: 0,
  zoom: 1,
  selectedCardIds: new Set(),
  editingCardId: null,
  maximizedCardId: null,
  connectingFrom: null,
  connectingPending: null,
  isPanning: false,
  panStart: null,
  panStartOffset: null,
  dragCardIds: null,
  dragStart: null,
  dragOrigPositions: null,
  resizeCardId: null,
  resizeStart: null,
  resizeOrig: null,
  editors: new Map(),
  lastSelectedCardId: null,
  selectedEdgeId: null,
  leftSidebarVisible: false,
  multiSelectMode: false,
  clipboardCards: null,
};

// ── Book (multi-canvas container) ──
const book = {
  id: null,
  bookTitle: "Research Workspace",
  activeCanvasId: null,
  canvases: [],
};

function getCanvasById(canvasId) {
  return book.canvases.find((c) => c.id === canvasId) || null;
}

function saveActiveCanvasToBook() {
  const idx = book.canvases.findIndex((c) => c.id === book.activeCanvasId);
  const existingName = idx !== -1 ? book.canvases[idx].name : board.boardTitle;
  const snapshot = {
    id: book.activeCanvasId,
    name: existingName,
    cards: JSON.parse(JSON.stringify(board.cards)),
    edges: JSON.parse(JSON.stringify(board.edges)),
    tagDefinitions: JSON.parse(JSON.stringify(board.tagDefinitions)),
    savedViews: board.savedViews,
    activeQuickView: board.activeQuickView,
    panX: board.panX,
    panY: board.panY,
    zoom: board.zoom,
  };
  if (idx >= 0) {
    book.canvases[idx] = snapshot;
  } else {
    if (book.activeCanvasId) book.canvases.push(snapshot);
  }
}

function loadCanvasIntoBoard(canvas) {
  board.editors.forEach((ed) => ed.setRootElement(null));
  board.editors.clear();
  board.editingCardId = null;
  board.maximizedCardId = null;
  board.selectedCardIds.clear();
  board.selectedEdgeId = null;
  board.multiSelectMode = false;
  board.connectingFrom = null;
  board.connectingPending = null;
  board.isPanning = false;
  board.panStart = null;
  board.panStartOffset = null;
  board.dragCardIds = null;
  board.dragStart = null;
  board.dragOrigPositions = null;
  board.resizeCardId = null;
  board.resizeStart = null;
  board.resizeOrig = null;

  board.boardTitle = (book.bookTitle || "Untitled Book").trim();
  board.cards = canvas.cards || [];
  board.edges = canvas.edges || [];
  board.tagDefinitions = canvas.tagDefinitions || [];
  board.savedViews = canvas.savedViews || [];
  board.activeQuickView = canvas.activeQuickView || "all";
  board.panX = canvas.panX || 0;
  board.panY = canvas.panY || 0;
  board.zoom = canvas.zoom || 1;

  if (boardTitleInput) boardTitleInput.value = board.boardTitle;
}

// ── Canvas Tab Management ──
function renderCanvasTabs() {
  const bar = $("#canvas-tab-bar");
  if (!bar) return;
  bar.innerHTML = "";
  book.canvases.forEach((c) => {
    const tab = document.createElement("div");
    tab.className = "canvas-tab";
    if (c.id === book.activeCanvasId) tab.classList.add("active");
    tab.dataset.canvasId = c.id;
    tab.textContent = c.name || "Untitled";
    // close button
    const close = document.createElement("span");
    close.className = "tab-close";
    close.textContent = "×";
    close.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteCanvas(c.id);
    });
    tab.appendChild(close);
    tab.addEventListener("click", () => {
      switchCanvas(c.id);
    });
    tab.addEventListener("dblclick", (e) => {
      const canvasId = c.id;
      const canvas = getCanvasById(canvasId);
      if (!canvas) return;
      const newName = prompt("Rename canvas", canvas.name);
      if (newName && newName.trim()) {
        canvas.name = newName.trim();
        if (canvas.id === book.activeCanvasId) {
          board.boardTitle = (book.bookTitle || "Untitled Book").trim();
          if (boardTitleInput) boardTitleInput.value = board.boardTitle;
        }
        renderCanvasTabs();
        autoSave();
      }
    });
    tab.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      showCanvasTabContextMenu(e.pageX, e.pageY, c.id);
    });
    bar.appendChild(tab);
  });
  // + button
  const add = document.createElement("div");
  add.className = "canvas-tab add-tab";
  add.textContent = "+";
  add.addEventListener("click", () => {
    startNewCanvas();
  });
  bar.appendChild(add);
}

function switchCanvas(canvasId) {
  if (canvasId === book.activeCanvasId) return;
  saveActiveCanvasToBook();
  book.activeCanvasId = canvasId;
  const canvas = getCanvasById(canvasId);
  if (canvas) loadCanvasIntoBoard(canvas);
  pushUndoState();
  renderAll();
}

function deleteCanvas(canvasId) {
  if (book.canvases.length === 1) {
    alert("Cannot delete the last canvas.");
    return;
  }
  const c = getCanvasById(canvasId);
  if (!c) return;
  const hasContent = c.cards && c.cards.length > 0;
  if (hasContent && !confirm('Delete canvas "' + c.name + '" and all its cards?')) {
    return;
  }
  const idx = book.canvases.findIndex((cv) => cv.id === canvasId);
  if (idx === -1) return;
  const wasActive = book.activeCanvasId === canvasId;
  book.canvases.splice(idx, 1);
  if (wasActive) {
    const newActive = book.canvases[0];
    book.activeCanvasId = newActive.id;
    loadCanvasIntoBoard(newActive);
  }
  pushUndoState();
  renderAll();
  autoSave();
}

function duplicateCanvas(canvasId) {
  const src = getCanvasById(canvasId);
  if (!src) return;
  const copy = JSON.parse(JSON.stringify(src));
  copy.id = uid("canvas");
  copy.name = src.name + " (copy)";
  book.canvases.push(copy);
  pushUndoState();
  renderAll();
  autoSave();
}

const MAX_UNDO = 50;
const undoStack = [];
const redoStack = [];

function getUndoableState() {
  saveActiveCanvasToBook();
  return JSON.parse(JSON.stringify(book));
}

function pushUndoState() {
  undoStack.push(getUndoableState());
  if (undoStack.length > MAX_UNDO) undoStack.shift();
  redoStack.length = 0;
  refreshUndoRedoButtons();
}

function undo() {
  if (undoStack.length === 0) return;
  if (board.editingCardId) setViewMode(board.editingCardId);
  redoStack.push(getUndoableState());
  const state = undoStack.pop();
  applyUndoableState(state);
  refreshUndoRedoButtons();
}

function redo() {
  if (redoStack.length === 0) return;
  if (board.editingCardId) setViewMode(board.editingCardId);
  undoStack.push(getUndoableState());
  const state = redoStack.pop();
  applyUndoableState(state);
  refreshUndoRedoButtons();
}

function applyUndoableState(state) {
  book.bookTitle = state.bookTitle;
  book.activeCanvasId = state.activeCanvasId;
  book.canvases = state.canvases;

  const canvas = getCanvasById(book.activeCanvasId);
  if (canvas) {
    loadCanvasIntoBoard(canvas);
  } else {
    board.cards = [];
    board.edges = [];
    board.tagDefinitions = [];
    board.savedViews = [];
    board.activeQuickView = "all";
    board.panX = 0;
    board.panY = 0;
    board.zoom = 1;
  }

  if (boardTitleInput) boardTitleInput.value = board.boardTitle;
  refreshTagFilterOptions();
  renderAll();
  applyTransform();
  updateInspector();
  autoSave();
}

function refreshUndoRedoButtons() {
  document.querySelectorAll('[data-action="undo"]').forEach((btn) => {
    btn.disabled = undoStack.length === 0;
    btn.textContent =
      undoStack.length > 0 ? `Undo (${undoStack.length})` : "Undo";
  });
  document.querySelectorAll('[data-action="redo"]').forEach((btn) => {
    btn.disabled = redoStack.length === 0;
    btn.textContent =
      redoStack.length > 0 ? `Redo (${redoStack.length})` : "Redo";
  });
}

// ── DOM refs ──
const $ = (s) => document.querySelector(s);
const container = $("#canvas-container");
const content = $("#canvas-content");
let edgeGroup = null;
let ghostPath = null;
const zoomLabel = $("#zoom-level");
const boardTitleInput = $("#board-title-input");
const importExcelInput = $("#import-excel-input");
const dropOverlay = $("#drop-overlay");
const importTypeModal = $("#import-type-modal");
const itmBackdrop = $("#itm-backdrop");
const itmFileName = $("#itm-file-name");
const btnCloseItm = $("#btn-close-itm");
const btnCancelItm = $("#btn-cancel-itm");
const btnConfirmItm = $("#btn-confirm-itm");

// ── Helpers ──
function uid(prefix) {
  return (
    prefix +
    "_" +
    Date.now().toString(36) +
    "_" +
    Math.random().toString(36).slice(2, 6)
  );
}
function ts() {
  return new Date().toISOString();
}
function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function getViewportCenterCanvasPoint() {
  const rect = container.getBoundingClientRect();
  return screenToCanvas(rect.width / 2, rect.height / 2);
}

function addCardAtViewportCenter(type) {
  const center = getViewportCenterCanvasPoint();
  addCard({ type, x: center.x - 160, y: center.y - 110 });
}

function setZoomLevel(nextZoom, anchorX = null, anchorY = null) {
  const rect = container.getBoundingClientRect();
  const ax = anchorX ?? rect.width / 2;
  const ay = anchorY ?? rect.height / 2;
  const canvasPoint = screenToCanvas(ax, ay);
  board.zoom = clamp(nextZoom, 0.1, 5);
  board.panX = ax - canvasPoint.x * board.zoom;
  board.panY = ay - canvasPoint.y * board.zoom;
  applyTransform();
  renderEdges();
  autoSave();
}

function fitCardsToViewport() {
  if (board.cards.length === 0) {
    setZoomLevel(1);
    return;
  }

  const padding = 56;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  board.cards.forEach((card) => {
    minX = Math.min(minX, card.x);
    minY = Math.min(minY, card.y);
    maxX = Math.max(maxX, card.x + card.width);
    maxY = Math.max(maxY, card.y + card.height);
  });

  const rect = container.getBoundingClientRect();
  const boundsWidth = Math.max(1, maxX - minX);
  const boundsHeight = Math.max(1, maxY - minY);
  const availableWidth = Math.max(1, rect.width - padding * 2);
  const availableHeight = Math.max(1, rect.height - padding * 2);
  const zoom = clamp(
    Math.min(availableWidth / boundsWidth, availableHeight / boundsHeight),
    0.1,
    5,
  );

  board.zoom = zoom;
  board.panX = (rect.width - boundsWidth * zoom) / 2 - minX * zoom;
  board.panY = (rect.height - boundsHeight * zoom) / 2 - minY * zoom;
  applyTransform();
  renderEdges();
  autoSave();
}

function normalizeTagName(name) {
  return String(name || "")
    .trim()
    .toLowerCase();
}

function getTagDefById(tagId) {
  return board.tagDefinitions.find((t) => t.id === tagId) || null;
}

function getTagDefByName(name, parentId = null) {
  const n = normalizeTagName(name);
  return (
    board.tagDefinitions.find(
      (t) =>
        normalizeTagName(t.name) === n &&
        (t.parentId || null) === (parentId || null),
    ) || null
  );
}

function ensureTagDefinition(name, parentId = null) {
  const clean = String(name || "").trim();
  if (!clean) return null;
  const existing = getTagDefByName(clean, parentId);
  if (existing) return existing;
  pushUndoState();
  const color =
    "#" +
    Math.floor(Math.random() * 0xffffff)
      .toString(16)
      .padStart(6, "0");
  const def = {
    id: uid("tag"),
    name: clean,
    parentId: parentId || null,
    color,
    group: "",
    icon: "",
    properties: [],
  };
  board.tagDefinitions.push(def);
  return def;
}

function ensureTagPath(path) {
  const parts = String(path || "")
    .split("/")
    .map((p) => p.trim())
    .filter(Boolean);
  let parentId = null;
  let current = null;
  parts.forEach((part) => {
    current = ensureTagDefinition(part, parentId);
    parentId = current?.id || null;
  });
  return current;
}

function getTagPath(tagId) {
  const names = [];
  let current = getTagDefById(tagId);
  while (current) {
    names.unshift(current.name);
    current = current.parentId ? getTagDefById(current.parentId) : null;
  }
  return names.join(" › ");
}

function getDescendantTagIds(rootTagId) {
  if (!rootTagId) return [];
  const out = [];
  const stack = [rootTagId];
  while (stack.length > 0) {
    const id = stack.pop();
    out.push(id);
    board.tagDefinitions
      .filter((t) => t.parentId === id)
      .forEach((child) => stack.push(child.id));
  }
  return out;
}

function cardHasTagOrDescendant(card, rootTagId) {
  if (!rootTagId || rootTagId === "all") return true;
  const tagIds = new Set(getDescendantTagIds(rootTagId));
  return (card.tags || []).some((t) => tagIds.has(t));
}

function getPrimaryTag(card) {
  const first = (card.tags || [])[0];
  return first ? getTagDefById(first) : null;
}

function normalizeBoardData() {
  if (!Array.isArray(board.tagDefinitions)) board.tagDefinitions = [];
  board.cards.forEach((card) => {
    if (!["text", "image", "table"].includes(card.type)) {
      card.type = card.type === "image" ? "image" : "text";
    }
    if (!Array.isArray(card.tags)) card.tags = [];
    if (!card.tagProperties || typeof card.tagProperties !== "object")
      card.tagProperties = {};
    if (!card.tableData || !card.tableData.columns || !card.tableData.rows) {
      card.tableData = { columns: [], rows: [] };
    }
    // Migrate old string tags or path strings to flat tag IDs.
    card.tags = card.tags
      .map((tag) => {
        if (String(tag).startsWith("tag_") && getTagDefById(tag)) return tag;
        const flatName = String(tag).split("/").pop().trim();
        const created = ensureTagDefinition(flatName);
        return created?.id || null;
      })
      .filter(Boolean);
  });
}

function makeCard(overrides = {}) {
  const type = overrides.type || "text";
  return {
    id: uid("card"),
    type,
    title: "",
    body: "<p></p>",
    x: 200 + Math.random() * 200,
    y: 200 + Math.random() * 200,
    width: 320,
    height: 220,
    tags: [],
    tagProperties: {},
    sourceUrl: "",
    imageUrl: "",
    metadata: {},
    tableData: { columns: [], rows: [] },
    createdAt: ts(),
    updatedAt: ts(),
    ...overrides,
  };
}

function makeEdge(overrides = {}) {
  return {
    id: uid("edge"),
    from: "",
    to: "",
    fromPort: null,
    toPort: null,
    label: "",
    type: "",
    ...overrides,
  };
}

// ── Pan & Zoom ──
function applyTransform() {
  content.style.transform = `translate(${board.panX}px, ${board.panY}px) scale(${board.zoom})`;
  zoomLabel.textContent = Math.round(board.zoom * 100) + "%";
}

function screenToCanvas(sx, sy) {
  return {
    x: (sx - board.panX) / board.zoom,
    y: (sy - board.panY) / board.zoom,
  };
}

function isEdgeSvgClick(e) {
  return !!e.target.closest("#edge-svg");
}

container.addEventListener("contextmenu", (e) => {
  const blankClick =
    e.target === container ||
    e.target === $("#canvas-bg") ||
    e.target === content ||
    isEdgeSvgClick(e);
  if (blankClick) {
    e.preventDefault();
    deselectAll();
    if (board.multiSelectMode) exitMultiSelectMode();
    ctxMenu.style.display = "none";
    const rect = container.getBoundingClientRect();
    const canvasPos = screenToCanvas(
      e.clientX - rect.left,
      e.clientY - rect.top,
    );
    showCanvasContextMenu(e.clientX, e.clientY, canvasPos);
  }
});

container.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const rect = container.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const oldZoom = board.zoom;
    const factor = e.deltaY > 0 ? 0.92 : 1.08;
    board.zoom = clamp(board.zoom * factor, 0.1, 5);
    const ratio = board.zoom / oldZoom;
    board.panX = mx - (mx - board.panX) * ratio;
    board.panY = my - (my - board.panY) * ratio;
    applyTransform();
    renderEdges();
  },
  { passive: false },
);

container.addEventListener("mousedown", (e) => {
  const blankCanvasClick =
    e.target === container ||
    e.target === $("#canvas-bg") ||
    e.target === content ||
    isEdgeSvgClick(e);
if (e.button === 1 || (e.button === 0 && blankCanvasClick)) {
      deselectAll();
      if (board.multiSelectMode) exitMultiSelectMode();
    board.isPanning = true;
    board.panStart = { x: e.clientX, y: e.clientY };
    board.panStartOffset = { x: board.panX, y: board.panY };
    container.classList.add("panning");
    e.preventDefault();
  }
});

document.addEventListener("mousemove", (e) => {
  if (board.isPanning && board.panStart) {
    board.panX = board.panStartOffset.x + (e.clientX - board.panStart.x);
    board.panY = board.panStartOffset.y + (e.clientY - board.panStart.y);
    applyTransform();
    renderEdges();
    return;
  }
  if (board.dragCardIds) {
    const dx = (e.clientX - board.dragStart.x) / board.zoom;
    const dy = (e.clientY - board.dragStart.y) / board.zoom;
    board.dragCardIds.forEach((id) => {
      const c = board.cards.find((cc) => cc.id === id);
      const orig = board.dragOrigPositions[id];
      if (c && orig) {
        c.x = orig.x + dx;
        c.y = orig.y + dy;
        updateCardPosition(c);
      }
    });
    renderEdges();
    return;
  }
  if (board.resizeCardId) {
    const dx = (e.clientX - board.resizeStart.x) / board.zoom;
    const dy = (e.clientY - board.resizeStart.y) / board.zoom;
    const card = board.cards.find((c) => c.id === board.resizeCardId);
    if (card) {
      card.width = Math.max(200, board.resizeOrig.w + dx);
      card.height = Math.max(100, board.resizeOrig.h + dy);
      updateCardSize(card);
      renderEdges();
    }
    return;
  }
  if (board.connectingPending) {
    const dx = e.clientX - board.connectingPending.startX;
    const dy = e.clientY - board.connectingPending.startY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      board.connectingFrom = {
        cardId: board.connectingPending.cardId,
        port: board.connectingPending.port,
      };
      board.connectingPending = null;
    }
  }
  if (board.connectingFrom) {
    const rect = container.getBoundingClientRect();
    const p = screenToCanvas(e.clientX - rect.left, e.clientY - rect.top);
    const src = getPortPos(
      board.connectingFrom.cardId,
      board.connectingFrom.port,
    );
    if (ghostPath) {
      ghostPath.setAttribute(
        "d",
        `M ${src.x} ${src.y} C ${src.x + 60} ${src.y}, ${p.x - 60} ${p.y}, ${p.x} ${p.y}`,
      );
      ghostPath.setAttribute("display", "block");
    }
    // Highlight target port on card under cursor
    clearPortHighlights();
    const srcPort = content.querySelector(
      `.card-port.${board.connectingFrom.port}[data-card-id="${board.connectingFrom.cardId}"]`,
    );
    if (srcPort) srcPort.classList.add("active-source");
    const targetEl = document.elementFromPoint(e.clientX, e.clientY);
    if (targetEl) {
      const cardEl = targetEl.closest(".card");
      if (cardEl && cardEl.dataset.cardId !== board.connectingFrom.cardId) {
        const targetCardId = cardEl.dataset.cardId;
        const nearestPort = getNearestPort(targetCardId, p.x, p.y);
        const targetPort = cardEl.querySelector(`.card-port.${nearestPort}`);
        if (targetPort) targetPort.classList.add("active-target");
      }
    }
  }
});

document.addEventListener("mouseup", (e) => {
  if (board.isPanning) {
    board.isPanning = false;
    board.panStart = null;
    container.classList.remove("panning");
    autoSave();
    return;
  }
  if (board.dragCardIds) {
    board.dragCardIds = null;
    autoSave();
    return;
  }
  if (board.resizeCardId) {
    board.resizeCardId = null;
    autoSave();
    return;
  }
  if (board.connectingFrom || board.connectingPending) {
    if (board.connectingFrom) {
      const portEl = e.target.closest(".card-port");
      const cardEl = e.target.closest(".card");
      let toId = null;
      let toPort = null;
      if (cardEl) {
        toId = cardEl.dataset.cardId;
        if (portEl) {
          toPort = portEl.dataset.port;
        } else if (toId && toId !== board.connectingFrom.cardId) {
          const rect = container.getBoundingClientRect();
          const canvas = screenToCanvas(
            e.clientX - rect.left,
            e.clientY - rect.top,
          );
          toPort = getNearestPort(toId, canvas.x, canvas.y);
        }
      }
      if (toId && toId !== board.connectingFrom.cardId) {
        const label = prompt("Edge label (optional):", "") || "";
        const edge = makeEdge({
          from: board.connectingFrom.cardId,
          to: toId,
          fromPort: board.connectingFrom.port,
          toPort,
          label,
        });
        pushUndoState();
        board.edges.push(edge);
        renderEdges();
        autoSave();
      }
    }
    board.connectingFrom = null;
    board.connectingPending = null;
    if (ghostPath) ghostPath.setAttribute("display", "none");
    clearPortHighlights();
  }
});

// ── Card Ports ──
const PORTS = ["top", "bottom", "left", "right"];

function getPortPos(cardId, port) {
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) return { x: 0, y: 0 };
  const cx = card.x + card.width / 2;
  const cy = card.y + card.height / 2;
  switch (port) {
    case "top":
      return { x: cx, y: card.y };
    case "bottom":
      return { x: cx, y: card.y + card.height };
    case "left":
      return { x: card.x, y: cy };
    case "right":
      return { x: card.x + card.width, y: cy };
    default:
      return { x: cx, y: cy };
  }
}

function getNearestPort(cardId, cx, cy) {
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) return "top";
  const dl = Math.abs(cx - card.x);
  const dr = Math.abs(cx - (card.x + card.width));
  const dt = Math.abs(cy - card.y);
  const db = Math.abs(cy - (card.y + card.height));
  const min = Math.min(dl, dr, dt, db);
  if (min === dt) return "top";
  if (min === db) return "bottom";
  if (min === dl) return "left";
  return "right";
}

// ── Card DOM ──
function createCardElement(card) {
  const primaryTag = getPrimaryTag(card);
  const semanticLabel = primaryTag ? getTagPath(primaryTag.id) : "untagged";
  const el = document.createElement("div");
  el.className = "card";
  el.dataset.cardId = card.id;
  el.style.left = card.x + "px";
  el.style.top = card.y + "px";
  el.style.width = card.width + "px";
  el.style.height = card.height + "px";

  const viewMeta = renderViewMeta(card);

  const bodyViewContent =
    card.type === "table"
      ? renderTableView(card)
      : card.type === "image"
        ? renderImageView(card)
        : sanitizeHtml(card.body) + viewMeta;

  el.innerHTML = `
    <div class="card-checkbox" data-card-id="${card.id}"></div>
    <div class="card-header type-${card.type}">
      <span class="card-type-badge badge-${card.type}">${card.type}</span>
      <span class="card-semantic-badge" title="Derived from first tag">${escapeHtml(semanticLabel)}</span>
      <input class="card-title-input" value="${escapeHtml(card.title)}" placeholder="Untitled" readonly />
      <button class="card-toggle-btn" title="Toggle edit mode">&#9998;</button>
      <button class="card-maximize-btn" title="Maximize editor">&#x2922;</button>
    </div>
    <div class="card-body">
      <div class="card-body-view">${bodyViewContent}</div>
      <div class="card-body-editor" style="display:none;flex:1"></div>
    </div>
    <div class="card-format-bar"></div>
    <div class="card-meta-edit"></div>
    <div class="card-resize-handle"></div>
  `;
  el._card = card;
  applyCardSemantics(el, card);

  // Ports (visual connection anchors)
  PORTS.forEach((p) => {
    const port = document.createElement("div");
    port.className = "card-port " + p;
    port.dataset.cardId = card.id;
    port.dataset.port = p;
    port.addEventListener("mousedown", (e) => {
      e.stopPropagation();
      clearPortHighlights();
      port.classList.add("active-source");
      board.connectingFrom = { cardId: card.id, port: p };
    });
    el.appendChild(port);
  });

  // Multi-select checkbox
  const checkbox = el.querySelector(".card-checkbox");
  checkbox.addEventListener("click", (e) => {
    e.stopPropagation();
    selectCard(card.id, true, false);
  });
  checkbox.addEventListener("mousedown", (e) => e.stopPropagation());

  // Drag (entire card when not editing; header-only when editing)
  const header = el.querySelector(".card-header");
  el.addEventListener("mousedown", (e) => {
    if (board.editingCardId === card.id) {
      if (!e.target.closest(".card-header")) return;
      if (e.target.tagName === "INPUT" || e.target.tagName === "BUTTON") return;
    }
    if (
      e.target.closest(".card-port") ||
      e.target.closest(".card-resize-handle") ||
      e.target.closest(".card-checkbox") ||
      e.target.closest(".card-toggle-btn") ||
      e.target.closest(".card-maximize-btn")
    ) return;
    const add = board.multiSelectMode || e.ctrlKey || e.metaKey;
    if (e.ctrlKey || e.metaKey) {
      if (!board.multiSelectMode) {
        board.multiSelectMode = true;
        refreshMultiSelectUI();
      }
    }
    if (add) {
      selectCard(card.id, true, false);
      e.preventDefault();
      return;
    }
    if (e.shiftKey) {
      selectCard(card.id, false, true);
      e.preventDefault();
      return;
    }
    if (!board.selectedCardIds.has(card.id)) {
      selectCard(card.id, false, false);
    }
    pushUndoState();
    const ids = [...board.selectedCardIds];
    board.dragCardIds = ids;
    board.dragStart = { x: e.clientX, y: e.clientY };
    board.dragOrigPositions = {};
    ids.forEach((id) => {
      const c = board.cards.find((cc) => cc.id === id);
      if (c) board.dragOrigPositions[id] = { x: c.x, y: c.y };
    });
    e.preventDefault();
  });

  // Title
  const titleInput = el.querySelector(".card-title-input");
  titleInput.addEventListener("change", () => {
    pushUndoState();
    card.title = titleInput.value;
    card.updatedAt = ts();
    autoSave();
  });
  titleInput.addEventListener("mousedown", (e) => e.stopPropagation());

  // Toggle edit mode
  const toggleBtn = el.querySelector(".card-toggle-btn");
  toggleBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (board.editingCardId === card.id) {
      setViewMode(card.id);
    } else {
      setEditMode(card.id);
    }
  });

  const maximizeBtn = el.querySelector(".card-maximize-btn");
  maximizeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleMaximizedCard(card.id);
  });

  const viewDiv = el.querySelector(".card-body-view");
  viewDiv.addEventListener("click", (e) => {
    if (e.target.tagName === "A" || e.target.closest("a")) {
      e.preventDefault();
    }
  });
  viewDiv.addEventListener("dblclick", (e) => {
    e.stopPropagation();
    e.preventDefault();
    setEditMode(card.id);
  });

  // UX contract: double-clicking anywhere on a card enters edit mode.
  el.addEventListener("dblclick", (e) => {
    if (board.editingCardId === card.id) return;
    const target = e.target;
    if (
      target.closest(".card-port") ||
      target.closest(".card-resize-handle") ||
      target.closest(".card-toggle-btn") ||
      target.closest(".card-maximize-btn")
    ) {
      return;
    }
    e.preventDefault();
    setEditMode(card.id);
  });

  const resizeHandle = el.querySelector(".card-resize-handle");
  resizeHandle.addEventListener("mousedown", (e) => {
    e.stopPropagation();
    pushUndoState();
    board.resizeCardId = card.id;
    board.resizeStart = { x: e.clientX, y: e.clientY };
    board.resizeOrig = { w: card.width, h: card.height };
  });

  el.addEventListener("mousedown", (e) => {
    if (!board.dragCardIds) {
      selectCard(card.id, board.multiSelectMode, e.shiftKey);
    }
    if (e.button !== 0) return;
    const target = e.target;
    const isPort = target.classList.contains("card-port");
    const isHeader = target.closest(".card-header");
    const isResize = target.closest(".card-resize-handle");
    const isInteractive =
      target.tagName === "INPUT" ||
      target.tagName === "BUTTON" ||
      target.tagName === "SELECT" ||
      target.tagName === "TEXTAREA" ||
      target.closest(".card-body-editor") ||
      target.closest(".ProseMirror");
    const isFormatBar = target.closest(".card-format-bar");
    const isBodyView = target.closest(".card-body-view");
    const isBody = target.closest(".card-body");
    // Don't start connection mode when clicking on body view/body (for editing)
    if (
      !isPort &&
      !isHeader &&
      !isResize &&
      !isInteractive &&
      !isFormatBar &&
      !isBodyView &&
      !isBody
    ) {
      const rect = container.getBoundingClientRect();
      const canvas = screenToCanvas(
        e.clientX - rect.left,
        e.clientY - rect.top,
      );
      const nearestPort = getNearestPort(card.id, canvas.x, canvas.y);
      board.connectingPending = {
        cardId: card.id,
        port: nearestPort,
        startX: e.clientX,
        startY: e.clientY,
      };
    }
  });

  el.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    showContextMenu(e.clientX, e.clientY, card.id);
  });

  return el;
}

function renderViewMeta(card) {
  let html = "";
  if (card.imageUrl && card.type !== "image") {
    html += `<img class="card-image-preview" src="${escapeHtml(card.imageUrl)}" alt="" onerror="this.style.display='none'" />`;
  }
  if (card.sourceUrl) {
    html += `<a class="card-source-link" href="${escapeHtml(card.sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(card.sourceUrl)}</a>`;
  }
  if (card.tags && card.tags.length > 0) {
    html +=
      "<div>" +
      card.tags
        .map(
          (t) =>
            `<span class="card-tag">${escapeHtml(getTagPath(t) || t)}</span>`,
        )
        .join("") +
      "</div>";
  }
  if (html) {
    html = '<div class="card-meta-view">' + html + "</div>";
  }
  return html;
}

function renderTableView(card) {
  const td = card.tableData || { columns: [], rows: [] };
  const cols = td.columns || [];
  const rows = td.rows || [];
  if (cols.length === 0) {
    return '<div class="table-placeholder">No data. Click edit to import or add data.</div>';
  }
  let html =
    '<div class="table-view-wrapper"><table class="table-view"><thead><tr>';
  cols.forEach((c) => {
    html += `<th>${escapeHtml(c)}</th>`;
  });
  html += "</tr></thead><tbody>";
  rows.forEach((row) => {
    html += "<tr>";
    cols.forEach((_, ci) => {
      html += `<td>${escapeHtml(String(row[ci] ?? ""))}</td>`;
    });
    html += "</tr>";
  });
  html += "</tbody></table></div>";
  return html;
}

function renderImageView(card) {
  let html = '<div class="image-view-wrapper">';
  if (card.imageUrl) {
    html += `<img class="card-image-preview card-image-preview-main" src="${escapeHtml(card.imageUrl)}" alt="" onerror="this.style.display='none'" />`;
  } else {
    html +=
      '<div class="image-placeholder">No image yet. Enter a URL, paste from clipboard, or upload a file in edit mode.</div>';
  }
  html += "</div>";
  return html + renderViewMeta(card);
}

function applyCardSemantics(el, card) {
  if (!el || !card) return;
  const typeInfo = CARD_TYPES[card.type] || CARD_TYPES.text;
  const primaryTag = getPrimaryTag(card);
  const semanticColor = primaryTag?.color || typeInfo.color || "#6c63ff";
  el.style.setProperty("--semantic-color", semanticColor);
  const badge = el.querySelector(".card-semantic-badge");
  if (badge) badge.textContent = getTagPath(primaryTag?.id) || "untagged";
}

function updateCardPosition(card) {
  const el = content.querySelector(`[data-card-id="${card.id}"]`);
  if (el) {
    el.style.left = card.x + "px";
    el.style.top = card.y + "px";
  }
}

function updateCardSize(card) {
  const el = content.querySelector(`[data-card-id="${card.id}"]`);
  if (el) {
    el.style.width = card.width + "px";
    el.style.height = card.height + "px";
  }
}

// ── Select ──
function selectCard(cardId, add, shift) {
  board.selectedEdgeId = null;
  if (shift && board.lastSelectedCardId) {
    const all = board.cards;
    const idx1 = all.findIndex((c) => c.id === board.lastSelectedCardId);
    const idx2 = all.findIndex((c) => c.id === cardId);
    if (idx1 !== -1 && idx2 !== -1) {
      const [start, end] = idx1 < idx2 ? [idx1, idx2] : [idx2, idx1];
      for (let i = start; i <= end; i++) board.selectedCardIds.add(all[i].id);
      updateSelection();
      updateCardList();
      updateInspector();
      return;
    }
  }
  if (add) {
    if (board.selectedCardIds.has(cardId)) board.selectedCardIds.delete(cardId);
    else board.selectedCardIds.add(cardId);
  } else {
    board.selectedCardIds.clear();
    board.selectedCardIds.add(cardId);
  }
  board.lastSelectedCardId = cardId;
  updateSelection();
  updateCardList();
  updateInspector();
}

function selectEdge(edgeId) {
  board.selectedCardIds.clear();
  board.selectedEdgeId = edgeId;
  updateSelection();
  updateCardList();
  updateInspector();
}

function updateSelection() {
  content.querySelectorAll(".card").forEach((el) => {
    el.classList.toggle(
      "selected",
      board.selectedCardIds.has(el.dataset.cardId),
    );
  });
  content.querySelectorAll(".edge-line, .edge-hit").forEach((el) => {
    el.classList.toggle("selected", el.dataset.edgeId === board.selectedEdgeId);
  });
  refreshMultiSelectUI();
  updateCardList();
  updateInspector();
}

function deselectAll() {
  if (board.editingCardId) setViewMode(board.editingCardId);
  board.selectedCardIds.clear();
  board.selectedEdgeId = null;
  updateSelection();
  updateCardList();
  updateInspector();
}

function syncSidebarState() {
  const sidebar = $("#left-sidebar");
  const container = $("#canvas-container");
  const btn = $("#btn-collapse-sidebar");
  sidebar.classList.toggle("collapsed", !board.leftSidebarVisible);
  container.classList.toggle("sidebar-collapsed", !board.leftSidebarVisible);
  btn.classList.toggle("collapsed", !board.leftSidebarVisible);
  btn.title = board.leftSidebarVisible ? "Collapse sidebar" : "Expand sidebar";
}

function toggleLeftSidebar() {
  board.leftSidebarVisible = !board.leftSidebarVisible;
  const sidebar = $("#left-sidebar");
  const container = $("#canvas-container");
  const btn = $("#btn-collapse-sidebar");
  sidebar.classList.toggle("collapsed", !board.leftSidebarVisible);
  container.classList.toggle("sidebar-collapsed", !board.leftSidebarVisible);
  btn.classList.toggle("collapsed", !board.leftSidebarVisible);
  btn.title = board.leftSidebarVisible ? "Collapse sidebar" : "Expand sidebar";
}

function clearPortHighlights() {
  content
    .querySelectorAll(".card-port.active-source, .card-port.active-target")
    .forEach((el) => {
      el.classList.remove("active-source", "active-target");
    });
}

function isTypingTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  if (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  ) {
    return true;
  }
  return !!target.closest(
    ".card-body-editor, .lexical-editor, .table-editor-container, .table-editor, .card-meta-edit, #toolbar, #right-inspector, #left-sidebar",
  );
}

function getVisibleCardIdsInViewport() {
  const viewport = container.getBoundingClientRect();
  const visible = [];
  content.querySelectorAll(".card").forEach((el) => {
    if (el.style.display === "none") return;
    const rect = el.getBoundingClientRect();
    const intersects =
      rect.right > viewport.left &&
      rect.left < viewport.right &&
      rect.bottom > viewport.top &&
      rect.top < viewport.bottom;
    if (!intersects) return;
    visible.push({
      id: el.dataset.cardId,
      top: rect.top,
      left: rect.left,
    });
  });
  visible.sort((a, b) => (a.top === b.top ? a.left - b.left : a.top - b.top));
  return visible.map((item) => item.id);
}

function cycleCardSelectionByTab(reverse = false) {
  const visibleCardIds = getVisibleCardIdsInViewport();
  if (visibleCardIds.length === 0) return false;
  const selected = [...board.selectedCardIds];
  const currentId =
    selected.length === 1 ? selected[0] : board.lastSelectedCardId;
  const currentIndex = currentId ? visibleCardIds.indexOf(currentId) : -1;
  let nextIndex = 0;
  if (currentIndex !== -1) {
    const delta = reverse ? -1 : 1;
    nextIndex =
      (currentIndex + delta + visibleCardIds.length) % visibleCardIds.length;
  } else if (reverse) {
    nextIndex = visibleCardIds.length - 1;
  }
  selectCard(visibleCardIds[nextIndex], false, false);
  return true;
}

// ── Context Menu ──
const ctxMenu = $("#card-context-menu");
let ctxCardId = null;
let ctxCanvasId = null;

function showCanvasTabContextMenu(pageX, pageY, canvasId) {
  ctxCanvasId = canvasId;
  ctxMenu.innerHTML = "";

  const label = document.createElement("div");
  label.textContent = "Canvas";
  label.style.cssText =
    "padding:6px 12px;font-size:11px;color:#888;font-weight:600;text-transform:uppercase;letter-spacing:.05em;pointer-events:none";
  ctxMenu.appendChild(label);

  const rename = document.createElement("button");
  rename.dataset.action = "rename-canvas";
  rename.textContent = "Rename";
  ctxMenu.appendChild(rename);

  const dup = document.createElement("button");
  dup.dataset.action = "duplicate-canvas";
  dup.textContent = "Duplicate";
  ctxMenu.appendChild(dup);

  const del = document.createElement("button");
  del.dataset.action = "delete-canvas";
  del.textContent = "Delete";
  ctxMenu.appendChild(del);

  ctxMenu.style.left = pageX + "px";
  ctxMenu.style.top = pageY + "px";
  ctxMenu.style.display = "block";
}

function showCanvasContextMenu(screenX, screenY, canvasPos) {
  ctxMenu.innerHTML = "";

  const label = document.createElement("div");
  label.textContent = "Create Card";
  label.style.cssText =
    "padding:6px 12px;font-size:11px;color:#888;font-weight:600;text-transform:uppercase;letter-spacing:.05em;pointer-events:none";
  ctxMenu.appendChild(label);

  const types = [
    { type: "text", icon: "📝", label: "Text Card" },
    { type: "image", icon: "🖼️", label: "Image Card" },
    { type: "table", icon: "📊", label: "Table Card" },
  ];

  types.forEach(({ type, icon, label: typeName }) => {
    const btn = document.createElement("button");
    btn.textContent = icon + " " + typeName;
    btn.addEventListener("click", () => {
      ctxMenu.style.display = "none";
      addCard({ type, x: canvasPos.x, y: canvasPos.y });
    });
    ctxMenu.appendChild(btn);
  });

  ctxMenu.style.left = screenX + "px";
  ctxMenu.style.top = screenY + "px";
  ctxMenu.style.display = "block";
}

function showContextMenu(x, y, cardId) {
  ctxCardId = cardId;
  const isEditing = board.editingCardId === cardId;
  const hasMulti = board.selectedCardIds.size > 1;
  ctxMenu.innerHTML = "";

  if (isEditing) {
    const cutBtn = document.createElement("button");
    cutBtn.dataset.action = "cut";
    cutBtn.textContent = "Cut";
    ctxMenu.appendChild(cutBtn);

    const copyBtn = document.createElement("button");
    copyBtn.dataset.action = "copy";
    copyBtn.textContent = "Copy";
    ctxMenu.appendChild(copyBtn);

    const pasteBtn = document.createElement("button");
    pasteBtn.dataset.action = "paste";
    pasteBtn.textContent = "Paste";
    ctxMenu.appendChild(pasteBtn);
  } else {
    if (hasMulti) {
      const copyBtn = document.createElement("button");
      copyBtn.dataset.action = "copy-cards";
      copyBtn.textContent = "Copy Selected (" + board.selectedCardIds.size + ")";
      ctxMenu.appendChild(copyBtn);

      const cutBtn = document.createElement("button");
      cutBtn.dataset.action = "cut-cards";
      cutBtn.textContent = "Cut Selected (" + board.selectedCardIds.size + ")";
      ctxMenu.appendChild(cutBtn);

      const del = document.createElement("button");
      del.dataset.action = "delete-all";
      del.textContent =
        "Delete All Selected (" + board.selectedCardIds.size + ")";
      ctxMenu.appendChild(del);
    } else {
      const copyBtn = document.createElement("button");
      copyBtn.dataset.action = "copy-cards";
      copyBtn.textContent = "Copy Card";
      ctxMenu.appendChild(copyBtn);

      const cutBtn = document.createElement("button");
      cutBtn.dataset.action = "cut-cards";
      cutBtn.textContent = "Cut Card";
      ctxMenu.appendChild(cutBtn);

      const del = document.createElement("button");
      del.dataset.action = "delete";
      del.textContent = "Delete Card";
      ctxMenu.appendChild(del);
      const dup = document.createElement("button");
      dup.dataset.action = "duplicate";
      dup.textContent = "Duplicate";
      ctxMenu.appendChild(dup);
    }
  }

  const selAll = document.createElement("button");
  selAll.dataset.action = "select-all";
  selAll.textContent = "Select All Cards";
  ctxMenu.appendChild(selAll);

  const multiSel = document.createElement("button");
  multiSel.dataset.action = "multi-select";
  multiSel.textContent = "Multi-Select Mode";
  ctxMenu.appendChild(multiSel);

  ctxMenu.style.left = x + "px";
  ctxMenu.style.top = y + "px";
  ctxMenu.style.display = "block";
}

document.addEventListener("click", (e) => {
  if (!ctxMenu.contains(e.target)) ctxMenu.style.display = "none";
});

document.addEventListener(
  "keydown",
  (e) => {
    if (e.key === "Tab") {
      if (board.editingCardId || isTypingTarget(e.target)) return;
      if (cycleCardSelectionByTab(e.shiftKey)) {
        e.preventDefault();
        e.stopPropagation();
      }
      return;
    }

    if (e.key === "Enter") {
      if (board.editingCardId || isTypingTarget(e.target)) return;
      if (board.selectedCardIds.size === 1) {
        const cardId = [...board.selectedCardIds][0];
        if (cardId) {
          e.preventDefault();
          e.stopPropagation();
          setEditMode(cardId);
        }
      }
      return;
    }

    if (e.ctrlKey || e.metaKey) {
      if (e.key === "z") {
        if (!board.editingCardId && !isTypingTarget(e.target)) {
          e.preventDefault();
          e.stopPropagation();
          if (e.shiftKey) redo();
          else undo();
          return;
        }
      } else if (e.key === "y") {
        if (!board.editingCardId && !isTypingTarget(e.target)) {
          e.preventDefault();
          e.stopPropagation();
          redo();
          return;
        }
      } else if ((e.key === "c" || e.key === "C") && !board.editingCardId && !isTypingTarget(e.target)) {
        if (board.selectedCardIds.size > 0) {
          e.preventDefault();
          e.stopPropagation();
          copySelectedCards();
          return;
        }
      } else if ((e.key === "x" || e.key === "X") && !board.editingCardId && !isTypingTarget(e.target)) {
        if (board.selectedCardIds.size > 0) {
          e.preventDefault();
          e.stopPropagation();
          cutSelectedCards();
          return;
        }
      } else if ((e.key === "v" || e.key === "V") && !board.editingCardId && !isTypingTarget(e.target)) {
        if (board.clipboardCards) {
          e.preventDefault();
          e.stopPropagation();
          pasteCardsFromClipboard();
          return;
        }
      }
    }

    if (e.key === "Escape") {
      if (board.multiSelectMode) {
        e.preventDefault();
        e.stopPropagation();
        exitMultiSelectMode();
        return;
      }
      if (
        !board.editingCardId &&
        !board.selectedCardIds.size &&
        !board.selectedEdgeId
      ) {
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      deselectAll();
    }
  },
  true,
);

ctxMenu.addEventListener("click", (e) => {
  const action = e.target.dataset.action;
  if (action === "delete" && ctxCardId) {
    deleteCard(ctxCardId);
  } else if (action === "delete-all") {
    [...board.selectedCardIds].forEach((id) => deleteCard(id));
    deselectAll();
  } else if (action === "duplicate" && ctxCardId) {
    duplicateCard(ctxCardId);
  } else if (action === "select-all") {
    board.cards.forEach((c) => board.selectedCardIds.add(c.id));
    updateSelection();
  } else if (action === "multi-select") {
    if (ctxCardId) {
      if (!board.multiSelectMode) {
        board.multiSelectMode = true;
        refreshMultiSelectUI();
      }
      selectCard(ctxCardId, true, false);
    }
  } else if (action === "copy-cards") {
    if (board.selectedCardIds.size === 0 && ctxCardId) {
      selectCard(ctxCardId, false, false);
    }
    copySelectedCards();
  } else if (action === "cut-cards") {
    if (board.selectedCardIds.size === 0 && ctxCardId) {
      selectCard(ctxCardId, false, false);
    }
    cutSelectedCards();
  } else if (action === "cut") {
    const editor = board.editors.get(ctxCardId);
    if (editor) {
      let text = "";
      editor.getEditorState().read(() => {
        const s = $getSelection();
        if ($isRangeSelection(s)) text = s.getTextContent();
      });
      if (text) {
        navigator.clipboard
          .writeText(text)
          .then(() => {
            editor.update(() => {
              const s = $getSelection();
              if ($isRangeSelection(s)) s.insertText("");
            });
          })
          .catch(() => {});
      }
    }
  } else if (action === "copy") {
    const editor = board.editors.get(ctxCardId);
    if (editor) {
      let text = "";
      editor.getEditorState().read(() => {
        const s = $getSelection();
        if ($isRangeSelection(s)) text = s.getTextContent();
      });
      if (text) {
        navigator.clipboard.writeText(text).catch(() => {});
      }
    }
  } else if (action === "paste") {
    const editor = board.editors.get(ctxCardId);
    if (editor) {
      navigator.clipboard
        .readText()
        .then((text) => {
          if (!text) return;
          editor.update(() => {
            const s = $getSelection();
            if ($isRangeSelection(s)) s.insertText(text);
          });
        })
        .catch(() => {});
    }
  } else if (action === "rename-canvas" && ctxCanvasId) {
    const c = getCanvasById(ctxCanvasId);
    if (c) {
      const newName = prompt("Rename canvas", c.name);
      if (newName && newName.trim()) {
        c.name = newName.trim();
        if (c.id === book.activeCanvasId) {
          board.boardTitle = (book.bookTitle || "Untitled Book").trim();
          if (boardTitleInput) boardTitleInput.value = board.boardTitle;
        }
        renderCanvasTabs();
        autoSave();
      }
    }
  } else if (action === "duplicate-canvas" && ctxCanvasId) {
    duplicateCanvas(ctxCanvasId);
  } else if (action === "delete-canvas" && ctxCanvasId) {
    deleteCanvas(ctxCanvasId);
  }
  ctxMenu.style.display = "none";
});

// ── Card Operations ──
function addCard(overrides, openInEditMode = true) {
  pushUndoState();
  const card = makeCard(overrides);
  board.cards.push(card);
  const el = createCardElement(card);
  content.appendChild(el);
  if (openInEditMode) {
    setTimeout(() => {
      setEditMode(card.id);
    }, 50);
  }
  updateCardList();
  autoSave();
  return card;
}

function deleteCard(cardId) {
  pushUndoState();
  unmountEditor(cardId);
  board.cards = board.cards.filter((c) => c.id !== cardId);
  board.edges = board.edges.filter((e) => e.from !== cardId && e.to !== cardId);
  const el = content.querySelector(`[data-card-id="${cardId}"]`);
  if (el) el.remove();
  board.selectedCardIds.delete(cardId);
  renderEdges();
  updateCardList();
  updateInspector();
  autoSave();
}

function duplicateCard(cardId) {
  pushUndoState();
  const orig = board.cards.find((c) => c.id === cardId);
  if (!orig) return;
  const card = makeCard({
    ...orig,
    id: uid("card"),
    title: orig.title + " (copy)",
    x: orig.x + 30,
    y: orig.y + 30,
    createdAt: ts(),
    updatedAt: ts(),
  });
  board.cards.push(card);
  const el = createCardElement(card);
  content.appendChild(el);
  renderEdges();
  updateCardList();
  autoSave();
}

// ── Clipboard ──
const CLIPBOARD_MARKER = "__kg_card_clipboard__";

function getViewportCanvasCenter() {
  const rect = container.getBoundingClientRect();
  return screenToCanvas(rect.width / 2, rect.height / 2);
}

function hasExternalConnections(cardIds) {
  const idSet = new Set(cardIds);
  return board.edges.some(
    (e) => (idSet.has(e.from) && !idSet.has(e.to)) || (idSet.has(e.to) && !idSet.has(e.from)),
  );
}

function getInternalEdges(cardIds) {
  const idSet = new Set(cardIds);
  return board.edges.filter(
    (e) => idSet.has(e.from) && idSet.has(e.to),
  );
}

function copySelectedCards() {
  const ids = [...board.selectedCardIds];
  if (ids.length === 0) return;

  const external = hasExternalConnections(ids);
  if (external) {
    const proceed = confirm(
      "Some selected cards have connections to cards outside the selection.\n\nCopying will preserve only internal connections. External connections will be lost when pasting.\n\nContinue?",
    );
    if (!proceed) return;
  }

  const cardsData = ids
    .map((id) => board.cards.find((c) => c.id === id))
    .filter(Boolean)
    .map((c) => ({ ...c }));

  const edgesData = getInternalEdges(ids).map((e) => ({ ...e }));

  board.clipboardCards = { cards: cardsData, edges: edgesData };

  const payload = CLIPBOARD_MARKER + JSON.stringify({
    version: 1,
    type: "kg-cards",
    cards: cardsData,
    edges: edgesData,
  });

  navigator.clipboard.writeText(payload).catch(() => {});
  refreshMultiSelectUI();
}

function cutSelectedCards() {
  const ids = [...board.selectedCardIds];
  if (ids.length === 0) return;

  copySelectedCards();
  // If copy was cancelled (connection warning declined), clipboard won't be set
  if (!board.clipboardCards) return;

  pushUndoState();
  ids.forEach((id) => deleteCard(id));
  deselectAll();
  refreshMultiSelectUI();
}

function pasteCardsFromClipboard() {
  const data = board.clipboardCards;
  if (!data || !data.cards || data.cards.length === 0) {
    // Try reading from system clipboard
    navigator.clipboard
      .readText()
      .then((text) => {
        if (!text || !text.startsWith(CLIPBOARD_MARKER)) return;
        try {
          const parsed = JSON.parse(text.slice(CLIPBOARD_MARKER.length));
          if (parsed.type !== "kg-cards" || !Array.isArray(parsed.cards)) return;
          doPasteCards(parsed.cards, parsed.edges || []);
        } catch (_) {}
      })
      .catch(() => {});
    return;
  }
  doPasteCards(data.cards, data.edges);
}

function doPasteCards(cardsData, edgesData) {
  pushUndoState();

  const center = getViewportCanvasCenter();
  const idMap = new Map();
  let minX = Infinity, minY = Infinity;

  const newCards = cardsData.map((c) => {
    if (c.x < minX) minX = c.x;
    if (c.y < minY) minY = c.y;
    const newId = uid("card");
    idMap.set(c.id, newId);
    return { ...c, id: newId, createdAt: ts(), updatedAt: ts() };
  });

  const offsetX = center.x - minX;
  const offsetY = center.y - minY;

  newCards.forEach((c) => {
    c.x += offsetX;
    c.y += offsetY;
    board.cards.push(c);
    const el = createCardElement(c);
    content.appendChild(el);
  });

  const newEdges = edgesData
    .map((e) => {
      const from = idMap.get(e.from);
      const to = idMap.get(e.to);
      if (!from || !to) return null;
      return { ...e, id: uid("edge"), from, to };
    })
    .filter(Boolean);

  newEdges.forEach((e) => board.edges.push(e));
  renderEdges();
  updateCardList();
  updateInspector();
  autoSave();

  // Exit multi-select mode after paste
  if (board.multiSelectMode) {
    board.multiSelectMode = false;
  }
  deselectAll();
  refreshMultiSelectUI();
}

// ── View / Edit Mode ──
function setEditMode(cardId) {
  if (board.editingCardId) setViewMode(board.editingCardId);
  board.connectingFrom = null;
  board.connectingPending = null;
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) return;
  board.editingCardId = cardId;
  const el = content.querySelector(`[data-card-id="${cardId}"]`);
  if (!el) return;
  el.classList.add("editing");
  el.classList.toggle("maximized", board.maximizedCardId === cardId);
  el.querySelector(".card-body-view").style.display = "none";
  const editorEl = el.querySelector(".card-body-editor");
  editorEl.style.display = "block";
  editorEl.style.height = card.height - 80 + "px";
  const titleInput = el.querySelector(".card-title-input");
  if (titleInput) titleInput.removeAttribute("readonly");

  if (card.type === "image") {
    setupImageEditMode(card, editorEl, el);
    setupMetaEdit(el, card);
    return;
  }

  if (card.type === "table") {
    setupTableEditMode(card, editorEl, el);
    setupMetaEdit(el, card);
    return;
  }

  // Pre-process TipTap HTML tags to Lexical-compatible inline styles
  const processed = (card.body || "<p></p>")
    .replace(/<mark>/g, '<span style="background-color: #6c63ff44">')
    .replace(/<\/mark>/g, "</span>")
    .replace(/<u>/g, '<span style="text-decoration: underline">')
    .replace(/<\/u>/g, "</span>");

  const editor = createEditor({
    nodes: [HeadingNode, QuoteNode, ListNode, ListItemNode, LinkNode, TableNode, TableCellNode, TableRowNode],
    onError: (err) => console.error("Lexical error:", err),
  });

  editorEl.classList.add("lexical-editor");
  editorEl.setAttribute("contenteditable", "true");
  editorEl.setAttribute("spellcheck", "true");
  editor.setRootElement(editorEl);
  registerRichText(editor);

  editor.update(() => {
    const parser = new DOMParser();
    const dom = parser.parseFromString(processed, "text/html");
    const nodes = $generateNodesFromDOM(editor, dom);
    $getRoot()
      .clear()
      .append(...nodes);
  });

  editor.registerUpdateListener(({ editorState }) => {
    editorState.read(() => {
      card.body = $generateHtmlFromNodes(editor, null);
    });
  });

  editor.focus();
  board.editors.set(cardId, editor);
  setupFormatBar(el, card, editor);
  setupMetaEdit(el, card);
}

function setupTableEditMode(card, editorEl, el) {
  editorEl.innerHTML = "";
  const container = document.createElement("div");
  container.className = "table-editor-container";

  // Import / Export buttons
  const btnRow = document.createElement("div");
  btnRow.className = "table-editor-actions";

  const importBtn = document.createElement("button");
  importBtn.className = "tb-btn";
  importBtn.textContent = "Import Excel/CSV";
  importBtn.addEventListener("click", () => {
    importExcelInput.click();
  });
  btnRow.appendChild(importBtn);

  const exportBtn = document.createElement("button");
  exportBtn.className = "tb-btn";
  exportBtn.textContent = "Export XLSX";
  exportBtn.addEventListener("click", async () => {
    const url = `/api/export/table/${card.id}`;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const dlUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = dlUrl;
      a.download = (card.title || "table") + ".xlsx";
      a.click();
      URL.revokeObjectURL(dlUrl);
    } catch (err) {
      console.error("Export error:", err);
      // Fallback: client-side export
      exportTableXLSX(card);
    }
  });
  btnRow.appendChild(exportBtn);

  const addRowBtn = document.createElement("button");
  addRowBtn.className = "tb-btn";
  addRowBtn.textContent = "+ Row";
  addRowBtn.addEventListener("click", () => {
    pushUndoState();
    const td = card.tableData;
    const newRow = td.columns.map(() => "");
    td.rows.push(newRow);
    card.updatedAt = ts();
    setupTableEditMode(card, editorEl, el);
    autoSave();
  });
  btnRow.appendChild(addRowBtn);

  const addColBtn = document.createElement("button");
  addColBtn.className = "tb-btn";
  addColBtn.textContent = "+ Column";
  addColBtn.addEventListener("click", () => {
    pushUndoState();
    const td = card.tableData;
    const colName = prompt("Column name:", "Column " + (td.columns.length + 1));
    if (!colName) return;
    td.columns.push(colName);
    td.rows.forEach((r) => r.push(""));
    card.updatedAt = ts();
    setupTableEditMode(card, editorEl, el);
    autoSave();
  });
  btnRow.appendChild(addColBtn);

  const clearBtn = document.createElement("button");
  clearBtn.className = "tb-btn";
  clearBtn.textContent = "Clear";
  clearBtn.addEventListener("click", () => {
    pushUndoState();
    if (confirm("Clear all table data?")) {
      card.tableData = { columns: [], rows: [] };
      card.updatedAt = ts();
      setupTableEditMode(card, editorEl, el);
      autoSave();
    }
  });
  btnRow.appendChild(clearBtn);

  container.appendChild(btnRow);

  // Editable table
  const td = card.tableData || { columns: [], rows: [] };
  const cols = td.columns || [];
  const rows = td.rows || [];

  if (cols.length === 0 && rows.length === 0) {
    const emptyMsg = document.createElement("div");
    emptyMsg.className = "table-placeholder";
    emptyMsg.textContent = "Add columns and rows, or import an Excel/CSV file.";
    container.appendChild(emptyMsg);
  } else {
    const tableWrapper = document.createElement("div");
    tableWrapper.className = "table-editor-wrapper";
    const table = document.createElement("table");
    table.className = "table-editor";

    // Header row
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    cols.forEach((colName, ci) => {
      const th = document.createElement("th");
      const input = document.createElement("input");
      input.value = colName;
      input.className = "table-header-input";
      input.addEventListener("change", () => {
        pushUndoState();
        td.columns[ci] = input.value;
        card.updatedAt = ts();
        autoSave();
      });
      th.appendChild(input);
      const delCol = document.createElement("button");
      delCol.className = "table-col-del";
      delCol.textContent = "✕";
      delCol.title = "Delete column";
      delCol.addEventListener("click", () => {
        pushUndoState();
        td.columns.splice(ci, 1);
        td.rows.forEach((r) => r.splice(ci, 1));
        card.updatedAt = ts();
        setupTableEditMode(card, editorEl, el);
        autoSave();
      });
      th.appendChild(delCol);
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Body rows
    const tbody = document.createElement("tbody");
    rows.forEach((row, ri) => {
      const tr = document.createElement("tr");
      cols.forEach((_, ci) => {
        const td_cell = document.createElement("td");
        const input = document.createElement("input");
        input.value = String(row[ci] ?? "");
        input.className = "table-cell-input";
        input.addEventListener("change", () => {
          pushUndoState();
          td.rows[ri][ci] = input.value;
          card.updatedAt = ts();
          autoSave();
        });
        td_cell.appendChild(input);
        tr.appendChild(td_cell);
      });
      const delRow = document.createElement("td");
      delRow.className = "table-row-del-cell";
      const delBtn = document.createElement("button");
      delBtn.className = "table-row-del";
      delBtn.textContent = "✕";
      delBtn.title = "Delete row";
      delBtn.addEventListener("click", () => {
        pushUndoState();
        td.rows.splice(ri, 1);
        card.updatedAt = ts();
        setupTableEditMode(card, editorEl, el);
        autoSave();
      });
      delRow.appendChild(delBtn);
      tr.appendChild(delRow);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    tableWrapper.appendChild(table);
    container.appendChild(tableWrapper);

    const rowCount = document.createElement("div");
    rowCount.className = "table-row-count";
    rowCount.textContent = `${rows.length} row(s)`;
    container.appendChild(rowCount);
  }

  editorEl.appendChild(container);

  // Metadata edit fields (only non-table ones)
  setupMetaEdit(el, card);
}

function setupFormatBar(el, card, editor) {
  const fmtBar = el.querySelector(".card-format-bar");
  fmtBar.innerHTML = "";

  const btns = {};

  const defs = [
    { key: "bold", label: "B", title: "Bold", cmd: "bold" },
    { key: "italic", label: "<em>I</em>", title: "Italic", cmd: "italic" },
    { key: "underline", label: "<u>U</u>", title: "Underline" },
    { key: "highlight", label: "H", title: "Highlight" },
    { key: "link", label: "Link", title: "Link" },
    { key: "list", label: "\u2022 List", title: "Bullet List" },
  ];

  defs.forEach((d) => {
    const btn = document.createElement("button");
    btn.className = "fmt-btn";
    btn.innerHTML = d.label;
    btn.title = d.title;
    btn.dataset.key = d.key;

    btn.addEventListener("click", () => {
      editor.focus();

      if (d.cmd) {
        editor.dispatchCommand(FORMAT_TEXT_COMMAND, d.cmd);
        return;
      }

      if (d.key === "underline") {
        editor.dispatchCommand(FORMAT_TEXT_COMMAND, "underline");
        return;
      }

      if (d.key === "highlight") {
        editor.update(() => {
          const s = $getSelection();
          if ($isRangeSelection(s)) {
            const cur = $getSelectionStyleValueForProperty(
              s,
              "background-color",
              "",
            );
            $patchStyleText(s, { "background-color": cur ? "" : "#6c63ff44" });
          }
        });
        return;
      }

      if (d.key === "link") {
        const currentUrl = editor.getEditorState().read(() => {
          const s = $getSelection();
          if (!$isRangeSelection(s)) return "";
          let n = s.anchor.getNode();
          while (n) {
            if (n.getType() === "link") return n.getURL();
            n = n.getParent();
          }
          return "";
        });
        const selectedText = editor.getEditorState().read(() => {
          const s = $getSelection();
          return $isRangeSelection(s) ? s.getTextContent() : "";
        });
        let rawUrl = null;
        try {
          rawUrl = prompt(
            "Enter URL:",
            currentUrl || card.sourceUrl || "https://",
          );
        } catch (err) {
          rawUrl = currentUrl || card.sourceUrl || "https://";
        }
        if (!rawUrl) return;
        const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : "https://" + rawUrl;
        editor.update(() => {
          const s = $getSelection();
          const text = (selectedText || url).trim();
          const linkNode = $createLinkNode(url);
          linkNode.append($createTextNode(text));

          if ($isRangeSelection(s)) {
            if (s.isCollapsed()) {
              const p = $createParagraphNode();
              p.append(linkNode);
              $getRoot().append(p);
            } else {
              s.insertNodes([linkNode]);
            }
            return;
          }

          const p = $createParagraphNode();
          p.append(linkNode);
          $getRoot().append(p);
        });
        return;
      }

      if (d.key === "list") {
        let isList = false;
        editor.getEditorState().read(() => {
          const s = $getSelection();
          if (!$isRangeSelection(s)) return;
          let n = s.anchor.getNode();
          while (n) {
            if (n.getType() === "list") {
              isList = true;
              break;
            }
            n = n.getParent();
          }
        });
        editor.dispatchCommand(
          isList ? REMOVE_LIST_COMMAND : INSERT_UNORDERED_LIST_COMMAND,
          undefined,
        );
      }
    });

    fmtBar.appendChild(btn);
    btns[d.key] = btn;
  });

  editor.registerUpdateListener(({ editorState }) => {
    editorState.read(() => {
      const s = $getSelection();
      const r = $isRangeSelection(s);

      if (btns.bold)
        btns.bold.classList.toggle("is-active", r && s.hasFormat("bold"));
      if (btns.italic)
        btns.italic.classList.toggle("is-active", r && s.hasFormat("italic"));

      if (r) {
        const isUl =
          $getSelectionStyleValueForProperty(s, "text-decoration", "") ===
          "underline";
        btns.underline.classList.toggle("is-active", isUl);

        const isHl = !!$getSelectionStyleValueForProperty(
          s,
          "background-color",
          "",
        );
        btns.highlight.classList.toggle("is-active", isHl);

        let isLink = false;
        let n = s.anchor.getNode();
        while (n) {
          if (n.getType() === "link") {
            isLink = true;
            break;
          }
          n = n.getParent();
        }
        btns.link.classList.toggle("is-active", isLink);

        let isList = false;
        n = s.anchor.getNode();
        while (n) {
          if (n.getType() === "list") {
            isList = true;
            break;
          }
          n = n.getParent();
        }
        btns.list.classList.toggle("is-active", isList);
      } else {
        btns.underline?.classList.remove("is-active");
        btns.highlight?.classList.remove("is-active");
        btns.link?.classList.remove("is-active");
        btns.list?.classList.remove("is-active");
      }
    });
  });
}

function setupImageEditMode(card, editorEl) {
  editorEl.classList.remove("lexical-editor");
  editorEl.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "image-editor-container";

  const preview = document.createElement("div");
  preview.className = "image-editor-preview";

  const img = document.createElement("img");
  img.className = "card-image-preview card-image-preview-main";
  if (card.imageUrl) img.src = card.imageUrl;
  img.alt = "";
  img.style.display = card.imageUrl ? "block" : "none";
  preview.appendChild(img);

  const placeholder = document.createElement("div");
  placeholder.className = "image-placeholder";
  placeholder.textContent =
    "No image selected. Use clipboard, URL, or file upload.";
  placeholder.style.display = card.imageUrl ? "none" : "block";
  preview.appendChild(placeholder);

  const actions = document.createElement("div");
  actions.className = "image-editor-actions";

  const clipBtn = document.createElement("button");
  clipBtn.className = "tb-btn";
  clipBtn.textContent = "Get Image from Clipboard";
  clipBtn.style.display = card.imageUrl ? "none" : "inline-flex";
  clipBtn.addEventListener("click", async () => {
    try {
      if (!navigator.clipboard?.read) {
        alert("Clipboard image read is not supported in this browser.");
        return;
      }
      const items = await navigator.clipboard.read();
      let imageBlob = null;
      for (const item of items) {
        const imageType = item.types.find((t) => t.startsWith("image/"));
        if (imageType) {
          imageBlob = await item.getType(imageType);
          break;
        }
      }
      if (!imageBlob) {
        alert("No image found in clipboard.");
        return;
      }
      const reader = new FileReader();
      reader.onload = (ev) => {
        const dataUrl = ev.target.result;
        pushUndoState();
        card.imageUrl = dataUrl;
        card.updatedAt = ts();
        img.src = dataUrl;
        img.style.display = "block";
        placeholder.style.display = "none";
        editBtn.style.display = "block";
        updateCardView(card.id);
        autoSave();
      };
      reader.readAsDataURL(imageBlob);
    } catch (err) {
      alert("Unable to read clipboard image. Copy an image, then try again.");
      console.error(err);
    }
  });
  actions.appendChild(clipBtn);

  const urlRow = document.createElement("div");
  urlRow.className = "image-url-row";
  urlRow.style.display = card.imageUrl ? "none" : "flex";
  const urlInput = document.createElement("input");
  urlInput.type = "text";
  urlInput.placeholder = "Paste image URL";
  urlInput.value = card.imageUrl || "";
  const applyUrlBtn = document.createElement("button");
  applyUrlBtn.className = "tb-btn";
  applyUrlBtn.textContent = "Apply URL";
  applyUrlBtn.addEventListener("click", async () => {
    const nextUrl = urlInput.value.trim();
    if (!nextUrl) return;
    pushUndoState();
    applyUrlBtn.disabled = true;
    applyUrlBtn.textContent = "Downloading...";
    try {
      let dataUrl;
      if (nextUrl.startsWith("data:")) {
        dataUrl = nextUrl;
      } else {
        dataUrl = await downloadImageAsDataUrl(nextUrl);
      }
      card.imageUrl = dataUrl;
      card.updatedAt = ts();
      img.src = dataUrl;
      img.style.display = "block";
      placeholder.style.display = "none";
      editBtn.style.display = "block";
      updateCardView(card.id);
      autoSave();
    } catch (err) {
      alert("Failed to download image from URL. Check the URL and try again.");
      console.error(err);
    } finally {
      applyUrlBtn.disabled = false;
      applyUrlBtn.textContent = "Apply URL";
    }
  });
  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyUrlBtn.click();
  });
  urlRow.appendChild(urlInput);
  urlRow.appendChild(applyUrlBtn);
  actions.appendChild(urlRow);

  const fileBtn = document.createElement("button");
  fileBtn.className = "tb-btn";
  fileBtn.textContent = "Upload Image File";
  fileBtn.style.display = card.imageUrl ? "none" : "inline-flex";
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/*";
  fileInput.style.display = "none";
  fileBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target.result;
      pushUndoState();
      card.imageUrl = dataUrl;
      card.updatedAt = ts();
      img.src = dataUrl;
      img.style.display = "block";
      placeholder.style.display = "none";
      editBtn.style.display = "block";
      updateCardView(card.id);
      autoSave();
    };
    reader.readAsDataURL(file);
  });
  actions.appendChild(fileBtn);
  actions.appendChild(fileInput);

  const editBtn = document.createElement("button");
  editBtn.className = "tb-btn image-edit-btn";
  editBtn.textContent = "✏ Edit Image";
  editBtn.style.display = card.imageUrl ? "block" : "none";
  editBtn.addEventListener("click", () => {
    if (card.imageUrl) {
      openImageEditor(card.imageUrl, (newDataUrl) => {
        pushUndoState();
        card.imageUrl = newDataUrl;
        card.updatedAt = ts();
        img.src = newDataUrl;
        updateCardView(card.id);
        autoSave();
      });
    }
  });
  actions.appendChild(editBtn);

  wrap.appendChild(preview);
  wrap.appendChild(actions);
  editorEl.appendChild(wrap);
}

function setupMetaEdit(el, card) {
  const metaEdit = el.querySelector(".card-meta-edit");
  metaEdit.innerHTML = "";
  const metaFields = [
    {
      key: "tags",
      label: "Tags",
      type: "text",
      value: (card.tags || [])
        .map((t) => getTagDefById(t)?.name || t)
        .join(", "),
    },
    {
      key: "sourceUrl",
      label: "Source URL",
      type: "text",
      value: card.sourceUrl || "",
    },
  ];
  metaFields.forEach((f) => {
    if (f.type === "select") {
      const sel = document.createElement("select");
      f.options.forEach((o) => {
        const opt = document.createElement("option");
        opt.value = o;
        opt.textContent = o;
        if (o === f.value) opt.selected = true;
        sel.appendChild(opt);
      });
      sel.addEventListener("change", () => {
        card[f.key] = sel.value;
        card.updatedAt = ts();
        updateCardView(card.id);
        autoSave();
      });
      const lbl = document.createElement("label");
      lbl.textContent = f.label + ": ";
      lbl.style.cssText =
        "font-size:11px;color:#888;display:flex;align-items:center;gap:4px";
      lbl.appendChild(sel);
      metaEdit.appendChild(lbl);
    } else {
      const inp = document.createElement("input");
      inp.placeholder = f.label;
      inp.value = f.value;
      inp.addEventListener("change", () => {
        pushUndoState();
        if (f.key === "tags") {
          const tagIds = inp.value
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
            .map((name) => ensureTagDefinition(name)?.id)
            .filter(Boolean);
          card.tags = tagIds;
          refreshTagFilterOptions();
        } else card[f.key] = inp.value;
        card.updatedAt = ts();
        updateCardView(card.id);
        autoSave();
      });
      metaEdit.appendChild(inp);
    }
  });
}

function exportTableXLSX(card) {
  const td = card.tableData || { columns: [], rows: [] };
  const ws = XLSX.utils.aoa_to_sheet([td.columns, ...td.rows]);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, card.title || "Table");
  const wbout = XLSX.write(wb, { bookType: "xlsx", type: "array" });
  const blob = new Blob([wbout], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = (card.title || "table") + ".xlsx";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 100);
}

function parseExcelToTableData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target.result);
        const wb = XLSX.read(data, { type: "array" });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const aoa = XLSX.utils.sheet_to_json(ws, { header: 1 });
        if (aoa.length === 0) {
          reject(new Error("The file contains no data."));
          return;
        }
        const columns = aoa[0].map((c) => String(c ?? ""));
        const rows = aoa
          .slice(1)
          .map((row) => columns.map((_, ci) => String(row[ci] ?? "")));
        resolve({ columns, rows });
      } catch (err) {
        reject(err);
      }
    };
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsArrayBuffer(file);
  });
}

function importTableXLSX(file, card) {
  pushUndoState();
  parseExcelToTableData(file)
    .then(({ columns, rows }) => {
      card.tableData = { columns, rows };
      card.updatedAt = ts();
      const el = content.querySelector(`[data-card-id="${card.id}"]`);
      if (el && board.editingCardId === card.id) {
        const editorEl = el.querySelector(".card-body-editor");
        setupTableEditMode(card, editorEl, el);
      } else {
        updateCardView(card.id);
      }
      autoSave();
    })
    .catch((err) => {
      alert("Failed to import file: " + err.message);
    });
}

function toggleMaximizedCard(cardId) {
  if (board.editingCardId !== cardId) return;
  board.maximizedCardId = board.maximizedCardId === cardId ? null : cardId;
  const el = content.querySelector(`[data-card-id="${cardId}"]`);
  if (!el) return;
  const isMaximized = board.maximizedCardId === cardId;
  el.classList.toggle("maximized", isMaximized);
  const btn = el.querySelector(".card-maximize-btn");
  if (btn) {
    btn.innerHTML = isMaximized ? "&#x21A9;" : "&#x2922;";
    btn.title = isMaximized ? "Restore editor" : "Maximize editor";
  }
}

function setViewMode(cardId) {
  if (board.editingCardId !== cardId) return;
  const editor = board.editors.get(cardId);
  const card = board.cards.find((c) => c.id === cardId);

  if (editor && card && card.type !== "table") {
    card.body = editor.getEditorState().read(() => {
      return $generateHtmlFromNodes(editor, null);
    });
  }

  if (editor) {
    editor.setRootElement(null);
    board.editors.delete(cardId);
  }

  board.editingCardId = null;
  if (board.maximizedCardId === cardId) board.maximizedCardId = null;
  const el = content.querySelector(`[data-card-id="${cardId}"]`);
  if (!el) return;
  el.classList.remove("editing");
  el.classList.remove("maximized");
  el.querySelector(".card-body-view").style.display = "block";
  el.querySelector(".card-body-editor").style.display = "none";
  const titleInput = el.querySelector(".card-title-input");
  if (titleInput) titleInput.setAttribute("readonly", "");
  if (card && card.type === "table") {
    el.querySelector(".card-body-view").innerHTML = renderTableView(card);
  } else if (card && card.type === "image") {
    el.querySelector(".card-body-view").innerHTML = renderImageView(card);
  } else if (card) {
    el.querySelector(".card-body-view").innerHTML =
      sanitizeHtml(card.body || "<p></p>") + renderViewMeta(card);
  }
  el.querySelector(".card-format-bar").innerHTML = "";
  el.querySelector(".card-meta-edit").innerHTML = "";
  updateCardList();
  updateInspector();
  autoSave();
}

function unmountEditor(cardId) {
  const editor = board.editors.get(cardId);
  if (editor) {
    editor.setRootElement(null);
    board.editors.delete(cardId);
  }
  if (board.editingCardId === cardId) board.editingCardId = null;
}

// ── Edges ──
function renderEdges() {
  edgeGroup = document.getElementById("edge-group");
  if (!edgeGroup) return;
  edgeGroup.innerHTML = "";
  board.edges.forEach((edge) => {
    const fromCard = board.cards.find((c) => c.id === edge.from);
    const toCard = board.cards.find((c) => c.id === edge.to);
    if (!fromCard || !toCard) return;

    const fromPos = edge.fromPort
      ? getPortPos(edge.from, edge.fromPort)
      : {
          x: fromCard.x + fromCard.width / 2,
          y: fromCard.y + fromCard.height / 2,
        };
    const toPos = edge.toPort
      ? getPortPos(edge.to, edge.toPort)
      : { x: toCard.x + toCard.width / 2, y: toCard.y + toCard.height / 2 };

    const fx = fromPos.x,
      fy = fromPos.y;
    const tx = toPos.x,
      ty = toPos.y;

    const dx = tx - fx,
      dy = ty - fy;
    const cx1 = fx + dx * 0.4,
      cy1 = fy + dy * 0.1;
    const cx2 = tx - dx * 0.4,
      cy2 = ty - dy * 0.1;

    const d = `M ${fx} ${fy} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${tx} ${ty}`;

    const hitPath = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "path",
    );
    hitPath.setAttribute("d", d);
    hitPath.setAttribute("class", "edge-hit");
    hitPath.dataset.edgeId = edge.id;
    if (board.selectedEdgeId === edge.id) hitPath.classList.add("selected");
    hitPath.addEventListener("click", (e) => {
      e.stopPropagation();
      selectEdge(edge.id);
    });
    edgeGroup.appendChild(hitPath);

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("class", "edge-line");
    path.dataset.edgeId = edge.id;
    path.setAttribute("marker-end", "url(#arrowhead)");
    if (board.selectedEdgeId === edge.id) path.classList.add("selected");
    edgeGroup.appendChild(path);

    if (edge.label) {
      const mx = (fx + tx) / 2,
        my = (fy + ty) / 2;
      const text = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "text",
      );
      text.setAttribute("x", mx);
      text.setAttribute("y", my - 8);
      text.setAttribute("class", "edge-label");
      text.dataset.edgeId = edge.id;
      text.setAttribute("text-anchor", "middle");
      text.textContent = edge.label;
      text.addEventListener("click", (e) => {
        e.stopPropagation();
        selectEdge(edge.id);
      });
      text.addEventListener("dblclick", () => {
        const label = prompt("Edge label:", edge.label || "");
        if (label !== null) {
          pushUndoState();
          edge.label = label;
          renderEdges();
          autoSave();
        }
      });
      edgeGroup.appendChild(text);
    }
  });
}

// ── Render All ──
function renderAll() {
  renderCanvasTabs();
  content.innerHTML = "";

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("id", "edge-svg");
  svg.setAttribute(
    "style",
    "position:absolute;inset:0;width:100%;height:100%;pointer-events:auto;z-index:1;overflow:visible",
  );
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `<marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
    <path d="M 0 0 L 10 5 L 0 10 Z" fill="#8d90c8" />
  </marker>`;
  svg.appendChild(defs);
  const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
  group.setAttribute("id", "edge-group");
  svg.appendChild(group);
  content.appendChild(svg);
  edgeGroup = group;

  const ghostSvg = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "svg",
  );
  ghostSvg.setAttribute("id", "ghost-svg");
  ghostSvg.setAttribute(
    "style",
    "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:6;overflow:visible",
  );
  const ghost = document.createElementNS("http://www.w3.org/2000/svg", "path");
  ghost.setAttribute("id", "ghost-path");
  ghost.setAttribute("stroke", "#6c63ff");
  ghost.setAttribute("stroke-width", "2");
  ghost.setAttribute("fill", "none");
  ghost.setAttribute("stroke-dasharray", "6,4");
  ghost.setAttribute("display", "none");
  ghostSvg.appendChild(ghost);
  content.appendChild(ghostSvg);
  ghostPath = ghost;

  board.cards.forEach((card) => {
    const el = createCardElement(card);
    content.appendChild(el);
  });
  renderEdges();
  updateCardList();
  refreshMultiSelectUI();
  applyTransform();
}

// ── Persistence ──

function getState() {
  saveActiveCanvasToBook();
  return {
    id: book.id,
    version: 2,
    bookTitle: book.bookTitle,
    activeCanvasId: book.activeCanvasId,
    canvases: JSON.parse(JSON.stringify(book.canvases)),
  };
}

function loadState(data) {
  board.editors.forEach((ed) => ed.setRootElement(null));
  board.editors.clear();
  board.editingCardId = null;
  board.maximizedCardId = null;
  board.selectedCardIds.clear();
  board.selectedEdgeId = null;
  board.connectingFrom = null;
  board.connectingPending = null;
  board.isPanning = false;
  board.panStart = null;
  board.panStartOffset = null;
  board.dragCardIds = null;
  board.dragStart = null;
  board.dragOrigPositions = null;
  board.resizeCardId = null;
  board.resizeStart = null;
  board.resizeOrig = null;

  if (data.version === 2 && Array.isArray(data.canvases) && data.canvases.length > 0) {
    book.id = data.id || null;
    book.bookTitle = data.bookTitle || "Research Workspace";
    book.activeCanvasId = data.activeCanvasId || data.canvases[0].id;
    book.canvases = data.canvases;
    const canvas = getCanvasById(book.activeCanvasId);
    if (canvas) loadCanvasIntoBoard(canvas);
  } else {
    const canvasId = uid("canvas");
    book.bookTitle = data.boardTitle || "Research Workspace";
    book.activeCanvasId = canvasId;
    book.canvases = [
      {
        id: canvasId,
        name: (data.boardTitle || "Research Workspace").trim(),
        cards: data.cards || [],
        edges: data.edges || [],
        tagDefinitions: data.tagDefinitions || [],
        savedViews: data.savedViews || [],
        activeQuickView: data.activeQuickView || "all",
        panX: data.panX || 0,
        panY: data.panY || 0,
        zoom: data.zoom || 1,
      },
    ];
    loadCanvasIntoBoard(book.canvases[0]);
  }
  if (boardTitleInput) boardTitleInput.value = board.boardTitle;
  normalizeBoardData();
}

function startNewCanvas() {
  pushUndoState();
  const canvasId = uid("canvas");
  saveActiveCanvasToBook();
  book.activeCanvasId = canvasId;
  book.canvases.push({
    id: canvasId,
    name: "Canvas " + (book.canvases.length + 1),
    cards: [],
    edges: [],
    tagDefinitions: [],
    savedViews: [],
    activeQuickView: "all",
    panX: 0,
    panY: 0,
    zoom: 1,
  });
  loadCanvasIntoBoard(book.canvases[book.canvases.length - 1]);
  $("#search-input").value = "";
  $("#filter-type").value = "all";
  $("#filter-tag-id").value = "all";
  $("#filter-tag").value = "";
  refreshTagFilterOptions();
  renderAll();
  applyTransform();
  updateInspector();
  autoSave();
}

let saveTimer = null;
function autoSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const data = getState();
    saveBook(data).catch((err) => console.error("autoSave failed", err));
  }, 500);
}

function forceAutoSave() {
  const data = getState();
  return saveBook(data);
}

// ── Export / Import ──
function exportBoard() {
  const data = getState();
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = (book.bookTitle || "research-workspace")
    .toLowerCase()
    .replace(/\s+/g, "-") + ".json";
  a.click();
  URL.revokeObjectURL(url);
}

function importBoard(file) {
  pushUndoState();
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      board.editors.forEach((ed) => ed.setRootElement(null));
      board.editors.clear();
      board.editingCardId = null;
      loadState(data);
      refreshTagFilterOptions();
      renderAll();
      applyTransform();
      updateInspector();
      autoSave();
    } catch (err) {
      alert("Invalid book file: " + err.message);
    }
  };
  reader.readAsText(file);
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

const DANGEROUS_TAGS = new Set([
  "script", "style", "iframe", "object", "embed", "form", "input",
  "button", "meta", "link", "svg", "math", "template", "slot",
]);

function sanitizeHtml(html) {
  if (!html) return "<p></p>";
  const tpl = document.createElement("template");
  tpl.innerHTML = String(html);
  tpl.content.querySelectorAll("*").forEach((el) => {
    if (DANGEROUS_TAGS.has(el.tagName.toLowerCase())) {
      el.remove();
      return;
    }
    Array.from(el.attributes).forEach((attr) => {
      const n = attr.name.toLowerCase();
      if (
        n.startsWith("on") ||
        (n === "href" && attr.value.toLowerCase().startsWith("javascript:"))
      ) {
        el.removeAttribute(attr.name);
      }
    });
  });
  return tpl.innerHTML;
}

// ── File Import: type detection ──
const FILE_TYPE_MAP = {
  png: "image", jpg: "image", jpeg: "image", gif: "image", webp: "image",
  svg: "image", bmp: "image", ico: "image", avif: "image",
  csv: "table", xlsx: "table", xls: "table", ods: "table",
  txt: "text", md: "text", html: "text", htm: "text", json: "text",
  xml: "text", yaml: "text", yml: "text", log: "text", ini: "text",
  cfg: "text", conf: "text", css: "text", js: "text", jsx: "text",
  ts: "text", tsx: "text", py: "text", rb: "text", java: "text",
  c: "text", cpp: "text", h: "text", hpp: "text", rs: "text",
  go: "text", vue: "text", svelte: "text", toml: "text", rtf: "text",
  php: "text", swift: "text", kt: "text", scala: "text", sh: "text",
  bash: "text", zsh: "text", ps1: "text", bat: "text", sql: "text",
  graphql: "text", gql: "text", proto: "text", env: "text",
};

const FILENAME_TEXT_MAP = new Set([
  "makefile", "dockerfile", "gitignore",
]);

const MAX_IMAGE_FILE_SIZE = 5 * 1024 * 1024;
const MAX_TEXT_FILE_SIZE = 1 * 1024 * 1024;

async function downloadImageAsDataUrl(url) {
  const resp = await fetch("/api/download-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!resp.ok) throw new Error("Failed to download image");
  const data = await resp.json();
  return data.dataUrl;
}

let imageEditorInstance = null;
let imageEditorCallback = null;

function openImageEditor(dataUrl, onSave) {
  const modal = document.getElementById("image-editor-modal");
  const container = document.getElementById("iem-editor-container");
  modal.classList.add("active");
  void modal.offsetHeight;

  if (imageEditorInstance) {
    imageEditorInstance.destroy();
    imageEditorInstance = null;
  }

  imageEditorInstance = new tui.ImageEditor(container, {
    includeUI: {
      loadImage: { path: dataUrl, name: "image" },
      theme: {
        "common.bi.image": "",
        "common.bisize.width": "0px",
        "common.bisize.height": "0px",
        "menu.backgroundColor": "#1e1e38",
        "menu.normalIcon.color": "#c0c0d0",
        "menu.activeIcon.color": "#6c63ff",
        "menu.disabledIcon.color": "#555",
        "menu.hoverIcon.color": "#6c63ff",
        "submenu.backgroundColor": "#252545",
        "submenu.normalIcon.color": "#c0c0d0",
        "submenu.activeIcon.color": "#6c63ff",
        "submenu.normalLabel.color": "#c0c0d0",
        "submenu.activeLabel.color": "#fff",
      },
      menu: ["crop", "flip", "rotate", "draw", "shape", "icon", "text", "filter"],
      uiSize: { width: "100%", height: "100%" },
      menuBarPosition: "bottom",
    },
    cssMaxWidth: 1200,
    cssMaxHeight: 800,
    usageStatistics: false,
  });

  imageEditorCallback = onSave;
}

function closeImageEditor() {
  const modal = document.getElementById("image-editor-modal");
  modal.classList.remove("active");
  if (imageEditorInstance) {
    imageEditorInstance.destroy();
    imageEditorInstance = null;
  }
  imageEditorCallback = null;
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-close-iem").addEventListener("click", closeImageEditor);
  document.getElementById("btn-save-iem").addEventListener("click", () => {
    if (!imageEditorInstance || !imageEditorCallback) return;
    const dataUrl = imageEditorInstance.toDataURL();
    imageEditorCallback(dataUrl);
    closeImageEditor();
  });
  document.getElementById("iem-backdrop").addEventListener("click", closeImageEditor);
});

function getFileExtension(filename) {
  const dot = (filename || "").lastIndexOf(".");
  if (dot === -1) return "";
  return filename.slice(dot + 1).toLowerCase();
}

function detectCardTypeFromFile(file) {
  const ext = getFileExtension(file.name);
  if (ext) return FILE_TYPE_MAP[ext] || null;
  const lower = (file.name || "").toLowerCase();
  return FILENAME_TEXT_MAP.has(lower) ? "text" : null;
}

// ── File Import: card creation from file ──
let _pendingImportFile = null;
let _pendingImportCanvasPos = null;
let _pendingImportQueue = [];

function handleFileDrop(file, canvasPos) {
  const detectedType = detectCardTypeFromFile(file);
  if (detectedType) {
    pushUndoState();
    createCardFromFile(file, detectedType, canvasPos);
  } else {
    _pendingImportFile = file;
    _pendingImportCanvasPos = canvasPos;
    showImportDialog(file);
  }
}

function showImportDialog(file) {
  itmFileName.textContent = "" + file.name;
  const radios = importTypeModal.querySelectorAll('input[name="import-type"]');
  radios.forEach((r) => (r.checked = r.value === "text"));
  importTypeModal.style.display = "flex";
}

function closeImportDialog() {
  importTypeModal.style.display = "none";
  _pendingImportFile = null;
  _pendingImportCanvasPos = null;
  processImportQueue();
}

function confirmImportDialog() {
  const selected = importTypeModal.querySelector(
    'input[name="import-type"]:checked',
  );
  const parseType = selected ? selected.value : "text";
  if (_pendingImportFile && _pendingImportCanvasPos) {
    pushUndoState();
    createCardFromFile(_pendingImportFile, parseType, _pendingImportCanvasPos);
  }
  closeImportDialog();
}

function processImportQueue() {
  if (_pendingImportQueue.length > 0) {
    const next = _pendingImportQueue.shift();
    _pendingImportFile = next.file;
    _pendingImportCanvasPos = next.canvasPos;
    showImportDialog(next.file);
  }
}

function createCardFromFile(file, parseType, canvasPos) {
  if (parseType === "image") {
    if (file.size > MAX_IMAGE_FILE_SIZE) {
      alert("Image \"" + file.name + "\" is too large (max " + (MAX_IMAGE_FILE_SIZE / 1024 / 1024) + " MB).");
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target.result;
      addCard({
        type: "image",
        imageUrl: dataUrl,
        title: stripExtension(file.name),
        body: "<p></p>",
        x: canvasPos.x,
        y: canvasPos.y,
      });
    };
    reader.readAsDataURL(file);
    return;
  }

  if (parseType === "table") {
    const isExcel = /\.(xlsx|xls|ods)$/i.test(file.name);
    if (isExcel) {
      importTableFromFile(file, canvasPos);
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      const raw = ev.target.result;
      const rows = parseCsv(raw);
      const columns = rows.length > 0 ? rows[0] : [];
      const dataRows = rows.slice(1);
      addCard({
        type: "table",
        title: stripExtension(file.name),
        body: "<p></p>",
        tableData: { columns, rows: dataRows },
        x: canvasPos.x,
        y: canvasPos.y,
      });
    };
    reader.readAsText(file);
    return;
  }

  if (file.size > MAX_TEXT_FILE_SIZE) {
    alert("File \"" + file.name + "\" is too large (max " + (MAX_TEXT_FILE_SIZE / 1024 / 1024) + " MB).");
    return;
  }
  const reader = new FileReader();
  reader.onload = (ev) => {
    const raw = ev.target.result;
    const isHtml = /\.(html|htm)$/i.test(file.name);
    let body;
    if (isHtml) {
      body = sanitizeHtml(raw);
    } else {
      const escaped = escapeHtml(raw);
      body = "<p>" + escaped.replace(/\n/g, "</p><p>") + "</p>";
    }
    addCard({
      type: "text",
      title: stripExtension(file.name),
      body,
      x: canvasPos.x,
      y: canvasPos.y,
    });
  };
  reader.readAsText(file);
}

function importTableFromFile(file, canvasPos) {
  parseExcelToTableData(file)
    .then(({ columns, rows }) => {
      addCard({
        type: "table",
        title: stripExtension(file.name),
        body: "<p></p>",
        tableData: { columns, rows },
        x: canvasPos.x,
        y: canvasPos.y,
      });
    })
    .catch((err) => {
      alert("Failed to import file: " + err.message);
    });
}

function handleTextDrop(text, canvasPos) {
  pushUndoState();
  const escaped = escapeHtml(text);
  const body = "<p>" + escaped.replace(/\n/g, "</p><p>") + "</p>";
  addCard({
    type: "text",
    title: "Dropped Text",
    body,
    x: canvasPos.x,
    y: canvasPos.y,
  });
}

function stripExtension(filename) {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(0, dot) : filename;
}

function parseCsv(text) {
  const rows = [];
  let current = [];
  let field = "";
  let inQuotes = false;
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < text.length && text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
      } else {
        field += ch;
      }
      i++;
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (ch === ",") {
      current.push(field.trim());
      field = "";
      i++;
      continue;
    }
    if (ch === "\n") {
      current.push(field.trim());
      if (current.some((c) => c.length > 0)) rows.push(current);
      current = [];
      field = "";
      i++;
      continue;
    }
    if (ch === "\r") {
      current.push(field.trim());
      if (current.some((c) => c.length > 0)) rows.push(current);
      current = [];
      field = "";
      i++;
      if (i < text.length && text[i] === "\n") i++;
      continue;
    }
    field += ch;
    i++;
  }
  current.push(field.trim());
  if (current.some((c) => c.length > 0)) rows.push(current);
  return rows;
}

// ── File Import: drag-and-drop events ──
let _dragCounter = 0;

container.addEventListener("dragenter", (e) => {
  e.preventDefault();
  e.stopPropagation();
  _dragCounter++;
  dropOverlay.classList.add("active");
});

container.addEventListener("dragover", (e) => {
  e.preventDefault();
  e.stopPropagation();
  e.dataTransfer.dropEffect = "copy";
});

container.addEventListener("dragleave", (e) => {
  e.preventDefault();
  e.stopPropagation();
  _dragCounter--;
  if (_dragCounter <= 0) {
    _dragCounter = 0;
    dropOverlay.classList.remove("active");
  }
});

container.addEventListener("drop", (e) => {
  e.preventDefault();
  e.stopPropagation();
  _dragCounter = 0;
  dropOverlay.classList.remove("active");

  const rect = container.getBoundingClientRect();
  const canvasPos = screenToCanvas(
    e.clientX - rect.left,
    e.clientY - rect.top,
  );

  const files = e.dataTransfer.files;
  if (files.length > 0) {
    const unrecognized = [];
    for (let i = 0; i < files.length; i++) {
      const offsetPos = {
        x: canvasPos.x + i * 30,
        y: canvasPos.y + i * 30,
      };
      const detectedType = detectCardTypeFromFile(files[i]);
      if (detectedType) {
        handleFileDrop(files[i], offsetPos);
      } else {
        unrecognized.push({ file: files[i], canvasPos: offsetPos });
      }
    }
    if (unrecognized.length > 0) {
      _pendingImportQueue = unrecognized;
      const next = _pendingImportQueue.shift();
      _pendingImportFile = next.file;
      _pendingImportCanvasPos = next.canvasPos;
      showImportDialog(next.file);
    }
    return;
  }

  const text = e.dataTransfer.getData("text/plain");
  if (text) {
    handleTextDrop(text, canvasPos);
  }
});

// ── Paste handler ──
document.addEventListener("paste", (e) => {
  const items = e.clipboardData.items;
  let imageFile = null;
  let text = "";

  for (const item of items) {
    if (item.type.startsWith("image/")) {
      imageFile = item.getAsFile();
    } else if (item.type === "text/plain") {
      item.getAsString((s) => {
        text = s;
      });
    }
  }

  setTimeout(() => {
    const selectedId = [...board.selectedCardIds][0];
    if (imageFile) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const dataUrl = ev.target.result;
        if (selectedId) {
          const card = board.cards.find((c) => c.id === selectedId);
          if (card) {
            pushUndoState();
            card.imageUrl = dataUrl;
            card.updatedAt = ts();
            updateCardView(selectedId);
            autoSave();
          }
        } else {
          addCard({
            type: "image",
            imageUrl: dataUrl,
            title: "Pasted Image",
            body: "<p></p>",
          });
        }
      };
      reader.readAsDataURL(imageFile);
      return;
    }

    if (text) {
      const isUrl = /^https?:\/\//i.test(text.trim());
      if (isUrl && selectedId) {
        const card = board.cards.find((c) => c.id === selectedId);
        if (card) {
          pushUndoState();
          card.sourceUrl = text.trim();
          card.updatedAt = ts();
          updateCardView(selectedId);
          autoSave();
        }
      } else if (isUrl) {
        const sourceTag = ensureTagDefinition("source");
        refreshTagFilterOptions();
        addCard({
          type: "text",
          sourceUrl: text.trim(),
          tags: sourceTag ? [sourceTag.id] : [],
          title: "Source Link",
          body:
            '<p><a href="' +
            escapeHtml(text.trim()) +
            '">' +
            escapeHtml(text.trim()) +
            "</a></p>",
        });
      }
    }
  }, 50);
});

function updateCardView(cardId) {
  const el = content.querySelector(`[data-card-id="${cardId}"]`);
  if (!el) return;
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) return;
  applyCardSemantics(el, card);
  const view = el.querySelector(".card-body-view");
  if (view && !el.classList.contains("editing")) {
    if (card.type === "table") {
      view.innerHTML = renderTableView(card);
    } else if (card.type === "image") {
      view.innerHTML = renderImageView(card);
    } else {
      view.innerHTML = sanitizeHtml(card.body) + renderViewMeta(card);
    }
  }
  refreshTagFilterOptions();
  updateCardList();
  updateInspector();
}

// ── Left Sidebar: Card List ──
function getFilteredCards() {
  const searchTerm = ($("#search-input").value || "").toLowerCase().trim();
  const typeFilter = $("#filter-type").value;
  const tagTreeFilter = $("#filter-tag-id").value;
  const tagFilter = ($("#filter-tag").value || "").toLowerCase().trim();
  const quick = $("#quick-view-toggle").value;

  return board.cards.filter((card) => {
    if (typeFilter !== "all" && card.type !== typeFilter) return false;
    if (!cardHasTagOrDescendant(card, tagTreeFilter)) return false;

    if (quick === "high-confidence") {
      const hasHigh = Object.values(card.tagProperties || {}).some(
        (props) => String(props?.confidence || "").toLowerCase() === "high",
      );
      if (!hasHigh) return false;
    }

    if (tagFilter) {
      const tags = (card.tags || [])
        .map((t) => getTagPath(t) || t)
        .join(" ")
        .toLowerCase();
      if (!tags.includes(tagFilter)) return false;
    }
    if (searchTerm) {
      const title = (card.title || "").toLowerCase();
      const body = (card.body || "").toLowerCase();
      const tags = (card.tags || [])
        .map((t) => getTagPath(t) || t)
        .join(" ")
        .toLowerCase();
      if (
        !title.includes(searchTerm) &&
        !body.includes(searchTerm) &&
        !tags.includes(searchTerm)
      )
        return false;
    }
    return true;
  });
}

function refreshTagFilterOptions() {
  const sel = $("#filter-tag-id");
  const prev = sel.value;
  sel.innerHTML = '<option value="all">All Tags</option>';

  const roots = board.tagDefinitions.filter((t) => !t.parentId);
  const appendNode = (tag, depth) => {
    const opt = document.createElement("option");
    opt.value = tag.id;
    opt.textContent = `${"  ".repeat(depth)}${tag.name}`;
    sel.appendChild(opt);
    board.tagDefinitions
      .filter((t) => t.parentId === tag.id)
      .forEach((child) => appendNode(child, depth + 1));
  };
  roots.forEach((root) => appendNode(root, 0));
  sel.value = Array.from(sel.options).some((o) => o.value === prev)
    ? prev
    : "all";
}

function updateCardList() {
  const list = $("#card-list");
  const filtered = getFilteredCards();

  if (filtered.length === 0) {
    list.innerHTML = '<div class="cl-empty">No cards match filters</div>';
    updateCanvasStats();
    return;
  }

  list.innerHTML = "";
  filtered.forEach((card) => {
    const item = document.createElement("div");
    item.className = "cl-item";
    if (board.selectedCardIds.has(card.id)) {
      item.classList.add("selected", card.type);
    }

    const badge = document.createElement("span");
    badge.className = `cl-badge cb-${card.type}`;
    badge.textContent = card.type;
    item.appendChild(badge);

    const title = document.createElement("span");
    title.className = "cl-title";
    title.textContent = card.title || "Untitled";
    item.appendChild(title);

    if (card.tags && card.tags.length > 0) {
      const tags = document.createElement("span");
      tags.className = "cl-tags";
      tags.textContent = card.tags.map((t) => getTagPath(t) || t).join(", ");
      item.appendChild(tags);
    }

    item.addEventListener("click", (e) => {
      selectCard(
        card.id,
        board.multiSelectMode || e.ctrlKey || e.metaKey,
        e.shiftKey,
      );
      panToCard(card.id);
    });

    list.appendChild(item);
  });
  updateCanvasStats();
}

function updateCanvasStats() {
  const cardsEl = $("#stat-cards");
  const connEl = $("#stat-connections");
  const tagsEl = $("#stat-tags");
  if (!cardsEl) return;
  cardsEl.textContent = board.cards.length;
  connEl.textContent = board.edges.length;
  const tagSet = new Set();
  board.cards.forEach((c) => (c.tags || []).forEach((t) => tagSet.add(t)));
  tagsEl.textContent = tagSet.size;
}

function panToCard(cardId) {
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) return;
  const rect = container.getBoundingClientRect();
  const targetX =
    -(card.x * board.zoom) + rect.width / 2 - (card.width * board.zoom) / 2;
  const targetY =
    -(card.y * board.zoom) + rect.height / 2 - (card.height * board.zoom) / 2;
  board.panX = targetX;
  board.panY = targetY;
  applyTransform();
  renderEdges();
}

// ── Right Inspector ──
function updateInspector() {
  const inspEl = $("#right-inspector");
  const container = $("#canvas-container");
  const emptyEl = $("#inspector-empty");
  const contentEl = $("#inspector-content");
  const edgeContentEl = $("#inspector-edge-content");

  if (board.selectedEdgeId) {
    inspEl.style.display = "block";
    container.classList.remove("inspector-collapsed");
    const edge = board.edges.find((e) => e.id === board.selectedEdgeId);
    if (!edge) {
      board.selectedEdgeId = null;
      updateInspector();
      return;
    }
    emptyEl.style.display = "none";
    contentEl.style.display = "none";
    edgeContentEl.style.display = "block";

    const fromCard = board.cards.find((c) => c.id === edge.from);
    const toCard = board.cards.find((c) => c.id === edge.to);
    $("#insp-edge-id").textContent = edge.id;
    $("#insp-edge-connection").textContent =
      (fromCard?.title || edge.from) + " → " + (toCard?.title || edge.to);
    $("#insp-edge-label").value = edge.label || "";
    $("#insp-edge-type").value = edge.type || "";
    return;
  }

  if (board.selectedCardIds.size !== 1) {
    emptyEl.style.display = "block";
    contentEl.style.display = "none";
    edgeContentEl.style.display = "none";
    if (board.selectedCardIds.size > 1) {
      emptyEl.textContent = board.selectedCardIds.size + " cards selected";
    } else {
      emptyEl.textContent = "Select a card or edge to inspect";
    }
    inspEl.style.display = board.selectedCardIds.size === 0 ? "none" : "block";
    container.classList.toggle(
      "inspector-collapsed",
      board.selectedCardIds.size === 0,
    );
    return;
  }

  const cardId = [...board.selectedCardIds][0];
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) {
    emptyEl.style.display = "block";
    contentEl.style.display = "none";
    edgeContentEl.style.display = "none";
    emptyEl.textContent = "Select a card or edge to inspect";
    inspEl.style.display = "none";
    container.classList.add("inspector-collapsed");
    return;
  }

  emptyEl.style.display = "none";
  contentEl.style.display = "block";
  edgeContentEl.style.display = "none";
  inspEl.style.display = "block";

  $("#insp-id").textContent = card.id;
  $("#insp-type").textContent = CARD_TYPES[card.type]?.label || card.type;
  $("#insp-title").value = card.title || "";
  $("#insp-created").textContent = card.createdAt
    ? new Date(card.createdAt).toLocaleString()
    : "-";
  $("#insp-updated").textContent = card.updatedAt
    ? new Date(card.updatedAt).toLocaleString()
    : "-";
  $("#insp-position").textContent =
    Math.round(card.x) + ", " + Math.round(card.y);
  $("#insp-size").textContent =
    Math.round(card.width) + " x " + Math.round(card.height);
  $("#insp-tags").value = (card.tags || [])
    .map((t) => getTagDefById(t)?.name || t)
    .join(", ");
  $("#insp-source").value = card.sourceUrl || "";
  $("#insp-image").value = card.imageUrl || "";

  const showImage = card.type === "image";
  document.querySelector(".insp-field-image").style.display = showImage
    ? "block"
    : "none";
}

function setupInspectorBindings() {
  $("#insp-title").addEventListener("change", () => {
    const id = [...board.selectedCardIds][0];
    if (!id) return;
    const card = board.cards.find((c) => c.id === id);
    if (!card) return;
    pushUndoState();
    card.title = $("#insp-title").value;
    card.updatedAt = ts();
    const el = content.querySelector(`[data-card-id="${id}"]`);
    if (el) el.querySelector(".card-title-input").value = card.title;
    updateCardList();
    autoSave();
  });

  $("#insp-tags").addEventListener("change", () => {
    const id = [...board.selectedCardIds][0];
    if (!id) return;
    const card = board.cards.find((c) => c.id === id);
    if (!card) return;
    pushUndoState();
    card.tags = $("#insp-tags")
      .value.split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((name) => ensureTagDefinition(name)?.id)
      .filter(Boolean);
    card.updatedAt = ts();
    refreshTagFilterOptions();
    updateCardList();
    updateCardView(id);
    autoSave();
  });

  $("#insp-source").addEventListener("change", () => {
    const id = [...board.selectedCardIds][0];
    if (!id) return;
    const card = board.cards.find((c) => c.id === id);
    if (!card) return;
    pushUndoState();
    card.sourceUrl = $("#insp-source").value;
    card.updatedAt = ts();
    updateCardView(id);
    autoSave();
  });

  $("#insp-image").addEventListener("change", async () => {
    const id = [...board.selectedCardIds][0];
    if (!id) return;
    const card = board.cards.find((c) => c.id === id);
    if (!card) return;
    const nextUrl = $("#insp-image").value.trim();
    if (!nextUrl) return;
    pushUndoState();
    try {
      let dataUrl;
      if (nextUrl.startsWith("data:")) {
        dataUrl = nextUrl;
      } else {
        dataUrl = await downloadImageAsDataUrl(nextUrl);
      }
      card.imageUrl = dataUrl;
      card.updatedAt = ts();
      updateCardView(id);
      autoSave();
    } catch (err) {
      alert("Failed to download image from URL. Check the URL and try again.");
      console.error(err);
    }
  });

  $("#insp-edge-label").addEventListener("change", () => {
    if (!board.selectedEdgeId) return;
    const edge = board.edges.find((e) => e.id === board.selectedEdgeId);
    if (!edge) return;
    pushUndoState();
    edge.label = $("#insp-edge-label").value;
    renderEdges();
    autoSave();
  });

  $("#insp-edge-type").addEventListener("change", () => {
    if (!board.selectedEdgeId) return;
    const edge = board.edges.find((e) => e.id === board.selectedEdgeId);
    if (!edge) return;
    pushUndoState();
    edge.type = $("#insp-edge-type").value;
    autoSave();
  });
}

function setupSearchAndFilters() {
  $("#search-input").addEventListener("input", updateCardList);
  $("#filter-type").addEventListener("change", updateCardList);
  $("#quick-view-toggle").addEventListener("change", updateCardList);
  $("#filter-tag-id").addEventListener("change", updateCardList);
  $("#filter-tag").addEventListener("input", updateCardList);
  $("#btn-open-tag-hierarchy").addEventListener("click", openTagHierarchyModal);
}

function closeTopbarMenus() {
  document.querySelectorAll("[data-menu-root].open").forEach((root) => {
    root.classList.remove("open");
  });
}

function refreshMultiSelectUI() {
  const show = board.multiSelectMode;
  const hasSelection = board.selectedCardIds.size > 0;
  const hasClipboard = board.clipboardCards !== null;

  // Toggle class on canvas-content for checkbox visibility
  content.classList.toggle("multi-select-mode", show);

  // Update checkbox visual states
  content.querySelectorAll(".card-checkbox").forEach((cb) => {
    const id = cb.dataset.cardId;
    cb.classList.toggle("checked", board.selectedCardIds.has(id));
  });

  // Toolbar clipboard group and separators
  const cutBtn = document.querySelector('[data-action="cut-cards"]');
  const copyBtn = document.querySelector('[data-action="copy-cards"]');
  const pasteBtn = document.querySelector('[data-action="paste-cards"]');
  const group = document.querySelector(".tb-clipboard-group");
  const seps = document.querySelectorAll(".clipboard-sep");
  const groupVisible = show || hasClipboard;

  if (group) group.classList.toggle("show", groupVisible);
  seps.forEach((s) => s.classList.toggle("show", groupVisible));

  if (cutBtn) {
    cutBtn.classList.toggle("show", show);
    cutBtn.disabled = !hasSelection;
  }
  if (copyBtn) {
    copyBtn.classList.toggle("show", show);
    copyBtn.disabled = !hasSelection;
  }
  if (pasteBtn) {
    pasteBtn.classList.toggle("show", show || hasClipboard);
    pasteBtn.disabled = !hasClipboard;
  }

  // Update menu items
  document.querySelectorAll('[data-action="toggle-multi-select"]').forEach((btn) => {
    btn.textContent = show ? "Disable Multi-Select Mode" : "Enable Multi-Select Mode";
  });
}

function exitMultiSelectMode() {
  if (!board.multiSelectMode) return;
  board.multiSelectMode = false;
  board.selectedCardIds.clear();
  board.lastSelectedCardId = null;
  updateSelection();
  refreshMultiSelectUI();
}

function handleTopbarAction(actionEl) {
  const action = actionEl.dataset.action;
  if (!action) return;

  if (action === "undo") {
    undo();
  } else if (action === "redo") {
    redo();
  } else if (action === "new-card") {
    addCardAtViewportCenter(actionEl.dataset.cardType || "text");
  } else if (action === "export-board") {
    exportBoard();
  } else if (action === "back-to-books") {
    forceAutoSave().then(() => {
      window.location.href = "/landing.html";
    });
  } else if (action === "zoom-preset") {
    const z = Number(actionEl.dataset.zoom);
    if (Number.isFinite(z) && z > 0) setZoomLevel(z);
  } else if (action === "zoom-fit") {
    fitCardsToViewport();
  } else if (action === "select-all-cards") {
    board.cards.forEach((c) => board.selectedCardIds.add(c.id));
    updateSelection();
    refreshMultiSelectUI();
  } else if (action === "toggle-multi-select") {
    board.multiSelectMode = !board.multiSelectMode;
    if (!board.multiSelectMode) board.selectedCardIds.clear();
    updateSelection();
    refreshMultiSelectUI();
  } else if (action === "copy-cards") {
    copySelectedCards();
  } else if (action === "cut-cards") {
    cutSelectedCards();
  } else if (action === "paste-cards") {
    pasteCardsFromClipboard();
  }
}

function setupTopbar() {
  if (boardTitleInput) {
    boardTitleInput.addEventListener("change", () => {
      pushUndoState();
      book.bookTitle = boardTitleInput.value.trim() || "Untitled Book";
      board.boardTitle = book.bookTitle;
      boardTitleInput.value = board.boardTitle;
      autoSave();
    });
  }

  const toolbar = $("#toolbar");
  toolbar.addEventListener("click", (e) => {
    const toggle = e.target.closest("[data-menu-toggle]");
    if (toggle) {
      const root = toggle.closest("[data-menu-root]");
      const wasOpen = root.classList.contains("open");
      closeTopbarMenus();
      if (!wasOpen) root.classList.add("open");
      e.stopPropagation();
      return;
    }

    const actionEl = e.target.closest("[data-action]");
    if (!actionEl || actionEl.disabled) return;
    handleTopbarAction(actionEl);
    closeTopbarMenus();
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#toolbar")) closeTopbarMenus();
  });

  refreshMultiSelectUI();
}

// ── Init ──
async function init() {
  const params = new URLSearchParams(window.location.search);
  const bookId = params.get("bookId");

  if (!bookId) {
    window.location.href = "/landing.html";
    return;
  }

  const data = await getBook(bookId);
  if (!data) {
    window.location.href = "/landing.html";
    return;
  }

  loadState(data);

  normalizeBoardData();
  refreshTagFilterOptions();
  renderAll();
  applyTransform();
  updateCardList();
  setupInspectorBindings();
  setupSearchAndFilters();
  setupTopbar();

  // Toolbar buttons
  syncSidebarState();
  $("#btn-collapse-sidebar").addEventListener("click", toggleLeftSidebar);
  $("#btn-close-thm").addEventListener("click", closeTagHierarchyModal);
  $("#btn-done-thm").addEventListener("click", closeTagHierarchyModal);
  $("#thm-backdrop").addEventListener("click", closeTagHierarchyModal);

  btnCloseItm.addEventListener("click", closeImportDialog);
  btnCancelItm.addEventListener("click", closeImportDialog);
  btnConfirmItm.addEventListener("click", confirmImportDialog);
  itmBackdrop.addEventListener("click", closeImportDialog);

  importExcelInput.addEventListener("change", (e) => {
    if (!e.target.files[0]) return;
    const selectedId = [...board.selectedCardIds][0];
    const card = board.cards.find((c) => c.id === selectedId);
    if (card && card.type === "table") {
      importTableXLSX(e.target.files[0], card);
    }
    e.target.value = "";
  });
  undoStack.length = 0;
  redoStack.length = 0;
  pushUndoState();
}

// ── Tag Hierarchy Modal ──
let _draggedTagId = null;

function openTagHierarchyModal() {
  renderHierarchyList();
  $("#tag-hierarchy-modal").style.display = "flex";
}

function closeTagHierarchyModal() {
  $("#tag-hierarchy-modal").style.display = "none";
  refreshTagFilterOptions();
  // Re-render all card views so semantic colors/badges update
  board.cards.forEach((card) => {
    const el = content.querySelector(`[data-card-id="${card.id}"]`);
    if (el) applyCardSemantics(el, card);
  });
  updateCardList();
  autoSave();
}

function renderHierarchyList() {
  const list = $("#thm-list");
  list.innerHTML = "";

  // Depth-first traversal to render ordered with indent
  function appendNode(tagId, depth) {
    const tag = getTagDefById(tagId);
    if (!tag) return;

    const pill = document.createElement("div");
    pill.className = "thm-pill";
    pill.dataset.tagId = tag.id;
    pill.draggable = true;
    pill.style.marginLeft = depth * 22 + "px";

    pill.innerHTML = `
      <span class="thm-drag-handle" title="Drag to reparent">⠿</span>
      <span class="thm-color-dot" style="background:${escapeHtml(tag.color || "#6c63ff")}"></span>
      <span class="thm-pill-name">${escapeHtml(tag.name)}</span>
      ${tag.parentId ? `<button class="thm-btn-root" title="Remove parent (make root)">↑ root</button>` : ""}
    `;

    // Drag source
    pill.addEventListener("dragstart", (e) => {
      _draggedTagId = tag.id;
      pill.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    pill.addEventListener("dragend", () => {
      pill.classList.remove("dragging");
      _draggedTagId = null;
      document
        .querySelectorAll(".thm-pill.drag-over, .thm-root-zone.drag-over")
        .forEach((el) => el.classList.remove("drag-over"));
    });

    // Drop target: drop onto this pill → dragged becomes child
    pill.addEventListener("dragover", (e) => {
      if (!_draggedTagId || _draggedTagId === tag.id) return;
      // Prevent circular nesting: don't allow drop onto a descendant
      if (getDescendantTagIds(_draggedTagId).includes(tag.id)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      document
        .querySelectorAll(".thm-pill.drag-over")
        .forEach((el) => el.classList.remove("drag-over"));
      pill.classList.add("drag-over");
    });
    pill.addEventListener("dragleave", () =>
      pill.classList.remove("drag-over"),
    );
    pill.addEventListener("drop", (e) => {
      e.preventDefault();
      pill.classList.remove("drag-over");
      if (!_draggedTagId || _draggedTagId === tag.id) return;
      if (getDescendantTagIds(_draggedTagId).includes(tag.id)) return;
      const dragged = getTagDefById(_draggedTagId);
      if (dragged) {
        pushUndoState();
        dragged.parentId = tag.id;
      }
      renderHierarchyList();
    });

    // Make root button
    const rootBtn = pill.querySelector(".thm-btn-root");
    if (rootBtn) {
      rootBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const t = getTagDefById(tag.id);
        if (t) {
          pushUndoState();
          t.parentId = null;
        }
        renderHierarchyList();
      });
    }

    list.appendChild(pill);

    // Render children immediately after
    board.tagDefinitions
      .filter((t) => t.parentId === tag.id)
      .forEach((child) => appendNode(child.id, depth + 1));
  }

  // Root tags first
  board.tagDefinitions
    .filter((t) => !t.parentId)
    .forEach((root) => appendNode(root.id, 0));

  // Root drop zone
  const rootZone = $("#thm-root-zone");
  rootZone.addEventListener("dragover", (e) => {
    if (!_draggedTagId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    rootZone.classList.add("drag-over");
  });
  rootZone.addEventListener("dragleave", () =>
    rootZone.classList.remove("drag-over"),
  );
  rootZone.addEventListener("drop", (e) => {
    e.preventDefault();
    rootZone.classList.remove("drag-over");
    if (!_draggedTagId) return;
    const dragged = getTagDefById(_draggedTagId);
    if (dragged) {
      pushUndoState();
      dragged.parentId = null;
    }
    renderHierarchyList();
  });
}

init();
