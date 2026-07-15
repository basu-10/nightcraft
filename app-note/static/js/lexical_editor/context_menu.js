import {
  $getNodeByKey,
  $createParagraphNode,
  TableCellNode,
  TableRowNode,
  TableNode,
} from './deps.js';

function getLexicalNode(editor, domEl) {
  let el = domEl;
  const root = editor.getRootElement();
  while (el && el !== root) {
    const keyProp = Object.getOwnPropertyNames(el).find(name => name.startsWith('__lexicalKey_'));
    const key = keyProp ? el[keyProp] : undefined;
    if (key !== undefined) {
      let node = null;
      editor.getEditorState().read(() => { node = $getNodeByKey(key); });
      return node;
    }
    el = el.parentElement;
  }
  return null;
}

// ── Menu DOM helpers ──────────────────────────────────────────────────────
function createMenu() {
  const m = document.createElement('div');
  m.className = 'lex-ctx-menu';
  m.setAttribute('role', 'menu');
  return m;
}

function addTitle(menu, text) {
  const d = document.createElement('div');
  d.className = 'lex-ctx-menu__title';
  d.textContent = text;
  menu.appendChild(d);
  addSep(menu);
}

function addItem(menu, icon, label, action, danger, hasSubmenu) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'lex-ctx-menu__item' + (danger ? ' lex-ctx-menu__item--danger' : '') + (hasSubmenu ? ' lex-ctx-menu__item--submenu' : '');
  b.setAttribute('role', 'menuitem');
  const arrowHtml = hasSubmenu ? `<span class="lex-ctx-menu__arrow" aria-hidden="true">›</span>` : '';
  b.innerHTML =
    `<span class="lex-ctx-menu__icon" aria-hidden="true">${icon}</span>` +
    `<span class="lex-ctx-menu__label">${label}</span>` +
    arrowHtml;
  b.addEventListener('mousedown', e => e.preventDefault());
  if (!hasSubmenu) b.addEventListener('click', e => { e.stopPropagation(); action(); });
  menu.appendChild(b);
  return b;
}

function addSep(menu) {
  const s = document.createElement('div');
  s.className = 'lex-ctx-menu__sep';
  s.setAttribute('role', 'separator');
  menu.appendChild(s);
}

function mountMenu(menu, x, y) {
  document.body.appendChild(menu);
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const r  = menu.getBoundingClientRect();
  menu.style.left = Math.min(x, vw - r.width  - 8) + 'px';
  menu.style.top  = Math.min(y, vh - r.height - 8) + 'px';
  // focus first item for keyboard nav
  const first = menu.querySelector('.lex-ctx-menu__item');
  if (first) first.focus();
}

// ── Table operations ──────────────────────────────────────────────────────
function tableOp(editor, cellKey, fn) {
  editor.update(() => {
    const cell = $getNodeByKey(cellKey);
    if (!(cell instanceof TableCellNode)) return;
    fn(cell);
  });
}

function insertRow(editor, cellKey, above) {
  tableOp(editor, cellKey, cell => {
    const row   = cell.getParent();
    if (!(row instanceof TableRowNode)) return;
    const cols  = row.getChildrenSize();
    const newRow = new TableRowNode();
    for (let i = 0; i < cols; i++) {
      const c = new TableCellNode(0);
      c.append($createParagraphNode());
      newRow.append(c);
    }
    if (above) row.insertBefore(newRow);
    else       row.insertAfter(newRow);
  });
}

function insertCol(editor, cellKey, left) {
  tableOp(editor, cellKey, cell => {
    const row   = cell.getParent();
    if (!(row instanceof TableRowNode)) return;
    const table = row.getParent();
    if (!(table instanceof TableNode)) return;
    const colIdx = cell.getIndexWithinParent();
    for (const r of table.getChildren()) {
      const cells  = r.getChildren();
      const target = cells[colIdx];
      if (!target) continue;
      const newCell = new TableCellNode(0);
      newCell.append($createParagraphNode());
      if (left) target.insertBefore(newCell);
      else      target.insertAfter(newCell);
    }
  });
}

