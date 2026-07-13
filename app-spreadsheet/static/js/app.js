// State
let currentFile = null;
let currentFileId = null;
let currentSheet = null;
let sheetData = null;
let layoutState = null;
let selectedCell = null;
let saveLayoutTimer = null;
let sheetsList = [];
const SAVE_DEBOUNCE_MS = 400;

// Mount prefix injected by the server (e.g. "/tinyxl") so all asset/API
// references work both when served at the root and under a subpath.
const BASE = (window.BASE_PATH || "").replace(/\/$/, "");

// Multi-cell selection
let isSelecting = false;
let selectionStart = null;
let selectionEnd = null;
let selectedCells = [];
let clipboard = null;
let headerRows = new Set();
let selectedRows = new Set();
let lastClickedRow = null;
let columnTypes = {};
let pendingPaste = null;

// Undo / Redo
let undoStack = [];
let redoStack = [];
const MAX_UNDO = 50;

// Linked sheet (filter) state
let linkedSheets = [];
let isLinkedView = false;
let currentLinkedId = null;
let currentLinkedFilter = null;

// ---- Cell Object Helpers ----
// Cells are { v: string, s?: { bg?: string, text?: string } }
// This unifies value + style so they always travel together.

function cv(cell) {
    // Safe cell value accessor — works for cell objects and plain strings
    if (cell == null) return '';
    return typeof cell === 'object' ? (cell.v ?? '') : String(cell);
}

function cs(cell) {
    // Safe cell style accessor — returns {bg?, text?} or null
    return (cell && typeof cell === 'object' && cell.s) || null;
}

function hydrateData(data, cell_colors) {
    // Merge separate cell_colors dict into cell objects, called once on load.
    // After this, all cells in data are { v: string, s?: { bg?, text? } }.
    if (!data) return;
    for (let r = 0; r < data.length; r++) {
        for (let c = 0; c < data[r].length; c++) {
            const val = data[r][c];
            if (val && typeof val === 'object' && 'v' in val) continue;
            const key = r + ',' + c;
            const clr = cell_colors ? cell_colors[key] : null;
            const cell = { v: val == null ? '' : String(val) };
            if (clr) {
                cell.s = {};
                if (typeof clr === 'string') {
                    cell.s.bg = clr;
                } else {
                    if (clr.bg) cell.s.bg = clr.bg;
                    if (clr.text) cell.s.text = clr.text;
                }
            }
            data[r][c] = cell;
        }
    }
}

function dehydrateData(data) {
    // Convert cell objects back to { plainData: [strings], cell_colors: {...} }
    // Inverse of hydrateData — called before saving to the server.
    if (!data || !data.length) return { plainData: data || [], cell_colors: {} };
    const plainData = [];
    const cell_colors = {};
    for (let r = 0; r < data.length; r++) {
        plainData[r] = [];
        for (let c = 0; c < data[r].length; c++) {
            const cell = data[r][c];
            if (cell && typeof cell === 'object' && 'v' in cell) {
                plainData[r][c] = String(cell.v ?? '');
                if (cell.s && (cell.s.bg || cell.s.text)) {
                    const k = r + ',' + c;
                    if (cell.s.bg && cell.s.text) {
                        cell_colors[k] = { bg: cell.s.bg, text: cell.s.text };
                    } else if (cell.s.bg) {
                        cell_colors[k] = cell.s.bg;
                    } else {
                        cell_colors[k] = { text: cell.s.text };
                    }
                }
            } else {
                plainData[r][c] = String(cell ?? '');
            }
        }
    }
    return { plainData, cell_colors };
}

// ---- End of cell object helpers ----

function newCell(value) {
    return { v: String(value ?? '') };
}

function freshRow(cols) {
    const row = new Array(cols);
    for (let i = 0; i < cols; i++) row[i] = newCell('');
    return row;
}

function setCellValue(data, row, col, value) {
    const existing = data[row][col];
    if (existing && typeof existing === 'object' && 'v' in existing) {
        existing.v = String(value ?? '');
    } else {
        data[row][col] = newCell(value);
    }
}

function deepCloneData(data) {
    return JSON.parse(JSON.stringify(data));
}

function pushUndo() {
    if (!sheetData || !layoutState) return;
    undoStack.push({
        data: deepCloneData(sheetData.data),
        rows: sheetData.rows,
        cols: sheetData.cols,
        row_heights: { ...layoutState.row_heights },
        column_widths: { ...layoutState.column_widths },
        sticky_row: layoutState.sticky_row,
        alternate_row_colors: layoutState.alternate_row_colors,
        header_rows: Array.from(headerRows),
        columnTypes: { ...columnTypes }
    });
    if (undoStack.length > MAX_UNDO) undoStack.shift();
    redoStack = [];
}

function undo() {
    if (!undoStack.length) return;
    redoStack.push({
        data: deepCloneData(sheetData.data),
        rows: sheetData.rows,
        cols: sheetData.cols,
        row_heights: { ...layoutState.row_heights },
        column_widths: { ...layoutState.column_widths },
        sticky_row: layoutState.sticky_row,
        alternate_row_colors: layoutState.alternate_row_colors,
        header_rows: Array.from(headerRows),
        columnTypes: { ...columnTypes }
    });
    const state = undoStack.pop();
    applySnapshot(state);
    renderTable();
    debouncedSaveLayout();
}

function applySnapshot(state) {
    sheetData.data = state.data;
    sheetData.rows = state.rows;
    sheetData.cols = state.cols;
    layoutState.row_heights = state.row_heights;
    layoutState.column_widths = state.column_widths;
    layoutState.sticky_row = state.sticky_row;
    layoutState.alternate_row_colors = state.alternate_row_colors;
    layoutState.cell_colors = {};
    headerRows = new Set(state.header_rows || []);
    layoutState.header_rows = Array.from(headerRows);
    columnTypes = state.columnTypes ? { ...state.columnTypes } : {};
    layoutState.columnTypes = { ...columnTypes };
}

function resetUndoRedo() {
    undoStack = [];
    redoStack = [];
    pushUndo();
}

function debouncedSaveLayout() {
    if (saveLayoutTimer) clearTimeout(saveLayoutTimer);
    saveLayoutTimer = setTimeout(() => {
        saveLayoutTimer = null;
        pendingLayoutSave = saveLayout().finally(() => { pendingLayoutSave = null; });
    }, SAVE_DEBOUNCE_MS);
}

function redo() {
    if (!redoStack.length) return;
    undoStack.push({
        data: deepCloneData(sheetData.data),
        rows: sheetData.rows,
        cols: sheetData.cols,
        row_heights: { ...layoutState.row_heights },
        column_widths: { ...layoutState.column_widths },
        sticky_row: layoutState.sticky_row,
        alternate_row_colors: layoutState.alternate_row_colors,
        header_rows: Array.from(headerRows),
        columnTypes: { ...columnTypes }
    });
    const state = redoStack.pop();
    applySnapshot(state);
    renderTable();
    debouncedSaveLayout();
}

let saveSheetTimer = null;
let pendingSheetSave = null;
let pendingLayoutSave = null;

function debouncedSaveSheet() {
    if (saveSheetTimer) clearTimeout(saveSheetTimer);
    saveSheetTimer = setTimeout(() => {
        saveSheetTimer = null;
        pendingSheetSave = saveSheet().finally(() => { pendingSheetSave = null; });
    }, SAVE_DEBOUNCE_MS);
}

async function flushPendingSaves() {
    // Run saves sequentially to avoid race conditions on the TXL file
    if (saveSheetTimer) {
        clearTimeout(saveSheetTimer);
        saveSheetTimer = null;
        await saveSheet().finally(() => { pendingSheetSave = null; });
    } else if (pendingSheetSave) {
        await pendingSheetSave;
    }
    if (saveLayoutTimer) {
        clearTimeout(saveLayoutTimer);
        saveLayoutTimer = null;
        await saveLayout().finally(() => { pendingLayoutSave = null; });
    } else if (pendingLayoutSave) {
        await pendingLayoutSave;
    }
}

function flushPendingSavesSync() {
    if (saveSheetTimer) {
        clearTimeout(saveSheetTimer);
        saveSheetTimer = null;
        saveSheetUnload();
    }
    if (saveLayoutTimer) {
        clearTimeout(saveLayoutTimer);
        saveLayoutTimer = null;
        saveLayoutUnload();
    }
}

function saveSheetUnload() {
    if (!currentFile || !currentSheet || !sheetData) return;
    try {
        const { plainData } = dehydrateData(sheetData.data);
        fetch(BASE + '/api/sheet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            keepalive: true,
            body: JSON.stringify({
                file_path: currentFile,
                sheet_name: currentSheet,
                data: plainData
            })
        });
    } catch (_) {}
}

function saveLayoutUnload() {
    if (!currentFile || !currentSheet) return;
    try {
        const { cell_colors } = dehydrateData(sheetData.data);
        const stateToSave = { ...layoutState, cell_colors };
        fetch(BASE + '/api/layout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            keepalive: true,
            body: JSON.stringify({
                file_path: currentFile,
                sheet_name: currentSheet,
                state: stateToSave
            })
        });
    } catch (_) {}
}

// Modals
function setupModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.remove('active');
        });
    });
}

function showModal(id) {
    document.getElementById(id).classList.add('active');
}

function hideModal(id) {
    document.getElementById(id).classList.remove('active');
}

// Dropdowns
function setupDropdowns() {
    document.querySelectorAll('.dropdown-toggle').forEach(toggle => {
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const menu = toggle.nextElementSibling;
            const isOpen = menu.classList.contains('active');
            closeAllDropdowns();
            if (!isOpen) menu.classList.add('active');
        });
    });
    document.querySelectorAll('.dropdown-item').forEach(item => {
        item.addEventListener('click', () => closeAllDropdowns());
    });
    document.addEventListener('click', closeAllDropdowns);
}

function closeAllDropdowns() {
    document.querySelectorAll('.dropdown-menu.active').forEach(m => m.classList.remove('active'));
}

function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        file_path: params.get('path'),
        file_id: params.get('id'),
        sheet: params.get('sheet')
    };
}

function navigateToFile(filePath, fileId) {
    const params = new URLSearchParams();
    params.set('path', filePath);
    if (fileId) params.set('id', fileId);
    window.location.href = BASE + '/file?' + params.toString();
}

function navigateToHome() {
    window.location.href = BASE + '/app/';
}

// ==================== HOME PAGE ====================

function initHomePage() {
    setupModals();
    setupUpload();
    setupSettings();
    loadRecentFiles();

    document.getElementById('btn-home').addEventListener('click', () => {
        document.getElementById('home-view').style.display = 'block';
        document.getElementById('settings-view').style.display = 'none';
        document.getElementById('about-view').style.display = 'none';
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('btn-home').classList.add('active');
    });

    document.getElementById('btn-new').addEventListener('click', createNewFile);

    document.getElementById('btn-upload').addEventListener('click', () => showModal('modal-upload'));

    document.getElementById('btn-settings').addEventListener('click', () => {
        document.getElementById('home-view').style.display = 'none';
        document.getElementById('settings-view').style.display = 'block';
        document.getElementById('about-view').style.display = 'none';
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('btn-settings').classList.add('active');
    });

    document.getElementById('btn-about').addEventListener('click', () => {
        document.getElementById('home-view').style.display = 'none';
        document.getElementById('settings-view').style.display = 'none';
        document.getElementById('about-view').style.display = 'block';
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('btn-about').classList.add('active');
    });

    checkSettings();
}

// Upload
function setupUpload() {
    const fileInput = document.getElementById('file-input');
    const btnConfirm = document.getElementById('btn-upload-confirm');
    const btnCancel = document.getElementById('btn-upload-cancel');

    btnConfirm.addEventListener('click', async () => {
        if (!fileInput.files.length) return;
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        try {
            const resp = await fetch(BASE + '/api/upload', { method: 'POST', body: formData });
            const data = await resp.json();
            if (data.error) throw new Error(data.error);
            hideModal('modal-upload');
            navigateToFile(data.file_path, data.file_id);
        } catch (err) {
            alert('Upload failed: ' + err.message);
        }
    });

    btnCancel.addEventListener('click', () => hideModal('modal-upload'));
}

