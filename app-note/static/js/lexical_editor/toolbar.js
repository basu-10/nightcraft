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

function buildToolbar(editor) {
  const bar = document.createElement('div');
  bar.className = 'lexical-toolbar';
  bar.setAttribute('aria-label', 'Formatting toolbar');

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

  function btn(title, html, action) {
    const b = document.createElement('button');
    b.type = 'button';
    b.title = title;
    b.className = 'lexical-toolbar__btn';
    b.innerHTML = html;
    b.addEventListener('mousedown', e => {
      e.preventDefault();
      snapshotSelection();
      action();
    });
    return b;
  }

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

  function colorSplitBtn(title, labelHtml, defaultColor, onApply) {
    const wrap = document.createElement('span');
    wrap.className = 'lexical-toolbar__split-color';
    wrap.title = title;

    const main = document.createElement('button');
    main.type = 'button';
    main.className = 'lexical-toolbar__btn lexical-toolbar__split-main';
    main.innerHTML = labelHtml;

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
      '#111111', '#2f2f2f', '#666666', '#999999', '#e8e8e8',
      '#be123c', '#dc2626', '#ea580c', '#ca8a04', '#65a30d',
      '#16a34a', '#0891b2', '#2563eb', '#4f46e5', '#7c3aed',
      '#ffff00', '#fde047', '#facc15', '#f59e0b', '#fb7185',
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
    trigger.textContent = '⊞';

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

  bar.appendChild(btn('Bold (Ctrl+B)', '<b>B</b>', () => editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'bold')));
  bar.appendChild(btn('Italic (Ctrl+I)', '<i>I</i>', () => editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'italic')));
  bar.appendChild(btn('Underline (Ctrl+U)', '<u>U</u>', () => editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'underline')));
  bar.appendChild(btn('Strikethrough', '<s>S</s>', () => editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'strikethrough')));
  bar.appendChild(sep());

  bar.appendChild(btn('Heading 1', 'H1', () => setBlock(() => $createHeadingNode('h1'))));
  bar.appendChild(btn('Heading 2', 'H2', () => setBlock(() => $createHeadingNode('h2'))));
  bar.appendChild(btn('Heading 3', 'H3', () => setBlock(() => $createHeadingNode('h3'))));
  bar.appendChild(btn('Paragraph', '¶', () => setBlock(() => $createParagraphNode())));
  bar.appendChild(btn('Blockquote', '❝', () => setBlock(() => $createQuoteNode())));
  bar.appendChild(sep());

  bar.appendChild(btn('Bullet list', '• —', () => editor.dispatchCommand(INSERT_UNORDERED_LIST_COMMAND, undefined)));
  bar.appendChild(btn('Numbered list', '1. —', () => editor.dispatchCommand(INSERT_ORDERED_LIST_COMMAND, undefined)));
  bar.appendChild(sep());

  bar.appendChild(btn('Align left', '⬅', () => editor.dispatchCommand(FORMAT_ELEMENT_COMMAND, 'left')));
  bar.appendChild(btn('Align center', '↔', () => editor.dispatchCommand(FORMAT_ELEMENT_COMMAND, 'center')));
  bar.appendChild(btn('Align right', '➡', () => editor.dispatchCommand(FORMAT_ELEMENT_COMMAND, 'right')));
  bar.appendChild(btn('Justify', '☰', () => editor.dispatchCommand(FORMAT_ELEMENT_COMMAND, 'justify')));
  bar.appendChild(sep());

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
    '<span class="lex-color-icon">A</span>',
    '#e8e8e8',
    color => patchStyle({ color }),
  ));
  bar.appendChild(colorSplitBtn(
    'Highlight colour',
    '<span class="lex-hl-icon">H</span>',
    '#ffff00',
    color => patchStyle({ 'background-color': color }),
  ));
  bar.appendChild(sep());

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

  bar.appendChild(btn('Insert image', '🖼', () => {
    imagePicker.click();
  }));
  bar.appendChild(imagePicker);
  bar.appendChild(sep());

  bar.appendChild(btn('Clear formatting', '✕ fmt', () => {
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
  bar.appendChild(sep());

  bar.appendChild(btn('Undo (Ctrl+Z)', '↩', () => editor.dispatchCommand(UNDO_COMMAND, undefined)));
  bar.appendChild(btn('Redo (Ctrl+Shift+Z)', '↪', () => editor.dispatchCommand(REDO_COMMAND, undefined)));

  return bar;
}

export { buildToolbar };