function deleteRow(editor, cellKey) {
  tableOp(editor, cellKey, cell => {
    const row   = cell.getParent();
    if (!(row instanceof TableRowNode)) return;
    const table = row.getParent();
    if (!(table instanceof TableNode)) return;
    if (table.getChildrenSize() <= 1) table.remove();
    else row.remove();
  });
}

function deleteCol(editor, cellKey) {
  tableOp(editor, cellKey, cell => {
    const row   = cell.getParent();
    if (!(row instanceof TableRowNode)) return;
    const table = row.getParent();
    if (!(table instanceof TableNode)) return;
    const colIdx = cell.getIndexWithinParent();
    if (row.getChildrenSize() <= 1) { table.remove(); return; }
    for (const r of table.getChildren()) {
      const cells = r.getChildren();
      if (cells[colIdx]) cells[colIdx].remove();
    }
  });
}

function deleteTable(editor, cellKey) {
  tableOp(editor, cellKey, cell => {
    const row   = cell.getParent();
    if (!(row instanceof TableRowNode)) return;
    const table = row.getParent();
    if (table instanceof TableNode) table.remove();
  });
}

// ── Image operations ──────────────────────────────────────────────────────
function deleteImage(editor, key) {
  editor.update(() => { const n = $getNodeByKey(key); if (n) n.remove(); });
}

function setImageAlt(editor, key, alt) {
  editor.update(() => {
    const n = $getNodeByKey(key);
    if (n && typeof n.setAlt === 'function') n.setAlt(alt);
  });
}

function setImageSrc(editor, key, src) {
  editor.update(() => {
    const n = $getNodeByKey(key);
    if (n && typeof n.setSrc === 'function') n.setSrc(src);
  });
}

function setImageSize(editor, key, width, height) {
  editor.update(() => {
    const n = $getNodeByKey(key);
    if (!n || !n.setWidth) return;
    if (width) n.setWidth(width);
    if (height) n.setHeight(height);
  });
}

// ── Menu builders ─────────────────────────────────────────────────────────
function buildTableMenu(editor, cellKey, menu, close) {
  addTitle(menu, 'Table');
  addItem(menu, '⬆', 'Insert row above',    () => { insertRow(editor, cellKey, true);  close(); });
  addItem(menu, '⬇', 'Insert row below',    () => { insertRow(editor, cellKey, false); close(); });
  addSep(menu);
  addItem(menu, '⬅', 'Insert column left',  () => { insertCol(editor, cellKey, true);  close(); });
  addItem(menu, '➡', 'Insert column right', () => { insertCol(editor, cellKey, false); close(); });
  addSep(menu);
  addItem(menu, '✕', 'Delete row',    () => { deleteRow(editor, cellKey);   close(); }, true);
  addItem(menu, '✕', 'Delete column', () => { deleteCol(editor, cellKey);   close(); }, true);
  addItem(menu, '🗑', 'Delete table',  () => { deleteTable(editor, cellKey); close(); }, true);
}

function buildImageMenu(editor, nodeKey, imgEl, triggerReplace, menu, close) {
  addTitle(menu, 'Image');
  addItem(menu, '✏', 'Edit alt text', async () => {
    close();
    const cur    = imgEl.alt || '';
    const newAlt = await showPrompt('Alt text:', cur);
    if (newAlt !== null) setImageAlt(editor, nodeKey, newAlt);
  });
  addItem(menu, '🔄', 'Replace image', () => { close(); triggerReplace(nodeKey); });
  
  // Resize submenu
  const resizeBtn = addItem(menu, '📏', 'Resize', () => {}, false, true);
  const submenu = document.createElement('div');
  submenu.className = 'lex-ctx-menu__submenu';
  submenu.style.cssText = 'position:absolute;left:100%;top:0;background:var(--bg-modal);border:1px solid var(--border-med);border-radius:var(--radius-sm);min-width:160px;padding:8px;display:none;box-shadow:var(--shadow-strong);';
  
  const sizes = [
    { label: '50%', w: '50%', h: 'auto' },
    { label: '75%', w: '75%', h: 'auto' },
    { label: '100%', w: '100%', h: 'auto' },
    { label: 'Reset', w: null, h: null }
  ];
  
  for (const size of sizes) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'lex-ctx-menu__item';
    btn.style.cssText = 'width:100%;';
    btn.textContent = size.label;
    btn.addEventListener('click', e => {
      e.stopPropagation();
      setImageSize(editor, nodeKey, size.w, size.h);
      close();
    });
    submenu.appendChild(btn);
  }
  
  resizeBtn.addEventListener('mouseenter', () => { submenu.style.display = 'block'; });
  resizeBtn.addEventListener('mouseleave', () => { submenu.style.display = 'none'; });
  submenu.addEventListener('mouseenter', () => { submenu.style.display = 'block'; });
  submenu.addEventListener('mouseleave', () => { submenu.style.display = 'none'; });
  
  resizeBtn.style.position = 'relative';
  resizeBtn.appendChild(submenu);
  
  addSep(menu);
  addItem(menu, '🗑', 'Delete image', () => { deleteImage(editor, nodeKey); close(); }, true);
}