// New File
function createNewFile() {
    const fileName = prompt('Enter file name (e.g., Untitled.xlsx):', 'Untitled.xlsx');
    if (!fileName) return;

    fetch(BASE + '/api/new', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_name: fileName })
    })
    .then(resp => resp.json())
    .then(data => {
        if (data.error) throw new Error(data.error);
        navigateToFile(data.file_path, data.file_id);
    })
    .catch(err => alert('Failed to create file: ' + err.message));
}

// Recent Files
async function loadRecentFiles() {
    try {
        const resp = await fetch(BASE + '/api/recent');
        const data = await resp.json();
        renderRecentFiles(data.files);
    } catch (err) {
        console.error('Failed to load recent files:', err);
    }
}

function renderRecentFiles(files) {
    const container = document.getElementById('recent-files-home');
    if (!files.length) {
        container.innerHTML = '<div class="empty-state">No recent files yet. Use Upload to pick your first workbook.</div>';
        return;
    }

    container.innerHTML = '<div class="section-title">Recent Files</div>';
    files.forEach(f => {
        const card = document.createElement('div');
        card.className = 'recent-card';

        const info = document.createElement('div');
        info.className = 'recent-card-info';

        const name = document.createElement('div');
        name.className = 'recent-card-name';
        name.textContent = f.name;

        const path = document.createElement('div');
        path.className = 'recent-card-path';
        path.textContent = f.path;

        info.appendChild(name);
        info.appendChild(path);

        const status = document.createElement('span');
        status.className = f.exists ? 'state-ready' : 'state-missing';
        status.textContent = f.exists ? 'Ready' : 'Missing';

        const actions = document.createElement('div');
        actions.className = 'recent-card-actions';

        if (f.exists) {
            const openBtn = document.createElement('button');
            openBtn.className = 'action-btn';
            openBtn.textContent = 'Open';
            openBtn.addEventListener('click', () => openRecentFile(f.path));
            actions.appendChild(openBtn);
        }

        const removeBtn = document.createElement('button');
        removeBtn.className = 'action-btn';
        removeBtn.textContent = 'Remove';
        removeBtn.style.color = '#7d2f2f';
        removeBtn.addEventListener('click', () => removeRecentFile(f.path));

        actions.appendChild(removeBtn);
        card.appendChild(info);
        card.appendChild(status);
        card.appendChild(actions);
        container.appendChild(card);
    });
}

async function openRecentFile(path) {
    try {
        const resp = await fetch(BASE + '/api/open-path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        navigateToFile(data.file_path, data.file_id);
    } catch (err) {
        alert('Failed to open file: ' + err.message);
    }
}

async function removeRecentFile(path) {
    try {
        await fetch(BASE + '/api/recent', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: path })
        });
        loadRecentFiles();
    } catch (err) {
        console.error('Failed to remove file:', err);
    }
}

// Settings
function setupSettings() {
    document.getElementById('btn-save-settings').addEventListener('click', saveSettings);
}

function checkSettings() {
    const showHome = localStorage.getItem('show_home') !== 'false';
    document.getElementById('setting-show-home').checked = showHome;
}

function saveSettings() {
    const showHome = document.getElementById('setting-show-home').checked;
    localStorage.setItem('show_home', showHome);
    alert('Settings saved');
}

// ==================== FILE PAGE ====================

function initFilePage() {
    setupModals();
    setupDropdowns();
    setupWorkbookActions();
    setupSelectionAndContextMenu();
    setupSheetContextMenu();
    setupKeyboardShortcuts();
    setupUpload();

    document.getElementById('btn-home').addEventListener('click', navigateToHome);
    document.getElementById('btn-new').addEventListener('click', createNewFile);
    document.getElementById('btn-upload').addEventListener('click', () => showModal('modal-upload'));

    window.addEventListener('resize', () => {
        if (layoutState && layoutState.sticky_row !== null) {
            updateStickyRowPosition();
        }
    });

    const params = getUrlParams();
    currentFile = params.file_path;

    if (!currentFile) {
        navigateToHome();
        return;
    }

    currentFileId = params.file_id;

    if (currentFile) {
        document.getElementById('current-file').textContent = currentFile.split('/').pop();
        fetchSheets();
    }

    window.addEventListener('beforeunload', flushPendingSavesSync);
}

async function fetchSheets() {
    try {
        const resp = await fetch(BASE + '/api/open-path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentFile })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        currentFileId = data.file_id;
        sheetsList = data.sheets;
        await loadLinkedSheets();
        renderSheetTabs();
        renderLinkedTabs();
        if (sheetsList.length > 0) {
            const params = new URLSearchParams(window.location.search);
            const sheetParam = params.get('sheet');
            const initialSheet = sheetParam && sheetsList.includes(sheetParam) ? sheetParam : sheetsList[0];
            if (!params.get('sheet')) {
                params.set('sheet', initialSheet);
                window.history.replaceState(null, '', BASE + '/file?' + params.toString());
            }
            await loadSheet(initialSheet);
        }
    } catch (err) {
        alert('Failed to load file: ' + err.message);
    }
}

async function loadLinkedSheets() {
    if (!currentFile) return;
    try {
        const url = new URL(BASE + '/api/linked-sheets', window.location.origin);
        url.searchParams.set('file', currentFile);
        if (currentSheet) {
            url.searchParams.set('sheet', currentSheet);
        }
        const resp = await fetch(url);
        const data = await resp.json();
        linkedSheets = data.linked_sheets || [];
    } catch (err) {
        console.error('Failed to load linked sheets:', err);
        linkedSheets = [];
    }
}

function renderSheetTabs() {
    const container = document.getElementById('sheet-tabs');
    container.innerHTML = '';
    sheetsList.forEach(name => {
        const tab = document.createElement('button');
        tab.className = 'sheet-tab' + (name === currentSheet && !isLinkedView ? ' active' : '');
        tab.textContent = name;
        tab.addEventListener('click', () => switchSheet(name));
        tab.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            showSheetContextMenu(e, name);
        });
        container.appendChild(tab);
    });
}

function renderLinkedTabs() {
    const container = document.getElementById('linked-tabs');
    container.innerHTML = '';
    if (linkedSheets.length === 0) {
        container.style.display = 'none';
        return;
    }
    container.style.display = 'flex';
    const viewsLabel = document.createElement('span');
    viewsLabel.className = 'linked-tabs-label';
    viewsLabel.textContent = 'Views:';
    container.appendChild(viewsLabel);
    linkedSheets.forEach(ls => {
        const tab = document.createElement('button');
        tab.className = 'linked-tab' + (currentLinkedId === ls.id ? ' active' : '');
        const tabLabel = document.createElement('span');
        tabLabel.textContent = ls.display_name;
        tab.appendChild(tabLabel);

        const delBtn = document.createElement('span');
        delBtn.className = 'linked-tab-del';
        delBtn.textContent = '×';
        delBtn.title = 'Remove filter view';
        delBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteLinkedSheet(ls.id);
        });
        tab.appendChild(delBtn);

        tab.addEventListener('click', () => switchLinkedSheet(ls));
        container.appendChild(tab);
    });
}

async function switchLinkedSheet(ls) {
    if (currentLinkedId === ls.id) return;
    await flushPendingSaves();

    currentLinkedId = ls.id;
    currentLinkedFilter = ls;
    isLinkedView = true;

    try {
        const url = new URL(BASE + '/api/linked-sheet-data', window.location.origin);
        url.searchParams.set('linked_id', ls.id);
        url.searchParams.set('file', currentFile);

        const resp = await fetch(url);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        currentSheet = data.name;
        sheetData = { data: data.data, rows: data.rows, cols: data.cols, name: data.name };
        const remoteLayout = data.layout || {};
        layoutState = {
            column_widths: remoteLayout.column_widths || {},
            row_heights: remoteLayout.row_heights || {},
            sticky_row: remoteLayout.sticky_row !== undefined ? remoteLayout.sticky_row : null,
            alternate_row_colors: !!remoteLayout.alternate_row_colors,
            cell_colors: {},
            header_rows: remoteLayout.header_rows || [],
            columnTypes: remoteLayout.columnTypes || {},
            data_rows: data.rows,
            data_cols: data.cols
        };
        columnTypes = { ...layoutState.columnTypes };
        headerRows = new Set(layoutState.header_rows);
        hydrateData(sheetData.data, remoteLayout.cell_colors || {});
        layoutState.cell_colors = {};

        renderSheetTabs();
        renderLinkedTabs();
        renderTable();
        resetUndoRedo();

        selectedCell = null;
        selectedCells = [];
        selectionStart = null;
        selectionEnd = null;
        isSelecting = false;
        selectedRows.clear();
        lastClickedRow = null;
        document.querySelectorAll('#spreadsheet td.selected').forEach(el => el.classList.remove('selected'));
        document.querySelectorAll('#spreadsheet th.row-header.selected').forEach(el => el.classList.remove('selected'));
        document.querySelectorAll('#spreadsheet tr.row-selected').forEach(el => el.classList.remove('row-selected'));
        updateNameBox();
    } catch (err) {
        alert('Failed to load linked sheet: ' + err.message);
    }
}

async function deleteLinkedSheet(id) {
    if (!confirm('Remove this filter view?')) return;
    try {
        await fetch(BASE + '/api/linked-sheet', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, file_path: currentFile })
        });
        if (currentLinkedId === id) {
            isLinkedView = false;
            currentLinkedId = null;
            currentLinkedFilter = null;
            const params = new URLSearchParams(window.location.search);
            const sheetName = params.get('sheet') || sheetsList[0];
            await loadSheet(sheetName);
        }
        await loadLinkedSheets();
        renderLinkedTabs();
    } catch (err) {
        alert('Failed to remove filter view: ' + err.message);
    }
}

async function switchSheet(sheetName) {
    if (sheetName === currentSheet && !isLinkedView) return;
    await flushPendingSaves();
    isLinkedView = false;
    currentLinkedId = null;
    currentLinkedFilter = null;
    const params = new URLSearchParams(window.location.search);
    params.set('sheet', sheetName);
    window.history.replaceState(null, '', BASE + '/file?' + params.toString());
    currentSheet = sheetName;
    await loadLinkedSheets();
    await loadSheet(sheetName);
}

async function loadSheet(sheetName) {
    currentSheet = sheetName;
    await loadLinkedSheets();
    try {
        const url = new URL(BASE + '/api/sheet', window.location.origin);
        url.searchParams.set('file', currentFile);
        url.searchParams.set('sheet', sheetName);
        if (currentFileId) url.searchParams.set('file_id', currentFileId);

        const resp = await fetch(url);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        sheetData = data.sheet;
        const hadLayout = data.layout != null;
        layoutState = data.layout || { column_widths: {}, row_heights: {}, sticky_row: null, alternate_row_colors: false, cell_colors: {}, header_rows: [], columnTypes: {}, data_rows: 0, data_cols: 0 };
        columnTypes = layoutState.columnTypes || {};
        headerRows = new Set(layoutState.header_rows || []);

        // Hydrate: merge cell_colors into cell objects
        hydrateData(sheetData.data, layoutState.cell_colors);
        // Clear the now-merged cell_colors from layoutState
        layoutState.cell_colors = {};

        if (!hadLayout) {
            layoutState.data_rows = sheetData.rows;
            layoutState.data_cols = sheetData.cols;
        }

        console.log('loadSheet:', sheetName, '- rows:', sheetData.rows, 'cols:', sheetData.cols, 'layout_dims:', layoutState.data_rows, 'x', layoutState.data_cols);

        if (!hadLayout && currentFileId) {
            saveLayout();
        }

        document.getElementById('current-file').textContent = currentFile.split('/').pop();
        renderSheetTabs();
        renderLinkedTabs();

        renderTable();
        applyLayout();
        resetUndoRedo();

        selectedCell = null;
        selectedCells = [];
        selectionStart = null;
        selectionEnd = null;
        isSelecting = false;
        selectedRows.clear();
        lastClickedRow = null;
        document.querySelectorAll('#spreadsheet td.selected').forEach(el => el.classList.remove('selected'));
        document.querySelectorAll('#spreadsheet th.row-header.selected').forEach(el => el.classList.remove('selected'));
        document.querySelectorAll('#spreadsheet tr.row-selected').forEach(el => el.classList.remove('row-selected'));
        updateNameBox();
    } catch (err) {
        alert('Failed to load sheet: ' + err.message);
    }
}

