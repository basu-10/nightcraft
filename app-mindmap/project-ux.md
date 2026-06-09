# Project UX

## Index of UX components to be designed and implemented

- Left sidebar
- Canvas space
- Right inspector panel
- Top bar
- Search and filter UI
- Card UI
- Connector UI
- Tag UI
- Board-level tag management UI
- View/edit mode toggle UI
- Multi-select UI
- Export/import UI
- Persistence and auto-save UX
- Workflow UX (pasting images/URLs, source notes, tag-driven status/confidence metadata)

### Left sidebar

Per canvas data

- Confidence filter
- Type of node filter
- Tag filter, Tag hierarchy setter option
- resultsant list of cards from the above filters.

### Canvas space

This is where the infinite canvas with pan & zoom will be implemented, along with draggable, resizable card nodes and connector arrows/edges between cards that stay attached on move.

- Pan & zoom controls
- Draggable, resizable card nodes
- Connector arrows/edges between cards that stay attached on move
- View/edit mode toggle per card (default readable, double-click/pencil to edit)
- Integration of rich text editor inside each card (bold, italic, underline, inline highlight, links, bullet lists)
- Tag display on cards, with option to edit tags in edit mode
- In edit mode only, the title, content, tags of a node card can be changed.

### Node cards

These are the main content elements on the canvas, which can be of different types (text, image, table) and have different fields and behaviors.

#### Common features of all node card types

- Can be created by clicking a "New Card" button in the UI, which opens a menu to select the card type
- Can be dragged and resized on the canvas
- when deselected (user clicks on the board , not on any card or connector), the card toggles to read only/rendered mode and the editor attachment is removed and right sidebar collapses.

- Can have connector arrows/edges attached to them that stay attached when the card is moved
- connector arrows/edges can be attached to the card and will stay attached when the card is moved
- connector can be created and attached to another node when user hovers over a connector point on the card edge and clicks in that connector point and drags to another card.
- connector arrows/edges can have editable labels (e.g. to specify relationship type) that becomes editable with double click on the label or arrow line.

- has fields: title, content(different for each card type), tags
- Have a view mode and an edit mode, which can be toggled by double-clicking the card or clicking an edit pencil icon
- in view mode, shows title and rendered content, with tags displayed as colored labels at the bottom
- in edit mode, title and content become editable (with rich text editor), and tags can be added/removed/edited.

#### Node Card Types

##### Text Card

Made with rich text editor, with support for bold, italic, underline, inline highlight, links, bullet lists.

- the content field of a text card is a rich text editor instance
- the content field of a text card is rendered as formatted text in view mode, and becomes an editable rich text editor in edit mode
- the content field of a text card supports basic formatting options like bold, italic, underline, inline highlight, links, bullet lists, etc.

##### Image Card

Simply Renders an image from a URL or local upload.

- the content field of an image card has options for a URL or local file path to an image or to get from clipboard paste
- the content field of an image card is rendered as an image in view mode, and becomes an input field for the URL or file upload in edit mode
- the content field of an image card supports pasting an image from the clipboard, which will automatically upload the image and set the content to the uploaded image URL
- the content field of an image card supports drag-and-drop of an image file from the user's computer, which will automatically upload the image and set the content to the uploaded image URL

##### Table Card

Simulates a mini excel kind of table, with rows and columns that can be added/removed, and cells that can be edited with rich text.

- the content field of a table card is a 2D array representing rows and columns, where each cell can contain rich text
- the content field of a table card is rendered as an HTML table in view mode, and becomes an editable table in edit mode, where users can add/remove rows and columns, and edit each cell with a rich text editor

### Right inspector panel

Per Item(node card, arrow/labels) data. When an item is selected, the inspector panel shows the metadata and properties of that item, and allows editing of those properties.
in deselected(no node card or connector arrow/label is selected) mode, the inspector panel collapses. If opened, it shows the metadata and properties of the board itself, such as board title, description, tags, etc.

### Top bar

- Board title (editable) [middle of the top bar]
- File menu with options for:
  - New Card option - options for different card types (text, image, table). click on the type to insert the card at the centre of the users curent view, not a fixed position.
  - export/import board JSON
  - board sub options like new, clear board etc.
