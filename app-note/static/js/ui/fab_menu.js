/**
 * fab_menu.js — Menu anchored to the create FAB's caret button.
 *
 * Self-contained, framework-free module. Renders its own menu element, positions
 * it above the FAB (flipping below only when there isn't room), and handles
 * outside-click / Escape dismissal.
 *
 * Kept intentionally separate from the right-click context menu
 * (context_menu.js): this menu is brand-themed (coral) to match the FAB and is
 * anchored to a trigger element rather than an (x, y) point. The two will gain
 * different options and theming over time.
 *
 * Exposes `window.NotestackFabMenu` with `show(anchorEl, items, opts)` and
 * `hide()`.
 *
 * Item shape: same as the context menu —
 *   - "sep"                   → visual separator
 *   - { label, action }       → clickable entry
 *   - { label, action, danger } → destructive entry
 */

(() => {
  "use strict";

  const MENU_ID = "fab-menu";
  const GAP = 8;

  let menuEl = null;
  let cleanup = null;
  let onCloseCb = null;

  function ensureMenuEl() {
    if (menuEl) return menuEl;
    menuEl = document.createElement("div");
    menuEl.id = MENU_ID;
    menuEl.className = "fab-menu";
    menuEl.hidden = true;
    document.body.appendChild(menuEl);
    return menuEl;
  }

  function renderItems(container, items) {
    container.innerHTML = "";
    items.forEach((item) => {
      if (item === "sep") {
        const sep = document.createElement("div");
        sep.className = "fab-menu__sep";
        container.appendChild(sep);
        return;
      }

      const el = document.createElement("button");
      el.type = "button";
      el.className = "fab-menu__item";
      if (item.danger) el.classList.add("fab-menu__item--danger");
      el.textContent = item.label;

      // Prevent the global dismiss handler from swallowing the click.
      el.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
      });

      el.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        hide();
        try {
          await item.action();
        } catch (err) {
          console.error("FAB menu action failed:", err);
        }
      });

      container.appendChild(el);
    });
  }

  function positionAbove(menuEl, anchorRect) {
    const mw = menuEl.offsetWidth;
    const mh = menuEl.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Right-align the menu with the FAB, clamped to the viewport.
    let left = anchorRect.right - mw;
    if (left < GAP) left = GAP;
    if (left + mw > vw - GAP) left = vw - mw - GAP;

    // Prefer appearing above the FAB; flip below if there isn't room.
    let top = anchorRect.top - mh - GAP;
    if (top < GAP) top = anchorRect.bottom + GAP;
    if (top + mh > vh - GAP) top = vh - mh - GAP;

    menuEl.style.left = left + "px";
    menuEl.style.top = top + "px";
  }

  function show(anchorEl, items, opts = {}) {
    const el = ensureMenuEl();
    hide();
    renderItems(el, items);
    el.hidden = false;
    positionAbove(el, anchorEl.getBoundingClientRect());

    const dismiss = (e) => {
      if (!el.contains(e.target)) hide();
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape") hide();
    };
    setTimeout(() => {
      if (el.hidden) return;
      document.addEventListener("mousedown", dismiss);
      document.addEventListener("contextmenu", dismiss);
      document.addEventListener("keydown", onKeyDown);
    }, 0);

    cleanup = () => {
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("contextmenu", dismiss);
      document.removeEventListener("keydown", onKeyDown);
    };
    onCloseCb = opts.onClose || null;
  }

  function hide() {
    if (!menuEl) return;
    menuEl.hidden = true;
    menuEl.innerHTML = "";
    if (onCloseCb) {
      onCloseCb();
      onCloseCb = null;
    }
    if (cleanup) {
      cleanup();
      cleanup = null;
    }
  }

  window.NotestackFabMenu = { show, hide };
})();