function renderTable() {
    const thead = document.getElementById('table-head');
    const tbody = document.getElementById('table-body');
    const table = document.getElementById('spreadsheet');
    const data = sheetData.data;
    const cols = sheetData.cols;

    let colgroup = table.querySelector('colgroup');
    if (!colgroup) {
        colgroup = document.createElement('colgroup');
        table.insertBefore(colgroup, table.firstChild);
    }
    colgroup.innerHTML = '';
    const cornerCol = document.createElement('col');
    cornerCol.dataset.col = 'corner';
    cornerCol.style.width = '50px';
    colgroup.appendChild(cornerCol);

    let totalWidth = 50;
    for (let c = 0; c < cols; c++) {
        const col = document.createElement('col');
        col.dataset.col = c;
        const width = layoutState.column_widths[c] || 100;
        col.style.width = width + 'px';
        colgroup.appendChild(col);
        totalWidth += width;
    }

    totalWidth += cols * 2;
    table.style.width = totalWidth + 'px';

    thead.innerHTML = '<tr></tr>';
    const headerRow = thead.querySelector('tr');
    const cornerTh = document.createElement('th');
    cornerTh.className = 'row-header-corner';
    headerRow.appendChild(cornerTh);
    for (let c = 0; c < cols; c++) {
        const th = document.createElement('th');
        th.dataset.col = c;
        const width = layoutState.column_widths[c] || 100;
        th.style.width = width + 'px';

        const label = document.createElement('span');
        label.textContent = 'C' + (c + 1);
        th.appendChild(label);

        const badge = document.createElement('span');
        badge.className = 'col-type-badge';
        const colType = getColumnType(c);
        badge.textContent = colType === 'numeric' ? '123' : 'ABC';
        badge.dataset.col = c;
        badge.title = 'Click to toggle datatype (numeric/text)';
        badge.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleColumnType(c);
        });
        th.appendChild(badge);

        const handle = document.createElement('div');
        handle.className = 'col-resize-handle';
        handle.addEventListener('mousedown', (e) => startColResize(e, c));
        th.appendChild(handle);
        headerRow.appendChild(th);
    }

    tbody.innerHTML = '';
    data.forEach((row, r) => {
        const tr = document.createElement('tr');
        tr.dataset.row = r;

        let trClass = '';
        if (layoutState.sticky_row !== null && layoutState.sticky_row === r) {
            trClass += 'sticky-row ';
        }
        if (headerRows.has(r)) {
            trClass += 'header-row ';
        }
        if (layoutState.alternate_row_colors && r % 2 === 1) {
            trClass += 'alternate ';
        }
        tr.className = trClass.trim();

        const rowTh = document.createElement('th');
        rowTh.className = 'row-header';
        rowTh.textContent = '' + (r + 1);
        rowTh.addEventListener('click', (e) => onRowHeaderClick(e, r));
        tr.appendChild(rowTh);

        row.forEach((cell, c) => {
            const td = document.createElement('td');
            td.textContent = cv(cell);
            td.dataset.row = r;
            td.dataset.col = c;

            if (layoutState.row_heights[r]) {
                td.style.height = layoutState.row_heights[r] + 'px';
            }

            // Cell style is embedded in the cell object itself
            const style = cs(cell);
            if (style) {
                if (style.bg) td.style.backgroundColor = style.bg;
                if (style.text) td.style.color = style.text;
            }

            td.addEventListener('dblclick', () => editCell(r, c));
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });

    updateStickyRowPosition();

    if (selectedCell) {
        const td = document.querySelector('td[data-row="' + selectedCell.row + '"][data-col="' + selectedCell.col + '"]');
        if (td) {
            td.classList.add('selected');
        }
    }

    applyLayout();
    updateRowSelectionVisuals();
}

function updateStickyRowPosition() {
    const table = document.getElementById('spreadsheet');
    const thead = document.getElementById('table-head');
    if (!table || !thead) return;

    requestAnimationFrame(() => {
        const theadHeight = thead.offsetHeight;
        table.style.setProperty('--header-height', theadHeight + 'px');
    });
}

// Cell Selection
function selectCell(td) {
    clearRowSelection();
    if (!isSelecting) {
        document.querySelectorAll('#spreadsheet td.selected').forEach(el => el.classList.remove('selected'));
        td.classList.add('selected');
        selectedCell = { row: +td.dataset.row, col: +td.dataset.col };
        selectionStart = { row: +td.dataset.row, col: +td.dataset.col };
        selectionEnd = { row: +td.dataset.row, col: +td.dataset.col };
        updateSelectionDisplay();
    }
    updateNameBox();
}

function updateNameBox() {
    const nameBox = document.getElementById('name-box');
    if (!selectionStart || !selectionEnd) {
        nameBox.textContent = 'Select a cell';
        return;
    }
    const minRow = Math.min(selectionStart.row, selectionEnd.row);
    const maxRow = Math.max(selectionStart.row, selectionEnd.row);
    const minCol = Math.min(selectionStart.col, selectionEnd.col);
    const maxCol = Math.max(selectionStart.col, selectionEnd.col);

    if (minRow === maxRow && minCol === maxCol) {
        nameBox.textContent = 'R' + (minRow + 1) + 'C' + (minCol + 1);
    } else {
        nameBox.textContent = 'R' + (minRow + 1) + 'C' + (minCol + 1) + ':R' + (maxRow + 1) + 'C' + (maxCol + 1);
    }
}

function clearRowSelection() {
    selectedRows.clear();
    document.querySelectorAll('#spreadsheet th.row-header.selected').forEach(el => el.classList.remove('selected'));
    document.querySelectorAll('#spreadsheet tr.row-selected').forEach(el => el.classList.remove('row-selected'));
}

function updateRowSelectionVisuals() {
    document.querySelectorAll('#spreadsheet th.row-header').forEach(th => {
        const tr = th.closest('tr');
        const row = parseInt(tr ? tr.dataset.row : -1);
        if (selectedRows.has(row)) {
            th.classList.add('selected');
            tr.classList.add('row-selected');
        } else {
            th.classList.remove('selected');
            tr.classList.remove('row-selected');
        }
    });
}

function updateSelectedCellsFromRows() {
    selectedCells = [];
    if (selectedRows.size === 0) return;
    const cols = sheetData.cols;
    const sortedRows = Array.from(selectedRows).sort((a, b) => a - b);
    sortedRows.forEach(r => {
        for (let c = 0; c < cols; c++) {
            selectedCells.push({ row: r, col: c, value: cv(sheetData.data[r][c]) });
        }
    });
    const minRow = sortedRows[0];
    const maxRow = sortedRows[sortedRows.length - 1];
    selectionStart = { row: minRow, col: 0 };
    selectionEnd = { row: maxRow, col: cols - 1 };
}

function onRowHeaderClick(e, row) {
    const isCtrl = e.ctrlKey || e.metaKey;
    const isShift = e.shiftKey;

    if (isShift && lastClickedRow !== null) {
        const minR = Math.min(lastClickedRow, row);
        const maxR = Math.max(lastClickedRow, row);
        for (let r = minR; r <= maxR; r++) {
            selectedRows.add(r);
        }
    } else if (isCtrl) {
        if (selectedRows.has(row)) {
            selectedRows.delete(row);
        } else {
            selectedRows.add(row);
        }
    } else {
        clearRowSelection();
        selectedRows.add(row);
    }

    lastClickedRow = row;
    updateRowSelectionVisuals();

    if (selectedRows.size > 0) {
        updateSelectedCellsFromRows();
        updateSelectionDisplay();
        updateNameBox();
    }
}

function setupSelectionAndContextMenu() {
    const table = document.getElementById('spreadsheet');

    table.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        const td = e.target.closest('td');
        if (!td) return;

        if (e.shiftKey && selectionStart) {
            // Shift+click: extend selection from selectionStart to clicked cell
            clearRowSelection();
            document.querySelectorAll('#spreadsheet td.selected').forEach(el => el.classList.remove('selected'));
            selectionEnd = { row: +td.dataset.row, col: +td.dataset.col };
            selectedCell = { row: +td.dataset.row, col: +td.dataset.col };
            updateSelectionDisplay();
            updateSelectedCellsList();
            isSelecting = false;
            e.preventDefault();
            return;
        }

        selectCell(td);
        isSelecting = true;
        selectionStart = { row: +td.dataset.row, col: +td.dataset.col };
        selectionEnd = { row: +td.dataset.row, col: +td.dataset.col };
        e.preventDefault();
    });

    table.addEventListener('mouseover', (e) => {
        if (!isSelecting) return;
        const td = e.target.closest('td');
        if (!td) return;
        selectionEnd = { row: +td.dataset.row, col: +td.dataset.col };
        updateSelectionDisplay();
    });

    document.addEventListener('mouseup', () => {
        if (isSelecting) {
            isSelecting = false;
            updateSelectedCellsList();
        }
    });

    table.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        const td = e.target.closest('td');
        if (!td) return;

        const row = +td.dataset.row;
        const col = +td.dataset.col;

        if (selectedRows.has(row)) {
            selectedCell = { row, col };
            updateNameBox();
        } else {
            clearRowSelection();
            if (!isInSelection(row, col)) {
                document.querySelectorAll('#spreadsheet td.selected').forEach(el => el.classList.remove('selected'));
                selectionStart = { row, col };
                selectionEnd = { row, col };
                updateSelectionDisplay();
            }
            selectedCell = { row, col };
            updateNameBox();
            updateSelectedCellsList();
        }

        showContextMenu(e.pageX, e.pageY);
    });

    document.addEventListener('click', () => hideContextMenu());
}

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if (!sheetData) return;
        // Don't intercept shortcuts when focus is in an input, textarea, select, or contenteditable element
        const tag = e.target.tagName;
        const isEditable = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable;
        if (isEditable) return;
        if (e.ctrlKey && e.key === 'z') {
            e.preventDefault();
            if (e.shiftKey) {
                redo();
            } else {
                undo();
            }
        } else if (e.ctrlKey && e.key === 'y') {
            e.preventDefault();
            redo();
        } else if (e.ctrlKey && (e.key === 'x' || e.key === 'X')) {
            e.preventDefault();
            cutSelection();
        } else if (e.ctrlKey && (e.key === 'c' || e.key === 'C')) {
            e.preventDefault();
            copySelection();
        } else if (e.ctrlKey && (e.key === 'v' || e.key === 'V')) {
            e.preventDefault();
            pasteSelection();
        } else if (e.ctrlKey && (e.key === 's' || e.key === 'S')) {
            e.preventDefault();
            manualSave();
        } else if (e.key === 'Delete' || e.key === 'Backspace') {
            if (selectedCell || selectedCells.length > 0) {
                e.preventDefault();
                clearCellContent();
            }
        }
    });
}

function updateSelectionDisplay() {
    if (!selectionStart || !selectionEnd) return;
    const minRow = Math.min(selectionStart.row, selectionEnd.row);
    const maxRow = Math.max(selectionStart.row, selectionEnd.row);
    const minCol = Math.min(selectionStart.col, selectionEnd.col);
    const maxCol = Math.max(selectionStart.col, selectionEnd.col);

    document.querySelectorAll('#spreadsheet td').forEach(td => {
        const r = +td.dataset.row;
        const c = +td.dataset.col;
        if (r >= minRow && r <= maxRow && c >= minCol && c <= maxCol) {
            td.classList.add('selected');
        } else if (!td.classList.contains('in-selection')) {
            td.classList.remove('selected');
        }
    });
    updateNameBox();
}

