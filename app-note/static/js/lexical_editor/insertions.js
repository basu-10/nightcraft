import {
  $getRoot,
  $getSelection,
  $isRangeSelection,
  $createParagraphNode,
  TableNode,
  TableRowNode,
  TableCellNode,
} from './deps.js';
import { $createImageNode } from './image_node.js';

function makeTable(rows, cols) {
  const table = new TableNode();
  for (let r = 0; r < rows; r++) {
    const row = new TableRowNode();
    for (let c = 0; c < cols; c++) {
      const cell = new TableCellNode(0);
      cell.append($createParagraphNode());
      row.append(cell);
    }
    table.append(row);
  }
  return table;
}

function insertTable(editor, rows, cols) {
  editor.update(() => {
    const sel = $getSelection();
    const table = makeTable(rows, cols);
    const after = $createParagraphNode();

    if ($isRangeSelection(sel)) {
      const anchor = sel.anchor.getNode();
      const topLevel = anchor.getTopLevelElement
        ? anchor.getTopLevelElement()
        : null;
      if (topLevel) {
        topLevel.insertAfter(after);
        topLevel.insertAfter(table);
        return;
      }
    }

    $getRoot().append(table);
    $getRoot().append(after);
  });
}

function insertImage(editor, src, alt) {
  editor.update(() => {
    const sel = $getSelection();
    const img = $createImageNode(src, alt);
    const after = $createParagraphNode();

    if ($isRangeSelection(sel)) {
      const anchor = sel.anchor.getNode();
      const topLevel = anchor.getTopLevelElement
        ? anchor.getTopLevelElement()
        : null;
      if (topLevel) {
        topLevel.insertAfter(after);
        topLevel.insertAfter(img);
        return;
      }
    }

    $getRoot().append(img);
    $getRoot().append(after);
  });
}

export { insertTable, insertImage };