- Edit menu with options for:
  - Undo/redo
  - zoom level presets, fit to screen(zoom all function), actual size,etc
  - multi-select mode toggle, select all cards
- About/help menu with links to documentation, contact, etc.
- Search bar for real time searching cards by title/content/tags [right aligned]

#### Search and filter UI

Searches title + content of cards in real time as user types, with results shown in a dropdown below the search bar. Clicking a search result focuses that card on the canvas.

### Card UI

Card UI is built as absolutely-positioned HTML elements inside the infinite canvas. Each card renders a DOM element (not canvas-painted content), ensuring rich text reflow, selectability, and copy/paste work natively.

#### Visual structure (top to bottom)

- **Card header**
- **Card body**
- **Card format bar** (edit mode only)
- **Card meta view area** (view mode): Shows attached image preview, source URL link, and tag labels as small colored pills at the bottom of the card
- **Card meta edit area** (edit mode): Shows editable input fields for tags (comma-separated), source URL, and image URL (image cards only), maximize view button, and any future metadata fields
- **Resize handle**
- **Connection ports**: Four circular anchors at top, bottom, left, right edges. Hidden by default, appear on hover. Click + drag from a port to create a connector edge to another card.

#### Card types visual differences

- **Text card**: Header left-border uses semantic color, body renders sanitized TipTap HTML styles
- **Image card**: Same header border, body shows preview image (max 120px height, object-fit cover, rounded) plus image URL field in edit mode
- **Table card**: Header left-border uses semantic color, body renders an HTML table in view mode or a full table editor with add/remove row/column controls, import Excel/CSV button, export XLSX button in edit mode

#### Interaction states

- **Default**: Visible with subtle border, hover elevates shadow and brightens border, z-index bumps to 10
- **Selected**: Colored border glow matching semantic color (derived from first tag or card type fallback) via CSS `--semantic-color` variable, box-shadow with color-mix overlay
- **Editing**: `.editing` class toggles on, switches body view/editor visibility, shows format bar and meta-edit fields, enables title editing
- **Maximized**: Fixed-position overlay (top:56px, left:256px, right:16px, bottom:16px) with deep shadow, only available in edit mode, toggle button switches between maximize and restore icon
- **Multi-selected**: All selected cards show the selected border glow, group-draggable via header mousedown

#### Card sizing and positioning

- Cards are positioned via `left`/`top` CSS (reflecting `card.x`/`card.y` in board data)
- Sized via `width`/`height` CSS (reflecting `card.width`/`card.height`), with min constraints enforced
- Resize updates are immediate during drag, persisted on mouseup via autoSave

#### Card lifecycle

- **Create**: `addCard()` pushes to `board.cards`, calls `createCardElement()`, appends to `#canvas-content`, auto-opens in edit mode (configurable)
- **Duplicate**: Copies all properties, adds "(copy)" suffix, offsets position by 30px, creates new card element
- **Delete**: Calls `unmountEditor()` to destroy TipTap instance, removes from `board.cards`, filters edges referencing this card, removes DOM element, clears from selection
- **View update**: `updateCardView()` re-renders body content based on card type, updates semantic badge, refreshes filter options and card list

#### Context menu (right-click)

Right-clicking a card opens a floating context menu with options:

- **Single card (view mode)**: Delete Card, Duplicate, Select All Cards, Multi-Select Mode
- **Single card (edit mode)**: Cut, Copy, Paste (operate on selected text within the TipTap editor)
- **Multiple cards selected**: Delete All Selected (with count), Select All Cards, Multi-Select Mode

### Connector UI

Connectors (edges) are rendered as SVG `<path>` elements with cubic Bezier curves inside an SVG overlay (`#edge-svg`) positioned at z-index 1 above the canvas background but below cards (z-index 2).

#### Structure

- Edge lines are in an `<svg>` with `pointer-events: none`, positioned absolutely over the canvas
- A `<defs>` block defines an arrowhead marker (`#arrowhead`) applied via `marker-end` attribute
- Each edge consists of two overlapping paths: a visible `.edge-line` (2px stroke, 14px invisible `.edge-hit` for click target)
- Edge labels are SVG `<text>` elements positioned at the midpoint of the curve

#### Visual appearance

