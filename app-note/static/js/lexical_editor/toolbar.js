import {
  $getSelection,
  $isRangeSelection,
  $setSelection,
  $isTextNode,
  $createParagraphNode,
  FORMAT_TEXT_COMMAND,
  FORMAT_ELEMENT_COMMAND,
  UNDO_COMMAND,
  REDO_COMMAND,
  $createHeadingNode,
  $createQuoteNode,
  INSERT_ORDERED_LIST_COMMAND,
  INSERT_UNORDERED_LIST_COMMAND,
  $setBlocksType,
  $patchStyleText,
} from './deps.js';
import { insertTable, insertImage } from './insertions.js';

const ICON = (inner) =>
  `<svg class="lexical-toolbar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
  `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;

const ICONS = {
  bold: ICON('<path d="M7 5h5a3.5 3.5 0 0 1 0 7H7z"/><path d="M7 12h6a3.5 3.5 0 0 1 0 7H7z"/><line x1="7" y1="5" x2="7" y2="19"/>'),
  italic: ICON('<line x1="11" y1="5" x2="17" y2="5"/><line x1="7" y1="19" x2="13" y2="19"/><line x1="14" y1="5" x2="10" y2="19"/>'),
  underline: ICON('<path d="M7 4v5a5 5 0 0 0 10 0V4"/><line x1="5" y1="20" x2="19" y2="20"/>'),
  strikethrough: ICON('<line x1="5" y1="12" x2="19" y2="12"/><path d="M8 7c1.5-1.6 4-2 6-1.4 2 .6 3 2 3 3.4"/><path d="M8 17c1.5 1.6 4 2 6 1.4 2-.6 3-2 3-3.4"/>'),
  h1: ICON('<path d="M4 18V6"/><path d="M4 13 11 6"/>'),
  h2: ICON('<path d="M4 6v12"/><path d="M4 12h4"/><path d="M4 18h4"/><path d="M12 9.5a2.5 2.5 0 1 1 2.5 2.5H12"/>'),
  h3: ICON('<path d="M4 6v12"/><path d="M4 12h4"/><path d="M4 18h4"/><path d="M12 9h4.5a2 2 0 1 1 0 4H12a2 2 0 0 0 0 4h5"/>'),
  paragraph: ICON('<path d="M12 5v14"/><path d="M12 5a4 4 0 0 1 0 8h4"/>'),
  quote: ICON('<path d="M9 7H6.5a1.5 1.5 0 0 0-1.5 1.5v3A1.5 1.5 0 0 0 6.5 13H8v-2H6.5V9H9z"/><path d="M18 7h-2.5a1.5 1.5 0 0 0-1.5 1.5v3A1.5 1.5 0 0 0 15.5 13H17v-2h-1.5V9H18z"/>'),
  bulletList: ICON('<line x1="9" y1="7" x2="19" y2="7"/><line x1="9" y1="12" x2="19" y2="12"/><line x1="9" y1="17" x2="19" y2="17"/><circle cx="4.5" cy="7" r="1.4" fill="currentColor" stroke="none"/><circle cx="4.5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="4.5" cy="17" r="1.4" fill="currentColor" stroke="none"/>'),
  orderedList: ICON('<line x1="10" y1="7" x2="19" y2="7"/><line x1="10" y1="12" x2="19" y2="12"/><line x1="10" y1="17" x2="19" y2="17"/><path d="M4 5h2v3.4"/><path d="M4 10.5h2V14"/><path d="M4 16.2h2V19"/>'),
  alignLeft: ICON('<line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="14" y2="12"/><line x1="4" y1="18" x2="17" y2="18"/>'),
  alignCenter: ICON('<line x1="4" y1="6" x2="20" y2="6"/><line x1="7" y1="12" x2="17" y2="12"/><line x1="5" y1="18" x2="19" y2="18"/>'),
  alignRight: ICON('<line x1="4" y1="6" x2="20" y2="6"/><line x1="10" y1="12" x2="20" y2="12"/><line x1="7" y1="18" x2="20" y2="18"/>'),
  alignJustify: ICON('<line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>'),
  table: ICON('<rect x="4" y="5" width="16" height="14" rx="1.5"/><line x1="4" y1="10" x2="20" y2="10"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="5" x2="10" y2="19"/><line x1="15" y1="5" x2="15" y2="19"/>'),
  image: ICON('<rect x="4" y="5" width="16" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M5 17l4.5-4 3 3 3-3 3.5 3.5"/>'),
  clear: ICON('<path d="M4 14 12 6l4 4-7 7H7z"/><line x1="9" y1="19" x2="19" y2="19"/>'),
  undo: ICON('<path d="M9 7 4 12l5 5"/><path d="M4 12h10a6 6 0 0 1 0 12H9"/>'),
  redo: ICON('<path d="M15 7 20 12l-5 5"/><path d="M20 12H10a6 6 0 0 0 0 12h5"/>'),
  textColor: (clr) => ICON('<path d="M5 15 8.5 6 12 15"/><line x1="6.4" y1="12" x2="11" y2="12"/><rect x="4.5" y="18.2" width="15" height="2.6" rx="1.3" style="fill: var(--clr, #e8e8e8)"/>').replace('--clr, #e8e8e8', `--clr, ${clr}`),
  highlight: (clr) => ICON('<path d="M4 17 12 9l3 3-7 7H7z"/><path d="M12 9l2.5-2.5a1.5 1.5 0 0 1 2 0l1 1a1.5 1.5 0 0 1 0 2L15 12"/><rect x="4.5" y="19.4" width="15" height="2.6" rx="1.3" style="fill: var(--clr, #ffff00); opacity: 0.5"/>').replace('--clr, #ffff00', `--clr, ${clr}`),
};

