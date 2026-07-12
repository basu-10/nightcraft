import {
  createEditor,
  $getRoot,
  $getSelection,
  $isRangeSelection,
  $createTextNode,
  $createParagraphNode,
  $createHeadingNode,
  $setBlocksType,
  FORMAT_TEXT_COMMAND,
  UNDO_COMMAND,
  REDO_COMMAND,
  registerRichText,
  HeadingNode,
  QuoteNode,
  ListNode,
  ListItemNode,
  registerList,
  registerHistory,
  createEmptyHistoryState,
  mergeRegister,
  TableNode,
  TableRowNode,
  TableCellNode,
} from './deps.js';
import { ImageNode } from './image_node.js';
import { buildToolbar } from './toolbar.js';
import { attachContextMenu } from './context_menu.js';

class LexicalNoteEditor {
  constructor(mountId, onChange) {
    this._mountId = mountId;
    this._onChange = onChange;
    this._editor = null;
    this._rootEl = null;
    this._unregister = null;
    this._ignoreChange = false;
    this._pendingContent = null;
  }

  init() {
    const mount = document.getElementById(this._mountId);
    if (!mount) return;

    this._editor = createEditor({
      namespace: 'notestack-lexical',
      nodes: [
        HeadingNode, QuoteNode,
        ListNode, ListItemNode,
        TableNode, TableRowNode, TableCellNode,
        ImageNode,
      ],
      onError: err => console.error('[Lexical]', err),
      theme: {
        text: {
          bold: 'lex-bold',
          italic: 'lex-italic',
          underline: 'lex-underline',
          strikethrough: 'lex-strikethrough',
          code: 'lex-code',
        },
        heading: { h1: 'lex-h1', h2: 'lex-h2', h3: 'lex-h3' },
        quote: 'lex-quote',
        list: {
          ul: 'lex-ul',
          ol: 'lex-ol',
          listitem: 'lex-listitem',
        },
        table: 'lex-table',
        tableRow: 'lex-table-row',
        tableCell: 'lex-table-cell',
        tableCellHeader: 'lex-table-cell-header',
      },
    });

    mount.innerHTML = '';

    const wrapper = document.createElement('div');
    wrapper.className = 'lexical-wrapper';
    wrapper.appendChild(buildToolbar(this._editor));

    this._rootEl = document.createElement('div');
    this._rootEl.className = 'lexical-content-editable';
    this._rootEl.setAttribute('role', 'textbox');
    this._rootEl.setAttribute('aria-multiline', 'true');
    this._rootEl.setAttribute('aria-label', 'Note content');
    this._rootEl.setAttribute('spellcheck', 'true');
    this._rootEl.tabIndex = 0;
    this._rootEl.contentEditable = 'true';

    wrapper.appendChild(this._rootEl);
    mount.appendChild(wrapper);

    this._editor.setRootElement(this._rootEl);

    const historyState = createEmptyHistoryState();
    this._unregister = mergeRegister(
      registerRichText(this._editor),
      registerList(this._editor),
      registerHistory(this._editor, historyState, 300),
    );

    attachContextMenu(this._editor, this._rootEl);
    this._attachPasteListener();
    this._attachKeyboardShortcuts();

    this._editor.registerUpdateListener(({ editorState }) => {
      if (this._ignoreChange) return;
      editorState.read(() => {
        if (this._onChange) this._onChange();
      });
    });

    if (this._pendingContent !== null) {
      this._applyContent(this._pendingContent);
      this._pendingContent = null;
    } else {
      this._editor.update(() => {
        const root = $getRoot();
        if (root.getFirstChild() === null) root.append($createParagraphNode());
      });
    }
  }

  setContent(contentString) {
    if (!this._editor) {
      this._pendingContent = contentString || '';
      return;
    }
    this._applyContent(contentString || '');
  }

  _applyContent(contentString) {
    if (!this._editor) return;
    this._ignoreChange = true;
    try {
      const text = String(contentString || '');
      if (this._isLexicalState(text)) {
        const parsedState = this._editor.parseEditorState(text);
        this._editor.setEditorState(parsedState);
      } else {
        this._setLegacyTextContent(text);
      }
    } catch (err) {
      console.warn('[Lexical] setContent failed, falling back to text import:', err);
      this._setLegacyTextContent(String(contentString || ''));
    } finally {
      setTimeout(() => { this._ignoreChange = false; }, 50);
    }
  }