- **Default**: Muted stroke (`#4a4a6a`), 2px width, rounded joins
- **Selected**: Purple stroke (`#6c63ff`), 3px width, drop-shadow glow
- **Ghost line** (during creation): Dashed stroke, shown in `#ghost-svg` overlay at z-index 6 while user drags from a port

#### Creating a connector

1. User hovers over a card edge — four circular port dots appear (top, bottom, left, right)
2. Ports scale up and change color on hover (purple glow effect)
3. User clicks a port and drags toward another card — a dashed ghost path follows the cursor
4. During the drag, the nearest port on the card under the cursor is highlighted green (`.active-target`)
5. On mouseup over a different card's port or body, a connector is created:
   - An `edge` object is pushed to `board.edges` with `from`, `to`, `fromPort`, `toPort`, and an optional label (user is prompted via `prompt()`)
   - The edge is rendered immediately
6. If mouseup is not over a card, the ghost path disappears and no edge is created

#### Edge labels

- Displayed as SVG text at the curve midpoint, offset slightly above
- Click to select the edge; double-click opens a `prompt()` dialog to edit the label
- Editable in the right inspector panel via the "Label" and "Type" fields when edge is selected

#### Edge hit detection

- A transparent thick stroke (14px width) overlays each visible edge line for reliable click targeting
- Clicking the hit path calls `selectEdge(edge.id)`, which clears card selection and shows edge data in the inspector

### Tag UI

Tags provide the semantic layer of the board. They are board-level definitions (not per-card local strings) that can be organized hierarchically and carry metadata properties.

#### Tag definition model

```js
{
  id: "tag_abc123",
  name: "source",
  parentId: null | "tag_xyz",
  color: "#4f46e5",  // randomly generated if not specified
  group: "classification",
  icon: "",           // optional
  properties: [       // optional property schema
    { key: "confidence", type: "enum", options: ["low", "medium", "high"] },
    { key: "status", type: "enum", options: ["draft", "review", "verified"] }
  ]
}
```

#### Tag display on cards

- Tags appear as small colored pills (`.card-tag`) in the card meta view area at the bottom
- The first tag on a card becomes the **primary tag** — its color drives the card's `--semantic-color` CSS variable, affecting the header left-border, selection glow, and semantic badge color
- A semantic badge in the card header displays the full hierarchical path of the primary tag (e.g. "source › interview › transcript")
- Tag pills display the full path (using `getTagPath()`) on hover via title attribute

#### Tag assignment

Tags are assigned to cards in three ways:

1. **Inline edit mode**: Comma-separated tag names in the meta-edit input field. Typing a new tag name auto-creates the tag definition via `ensureTagDefinition()`.
2. **Right inspector panel**: Tags field in inspector content, comma-separated, with the same auto-creation behavior.
3. **Workflow pasting**: Pasting a URL auto-assigns the "source" tag to the created card.

#### Tag hierarchy

Tags can be arranged in a parent-child tree structure:

- `parentId` on a tag definition links it to its parent
- `getTagPath(tagId)` returns the breadcrumb string (e.g. "source › interview › transcript")
- `getDescendantTagIds(rootTagId)` collects all descendants for filtering
- `ensureTagPath("source/interview/transcript")` auto-creates the full hierarchy if needed

#### Tag filtering in sidebar

- **Tag tree filter** (`#filter-tag-id`): Dropdown showing all root tags with indented children. Selecting a tag filters cards that have that tag or any descendant.
- **Tag text filter** (`#filter-tag`): Free-text input that matches against any tag path on the card.
- **Quick view toggle** (`#quick-view-toggle`): Preset filters like "High Confidence" that check `card.tagProperties` for confidence values.

### Board-level tag management UI

Tag management is done via a modal dialog (`.tag-hierarchy-modal`) triggered by the "⋮" button next to the tag filter dropdown.

#### Modal layout

- **Header**: "Tag Hierarchy" title and close (✕) button
- **Hint text**: Instructions — "Drop a tag onto another to nest it as a child. Use ↑ root to remove a parent."
- **Root drop zone**: Dashed border area labeled "Drop here to make a root tag ↓". Dragging a tag here clears its `parentId`.
- **Tag list**: Scrollable list of all tags rendered as draggable pills with depth-based left margin indentation
- **Footer**: "Done" button that closes the modal, refreshes tag filter options, re-applies semantic colors to all card views, and saves

#### Tag pill structure