function updateSelectedCellsList() {
    selectedCells = [];
    if (!selectionStart || !selectionEnd) return;
    const minRow = Math.min(selectionStart.row, selectionEnd.row);
    const maxRow = Math.max(selectionStart.row, selectionEnd.row);
    const minCol = Math.min(selectionStart.col, selectionEnd.col);
    const maxCol = Math.max(selectionStart.col, selectionEnd.col);

    for (let r = minRow; r <= maxRow; r++) {
        for (let c = minCol; c <= maxCol; c++) {
            selectedCells.push({ row: r, col: c, value: cv(sheetData.data[r][c]) });
        }
    }
}

function detectColumnType(col) {
    let numberCount = 0;
    let totalCount = 0;
    const data = sheetData.data;
    for (let r = 0; r < data.length; r++) {
        const val = cv(data[r][col]).trim();
        if (val === '') continue;
        totalCount++;
        if (!isNaN(parseFloat(val)) && isFinite(parseFloat(val))) {
            numberCount++;
        }
    }
    if (totalCount === 0) return 'text';
    return (numberCount / totalCount) > 0.5 ? 'numeric' : 'text';
}

function getColumnType(col) {
    if (columnTypes[col] !== undefined) return columnTypes[col];
    return detectColumnType(col);
}

function toggleColumnType(col) {
    const current = getColumnType(col);
    columnTypes[col] = current === 'numeric' ? 'text' : 'numeric';
    layoutState.columnTypes = { ...columnTypes };
    renderTable();
    debouncedSaveLayout();
}

function buildSortSubmenu() {
    const container = document.getElementById('sort-options');
    const title = document.getElementById('sort-submenu-title');
    if (!selectedCell || !sheetData) {
        container.innerHTML = '';
        title.textContent = 'Select a cell first';
        return;
    }

    const col = selectedCell.col;
    const colNum = col + 1;
    const colType = getColumnType(col);
    title.textContent = 'Sort by Column C' + colNum;

    const opts = [];

    if (colType === 'numeric') {
        opts.push(
            { label: '1 → 10 (Increasing)', sortType: 'numeric', direction: 'asc' },
            { label: '10 → 1 (Decreasing)', sortType: 'numeric', direction: 'desc' }
        );
    } else {
        opts.push(
            { label: 'A → Z', sortType: 'lexical', direction: 'asc' },
            { label: 'Z → A', sortType: 'lexical', direction: 'desc' },
            { label: 'Char Count ↑', sortType: 'char_count', direction: 'asc' },
            { label: 'Char Count ↓', sortType: 'char_count', direction: 'desc' }
        );
    }

    container.innerHTML = '';
    opts.forEach(opt => {
        const btn = document.createElement('button');
        btn.className = 'ctx-btn sort-option';
        btn.textContent = opt.label;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            sortByColumn(col, opt.direction, opt.sortType);
            hideContextMenu();
        });
        container.appendChild(btn);
    });
}

function sortByColumn(col, direction, sortType) {
    if (!sheetData || sheetData.data.length === 0) return;
    pushUndo();

    const headerData = [];
    const dataRows = [];  // will hold { idx: originalRowIndex, row: [...] }
    sheetData.data.forEach((row, idx) => {
        if (headerRows.has(idx)) {
            headerData.push(row);
        } else {
            dataRows.push({ idx, row });
        }
    });

    dataRows.sort((a, b) => {
        let valA = cv(a.row[col]);
        let valB = cv(b.row[col]);

        if (sortType === 'numeric') {
            const numA = valA === '' ? NaN : parseFloat(valA);
            const numB = valB === '' ? NaN : parseFloat(valB);
            const isValidA = !isNaN(numA) && isFinite(numA);
            const isValidB = !isNaN(numB) && isFinite(numB);
            if (!isValidA && !isValidB) return 0;
            if (!isValidA) return 1;
            if (!isValidB) return -1;
            return direction === 'asc' ? numA - numB : numB - numA;
        } else if (sortType === 'char_count') {
            if (valA === '' && valB === '') return 0;
            if (valA === '') return 1;
            if (valB === '') return -1;
            return direction === 'asc'
                ? valA.length - valB.length
                : valB.length - valA.length;
        } else {
            if (valA === '' && valB === '') return 0;
            if (valA === '') return 1;
            if (valB === '') return -1;
            const cmp = valA.localeCompare(valB);
            return direction === 'asc' ? cmp : -cmp;
        }
    });

    // Build old→new row mapping for data rows (for row_heights & sticky_row)
    const headerCount = headerData.length;
    const oldToNew = {};
    dataRows.forEach((item, newPos) => {
        oldToNew[item.idx] = headerCount + newPos;
    });

    // Remap row_heights for data rows
    const newHeights = {};
    for (const key of Object.keys(layoutState.row_heights || {})) {
        const r = parseInt(key);
        const newRow = Object.hasOwn(oldToNew, r) ? oldToNew[r] : r;
        newHeights[newRow] = layoutState.row_heights[key];
    }
    layoutState.row_heights = newHeights;

    // Remap sticky_row if it was a data row
    if (layoutState.sticky_row !== null && layoutState.sticky_row !== undefined) {
        if (Object.hasOwn(oldToNew, layoutState.sticky_row)) {
            layoutState.sticky_row = oldToNew[layoutState.sticky_row];
        }
    }

    // Remap cell_colors for data rows
    const newCellColors = {};
    for (const [key, color] of Object.entries(layoutState.cell_colors || {})) {
        const parts = key.split(',');
        const r = parseInt(parts[0]);
        const c = parts[1];
        const newRow = Object.hasOwn(oldToNew, r) ? oldToNew[r] : r;
        newCellColors[newRow + ',' + c] = color;
    }
    layoutState.cell_colors = newCellColors;

    // Assemble final data
    sheetData.data = [...headerData, ...dataRows.map(item => item.row)];
    sheetData.rows = sheetData.data.length;
    sheetData.cols = sheetData.data.length > 0 ? sheetData.data[0].length : 0;

    headerRows = new Set(headerData.map((_, i) => i));
    layoutState.header_rows = Array.from(headerRows);
    layoutState.data_rows = sheetData.rows;
    layoutState.data_cols = sheetData.cols;

    selectedCell = null;
    selectedCells = [];
    selectionStart = null;
    selectionEnd = null;

    renderTable();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function isInSelection(row, col) {
    if (!selectionStart || !selectionEnd) return false;
    const minRow = Math.min(selectionStart.row, selectionEnd.row);
    const maxRow = Math.max(selectionStart.row, selectionEnd.row);
    const minCol = Math.min(selectionStart.col, selectionEnd.col);
    const maxCol = Math.max(selectionStart.col, selectionEnd.col);
    return row >= minRow && row <= maxRow && col >= minCol && col <= maxCol;
}

function showContextMenu(x, y) {
    const menu = document.getElementById('context-menu');
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    menu.classList.add('active');

    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
        menu.style.left = Math.max(10, window.innerWidth - rect.width - 10) + 'px';
    }
    if (rect.bottom > window.innerHeight) {
        menu.style.top = Math.max(10, window.innerHeight - rect.height - 10) + 'px';
    }
    if (parseInt(menu.style.left) < 0) menu.style.left = '10px';
    if (parseInt(menu.style.top) < 0) menu.style.top = '10px';

    buildSortSubmenu();

    const removeHeaderBtn = document.getElementById('remove-header-btn');
    if (selectedCell && headerRows.has(selectedCell.row)) {
        removeHeaderBtn.style.display = 'block';
    } else {
        removeHeaderBtn.style.display = 'none';
    }

    const btns = menu.querySelectorAll('.ctx-btn:not(.ctx-has-submenu)');
    btns.forEach(btn => {
        btn.onclick = () => {
            const action = btn.dataset.action;
            if (!action) return;
            if (action === 'cut') cutSelection();
            else if (action === 'copy') copySelection();
            else if (action === 'paste') pasteSelection();
            else if (action === 'select-all') selectAllCells();
            else if (action === 'edit') editCell(selectedCell.row, selectedCell.col);
            else if (action === 'clear') clearCellContent();
            else if (action === 'cell-ui') showCellUI();
            else if (action === 'sticky-row') setStickyRow();
            else if (action === 'clear-sticky-row') clearStickyRow();
            else if (action === 'adjust-row') adjustCurrentRow();
            else if (action === 'set-header') setRowAsHeader();
            else if (action === 'remove-header') removeRowHeader();
            else if (action === 'remove-row') removeRow();
            else if (action === 'remove-col') removeColumn();
            else if (action === 'add-rows-below') showAddRowsModal('below');
            else if (action === 'add-rows-above') showAddRowsModal('above');
            else if (action === 'add-cols-left') showAddColsModal('left');
            else if (action === 'add-cols-right') showAddColsModal('right');
            else if (action === 'filter-by-col') showFilterModal();
            hideContextMenu();
        };
    });

    menu.querySelectorAll('.ctx-submenu-wrapper').forEach(wrapper => {
        wrapper.onmouseenter = () => {
            const submenu = wrapper.querySelector('.ctx-submenu');
            if (!submenu) return;
            submenu.style.left = '';
            submenu.style.top = '';
            submenu.style.right = '';
            requestAnimationFrame(() => {
                const subRect = submenu.getBoundingClientRect();
                if (subRect.right > window.innerWidth) {
                    submenu.style.left = 'auto';
                    submenu.style.right = '100%';
                }
                if (subRect.bottom > window.innerHeight) {
                    submenu.style.top = (window.innerHeight - subRect.bottom) + 'px';
                }
            });
        };
    });
}

function hideContextMenu() {
    document.getElementById('context-menu').classList.remove('active');
}

// ==================== SHEET TAB CONTEXT MENU ====================

let sheetContextSheetName = null;

function showSheetContextMenu(e, sheetName) {
    e.preventDefault();
    e.stopPropagation();

    // Hide the cell context menu
    hideContextMenu();
    // Hide any other sheet context menu
    hideSheetContextMenu();

    sheetContextSheetName = sheetName;
    document.getElementById('sheet-ctx-sheet-name').textContent = sheetName;

    const menu = document.getElementById('sheet-ctx-menu');
    menu.style.left = e.pageX + 'px';
    menu.style.top = e.pageY + 'px';
    menu.classList.add('active');

    // Adjust position to stay within viewport
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
        menu.style.left = Math.max(10, window.innerWidth - rect.width - 10) + 'px';
    }
    if (rect.bottom > window.innerHeight) {
        menu.style.top = Math.max(10, window.innerHeight - rect.height - 10) + 'px';
    }
    if (parseInt(menu.style.left) < 0) menu.style.left = '10px';
    if (parseInt(menu.style.top) < 0) menu.style.top = '10px';

    // Disable Move Left/Right at edges
    const idx = sheetsList.indexOf(sheetName);
    const moveLeftBtn = menu.querySelector('[data-action="sheet-move-left"]');
    const moveRightBtn = menu.querySelector('[data-action="sheet-move-right"]');
    if (moveLeftBtn) moveLeftBtn.disabled = (idx <= 0);
    if (moveRightBtn) moveRightBtn.disabled = (idx >= sheetsList.length - 1);

    // Disable Delete if last sheet
    const deleteBtn = menu.querySelector('[data-action="sheet-delete"]');
    if (deleteBtn) deleteBtn.disabled = (sheetsList.length <= 1);
}

function hideSheetContextMenu() {
    document.getElementById('sheet-ctx-menu').classList.remove('active');
    sheetContextSheetName = null;
}

