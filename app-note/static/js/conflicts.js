/**
 * conflicts.js — Conflict resolution UI for NoteStack Web.
 *
 * Renders unresolved sync conflicts in a modal with side-by-side diff.
 * Fully self-contained: deleting this file disables only the conflict UI.
 */

const ConflictUI = (() => {
  let _openConflicts = [];
  const API_ROOT = window.NOTESTACK_API_ROOT || '/api';

  async function loadConflicts() {
    const res = await fetch(API_ROOT + '/sync/conflicts');
    if (!res.ok) return [];
    const data = await res.json();
    _openConflicts = data;
    return data;
  }

  function _escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function _renderCard(conflict) {
    const serverPreview = conflict.server_content.slice(0, 400);
    const clientPreview = conflict.client_content.slice(0, 400);

    return `
      <div class="conflict-card" data-id="${conflict.id}">
        <div class="conflict-card__header">
          <span>${_escHtml(conflict.server_title || conflict.client_title)}</span>
          <span style="font-size:11px;color:var(--text-muted)">${conflict.created_at}</span>
        </div>
        <div class="conflict-card__cols">
          <div class="conflict-col">
            <div class="conflict-col__label">Server version (web edit)</div>
            <div class="conflict-col__content">${_escHtml(serverPreview)}${serverPreview.length < conflict.server_content.length ? '\n…' : ''}</div>
          </div>
          <div class="conflict-col">
            <div class="conflict-col__label">Desktop version</div>
            <div class="conflict-col__content">${_escHtml(clientPreview)}${clientPreview.length < conflict.client_content.length ? '\n…' : ''}</div>
          </div>
        </div>
        <div class="conflict-card__actions">
          <button class="btn btn--sm btn--ghost" data-action="server" data-id="${conflict.id}">
            Keep server
          </button>
          <button class="btn btn--sm btn--ghost" data-action="client" data-id="${conflict.id}">
            Keep desktop
          </button>
          <button class="btn btn--sm btn--primary" data-action="custom" data-id="${conflict.id}">
            Edit &amp; merge
          </button>
        </div>
      </div>`;
  }

  async function _resolve(conflictId, choice, customTitle, customContent) {
    const body = { choice };
    if (choice === 'custom') {
      body.title = customTitle;
      body.content = customContent;
    }
    const res = await fetch(`${API_ROOT}/sync/conflicts/${conflictId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.ok;
  }

  async function _handleAction(conflictId, choice) {
    if (choice === 'custom') {
      const conflict = _openConflicts.find(c => c.id === conflictId);
      if (!conflict) return;
      // Prompt the user to merge in a simple textarea dialog
      const merged = await showPrompt(
        'Edit the merged content (title stays as server version):',
        conflict.server_content
      );
      if (merged === null) return; // cancelled
      const title = conflict.server_title || conflict.client_title;
      await _resolve(conflictId, 'custom', title, merged);
    } else {
      await _resolve(conflictId, choice, null, null);
    }
    // Refresh
    await renderModal();
    // Notify app.js if callback registered
    if (typeof window._onConflictResolved === 'function') {
      window._onConflictResolved();
    }
  }

  async function renderModal() {
    const conflicts = await loadConflicts();
    const list = document.getElementById('conflicts-list');
    const modal = document.getElementById('conflicts-modal');
    const banner = document.getElementById('conflict-banner');
    const countEl = document.getElementById('conflict-count');

    if (countEl) countEl.textContent = conflicts.length;
    if (banner) banner.hidden = conflicts.length === 0;

    if (!list) return;

    if (conflicts.length === 0) {
      list.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No conflicts. All clear!</p>';
      if (modal) modal.hidden = true;
      return;
    }

    list.innerHTML = conflicts.map(_renderCard).join('');

    // Attach listeners
    list.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id, 10);
        const action = btn.dataset.action;
        _handleAction(id, action);
      });
    });
  }

  function open() {
    const modal = document.getElementById('conflicts-modal');
    if (modal) modal.hidden = false;
    renderModal();
  }

  function close() {
    const modal = document.getElementById('conflicts-modal');
    if (modal) modal.hidden = true;
  }

  // Wire close button
  document.addEventListener('DOMContentLoaded', () => {
    const closeBtn = document.getElementById('btn-conflicts-close');
    if (closeBtn) closeBtn.addEventListener('click', close);

    const showBtn = document.getElementById('btn-show-conflicts');
    if (showBtn) showBtn.addEventListener('click', open);

    // Initial check
    loadConflicts().then(conflicts => {
      const banner = document.getElementById('conflict-banner');
      const countEl = document.getElementById('conflict-count');
      if (countEl) countEl.textContent = conflicts.length;
      if (banner) banner.hidden = conflicts.length === 0;
    });
  });

  return { open, close, renderModal, loadConflicts };
})();

window.ConflictUI = ConflictUI;