Each pill in the hierarchy list contains:

- **Drag handle** (⠿): Grabbable area to initiate drag
- **Color dot**: Small circle showing the tag's assigned color
- **Tag name**: The display name
- **↑ root button** (shown only for child tags): Click to remove parent and make this a root-level tag

#### Drag and drop behavior

- **Drag start**: Sets `_draggedTagId`, adds `.dragging` class (opacity reduced)
- **Drag over**: Checks for circular nesting (prevents dropping a tag onto its own descendant). Adds `.drag-over` highlight class.
- **Drop**: Reparents the dragged tag by setting its `parentId` to the target tag's ID
- **Drop on root zone**: Clears `parentId` to make the tag a root-level tag
- **Drag end**: Clears all drag state and removes highlight classes
- Circular nesting prevention uses `getDescendantTagIds(draggedTagId)` to check if the target is in the dragged tag's descendant tree

#### Tag property schema (future/partial)

The tag definition model supports a `properties` array with typed schemas (enum, string, number, date). This enables per-card tag property values stored in `card.tagProperties[tagId]`. The current board data model and filter logic already reference this — for example, the "High Confidence" quick view filter checks `card.tagProperties[tagId].confidence === "high"`. A dedicated property editor UI per tag definition is planned but not yet implemented in the MVP.

### View/edit mode toggle UI

Each card has a dual-mode system that switches between a clean read-only view and a full editing interface.

#### Default state

Cards load in **view mode** by default. The card displays:

- Title (readonly input)
- Rendered body content (sanitized HTML with ProseMirror output)
- Meta view area (image preview, source link, tag pills)
- Edit toggle button (pencil icon)

#### Entering edit mode

Three triggers:

1. **Double-click** on the card body view area
2. **Click** the pencil icon (`.card-toggle-btn`) in the card header
3. **Programmatic**: `setEditMode(cardId)` is called after creating a new card

What happens:

- Any other card currently in edit mode is saved and switched to view mode first
- Pending connection state is cancelled
- `board.editingCardId` is set to the card's ID
- The card element gets `.editing` class
- `.card-body-view` is hidden, `.card-body-editor` is shown
- A new TipTap editor instance is created with StarterKit, Underline, Link, Highlight, and Table extensions
- The format bar (B, I, U, H, Link, • List buttons) becomes visible
- The meta-edit area shows editable inputs for tags, source URL, and image URL
- Title input becomes editable (`readonly` removed)
- Maximize button appears
- Editor is focused immediately so the user can start typing

#### Exiting edit mode (saving)

Three triggers:

1. **Click** the pencil icon again
2. **Click** on another card to switch editing context
3. **Click** on blank canvas (deselect all) — but only if the card is being edited
4. **Press Escape** on the keyboard — saves the current editor and exits edit mode

What happens:

- `setViewMode(cardId)` is called
- Editor content is flushed to `card.body` via `editor.getHTML()`
- The TipTap instance is destroyed (`editor.destroy()`) and removed from `board.editors` map
- `board.editingCardId` is set to null
- `.editing` and `.maximized` classes are removed
- `.card-body-view` is shown again with updated content (freshly sanitized HTML + meta view)
- `.card-body-editor` is hidden
- Title is set back to `readonly`
- Format bar and meta-edit are cleared
- Card list and inspector are refreshed
- Auto-save is triggered

#### Maximize toggle

- Only available when card is in edit mode
- Click maximize button (⤢ icon) toggles `.maximized` class
- Maximized card becomes a fixed-position overlay panel
- Button icon changes to ↤ (restore) when maximized
- Only one card can be maximized at a time

### Multi-select UI

Multi-selection enables batch operations on cards.

#### Selection modes

- **Ctrl/Cmd+click** on a card header: Toggles that card in/out of the selection set without clearing existing selection
- **Shift+click** on a card header: Range-selects all cards between the last-selected card and the clicked card (based on `board.cards` array order)
- **Right-click → Multi-Select Mode**: Adds the clicked card to the existing selection set
- **Right-click → Select All Cards**: Selects every card on the board

#### Behavior during multi-selection

- All selected cards show the `.selected` visual state (colored border glow)
- Dragging the header of any selected card moves **all** selected cards together
  - `board.dragCardIds` stores the list of selected card IDs
  - `board.dragOrigPositions` captures initial positions of all selected cards
  - All cards update position simultaneously during drag