function setupSheetContextMenu() {
    const menu = document.getElementById('sheet-ctx-menu');
    const tabsContainer = document.getElementById('sheet-tabs');

    // Right-click on empty area of sheet tabs bar → show new-sheet-only menu
    tabsContainer.addEventListener('contextmenu', (e) => {
        // Only handle clicks directly on the container (not on a tab button)
        if (e.target === tabsContainer) {
            e.preventDefault();
            e.stopPropagation();
            hideContextMenu();
            hideSheetContextMenu();

            document.getElementById('sheet-ctx-sheet-name').textContent = '(new)';
            menu.style.left = e.pageX + 'px';
            menu.style.top = e.pageY + 'px';
            menu.classList.add('active');

            // Show only New Sheet, disable all other items
            menu.querySelectorAll('.sheet-ctx-btn').forEach(btn => {
                const action = btn.dataset.action;
                if (action === 'sheet-new') {
                    btn.disabled = false;
                } else {
                    btn.disabled = true;
                }
            });

            const rect = menu.getBoundingClientRect();
            if (rect.right > window.innerWidth) {
                menu.style.left = Math.max(10, window.innerWidth - rect.width - 10) + 'px';
            }
            if (rect.bottom > window.innerHeight) {
                menu.style.top = Math.max(10, window.innerHeight - rect.height - 10) + 'px';
            }
        }
    });

    // Handle button clicks via delegation
    menu.addEventListener('click', (e) => {
        const btn = e.target.closest('.sheet-ctx-btn');
        if (!btn) return;
        if (btn.disabled) return;

        const action = btn.dataset.action;
        const sheetName = sheetContextSheetName || currentSheet;
        hideSheetContextMenu();

        switch (action) {
            case 'sheet-duplicate':
                duplicateSheet(sheetName);
                break;
            case 'sheet-new':
                createNewSheet();
                break;
            case 'sheet-delete':
                deleteSheet(sheetName);
                break;
            case 'sheet-move-left':
                reorderSheet(sheetName, 'left');
                break;
            case 'sheet-move-right':
                reorderSheet(sheetName, 'right');
                break;
        }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!menu.contains(e.target)) {
            hideSheetContextMenu();
        }
    });
}

async function duplicateSheet(sheetName) {
    if (!currentFile || !sheetName) return;
    await flushPendingSaves();

    try {
        const resp = await fetch(BASE + '/api/sheet/duplicate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentFile,
                sheet_name: sheetName,
                file_id: currentFileId
            })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        sheetsList = data.sheets;
        renderSheetTabs();
        await switchSheet(data.new_sheet);
    } catch (err) {
        alert('Failed to duplicate sheet: ' + err.message);
    }
}

async function deleteSheet(sheetName) {
    if (!currentFile || !sheetName) return;
    if (!confirm('Are you sure you want to delete sheet "' + sheetName + '"? This action cannot be undone.')) return;

    await flushPendingSaves();

    try {
        const resp = await fetch(BASE + '/api/sheet/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentFile,
                sheet_name: sheetName,
                file_id: currentFileId
            })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        sheetsList = data.sheets;

        // Switch to first sheet if current was deleted
        if (sheetName === currentSheet || !sheetsList.includes(currentSheet)) {
            const params = new URLSearchParams(window.location.search);
            const targetSheet = sheetsList[0];
            params.set('sheet', targetSheet);
            window.history.replaceState(null, '', BASE + '/file?' + params.toString());
            await loadSheet(targetSheet);
        } else {
            renderSheetTabs();
        }
    } catch (err) {
        alert('Failed to delete sheet: ' + err.message);
    }
}

async function createNewSheet() {
    if (!currentFile) return;
    await flushPendingSaves();

    try {
        const resp = await fetch(BASE + '/api/sheet/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentFile,
                file_id: currentFileId
            })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        sheetsList = data.sheets;
        renderSheetTabs();
        await switchSheet(data.new_sheet);
    } catch (err) {
        alert('Failed to create sheet: ' + err.message);
    }
}

async function reorderSheet(sheetName, direction) {
    if (!currentFile || !sheetName) return;
    await flushPendingSaves();

    try {
        const resp = await fetch(BASE + '/api/sheet/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentFile,
                sheet_name: sheetName,
                direction: direction
            })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        sheetsList = data.sheets;
        renderSheetTabs();
        // Re-render linked tabs (though they won't change)
        renderLinkedTabs();
    } catch (err) {
        alert('Failed to reorder sheet: ' + err.message);
    }
}

function ensureSheetSize(needRows, needCols) {
    let changed = false;
    while (sheetData.data.length < needRows) {
        sheetData.data.push(freshRow(sheetData.cols));
        sheetData.rows++;
        changed = true;
    }
    if (needCols > sheetData.cols) {
        for (let r = 0; r < sheetData.data.length; r++) {
            while (sheetData.data[r].length < needCols) {
                sheetData.data[r].push(newCell(''));
            }
        }
        for (let c = sheetData.cols; c < needCols; c++) {
            layoutState.column_widths[c] = 100;
        }
        sheetData.cols = needCols;
        changed = true;
    }
    if (changed) {
        layoutState.data_rows = sheetData.rows;
        layoutState.data_cols = sheetData.cols;
    }
    return changed;
}

function copyToSystemClipboard(cells, anchorRow, anchorCol) {
    if (!cells.length) return;
    const minRow = Math.min(...cells.map(c => c.row));
    const maxRow = Math.max(...cells.map(c => c.row));
    const minCol = Math.min(...cells.map(c => c.col));
    const maxCol = Math.max(...cells.map(c => c.col));
    const rowCount = maxRow - minRow + 1;
    const colCount = maxCol - minCol + 1;
    const grid = Array.from({ length: rowCount }, () => new Array(colCount).fill(''));
    cells.forEach(cell => {
        grid[cell.row - minRow][cell.col - minCol] = cell.value;
    });
    const tsv = grid.map(row => row.join('\t')).join('\n');
    try {
        navigator.clipboard.writeText(tsv).catch(() => {});
    } catch (_) {}
}

function parseSystemClipboardText(text) {
    if (!text) return null;
    const rows = text.split('\n').filter(r => r.length > 0);
    const parsed = rows.map(row => {
        const parts = [];
        let current = '';
        let inQuotes = false;
        for (let i = 0; i < row.length; i++) {
            const ch = row[i];
            if (ch === '"') {
                inQuotes = !inQuotes;
            } else if ((ch === '\t' || ch === ',') && !inQuotes) {
                parts.push(current);
                current = '';
            } else {
                current += ch;
            }
        }
        parts.push(current);
        return parts;
    });
    if (parsed.length === 0) return null;
    return parsed;
}

function cutSelection() {
    if (!selectedCells.length) return;
    pushUndo();
    clipboard = {
        type: 'cut',
        cells: [...selectedCells],
        anchorRow: selectionStart.row,
        anchorCol: selectionStart.col
    };
    copyToSystemClipboard(selectedCells, selectionStart.row, selectionStart.col);
    selectedCells.forEach(cell => {
        setCellValue(sheetData.data, cell.row, cell.col, '');
    });
    renderTable();
    debouncedSaveSheet();
}

function copySelection() {
    if (!selectedCells.length) return;
    clipboard = {
        type: 'copy',
        cells: selectedCells.map(c => ({ row: c.row, col: c.col, value: cv(sheetData.data[c.row][c.col]) })),
        anchorRow: selectionStart.row,
        anchorCol: selectionStart.col
    };
    copyToSystemClipboard(selectedCells, selectionStart.row, selectionStart.col);
}

async function pasteFromSystemClipboard() {
    try {
        const text = await navigator.clipboard.readText();
        const parsed = parseSystemClipboardText(text);
        if (parsed && parsed.length > 0 && parsed[0].length > 0) {
            return parsed;
        }
    } catch (_) {}
    return null;
}

function cellId(row, col) {
    return 'R' + (row + 1) + 'C' + (col + 1);
}

function truncateContent(val, maxLen) {
    if (!val) return '';
    const s = String(val);
    return s.length > maxLen ? s.substring(0, maxLen) + '...' : s;
}

function findPasteConflicts(pasteSource, startRow, startCol) {
    const conflicts = [];
    const checked = new Set();
    pasteSource.cells.forEach(cell => {
        const targetRow = startRow + (cell.row - pasteSource.anchorRow);
        const targetCol = startCol + (cell.col - pasteSource.anchorCol);
        const key = targetRow + ',' + targetCol;
        if (checked.has(key)) return;
        checked.add(key);

        if (targetRow >= 0 && targetRow < sheetData.data.length &&
            targetCol >= 0 && targetCol < sheetData.data[0].length) {
            const existing = cv(sheetData.data[targetRow][targetCol]);
            if (existing && existing.trim() !== '') {
                conflicts.push({ row: targetRow, col: targetCol, value: existing });
            }
        }
    });
    return conflicts;
}

function showPasteConflictModal(conflicts, pasteSource, startRow, startCol) {
    pendingPaste = { pasteSource, startRow, startCol };

    const first = conflicts[0];
    const message = 'Paste would overwrite cell <strong>' + cellId(first.row, first.col) +
        '</strong> containing:';
    document.getElementById('paste-conflict-message').innerHTML = message;

    let details = conflicts.slice(0, 5).map(c =>
        cellId(c.row, c.col) + ': "' + truncateContent(c.value, 30) + '"'
    ).join('\n');
    if (conflicts.length > 5) {
        details += '\n... and ' + (conflicts.length - 5) + ' more cells';
    }
    document.getElementById('paste-conflict-details').textContent = details;

    document.getElementById('btn-paste-insert').onclick = () => {
        hideModal('modal-paste-conflict');
        executePasteWithInsert(pendingPaste.pasteSource, pendingPaste.startRow, pendingPaste.startCol);
        pendingPaste = null;
    };
    document.getElementById('btn-paste-new-sheet').onclick = () => {
        hideModal('modal-paste-conflict');
        executePasteWithNewSheet(conflicts, pendingPaste.pasteSource, pendingPaste.startRow, pendingPaste.startCol);
        pendingPaste = null;
    };
    document.getElementById('btn-paste-cancel').onclick = () => {
        hideModal('modal-paste-conflict');
        pendingPaste = null;
    };

    showModal('modal-paste-conflict');
}

function executePaste(forceInsert, pasteSource, startRow, startCol) {
    pushUndo();

    const pasteRows = Math.max(...pasteSource.cells.map(c => c.row - pasteSource.anchorRow)) + 1;
    const pasteCols = Math.max(...pasteSource.cells.map(c => c.col - pasteSource.anchorCol)) + 1;

    if (forceInsert) {
        const cols = sheetData.cols;
        for (let i = 0; i < pasteRows; i++) {
            sheetData.data.splice(startRow, 0, freshRow(cols));
        }
        sheetData.rows += pasteRows;
        shiftLayoutStateForInsert(startRow, pasteRows);

        sheetData.data.forEach(row => {
            for (let i = 0; i < pasteCols; i++) {
                row.splice(startCol, 0, newCell(''));
            }
        });
        sheetData.cols += pasteCols;
        shiftLayoutStateForColInsert(startCol, pasteCols);

        layoutState.data_rows = sheetData.rows;
        layoutState.data_cols = sheetData.cols;
    } else {
        const maxTargetRow = startRow + pasteRows - 1;
        const maxTargetCol = startCol + pasteCols - 1;
        const needRows = Math.max(sheetData.rows, maxTargetRow + 1);
        const needCols = Math.max(sheetData.cols, maxTargetCol + 1);
        const expanded = ensureSheetSize(needRows, needCols);
    }

    pasteSource.cells.forEach(cell => {
        const targetRow = startRow + (cell.row - pasteSource.anchorRow);
        const targetCol = startCol + (cell.col - pasteSource.anchorCol);
        if (targetRow >= 0 && targetRow < sheetData.data.length &&
            targetCol >= 0 && targetCol < sheetData.data[0].length) {
            setCellValue(sheetData.data, targetRow, targetCol, cell.value);
        }
    });

    if (clipboard && clipboard.type === 'cut') clipboard = null;
    renderTable();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function executePasteWithInsert(pasteSource, startRow, startCol) {
    executePaste(true, pasteSource, startRow, startCol);
}

async function executePasteWithNewSheet(conflicts, pasteSource, startRow, startCol) {
    const ts = Date.now();
    const newSheetName = 'Conflicts_' + ts;

    const maxRow = Math.max(...conflicts.map(c => c.row));
    const maxCol = Math.max(...conflicts.map(c => c.col));
    const minRow = Math.min(...conflicts.map(c => c.row));
    const minCol = Math.min(...conflicts.map(c => c.col));

    const rows = maxRow - minRow + 1;
    const cols = maxCol - minCol + 1;
    const newData = Array.from({ length: rows }, () => new Array(cols).fill(''));
    conflicts.forEach(c => {
        newData[c.row - minRow][c.col - minCol] = c.value;
    });

    try {
        await fetch(BASE + '/api/sheet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentFile,
                sheet_name: newSheetName,
                data: newData
            })
        });

        const resp = await fetch(BASE + '/api/open-path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentFile })
        });
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        sheetsList = data.sheets;
        renderSheetTabs();
    } catch (err) {
        console.error('Failed to create conflict sheet:', err);
    }

    executePasteWithInsert(pasteSource, startRow, startCol);

    switchSheet(newSheetName);
}