function buildToolbar(editor) {
  const bar = document.createElement('div');
  bar.className = 'lexical-toolbar';
  bar.setAttribute('aria-label', 'Formatting toolbar');

  const buttons = {};
  let savedSelection = null;
  const floatingMenus = [];

  function snapshotSelection() {
    editor.getEditorState().read(() => {
      const s = $getSelection();
      if ($isRangeSelection(s)) savedSelection = s.clone();
    });
  }

  function withSelection(action) {
    editor.update(() => {
      let s = $getSelection();
      if (!$isRangeSelection(s) && savedSelection) {
        $setSelection(savedSelection.clone());
        s = $getSelection();
      }
      if ($isRangeSelection(s)) action(s);
    });
  }

  function restoreSelection() {
    editor.update(() => {
      const s = $getSelection();
      if (!$isRangeSelection(s) && savedSelection) {
        $setSelection(savedSelection.clone());
      }
    });
  }

  function closeMenus(except = null) {
    for (const menu of floatingMenus) {
      if (menu !== except) menu.hidden = true;
    }
  }

  document.addEventListener('mousedown', e => {
    if (!bar.contains(e.target)) closeMenus();
  });

  function btn(key, title, icon, action) {
    const b = document.createElement('button');
    b.type = 'button';
    b.title = title;
    b.className = 'lexical-toolbar__btn';
    b.innerHTML = icon;
    if (key) buttons[key] = b;
    b.addEventListener('mousedown', e => {
      e.preventDefault();
      snapshotSelection();
      action();
    });
    return b;
  }

  function setActive(key, on) {
    const b = buttons[key];
    if (b) b.classList.toggle('is-active', !!on);
  }

  function refreshToolbarState() {
    const sel = $getSelection();
    const fmt = { bold: false, italic: false, underline: false, strikethrough: false };
    let blockType = null;
    let alignType = null;
    if ($isRangeSelection(sel)) {
      fmt.bold = sel.hasFormat('bold');
      fmt.italic = sel.hasFormat('italic');
      fmt.underline = sel.hasFormat('underline');
      fmt.strikethrough = sel.hasFormat('strikethrough');
      const anchorNode = sel.anchor.getNode();
      const top = anchorNode.getTopLevelElement ? anchorNode.getTopLevelElement() : null;
      if (top) {
        blockType = top.getType();
        alignType = top.getFormatType();
      }
    }
    setActive('bold', fmt.bold);
    setActive('italic', fmt.italic);
    setActive('underline', fmt.underline);
    setActive('strikethrough', fmt.strikethrough);
    setActive('paragraph', blockType === 'paragraph');
    setActive('h1', blockType === 'h1');
    setActive('h2', blockType === 'h2');
    setActive('h3', blockType === 'h3');
    setActive('quote', blockType === 'quote');
    setActive('align-left', alignType === 'left' || alignType === '');
    setActive('align-center', alignType === 'center');
    setActive('align-right', alignType === 'right');
    setActive('align-justify', alignType === 'justify');
  }

  editor.registerUpdateListener((payload) => {
    const state = payload && typeof payload.read === 'function'
      ? payload
      : (payload && payload.editorState);
    if (state && typeof state.read === 'function') {
      state.read(refreshToolbarState);
    }
  });

  function sep() {
    const s = document.createElement('span');
    s.className = 'lexical-toolbar__sep';
    return s;
  }

  function dropdown(title, opts, onChange) {
    const s = document.createElement('select');
    s.className = 'lexical-toolbar__select';
    s.title = title;
    opts.forEach(([val, label]) => {
      const o = document.createElement('option');
      o.value = val;
      o.textContent = label;
      s.appendChild(o);
    });
    s.addEventListener('mousedown', e => e.stopPropagation());
    s.addEventListener('change', () => {
      onChange(s.value);
      const root = editor.getRootElement();
      if (root) root.focus();
    });
    return s;
  }

  function colorSplitBtn(title, iconHtml, defaultColor, onApply) {
    const wrap = document.createElement('span');
    wrap.className = 'lexical-toolbar__split-color';
    wrap.title = title;

    const main = document.createElement('button');
    main.type = 'button';
    main.className = 'lexical-toolbar__btn lexical-toolbar__split-main';
    main.innerHTML = iconHtml;

    const caret = document.createElement('button');
    caret.type = 'button';
    caret.className = 'lexical-toolbar__btn lexical-toolbar__split-caret';
    caret.textContent = '▾';
    caret.setAttribute('aria-label', `${title} options`);

    const menu = document.createElement('div');
    menu.className = 'lexical-toolbar__menu lexical-toolbar__menu--color';
    menu.hidden = true;

    const heading = document.createElement('div');
    heading.className = 'lexical-toolbar__menu-title';
    heading.textContent = 'Pick color';
    menu.appendChild(heading);

    const swatches = document.createElement('div');
    swatches.className = 'lexical-toolbar__swatches';
    menu.appendChild(swatches);

    const customBtn = document.createElement('button');
    customBtn.type = 'button';
    customBtn.className = 'lexical-toolbar__menu-item';
    customBtn.textContent = 'Custom...';
    menu.appendChild(customBtn);

    const input = document.createElement('input');
    input.type = 'color';
    input.value = defaultColor;
    input.className = 'lexical-toolbar__color-input';
    input.tabIndex = -1;

    let activeColor = defaultColor;
    const presetColors = [
      '#111111', '#2f2f2f', '#555555', '#7a7a7a', '#a3a3a3', '#cccccc', '#e8e8e8',
      '#ff6f61',
    ];

    function applyColor(color) {
      activeColor = color;
      main.style.setProperty('--clr', color);
      input.value = color;
      closeMenus();
      onApply(color);
    }

    for (const color of presetColors) {
      const sw = document.createElement('button');
      sw.type = 'button';
      sw.className = 'lexical-toolbar__swatch';
      sw.style.setProperty('--swatch', color);
      sw.title = color;
      sw.addEventListener('mousedown', e => {
        e.preventDefault();
        snapshotSelection();
        applyColor(color);
      });
      swatches.appendChild(sw);
    }

    main.style.setProperty('--clr', activeColor);

    main.addEventListener('mousedown', e => {
      e.preventDefault();
      snapshotSelection();
      onApply(activeColor);
    });

    caret.addEventListener('mousedown', e => {
      e.preventDefault();
      snapshotSelection();
      const isOpen = !menu.hidden;
      closeMenus();
      menu.hidden = isOpen;
    });

    customBtn.addEventListener('mousedown', e => {
      e.preventDefault();
      snapshotSelection();
      input.click();
    });

    input.addEventListener('change', () => {
      snapshotSelection();
      applyColor(input.value);
    });

    floatingMenus.push(menu);

    wrap.appendChild(main);
    wrap.appendChild(caret);
    wrap.appendChild(menu);
    wrap.appendChild(input);
    return wrap;
  }

  function tablePickerBtn() {
    const wrap = document.createElement('span');
    wrap.className = 'lexical-toolbar__table-picker';

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'lexical-toolbar__btn';
    trigger.title = 'Insert table';
    trigger.innerHTML = ICONS.table;

    const menu = document.createElement('div');
    menu.className = 'lexical-toolbar__menu lexical-toolbar__menu--table';
    menu.hidden = true;

    const label = document.createElement('div');
    label.className = 'lexical-toolbar__menu-title';
    label.textContent = 'Insert table';
    menu.appendChild(label);

    const grid = document.createElement('div');
    grid.className = 'lexical-table-grid';
    menu.appendChild(grid);

    const maxRows = 8;
    const maxCols = 10;
    const cells = [];

    function paint(rows, cols) {
      for (const cell of cells) {
        const r = Number(cell.dataset.r);
        const c = Number(cell.dataset.c);
        cell.classList.toggle('is-active', r <= rows && c <= cols);
      }
      if (rows > 0 && cols > 0) {
        label.textContent = `${rows} × ${cols}`;
      } else {
        label.textContent = 'Insert table';
      }
    }

    for (let r = 1; r <= maxRows; r++) {
      for (let c = 1; c <= maxCols; c++) {
        const cell = document.createElement('button');
        cell.type = 'button';
        cell.className = 'lexical-table-grid__cell';
        cell.dataset.r = String(r);
        cell.dataset.c = String(c);
        cell.addEventListener('mouseover', () => paint(r, c));
        cell.addEventListener('mousedown', e => {
          e.preventDefault();
          snapshotSelection();
          restoreSelection();
          insertTable(editor, r, c);
          closeMenus();
          paint(0, 0);
        });
        cells.push(cell);
        grid.appendChild(cell);
      }
    }

    grid.addEventListener('mouseleave', () => paint(0, 0));

    trigger.addEventListener('mousedown', e => {
      e.preventDefault();
      snapshotSelection();
      const isOpen = !menu.hidden;
      closeMenus();
      menu.hidden = isOpen;
      if (!isOpen) paint(0, 0);
    });

    floatingMenus.push(menu);

    wrap.appendChild(trigger);
    wrap.appendChild(menu);
    return wrap;
  }

  function patchStyle(patch) {
    withSelection(s => {
      $patchStyleText(s, patch);
    });
  }

  function setBlock(createFn) {
    editor.update(() => {
      const s = $getSelection();
      if ($isRangeSelection(s)) $setBlocksType(s, createFn);
    });
  }

  // ── Group 1: Text Formatting ────────────────────────────────────────────
  bar.appendChild(btn('bold', 'Bold (Ctrl+B)', ICONS.bold, () => editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'bold')));
  bar.appendChild(btn('italic', 'Italic (Ctrl+I)', ICONS.italic, () => editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'italic')));
  bar.appendChild(btn('underline', 'Underline (Ctrl+U)', ICONS.underline, () => editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'underline')));
  bar.appendChild(btn('strikethrough', 'Strikethrough', ICONS.strikethrough, () => editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'strikethrough')));
  bar.appendChild(sep());

  // ── Group 2: Paragraph ─────────────────────────────────────────────────
  bar.appendChild(btn('h1', 'Heading 1', ICONS.h1, () => setBlock(() => $createHeadingNode('h1'))));
  bar.appendChild(btn('h2', 'Heading 2', ICONS.h2, () => setBlock(() => $createHeadingNode('h2'))));
  bar.appendChild(btn('h3', 'Heading 3', ICONS.h3, () => setBlock(() => $createHeadingNode('h3'))));
  bar.appendChild(btn('paragraph', 'Paragraph', ICONS.paragraph, () => setBlock(() => $createParagraphNode())));
  bar.appendChild(btn('quote', 'Blockquote', ICONS.quote, () => setBlock(() => $createQuoteNode())));
  bar.appendChild(sep());
  bar.appendChild(btn(null, 'Bullet list', ICONS.bulletList, () => editor.dispatchCommand(INSERT_UNORDERED_LIST_COMMAND, undefined)));
  bar.appendChild(btn(null, 'Numbered list', ICONS.orderedList, () => editor.dispatchCommand(INSERT_ORDERED_LIST_COMMAND, undefined)));
  bar.appendChild(sep());
  bar.appendChild(btn('align-left', 'Align left', ICONS.alignLeft, () => editor.dispatchCommand(FORMAT_ELEMENT_COMMAND, 'left')));
  bar.appendChild(btn('align-center', 'Align center', ICONS.alignCenter, () => editor.dispatchCommand(FORMAT_ELEMENT_COMMAND, 'center')));
  bar.appendChild(btn('align-right', 'Align right', ICONS.alignRight, () => editor.dispatchCommand(FORMAT_ELEMENT_COMMAND, 'right')));
  bar.appendChild(btn('align-justify', 'Justify', ICONS.alignJustify, () => editor.dispatchCommand(FORMAT_ELEMENT_COMMAND, 'justify')));
  bar.appendChild(sep());

  // ── Group 3: Insert ────────────────────────────────────────────────────
  bar.appendChild(tablePickerBtn());

  const imagePicker = document.createElement('input');
  imagePicker.type = 'file';
  imagePicker.accept = 'image/*';
  imagePicker.className = 'lexical-toolbar__file-input';
  imagePicker.tabIndex = -1;

  imagePicker.addEventListener('change', () => {
    const file = imagePicker.files && imagePicker.files[0];
    imagePicker.value = '';
    if (!file) return;
    if (!file.type || !file.type.startsWith('image/')) {
      window.alert('Please choose an image file.');
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const src = typeof reader.result === 'string' ? reader.result : '';
      if (!src) return;
      const alt = (file.name || '').replace(/\.[^.]+$/, '');
      restoreSelection();
      insertImage(editor, src, alt || 'Image');
      const root = editor.getRootElement();
      if (root) root.focus();
    };
    reader.readAsDataURL(file);
  });

  bar.appendChild(btn(null, 'Insert image', ICONS.image, () => {
    imagePicker.click();
  }));
  bar.appendChild(imagePicker);
  bar.appendChild(sep());

  // ── Group 4: Editing ───────────────────────────────────────────────────
  bar.appendChild(btn(null, 'Undo (Ctrl+Z)', ICONS.undo, () => editor.dispatchCommand(UNDO_COMMAND, undefined)));
  bar.appendChild(btn(null, 'Redo (Ctrl+Shift+Z)', ICONS.redo, () => editor.dispatchCommand(REDO_COMMAND, undefined)));
  bar.appendChild(sep());

  // ── Group 5: Miscellaneous ─────────────────────────────────────────────
  bar.appendChild(dropdown('Font family', [
    ['', 'Font'],
    ['inherit', 'Default'],
    ['Arial, sans-serif', 'Arial'],
    ['Georgia, serif', 'Georgia'],
    ['Verdana, sans-serif', 'Verdana'],
    ['Courier New, monospace', 'Courier New'],
    ['monospace', 'Monospace'],
    ['cursive', 'Cursive'],
  ], val => patchStyle({ 'font-family': val || null })));

  bar.appendChild(dropdown('Font size', [
    ['', 'Size'],
    ['11px', '11'],
    ['13px', '13'],
    ['14px', '14'],
    ['16px', '16'],
    ['18px', '18'],
    ['20px', '20'],
    ['24px', '24'],
    ['28px', '28'],
    ['32px', '32'],
    ['48px', '48'],
  ], val => patchStyle({ 'font-size': val || null })));
  bar.appendChild(sep());

  bar.appendChild(colorSplitBtn(
    'Text colour',
    ICONS.textColor('#e8e8e8'),
    '#e8e8e8',
    color => patchStyle({ color }),
  ));
  bar.appendChild(colorSplitBtn(
    'Highlight colour',
    ICONS.highlight('#ffff00'),
    '#ffff00',
    color => patchStyle({ 'background-color': color }),
  ));
  bar.appendChild(btn(null, 'Clear formatting', ICONS.clear, () => {
    editor.update(() => {
      const s = $getSelection();
      if (!$isRangeSelection(s)) return;
      $patchStyleText(s, {
        color: null,
        'background-color': null,
        'font-size': null,
        'font-family': null,
      });
      $setBlocksType(s, () => $createParagraphNode());
      for (const node of s.getNodes()) {
        if ($isTextNode(node)) node.setFormat(0);
      }
    });
  }));

  return bar;
}

export { buildToolbar };
