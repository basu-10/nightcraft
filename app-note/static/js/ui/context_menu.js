/**
 * context_menu.js — Right-click (desktop) and long-press context menu.
 *
 * Self-contained, framework-free module. Owns its own DOM element (#ctx-menu),
 * open/close lifecycle, positioning and outside-click dismissal.
 *
 * Intentionally kept separate from the FAB menu (fab_menu.js). The two will
 * diverge over time: the context menu gains extra entries such as "Select all"
 * and may be themed differently, while the FAB menu is anchored to the FAB and
 * uses the brand palette.
 *
 * Exposes `window.NotestackContextMenu` with `show(x, y, items, onClose)` and
 * `hide()`.
 *
 * Item shape:
 *   - "sep"                       → visual separator
 *   - { label, action }           → clickable entry
 *   - { label, action, danger }   → destructive entry (red)
 *   - { label, action, active }   → currently-selected entry (bold)
 */

(() => {
  "use strict";

  const MENU_ID = "ctx-menu";

  let menuEl = null;
  let cleanup = null;
  let onCloseCb = null;

  function getMenuEl() {
    if (!menuEl) menuEl = document.getElementById(MENU_ID);
    return menuEl;
  }

  function renderItems(container, items) {
    container.innerHTML = "";
    items.forEach((item) => {
      if (item === "sep") {
        const sep = document.createElement("div");
        sep.className = "ctx-menu__sep";
        container.appendChild(sep);
        return;
      }

      const el = document.createElement("button");
      el.type = "button";
      el.className = "ctx-menu__item";
      if (item.danger) el.classList.add("ctx-menu__item--danger");
      if (item.active) el.classList.add("ctx-menu__item--active");
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
          console.error("Context menu action failed:", err);
        }
      });

      container.appendChild(el);
    });
  }

  function position(menuEl, x, y) {
    menuEl.hidden = false;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const mw = menuEl.offsetWidth || 180;
    const mh = menuEl.offsetHeight || 200;
    menuEl.style.left = (x + mw > vw ? vw - mw - 8 : x) + "px";
    menuEl.style.top = (y + mh > vh ? vh - mh - 8 : y) + "px";
  }

  function show(x, y, items, onClose) {
    const el = getMenuEl();
    if (!el) return;
    hide();
    renderItems(el, items);
    position(el, x, y);

    const dismiss = (e) => {
      if (!el.contains(e.target)) hide();
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape") hide();
    };
    // Defer listeners so the opening event doesn't instantly close the menu.
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
    onCloseCb = onClose || null;
  }

  function hide() {
    const el = getMenuEl();
    if (!el) return;
    el.hidden = true;
    el.innerHTML = "";
    if (onCloseCb) {
      onCloseCb();
      onCloseCb = null;
    }
    if (cleanup) {
      cleanup();
      cleanup = null;
    }
  }

  window.NotestackContextMenu = { show, hide };
})();