  _isLexicalState(contentString) {
    const trimmed = contentString.trim();
    if (!trimmed.startsWith('{')) return false;
    try {
      const parsed = JSON.parse(trimmed);
      return !!(parsed && parsed.root && parsed.root.type === 'root');
    } catch {
      return false;
    }
  }

  _setLegacyTextContent(contentString) {
    this._editor.update(() => {
      const root = $getRoot();
      root.clear();

      const normalized = (contentString || '').replace(/\r\n?/g, '\n');
      const lines = normalized ? normalized.split('\n') : [''];
      lines.forEach(line => {
        const paragraph = $createParagraphNode();
        if (line) paragraph.append($createTextNode(line));
        root.append(paragraph);
      });

      if (root.getFirstChild() === null) root.append($createParagraphNode());
    });
  }

  getContent() {
    if (!this._editor) return '';
    return JSON.stringify(this._editor.getEditorState().toJSON());
  }

  _attachPasteListener() {
    if (!this._rootEl || !this._editor) return;
    const self = this;
    this._rootEl.addEventListener('paste', async (e) => {
      const items = e.clipboardData?.items || [];
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          e.preventDefault();
          const blob = item.getAsFile();
          if (!blob) return;
          const reader = new FileReader();
          reader.onload = () => {
            const src = typeof reader.result === 'string' ? reader.result : '';
            if (!src) return;
            const addImageToEditor = async () => {
              const { $createImageNode } = await import('./image_node.js');
              self._editor.update(() => {
                const root = $getRoot();
                const img = $createImageNode(src, 'Pasted image');
                const para = $createParagraphNode();
                root.append(img);
                root.append(para);
              });
            };
            addImageToEditor().catch(err => console.error('[Lexical] Paste image failed:', err));
          };
          reader.readAsDataURL(blob);
          return;
        }
      }
    });
  }

  _attachKeyboardShortcuts() {
    if (!this._rootEl || !this._editor) return;
    const editor = this._editor;

    this._rootEl.addEventListener('keydown', (e) => {
      const ctrl = e.ctrlKey || e.metaKey;
      if (!ctrl) return;

      // Undo / Redo — Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y.
      if (!e.altKey && e.code === 'KeyZ') {
        e.preventDefault();
        editor.dispatchCommand(e.shiftKey ? REDO_COMMAND : UNDO_COMMAND, undefined);
        return;
      }
      if (!e.altKey && !e.shiftKey && e.code === 'KeyY') {
        e.preventDefault();
        editor.dispatchCommand(REDO_COMMAND, undefined);
        return;
      }

      // Inline code — Ctrl+E.
      if (!e.altKey && !e.shiftKey && e.code === 'KeyE') {
        e.preventDefault();
        editor.dispatchCommand(FORMAT_TEXT_COMMAND, 'code');
        return;
      }

      // Headings — Ctrl+Alt+1 / 2 / 3.
      if (
        e.altKey &&
        !e.shiftKey &&
        (e.code === 'Digit1' || e.code === 'Digit2' || e.code === 'Digit3')
      ) {
        e.preventDefault();
        const tag = 'h' + e.code.slice(-1);
        editor.update(() => {
          const s = $getSelection();
          if ($isRangeSelection(s)) $setBlocksType(s, () => $createHeadingNode(tag));
        });
        return;
      }

      // Paste as plain text — Ctrl+Shift+V.
      if (e.shiftKey && !e.altKey && e.code === 'KeyV') {
        e.preventDefault();
        if (!navigator.clipboard || !navigator.clipboard.readText) return;
        navigator.clipboard
          .readText()
          .then((text) => {
            if (!text) return;
            editor.update(() => {
              const s = $getSelection();
              if ($isRangeSelection(s)) s.insertRawText(text);
            });
          })
          .catch((err) => console.warn('[Lexical] Plain-text paste failed:', err));
        return;
      }
    });
  }

  focus() {
    if (this._rootEl) this._rootEl.focus();
    if (this._editor) {
      try { this._editor.focus(); } catch (_) { }
    }
  }

  destroy() {
    if (this._unregister) {
      this._unregister();
      this._unregister = null;
    }
    if (this._editor) {
      this._editor.setRootElement(null);
      this._editor = null;
    }
    const mount = document.getElementById(this._mountId);
    if (mount) mount.innerHTML = '';
    this._rootEl = null;
  }
}

export { LexicalNoteEditor };