- Context menu shows "Delete All Selected (N)" when multiple cards are selected
- Right inspector shows "N cards selected" message instead of single card details
- Edges connected to selected cards remain rendered

#### Implementation details

- `board.selectedCardIds` is a `Set<string>` storing IDs of all selected cards
- `selectCard(cardId, add, shift)` manages selection logic:
  - `add=false, shift=false`: Clear all, select just this card
  - `add=true, shift=false`: Toggle this card in/out
  - `add=false, shift=true`: Range select
- `board.lastSelectedCardId` tracks the anchor for range selection
- `deselectAll()` clears selection, selected edge, and updates all dependent views
- Selection updates (`updateSelection()`) toggles `.selected` class on card elements and edge elements

### Export/import UI

Export and import provide board-level serialization in JSON format, plus Excel/CSV import/export for table cards.

#### Board export

- Triggered by the **Export** button (`#btn-export`) in the toolbar
- `exportBoard()` serializes the full board state via `getState()`:
  - Cards, edges, tagDefinitions, savedViews, activeQuickView, panX, panY, zoom
- Creates a JSON Blob and triggers a browser download as `research-workspace.json`
- File is formatted with 2-space indentation for readability

#### Board import

- Triggered by the **Import** button (`#btn-import`) which clicks a hidden `<input type="file" accept=".json">`
- `importBoard(file)` reads the file as text, parses JSON, and calls `loadState()`:
  - Destroys all active TipTap editor instances
  - Clears editor map and editing state
  - Loads cards, edges, tagDefinitions, savedViews, and viewport state
  - Calls `normalizeBoardData()` to migrate legacy formats
  - Refreshes tag filter options, re-renders all cards, applies transform, and auto-saves
- Invalid JSON shows an alert with the error message

#### New canvas

- **New Canvas** button (`#btn-new-canvas`) prompts to export first if the board has content
- Then loads an empty board state and re-renders everything from scratch

#### Table card Excel/CSV import

- **Import Excel** button (`#btn-import-excel`): Requires a selected table card, then opens a hidden file input for `.xlsx,.xls,.ods,.csv`
- `importTableXLSX(file, card)` uses SheetJS (xlsx library) to parse the first sheet:
  - First row becomes column headers
  - Subsequent rows become data rows
  - Updates `card.tableData` with `{ columns, rows }`
  - If the card is in edit mode, re-renders the table editor; otherwise re-renders view
- **Edit mode import button**: Same functionality, available as "Import Excel/CSV" button inside the table card's edit mode

#### Table card XLSX export

- **Export button in edit mode**: Calls backend API `/api/export/table/{cardId}` with fallback to client-side export
- Client-side fallback `exportTableXLSX(card)` uses SheetJS:
  - Converts `tableData.columns` and `tableData.rows` to a worksheet array of arrays
  - Creates a workbook and triggers download as `{cardTitle}.xlsx`
- Import Excel toolbar button is separate from the in-card table editor import button

### Persistence and auto-save UX

The board state is persisted automatically using a dual strategy: localStorage (client-side) and API POST (server-side).

#### Storage key

All state is stored under the localStorage key `"research_workspace_board"`.

#### State snapshotted

`getState()` captures a JSON-serializable subset of board state:

- `cards[]`: All card data (positions, content, tags, metadata)
- `edges[]`: All connector data
- `tagDefinitions[]`: All tag definitions (including hierarchy and property schemas)
- `savedViews[]`: Named filter views
- `activeQuickView`: Current quick view selection
- `panX`, `panY`, `zoom`: Viewport state (restored on reload)

Transient UI state is NOT persisted: active editor instances, selection, drag state, connection-in-progress, scroll positions.

#### Auto-save trigger

`autoSave()` is called after every user action that modifies board data:

- Card create, delete, duplicate, move, resize
- Edge create, label/type change
- Title, body content, tags, source URL, image URL changes
- Viewport pan/zoom changes
- Tag definition changes (add, reparent)

#### Debouncing

- A 500ms debounce timer (`saveTimer`) prevents rapid successive saves
- Each call to `autoSave()` clears the previous timer and sets a new one
- On timer expiry:
  1. Serializes state to JSON
  2. Writes to `localStorage.setItem()`
  3. Fires a POST `/api/board` with the JSON body (fire-and-forget, errors caught silently)