// ── Main attach function ──────────────────────────────────────────────────
function attachContextMenu(editor, rootEl) {
  let activeMenu = null;

  // Hidden file input for image replacement
  const filePicker = document.createElement('input');
  filePicker.type = 'file';
  filePicker.accept = 'image/*';
  filePicker.style.cssText = 'position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;top:-9999px;';
  document.body.appendChild(filePicker);

  let pendingKey = null;
  filePicker.addEventListener('change', () => {
    const file = filePicker.files && filePicker.files[0];
    filePicker.value = '';
    if (!file || !pendingKey) return;
    const key = pendingKey;
    pendingKey = null;
    const reader = new FileReader();
    reader.onload = () => {
      const src = typeof reader.result === 'string' ? reader.result : '';
      if (src) setImageSrc(editor, key, src);
    };
    reader.readAsDataURL(file);
  });

  function triggerReplace(nodeKey) { pendingKey = nodeKey; filePicker.click(); }

  function closeMenu() {
    if (activeMenu) { activeMenu.remove(); activeMenu = null; }
  }

  function openMenu(x, y, builderFn) {
    closeMenu();
    const menu = createMenu();
    builderFn(menu, closeMenu);
    mountMenu(menu, x, y);
    activeMenu = menu;
  }

  // Shared handler for both right-click and long-press
  function handleAt(target, x, y, preventDefault) {
    // Table cell?
    const tdEl = target.closest ? target.closest('td, th') : null;
    if (tdEl && rootEl.contains(tdEl)) {
      const node = getLexicalNode(editor, tdEl);
      if (node instanceof TableCellNode) {
        preventDefault();
        const k = node.__key;
        openMenu(x, y, (menu, close) => buildTableMenu(editor, k, menu, close));
        return;
      }
    }
    // Image?
    if (
      target.tagName === 'IMG' &&
      target.classList.contains('lex-image') &&
      rootEl.contains(target)
    ) {
      const node = getLexicalNode(editor, target);
      if (node) {
        preventDefault();
        const k = node.__key;
        openMenu(x, y, (menu, close) => buildImageMenu(editor, k, target, triggerReplace, menu, close));
      }
    }
  }

  // Desktop: contextmenu
  rootEl.addEventListener('contextmenu', e => {
    handleAt(e.target, e.clientX, e.clientY, () => e.preventDefault());
  });

  // Mobile: long-press (500 ms)
  let lpTimer = null;
  rootEl.addEventListener('touchstart', e => {
    if (e.touches.length !== 1) return;
    const { clientX: x, clientY: y } = e.touches[0];
    const tgt = e.target;
    lpTimer = setTimeout(() => {
      lpTimer = null;
      handleAt(tgt, x, y, () => {});
    }, 500);
  }, { passive: true });

  function cancelLP() { if (lpTimer) { clearTimeout(lpTimer); lpTimer = null; } }
  rootEl.addEventListener('touchmove',   cancelLP, { passive: true });
  rootEl.addEventListener('touchend',    cancelLP, { passive: true });
  rootEl.addEventListener('touchcancel', cancelLP, { passive: true });

  // Close on outside click / Escape
  document.addEventListener('mousedown', e => {
    if (activeMenu && !activeMenu.contains(e.target)) closeMenu();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && activeMenu) { closeMenu(); e.stopPropagation(); }
  });
}

export { attachContextMenu };