async function pasteSelection() {
    let pasteSource = clipboard;

    if (!pasteSource) {
        const systemData = await pasteFromSystemClipboard();
        if (systemData) {
            pasteSource = {
                type: 'copy',
                cells: [],
                anchorRow: 0,
                anchorCol: 0
            };
            systemData.forEach((row, r) => {
                row.forEach((val, c) => {
                    pasteSource.cells.push({ row: r, col: c, value: val });
                });
            });
        }
    }

    if (!pasteSource || !selectedCell) return;

    const startRow = selectedCell.row;
    const startCol = selectedCell.col;

    const conflicts = findPasteConflicts(pasteSource, startRow, startCol);

    if (conflicts.length > 0) {
        showPasteConflictModal(conflicts, pasteSource, startRow, startCol);
        return;
    }

    executePaste(false, pasteSource, startRow, startCol);
}

function selectAllCells() {
    clearRowSelection();
    const rows = sheetData.data.length;
    const cols = sheetData.data[0].length;
    selectionStart = { row: 0, col: 0 };
    selectionEnd = { row: rows - 1, col: cols - 1 };
    updateSelectionDisplay();
    updateSelectedCellsList();
}

// Cell Editing
function editCell(row, col) {
    const modal = document.getElementById('modal-edit');
    const textarea = document.getElementById('edit-cell-text');
    textarea.value = cv(sheetData.data[row][col]);
    modal.classList.add('active');

    const saveBtn = document.getElementById('btn-edit-save');
    const cancelBtn = document.getElementById('btn-edit-cancel');

    const saveHandler = () => {
        pushUndo();
        setCellValue(sheetData.data, row, col, textarea.value);
        renderTable();
        debouncedSaveSheet();
        hideModal('modal-edit');
        saveBtn.removeEventListener('click', saveHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    const cancelHandler = () => {
        hideModal('modal-edit');
        saveBtn.removeEventListener('click', saveHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    saveBtn.addEventListener('click', saveHandler);
    cancelBtn.addEventListener('click', cancelHandler);
}

function clearCellContent() {
    if (!sheetData || !selectedCell) return;
    pushUndo();
    if (selectedCells.length > 1) {
        selectedCells.forEach(cell => {
            setCellValue(sheetData.data, cell.row, cell.col, '');
        });
    } else {
        setCellValue(sheetData.data, selectedCell.row, selectedCell.col, '');
    }
    renderTable();
    debouncedSaveSheet();
}

// Workbook Actions
function setupWorkbookActions() {
    document.getElementById('btn-undo').addEventListener('click', undo);
    document.getElementById('btn-redo').addEventListener('click', redo);
    document.getElementById('btn-save').addEventListener('click', manualSave);
    document.getElementById('btn-add-rows').addEventListener('click', () => showAddModal('rows'));
    document.getElementById('btn-add-cols').addEventListener('click', () => showAddModal('cols'));
    document.getElementById('btn-toggle-alt').addEventListener('click', toggleAlternateColors);
    document.getElementById('btn-adjust-all').addEventListener('click', adjustAllRows);
    document.getElementById('btn-export-txl').addEventListener('click', exportTXL);
    document.getElementById('btn-import-txl').addEventListener('click', () => document.getElementById('txl-import-input').click());
    document.getElementById('txl-import-input').addEventListener('change', importTXL);
    document.getElementById('btn-file-properties').addEventListener('click', showFileProperties);
    document.getElementById('btn-file-props-close').addEventListener('click', () => hideModal('modal-file-properties'));
}

async function exportTXL() {
    if (!currentFile) {
        alert('No file open to export');
        return;
    }
    try {
        await flushPendingSaves();

        const url = new URL(BASE + '/api/export/txl', window.location.origin);
        url.searchParams.set('file', currentFile);

        const resp = await fetch(url);
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || 'Export failed');
        }
        const blob = await resp.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        const fileName = currentFile.split('/').pop().replace(/\.[^.]+$/, '') + '.txl';
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
        alert('Export failed: ' + err.message);
    }
}

function importTXL() {
    const input = document.getElementById('txl-import-input');
    if (!input.files.length) return;
    const file = input.files[0];
    input.value = '';

    const formData = new FormData();
    formData.append('file', file);

    fetch(BASE + '/api/import/txl', { method: 'POST', body: formData })
        .then(resp => resp.json())
        .then(data => {
            if (data.error) throw new Error(data.error);
            alert('Import successful: ' + data.original_name);
            navigateToFile(data.file_path, data.file_id);
        })
        .catch(err => alert('Import failed: ' + err.message));
}

async function showFileProperties() {
    if (!currentFileId || !currentFile) {
        alert('No file open');
        return;
    }
    try {
        const url = new URL(BASE + '/api/file-metadata', window.location.origin);
        url.searchParams.set('file_id', currentFileId);
        url.searchParams.set('file', currentFile);

        const resp = await fetch(url);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        document.getElementById('fp-name').textContent = data.original_name;
        document.getElementById('fp-size').textContent = formatFileSize(data.file_size);
        document.getElementById('fp-id').textContent = data.file_id;
        document.getElementById('fp-hash').textContent = data.content_hash;
        document.getElementById('fp-first-seen').textContent = formatDateTime(data.first_seen_at);
        document.getElementById('fp-last-opened').textContent = formatDateTime(data.last_opened_at);
        document.getElementById('fp-total-sheets').textContent = data.total_sheets;

        const sheetsContainer = document.getElementById('fp-sheets');
        sheetsContainer.innerHTML = '';
        data.sheets.forEach(s => {
            const sheetDiv = document.createElement('div');
            sheetDiv.className = 'fp-sheet-row';
            const headerCount = s.header_rows ? s.header_rows.length : 0;
            sheetDiv.innerHTML = `
                <span class="fp-sheet-name">${escapeHtml(s.name)}</span>
                <span class="fp-sheet-dims">${s.data_rows} rows × ${s.data_cols} cols</span>
                <span class="fp-sheet-details">
                    ${headerCount > 0 ? headerCount + ' header(s)' : 'No headers'}
                    ${s.sticky_row !== null ? ' | Sticky: row ' + (s.sticky_row + 1) : ''}
                    ${s.alternate_row_colors ? ' | Alt colors' : ''}
                </span>
            `;
            sheetsContainer.appendChild(sheetDiv);
        });

        const linkedSection = document.getElementById('fp-linked-section');
        const linkedContainer = document.getElementById('fp-linked');
        linkedContainer.innerHTML = '';
        const linkedBySheet = data.linked_sheets_by_sheet || {};
        const anyLinked = Object.values(linkedBySheet).some(arr => arr.length > 0);
        if (anyLinked) {
            linkedSection.style.display = '';
            for (const [sheetName, linkedList] of Object.entries(linkedBySheet)) {
                if (!linkedList || linkedList.length === 0) continue;
                const sheetHeader = document.createElement('div');
                sheetHeader.className = 'fp-linked-sheet-header';
                sheetHeader.textContent = sheetName;
                linkedContainer.appendChild(sheetHeader);
                linkedList.forEach(ls => {
                    const lsDiv = document.createElement('div');
                    lsDiv.className = 'fp-linked-row';
                    lsDiv.innerHTML = `
                        <span class="fp-linked-name">${escapeHtml(ls.display_name)}</span>
                        <span class="fp-linked-source">C${ls.filter_col + 1} ${ls.filter_op} "${escapeHtml(ls.filter_val)}"</span>
                    `;
                    linkedContainer.appendChild(lsDiv);
                });
            }
        } else {
            linkedSection.style.display = 'none';
        }

        showModal('modal-file-properties');
    } catch (err) {
        alert('Failed to load file properties: ' + err.message);
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function formatDateTime(isoStr) {
    if (!isoStr) return '-';
    try {
        const d = new Date(isoStr);
        return d.toLocaleString();
    } catch (_) {
        return isoStr;
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showAddModal(type) {
    const modal = document.getElementById('modal-add');
    const title = document.getElementById('add-modal-title');
    const countInput = document.getElementById('add-count');
    title.textContent = type === 'rows' ? 'Add Rows' : 'Add Columns';
    countInput.value = type === 'rows' ? '10' : '5';
    modal.classList.add('active');

    const confirmBtn = document.getElementById('btn-add-confirm');
    const cancelBtn = document.getElementById('btn-add-cancel');

    const confirmHandler = () => {
        const count = parseInt(countInput.value);
        if (type === 'rows') addRows(count);
        else addColumns(count);
        hideModal('modal-add');
        confirmBtn.removeEventListener('click', confirmHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    const cancelHandler = () => {
        hideModal('modal-add');
        confirmBtn.removeEventListener('click', confirmHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    confirmBtn.addEventListener('click', confirmHandler);
    cancelBtn.addEventListener('click', cancelHandler);
}

function addRows(count) {
    pushUndo();
    const cols = sheetData.cols;
    for (let i = 0; i < count; i++) {
        sheetData.data.push(freshRow(cols));
    }
    sheetData.rows += count;
    layoutState.data_rows = sheetData.rows;
    layoutState.data_cols = sheetData.cols;
    console.log('addRows: now', sheetData.rows, 'rows,', sheetData.cols, 'cols');
    renderTable();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function addColumns(count) {
    pushUndo();
    const cols = sheetData.cols;
    for (let i = 0; i < count; i++) {
        layoutState.column_widths[cols + i] = 100;
    }
    sheetData.data.forEach(row => {
        for (let i = 0; i < count; i++) {
            row.push(newCell(''));
        }
    });
    sheetData.cols += count;
    layoutState.data_rows = sheetData.rows;
    layoutState.data_cols = sheetData.cols;
    layoutState.columnTypes = { ...columnTypes };
    renderTable();
    updateTableWidth();
    saveSheet();
    saveLayout();
}

function adjustAllRows() {
    const colWidths = {};
    for (let c = 0; c < sheetData.cols; c++) {
        colWidths[c] = layoutState.column_widths[c] || 100;
    }
    const CHAR_WIDTH = 7.5;
    const LINE_HEIGHT = 20;
    const MIN_ROW_HEIGHT = 30;
    const PADDING = 16;

    for (let r = 0; r < sheetData.data.length; r++) {
        let maxLines = 1;
        for (let c = 0; c < sheetData.data[r].length; c++) {
            const text = cv(sheetData.data[r][c]);
            if (!text) continue;
            const availableWidth = (colWidths[c] || 100) - PADDING;
            const charsPerLine = Math.max(1, Math.floor(availableWidth / CHAR_WIDTH));
            const textLines = text.split('\n').reduce((sum, segment) => {
                return sum + Math.max(1, Math.ceil(segment.length / charsPerLine));
            }, 0);
            maxLines = Math.max(maxLines, textLines);
        }
        layoutState.row_heights[r] = Math.max(MIN_ROW_HEIGHT, maxLines * LINE_HEIGHT + PADDING);
    }
    renderTable();
    debouncedSaveLayout();
}

function adjustCurrentRow() {
    if (!selectedCell) return;
    const td = document.querySelector('td[data-row="' + selectedCell.row + '"][data-col="' + selectedCell.col + '"]');
    if (!td) return;
    const content = td.textContent;
    const lines = content.split('\n').length;
    const height = Math.max(30, lines * 20);
    td.style.height = height + 'px';
    layoutState.row_heights[selectedCell.row] = height;
    debouncedSaveLayout();
}

function setStickyRow() {
    if (!selectedCell) {
        alert('Please select a cell first');
        return;
    }
    if (selectedCell.row < 0 || selectedCell.row >= sheetData.data.length) {
        alert('Invalid row selected');
        return;
    }
    layoutState.sticky_row = selectedCell.row;
    renderTable();
    debouncedSaveLayout();
    alert('Set row ' + (selectedCell.row + 1) + ' as sticky row');
}

function clearStickyRow() {
    if (layoutState.sticky_row === null) {
        alert('No sticky row to clear');
        return;
    }
    const clearedRow = layoutState.sticky_row;
    layoutState.sticky_row = null;
    renderTable();
    debouncedSaveLayout();
    alert('Cleared sticky row ' + (clearedRow + 1));
}

function setRowAsHeader() {
    if (!selectedCell) return;
    const rowIdx = selectedCell.row;
    if (headerRows.has(rowIdx)) return;
    if (rowIdx < 0 || rowIdx >= sheetData.data.length) return;

    pushUndo();

    const rowData = sheetData.data.splice(rowIdx, 1)[0];
    sheetData.data.unshift(rowData);

    const rowHeight = layoutState.row_heights[rowIdx];
    for (let r = rowIdx; r > 0; r--) {
        layoutState.row_heights[r] = layoutState.row_heights[r - 1];
    }
    layoutState.row_heights[0] = rowHeight;

    const newHeaderRows = new Set();
    newHeaderRows.add(0);
    for (const h of headerRows) {
        if (h < rowIdx) {
            newHeaderRows.add(h + 1);
        } else if (h > rowIdx) {
            newHeaderRows.add(h);
        }
    }
    headerRows = newHeaderRows;
    layoutState.header_rows = Array.from(headerRows);

    // Also make this row sticky — a header row should always be pinned
    layoutState.sticky_row = 0;

    selectedCell.row = 0;

    renderTable();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function removeRowHeader() {
    if (!selectedCell) return;
    const rowIdx = selectedCell.row;
    if (!headerRows.has(rowIdx)) return;

    pushUndo();

    headerRows.delete(rowIdx);
    layoutState.header_rows = Array.from(headerRows);

    // If the row being un-headed is the current sticky row, clear sticky too
    if (layoutState.sticky_row === rowIdx) {
        layoutState.sticky_row = null;
    }

    renderTable();
    debouncedSaveLayout();
}

function removeRow() {
    if (!selectedCell && selectedRows.size === 0) return;
    if (sheetData.data.length <= 1) return;

    let rowsToRemove;
    if (selectedRows.size > 0) {
        rowsToRemove = Array.from(selectedRows).sort((a, b) => b - a);
    } else if (selectedCells.length > 1) {
        const uniqueRows = [...new Set(selectedCells.map(c => c.row))];
        if (uniqueRows.length > 1) {
            rowsToRemove = uniqueRows.sort((a, b) => b - a);
        } else {
            rowsToRemove = [selectedCell.row];
        }
    } else {
        rowsToRemove = [selectedCell.row];
    }

    if (rowsToRemove.length === 0) return;

    pushUndo();

    rowsToRemove.forEach(rowIdx => {
        if (sheetData.data.length <= 1) return;
        sheetData.data.splice(rowIdx, 1);
        sheetData.rows -= 1;

        delete layoutState.row_heights[rowIdx];
        const newHeights = {};
        for (const key of Object.keys(layoutState.row_heights)) {
            const k = parseInt(key);
            if (k > rowIdx) {
                newHeights[k - 1] = layoutState.row_heights[key];
            } else {
                newHeights[k] = layoutState.row_heights[key];
            }
        }
        layoutState.row_heights = newHeights;

        const newHeaderRows = new Set();
        for (const h of headerRows) {
            if (h === rowIdx) continue;
            newHeaderRows.add(h > rowIdx ? h - 1 : h);
        }
        headerRows = newHeaderRows;
        layoutState.header_rows = Array.from(headerRows);

        if (layoutState.sticky_row !== null) {
            if (layoutState.sticky_row === rowIdx) {
                layoutState.sticky_row = null;
            } else if (layoutState.sticky_row > rowIdx) {
                layoutState.sticky_row -= 1;
            }
        }
    });

    selectedRows.clear();
    lastClickedRow = null;

    if (selectedCell && selectedCell.row >= sheetData.data.length) {
        selectedCell.row = sheetData.data.length - 1;
    }

    layoutState.data_rows = sheetData.rows;
    layoutState.data_cols = sheetData.cols;

    renderTable();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function removeColumn() {
    if (!selectedCell) return;
    const colIdx = selectedCell.col;
    if (sheetData.cols <= 1) return;

    pushUndo();

    for (let r = 0; r < sheetData.data.length; r++) {
        sheetData.data[r].splice(colIdx, 1);
    }
    sheetData.cols -= 1;
    layoutState.data_rows = sheetData.rows;
    layoutState.data_cols = sheetData.cols;

    delete columnTypes[colIdx];
    const shiftedTypes = {};
    for (const key of Object.keys(columnTypes)) {
        const k = parseInt(key);
        if (k > colIdx) {
            shiftedTypes[k - 1] = columnTypes[key];
        } else {
            shiftedTypes[k] = columnTypes[key];
        }
    }
    columnTypes = shiftedTypes;
    layoutState.columnTypes = { ...columnTypes };

    delete layoutState.column_widths[colIdx];
    const newWidths = {};
    for (const key of Object.keys(layoutState.column_widths)) {
        const k = parseInt(key);
        if (k > colIdx) {
            newWidths[k - 1] = layoutState.column_widths[key];
        } else {
            newWidths[k] = layoutState.column_widths[key];
        }
    }
    layoutState.column_widths = newWidths;

    if (selectedCell.col >= sheetData.cols) {
        selectedCell.col = sheetData.cols - 1;
    }

    renderTable();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function showAddRowsModal(direction) {
    const modal = document.getElementById('modal-add');
    const title = document.getElementById('add-modal-title');
    const countInput = document.getElementById('add-count');
    const label = direction === 'below' ? 'Add Rows Below' : 'Add Rows Above';
    title.textContent = label;
    countInput.value = '1';
    modal.classList.add('active');

    const confirmBtn = document.getElementById('btn-add-confirm');
    const cancelBtn = document.getElementById('btn-add-cancel');

    const confirmHandler = () => {
        const count = parseInt(countInput.value) || 1;
        if (direction === 'below') addRowsBelow(count);
        else addRowsAbove(count);
        hideModal('modal-add');
        confirmBtn.removeEventListener('click', confirmHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    const cancelHandler = () => {
        hideModal('modal-add');
        confirmBtn.removeEventListener('click', confirmHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    confirmBtn.addEventListener('click', confirmHandler);
    cancelBtn.addEventListener('click', cancelHandler);
}

function addRowsBelow(count) {
    if (!selectedCell) return;
    const insertAt = selectedCell.row + 1;
    const cols = sheetData.cols;
    pushUndo();
    for (let i = 0; i < count; i++) {
        sheetData.data.splice(insertAt, 0, freshRow(cols));
    }
    sheetData.rows += count;
    layoutState.data_rows = sheetData.rows;
    layoutState.data_cols = sheetData.cols;
    shiftLayoutStateForInsert(insertAt, count);
    console.log('addRowsBelow: now', sheetData.rows, 'rows,', sheetData.cols, 'cols');
    renderTable();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function addRowsAbove(count) {
    if (!selectedCell) return;
    const insertAt = selectedCell.row;
    const cols = sheetData.cols;
    pushUndo();
    for (let i = 0; i < count; i++) {
        sheetData.data.splice(insertAt, 0, freshRow(cols));
    }
    sheetData.rows += count;
    layoutState.data_rows = sheetData.rows;
    layoutState.data_cols = sheetData.cols;
    shiftLayoutStateForInsert(insertAt, count);
    renderTable();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function shiftLayoutStateForInsert(insertAt, count) {
    const newHeights = {};
    for (const key of Object.keys(layoutState.row_heights)) {
        const k = parseInt(key);
        if (k >= insertAt) {
            newHeights[k + count] = layoutState.row_heights[key];
        } else {
            newHeights[k] = layoutState.row_heights[key];
        }
    }
    layoutState.row_heights = newHeights;

    const newHeaderRows = new Set();
    for (const h of headerRows) {
        newHeaderRows.add(h >= insertAt ? h + count : h);
    }
    headerRows = newHeaderRows;
    layoutState.header_rows = Array.from(headerRows);

    if (layoutState.sticky_row !== null && layoutState.sticky_row >= insertAt) {
        layoutState.sticky_row += count;
    }
}

function showAddColsModal(direction) {
    const modal = document.getElementById('modal-add');
    const title = document.getElementById('add-modal-title');
    const countInput = document.getElementById('add-count');
    const label = direction === 'left' ? 'Add Columns Left' : 'Add Columns Right';
    title.textContent = label;
    countInput.value = '1';
    modal.classList.add('active');

    const confirmBtn = document.getElementById('btn-add-confirm');
    const cancelBtn = document.getElementById('btn-add-cancel');

    const confirmHandler = () => {
        const count = parseInt(countInput.value) || 1;
        if (direction === 'left') addColsLeft(count);
        else addColsRight(count);
        hideModal('modal-add');
        confirmBtn.removeEventListener('click', confirmHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    const cancelHandler = () => {
        hideModal('modal-add');
        confirmBtn.removeEventListener('click', confirmHandler);
        cancelBtn.removeEventListener('click', cancelHandler);
    };

    confirmBtn.addEventListener('click', confirmHandler);
    cancelBtn.addEventListener('click', cancelHandler);
}

function addColsLeft(count) {
    if (!selectedCell) return;
    const insertAt = selectedCell.col;
    const cols = sheetData.cols;
    pushUndo();
    sheetData.data.forEach(row => {
        for (let i = 0; i < count; i++) {
            row.splice(insertAt, 0, newCell(''));
        }
    });
    sheetData.cols += count;
    shiftLayoutStateForColInsert(insertAt, count);
    renderTable();
    updateTableWidth();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function addColsRight(count) {
    if (!selectedCell) return;
    const insertAt = selectedCell.col + 1;
    const cols = sheetData.cols;
    pushUndo();
    sheetData.data.forEach(row => {
        for (let i = 0; i < count; i++) {
            row.splice(insertAt, 0, newCell(''));
        }
    });
    sheetData.cols += count;
    shiftLayoutStateForColInsert(insertAt, count);
    renderTable();
    updateTableWidth();
    debouncedSaveSheet();
    debouncedSaveLayout();
}

function shiftLayoutStateForColInsert(insertAt, count) {
    const newWidths = {};
    for (const key of Object.keys(layoutState.column_widths)) {
        const k = parseInt(key);
        if (k >= insertAt) {
            newWidths[k + count] = layoutState.column_widths[key];
        } else {
            newWidths[k] = layoutState.column_widths[key];
        }
    }
    for (let i = 0; i < count; i++) {
        newWidths[insertAt + i] = 100;
    }
    layoutState.column_widths = newWidths;

    const newTypes = {};
    for (const key of Object.keys(columnTypes)) {
        const k = parseInt(key);
        if (k >= insertAt) {
            newTypes[k + count] = columnTypes[key];
        } else {
            newTypes[k] = columnTypes[key];
        }
    }
    columnTypes = newTypes;
    layoutState.columnTypes = { ...columnTypes };
}

function toggleAlternateColors() {
    layoutState.alternate_row_colors = !layoutState.alternate_row_colors;
    renderTable();
    debouncedSaveLayout();
}

function showCellUI() {
    if (!selectedCell) {
        alert('Please select a cell first');
        return;
    }

    const modal = document.getElementById('modal-cell-ui');
    const textPicker = document.getElementById('cell-ui-text-picker');
    const bgPicker = document.getElementById('cell-ui-bg-picker');
    const textSwatches = document.getElementById('cell-ui-text-swatches');
    const bgSwatches = document.getElementById('cell-ui-bg-swatches');

    renderCustomSwatches('text', textSwatches);
    renderCustomSwatches('bg', bgSwatches);
    modal.classList.add('active');

    textPicker.onchange = () => {
        const color = textPicker.value;
        addCustomColor('text', color);
        renderCustomSwatches('text', textSwatches);
    };

    bgPicker.onchange = () => {
        const color = bgPicker.value;
        addCustomColor('bg', color);
        renderCustomSwatches('bg', bgSwatches);
    };

    document.querySelectorAll('.cell-ui-clear').forEach(btn => {
        btn.onclick = () => {
            const target = btn.dataset.target;
            if (target === 'text') {
                clearCellColor('text');
            } else {
                clearCellColor('bg');
            }
        };
    });

    document.getElementById('btn-cell-ui-apply').onclick = () => {
        hideModal('modal-cell-ui');
    };

    document.getElementById('btn-cell-ui-cancel').onclick = () => {
        hideModal('modal-cell-ui');
    };
}

function renderCustomSwatches(type, container) {
    const key = type === 'text' ? 'customTextColors' : 'customBgColors';
    const colors = getCustomColors(type);
    container.innerHTML = '';
    if (colors.length === 0) {
        const empty = document.createElement('span');
        empty.className = 'cell-ui-empty-swatches';
        empty.textContent = 'Pick a color from the wheel to add swatches';
        container.appendChild(empty);
        return;
    }
    colors.forEach(color => {
        const swatch = document.createElement('div');
        swatch.className = 'cell-ui-swatch';
        swatch.style.backgroundColor = color;
        if (color.toLowerCase() === '#ffffff') {
            swatch.style.border = '2px solid #aaa';
        }
        swatch.title = color;
        swatch.dataset.color = color;
        swatch.addEventListener('click', () => {
            if (type === 'text') {
                setCellTextColor(color);
            } else {
                setCellBgColor(color);
            }
        });
        container.appendChild(swatch);
    });
}

function getCustomColors(type) {
    const key = type === 'text' ? 'customTextColors' : 'customBgColors';
    try {
        const stored = localStorage.getItem(key);
        return stored ? JSON.parse(stored) : [];
    } catch {
        return [];
    }
}

function addCustomColor(type, color) {
    const key = type === 'text' ? 'customTextColors' : 'customBgColors';
    const colors = getCustomColors(type);
    const normalized = color.toLowerCase();
    if (!colors.some(c => c.toLowerCase() === normalized)) {
        colors.push(color);
        if (colors.length > 20) colors.shift();
        localStorage.setItem(key, JSON.stringify(colors));
    }
}

function setCellTextColor(color) {
    const targets = selectedCells.length > 1 ? selectedCells : [selectedCell];
    targets.forEach(cell => {
        const existing = sheetData.data[cell.row][cell.col];
        if (existing && typeof existing === 'object' && 'v' in existing) {
            if (!existing.s) existing.s = {};
            existing.s.text = color;
        } else {
            sheetData.data[cell.row][cell.col] = { v: cv(existing), s: { text: color } };
        }
    });
    renderTable();
    debouncedSaveLayout();
}

function setCellBgColor(color) {
    const targets = selectedCells.length > 1 ? selectedCells : [selectedCell];
    targets.forEach(cell => {
        const existing = sheetData.data[cell.row][cell.col];
        if (existing && typeof existing === 'object' && 'v' in existing) {
            if (!existing.s) existing.s = {};
            existing.s.bg = color;
        } else {
            sheetData.data[cell.row][cell.col] = { v: cv(existing), s: { bg: color } };
        }
    });
    renderTable();
    debouncedSaveLayout();
}

function clearCellColor(target) {
    const targets = selectedCells.length > 1 ? selectedCells : [selectedCell];
    targets.forEach(cell => {
        const existing = sheetData.data[cell.row][cell.col];
        if (!existing || typeof existing !== 'object' || !existing.s) return;
        if (target === 'text') {
            delete existing.s.text;
        } else {
            delete existing.s.bg;
        }
        if (!existing.s.bg && !existing.s.text) {
            delete existing.s;
        }
    });
    renderTable();
    debouncedSaveLayout();
}

function startColResize(e, col) {
    e.preventDefault();
    e.stopPropagation();
    const th = e.target.parentElement;
    const startX = e.pageX;
    const startWidth = th.offsetWidth;
    const table = document.getElementById('spreadsheet');
    const colElement = table.querySelector('col[data-col="' + col + '"]');

    function onMouseMove(e) {
        const diff = e.pageX - startX;
        const newWidth = Math.max(50, startWidth + diff);
        if (colElement) {
            colElement.style.width = newWidth + 'px';
        }
        th.style.width = newWidth + 'px';
        const cells = table.querySelectorAll('td[data-col="' + col + '"]');
        cells.forEach(cell => {
            cell.style.width = newWidth + 'px';
        });
        layoutState.column_widths[col] = newWidth;
        updateTableWidth();
    }

    function onMouseUp() {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        debouncedSaveLayout();
    }

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
}

function updateTableWidth() {
    const table = document.getElementById('spreadsheet');
    if (!table || !layoutState) return;

    let totalWidth = 0;
    const cols = table.querySelectorAll('col');
    cols.forEach((col) => {
        const colIndex = col.dataset.col;
        if (colIndex === 'corner') {
            totalWidth += 50;
            return;
        }
        const idx = parseInt(colIndex);
        const width = layoutState.column_widths[idx] || 100;
        totalWidth += width;
    });

    totalWidth += cols.length * 2;
    table.style.width = totalWidth + 'px';
}

// Save
async function saveSheet() {
    try {
        const { plainData } = dehydrateData(sheetData.data);
        const resp = await fetch(BASE + '/api/sheet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentFile,
                sheet_name: currentSheet,
                data: plainData
            })
        });
        const result = await resp.json();
        if (result.error) {
            console.error('Sheet save returned error:', result.error);
        } else {
            console.log('Sheet saved successfully. Rows:', sheetData.data.length, 'Cols:', sheetData.data[0] ? sheetData.data[0].length : 0);
        }
    } catch (err) {
        console.error('Sheet save failed:', err);
    }
}

async function saveLayout() {
    if (!currentFile || !currentSheet) return;
    try {
        const { cell_colors } = dehydrateData(sheetData.data);
        const stateToSave = { ...layoutState, cell_colors };
        await fetch(BASE + '/api/layout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: currentFile,
                sheet_name: currentSheet,
                state: stateToSave
            })
        });
    } catch (err) {
        console.error('Layout save failed:', err);
    }
}

function applyLayout() {
    if (!layoutState) return;
}

function manualSave() {
    flushPendingSaves();
    const msg = document.createElement('div');
    msg.className = 'save-indicator';
    msg.textContent = 'Saved';
    document.querySelector('.top-bar-right').appendChild(msg);
    requestAnimationFrame(() => msg.classList.add('show'));
    setTimeout(() => { msg.classList.remove('show'); setTimeout(() => msg.remove(), 300); }, 1500);
}

// ==================== FILTER / LINKED SHEET ====================

function showFilterModal() {
    if (!selectedCell || !sheetData) return;
    if (isLinkedView) {
        alert('Cannot create a filter from a filtered view. Switch to the original sheet first.');
        return;
    }

    const col = selectedCell.col;
    document.getElementById('filter-col-label').textContent = 'C' + (col + 1);
    document.getElementById('filter-operator').value = 'contains';
    document.getElementById('filter-value').value = '';
    document.getElementById('filter-match-count').textContent = '0 rows match';
    document.getElementById('filter-preview-table').innerHTML = '';
    document.getElementById('filter-preview-table-wrapper').style.display = 'none';
    document.getElementById('filter-preserve-headers').checked = false;

    // Show header info if header rows exist
    const headerInfo = document.getElementById('filter-header-info');
    const headerBadge = document.getElementById('filter-header-badge');
    if (headerRows.size > 0) {
        headerInfo.style.display = 'flex';
        headerBadge.textContent = headerRows.size + ' Header Row(s) Found';
        document.getElementById('filter-match-count').textContent = '0 rows match (headers excluded)';
    } else {
        headerInfo.style.display = 'none';
        document.getElementById('filter-match-count').textContent = '0 rows match';
    }

    const modal = document.getElementById('modal-filter');
    modal.classList.add('active');

    const operatorEl = document.getElementById('filter-operator');
    const valueEl = document.getElementById('filter-value');
    const previewBtn = document.getElementById('btn-filter-preview');
    const okBtn = document.getElementById('btn-filter-ok');
    const cancelBtn = document.getElementById('btn-filter-cancel');

    let currentFiltered = null;

    const previewHandler = async () => {
        const op = operatorEl.value;
        const val = valueEl.value;
        if (!val) {
            alert('Please enter a filter value');
            return;
        }
        const preserveHeaders = document.getElementById('filter-preserve-headers').checked;
        try {
            const resp = await fetch(BASE + '/api/filter-preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_path: currentFile,
                    sheet_name: currentSheet,
                    file_id: currentFileId,
                    filter_col: col,
                    filter_op: op,
                    filter_val: val,
                    preserve_headers: preserveHeaders,
                    header_rows: Array.from(headerRows)
                })
});
            if (!resp.ok) {
                const text = await resp.text();
                throw new Error(text.substring(0, 200));
            }
            const data = await resp.json();
            if (data.error) throw new Error(data.error);
            currentFiltered = data;
            const matchText = data.total_matches + ' rows match';
            document.getElementById('filter-match-count').textContent = preserveHeaders && headerRows.size > 0
                ? matchText + ' (' + (data.total_rows - data.total_matches) + ' header rows preserved)'
                : matchText + ' (headers excluded)';
            renderFilterPreview(data.preview);
        } catch (err) {
            alert('Preview failed: ' + err.message);
        }
    };

    const okHandler = async () => {
        const op = operatorEl.value;
        const val = valueEl.value;
        if (!val) {
            alert('Please enter a filter value');
            return;
        }
        if (!currentFiltered) {
            alert('Click Preview first to validate the filter');
            return;
        }
        const preserveHeaders = document.getElementById('filter-preserve-headers').checked;
        const name = prompt('Enter a name for this filter view:', 'Filter - C' + (col + 1) + ' ' + op + ' ' + val);
        if (!name) return;

        try {
            const resp = await fetch(BASE + '/api/linked-sheet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_path: currentFile,
                    source_sheet: currentSheet,
                    display_name: name,
                    filter_col: col,
                    filter_op: op,
                    filter_val: val,
                    preserve_headers: preserveHeaders
                })
            });
            if (!resp.ok) {
                const text = await resp.text();
                throw new Error(text.substring(0, 200));
            }
            const result = await resp.json();
            if (result.error) throw new Error(result.error);

            hideModal('modal-filter');
            await loadLinkedSheets();
            renderLinkedTabs();
        } catch (err) {
            alert('Failed to create filter view: ' + err.message);
        }
    };

    const cancelHandler = () => {
        hideModal('modal-filter');
    };

    previewBtn.onclick = previewHandler;
    okBtn.onclick = okHandler;
    cancelBtn.onclick = cancelHandler;
}

function renderFilterPreview(previewData) {
    const wrapper = document.getElementById('filter-preview-table-wrapper');
    const table = document.getElementById('filter-preview-table');
    wrapper.style.display = 'block';
    table.innerHTML = '';

    if (!previewData || previewData.length === 0) {
        table.innerHTML = '<tr><td style="padding:12px;color:#888;text-align:center;">No matching rows</td></tr>';
        return;
    }

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    const numCols = previewData[0].length;
    for (let c = 0; c < numCols && c < 10; c++) {
        const th = document.createElement('th');
        th.textContent = 'C' + (c + 1);
        headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    previewData.forEach(row => {
        const tr = document.createElement('tr');
        for (let c = 0; c < numCols && c < 10; c++) {
            const td = document.createElement('td');
            const val = row[c] || '';
            td.textContent = val.length > 20 ? val.substring(0, 20) + '...' : val;
            tr.appendChild(td);
        }
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
}

// ==================== INIT ====================

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('home-view')) {
        initHomePage();
    } else {
        initFilePage();
    }
});