#### Load on startup

`init()` runs the load sequence:

1. First attempts `loadFromServer()` — GET `/api/board`. If the response has cards, loads from server.
2. Falls back to `loadFromStorage()` — reads from localStorage. If data exists, loads from localStorage.
3. If neither has data, creates three default demo cards (Evidence Map Brief, Source Intake, Open Questions) with sample tags and content.

`loadState(data)` handles the full state restoration:

- Destroys all active editors
- Clears all transient state
- Loads cards, edges, tag definitions, saved views, viewport
- Runs `normalizeBoardData()` to migrate any legacy formats and ensure data integrity

#### New canvas flow

`startNewCanvas()`:

1. Checks if current board has any content
2. If yes, prompts "Export the current board before starting a new canvas?" — user can cancel or export first
3. Loads an empty board state
4. Resets all filters and search
5. Re-renders everything
6. Auto-saves the empty state (effectively clearing persisted data)

#### Error handling

- API failures during auto-save are silently caught and logged to console (non-blocking for the user)
- localStorage failures are silently caught during load
- Corrupted data shows an alert during import but is silently ignored during auto-load (falls through to default demo cards)

### Workflow UX (pasting images/URLs, source notes, tag-driven status/confidence metadata)

The workspace supports a research capture workflow through clipboard paste handling and tag-driven metadata.

#### Paste behavior

The global `paste` event listener (`document.addEventListener("paste", ...)`) checks clipboard contents:

##### Pasting an image

- Detected via `clipboardData.items` with `type.startsWith("image/")`
- If a card is selected: Sets the image URL on that card (reads as data URL via FileReader)
- If no card is selected: Creates a new **Image Card** with the pasted image as content, titled "Pasted Image"
- The image is read as a data URL and stored directly in `card.imageUrl`

##### Pasting a URL

- Detected via regex `^https?://` on the plain text clipboard content
- If a card is selected: Sets the text as the card's `sourceUrl` field
- If no card is selected: Creates a new **Text Card** with:
  - Title "Source Link"
  - Body containing a clickable anchor tag with the URL
  - Source URL set on the card
  - "source" tag auto-assigned (tag definition is auto-created if it doesn't exist via `ensureTagDefinition("source")`)

##### Pasting plain text (non-URL)

- Falls through to default browser behavior (the paste event does not prevent default for plain text)

#### Source notes workflow

Cards support a `sourceUrl` field that captures the original source of information:

- Stored as a string on the card object
- Rendered as a clickable link (`.card-source-link`) in the meta view area
- Editable in edit mode via the meta-edit "Source URL" input field
- Editable in the right inspector panel when the card is selected
- Auto-populated when pasting a URL onto the canvas (creates a new card with the URL as source)

#### Tag-driven status/confidence metadata

Tags can define a property schema that enables structured metadata on cards:

##### Property schema model

```js
{
  key: "confidence",
  type: "enum",
  options: ["low", "medium", "high"]
}
```

##### Per-card values

Card stores tag property values in `card.tagProperties`:

```js
{
  "tag_abc123": {
    "confidence": "high",
    "status": "verified"
  }
}
```

##### Quick view filters

The sidebar quick view toggle currently supports "High Confidence" as a preset:

- Iterates all cards and checks if any tag property has `confidence === "high"`
- Cards that match are shown; others are hidden
- This demonstrates the pattern for tag-driven saved views

##### Saved views (data model)

The board supports `savedViews[]` in its data model — each view stores a name and a set of filters (tag IDs, tag property value matchers). A dedicated saved view management UI (save, load, delete named views) is planned for post-MVP.

#### Example research workflow sequence

1. User finds a source article → copies URL → pastes onto canvas → a Source Link card is created with the URL and "source" tag
2. User reads the article and takes notes → adds a Text card with analysis → tags it as "source › analysis"
3. User takes a screenshot of a key chart → pastes onto canvas → an Image card is created
4. User connects the note card to the source card with an arrow labeled "derived from"
5. User assigns a confidence level via tag properties: "high" for directly verified information
6. User applies the "High Confidence" quick view to focus only on verified claims
7. Board can be exported as JSON for sharing or backup
