/*
 * NoteStack native dialogs
 * ------------------------
 * Replaces the browser's default alert/confirm/prompt with app-native,
 * styled modals that match the rest of the UI (see `.modal-overlay` /
 * `.modal` styles in style.css). Every entry point returns a Promise so
 * callers can `await` the user's choice.
 *
 * Public API (global `NoteDialog` + convenience globals):
 *   NoteDialog.alert(message, opts)            -> Promise<void>
 *   NoteDialog.confirm(message, opts)           -> Promise<boolean>
 *   NoteDialog.prompt(message, value, opts)     -> Promise<string|null>
 *   NoteDialog.open({...})                      -> Promise<any>
 *
 * All user-provided strings are inserted as text (never HTML) to avoid
 * any injection from note/folder names etc.
 */

(function () {
  "use strict";

  const DEFAULTS = {
    title: "",
    okLabel: "OK",
    cancelLabel: "Cancel",
  };

  let activeOverlay = null;

  function clearActive() {
    if (activeOverlay && activeOverlay.parentNode) {
      activeOverlay.parentNode.removeChild(activeOverlay);
    }
    activeOverlay = null;
    document.removeEventListener("keydown", onKeydown, true);
    document.body.style.overflow = "";
  }

  function onKeydown(e) {
    if (!activeOverlay) return;
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      const cancel = activeOverlay._cancel;
      if (cancel) cancel();
    } else if (e.key === "Enter" && !e.shiftKey) {
      const def = activeOverlay._default;
      if (!def) return;
      if (document.activeElement === def._input && def._input.tagName === "TEXTAREA") return;
      e.preventDefault();
      def._resolve();
    }
  }

  function focusFirst(overlay) {
    const target = overlay.querySelector("[data-autofocus]") || overlay.querySelector("button");
    if (target) target.focus();
  }

  /**
   * Open a native dialog.
   * @param {Object} opts
   *   title        {string}
   *   message      {string|Node}  optional body text
   *   body         {Node}         optional custom body element
   *   input        {Object}       { value, multiline, placeholder } -> turns dialog into a prompt
   *   actions      {Array}        [{ label, value, variant, autofocus }]
   *   danger       {boolean}      style the primary action as danger
   *   dismissable  {boolean}      clicking the scrim cancels (default true)
   *   onCancel     {Function}     resolve value when dismissed (default null/false)
   * @returns {Promise<any>}
   */
  function open(opts) {
    opts = opts || {};
    return new Promise((resolve) => {
      if (activeOverlay) clearActive();

      const overlay = document.createElement("div");
      overlay.className = "modal-overlay";
      overlay.setAttribute("role", "dialog");
      overlay.setAttribute("aria-modal", "true");

      const modal = document.createElement("div");
      modal.className = "modal";

      let inputEl = null;

      if (opts.title) {
        const title = document.createElement("h2");
        title.className = "modal__title";
        title.textContent = opts.title;
        modal.appendChild(title);
      }

      if (opts.message != null) {
        const p = document.createElement("p");
        p.className = "form-hint";
        if (opts.message instanceof Node) p.appendChild(opts.message);
        else p.textContent = opts.message;
        modal.appendChild(p);
      }

      if (opts.body) modal.appendChild(opts.body);

      if (opts.input) {
        const label = document.createElement("label");
        label.className = "form-label";
        label.textContent = opts.input.placeholder || "";
        inputEl = document.createElement(opts.input.multiline ? "textarea" : "input");
        if (opts.input.multiline) {
          inputEl.rows = 6;
          inputEl.style.resize = "vertical";
        } else {
          inputEl.type = "text";
        }
        inputEl.className = "form-input";
        if (opts.input.value != null) inputEl.value = opts.input.value;
        if (opts.input.placeholder) inputEl.placeholder = opts.input.placeholder;
        inputEl.setAttribute("data-autofocus", "");
        if (label.textContent) label.appendChild(inputEl);
        else modal.appendChild(inputEl);
        if (label.textContent) modal.appendChild(label);
        inputEl._input = true;
      }

      const actions = opts.actions || [
        { label: DEFAULTS.cancelLabel, value: null, variant: "ghost" },
        { label: DEFAULTS.okLabel, value: true, variant: opts.danger ? "danger" : "primary", autofocus: true },
      ];

      const bar = document.createElement("div");
      bar.className = "modal__actions";

      let defaultAction = null;

      function finish(value) {
        clearActive();
        resolve(value);
      }

      actions.forEach((action) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn--" + (action.variant || "ghost");
        btn.textContent = action.label;
        if (action.autofocus) btn.setAttribute("data-autofocus", "");
        btn.addEventListener("click", () => {
          let value = action.value;
          if (inputEl && value !== null && typeof value !== "boolean") {
            value = inputEl.value;
          } else if (inputEl && action.value === true) {
            value = inputEl.value;
          }
          finish(value);
        });
        if (action.value && action.value !== null && action.value !== false) {
          // resolved value is the input content for prompt-style
          btn._resolve = () => finish(inputEl ? inputEl.value : action.value);
          if (!defaultAction) defaultAction = btn;
        } else if (action.value === true && inputEl) {
          btn._resolve = () => finish(inputEl.value);
          defaultAction = btn;
        } else if (action.value === true) {
          btn._resolve = () => finish(true);
          defaultAction = btn;
        }
        btn._input = inputEl;
        bar.appendChild(btn);
      });

      modal.appendChild(bar);
      overlay.appendChild(modal);

      const cancelResolve = () =>
        finish(opts.onCancel !== undefined ? opts.onCancel : (inputEl ? null : false));

      overlay._cancel = cancelResolve;
      overlay._default = defaultAction;

      overlay.addEventListener("click", (e) => {
        if (e.target === overlay && opts.dismissable !== false) cancelResolve();
      });

      document.body.appendChild(overlay);
      document.body.style.overflow = "hidden";
      activeOverlay = overlay;
      document.addEventListener("keydown", onKeydown, true);
      requestAnimationFrame(() => focusFirst(overlay));
    });
  }

  const api = {
    open,

    alert(message, opts) {
      opts = Object.assign({}, DEFAULTS, opts);
      return open({
        title: opts.title,
        message,
        actions: [{ label: opts.okLabel, value: true, variant: "primary", autofocus: true }],
        onCancel: undefined,
      });
    },

    confirm(message, opts) {
      opts = Object.assign({}, DEFAULTS, opts);
      return open({
        title: opts.title,
        message,
        danger: opts.danger,
        actions: [
          { label: opts.cancelLabel, value: false, variant: "ghost", autofocus: true },
          { label: opts.okLabel, value: true, variant: opts.danger ? "danger" : "primary" },
        ],
        onCancel: false,
      });
    },

    prompt(message, value, opts) {
      opts = Object.assign({}, DEFAULTS, opts);
      return open({
        title: opts.title,
        message,
        input: {
          value: value != null ? value : "",
          multiline: !!opts.multiline,
          placeholder: opts.placeholder || "",
        },
        actions: [
          { label: opts.cancelLabel, value: null, variant: "ghost", autofocus: true },
          { label: opts.okLabel, value: true, variant: "primary" },
        ],
        onCancel: null,
      });
    },
  };

  window.NoteDialog = api;
  window.showAlert = api.alert;
  window.showConfirm = api.confirm;
  window.showPrompt = api.prompt;

  // ── Declarative form confirm ───────────────────────────────────────────────
  // Any <form data-confirm="..."> is intercepted: submission is paused and the
  // native confirm dialog is shown. Add `data-confirm-danger` to style the
  // confirm action as destructive. All original form fields (incl. CSRF
  // tokens) are preserved on the real submission.
  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!form || typeof form.hasAttribute !== "function") return;
    if (!form.hasAttribute("data-confirm")) return;
    if (form._confirmSkip) {
      form._confirmSkip = false;
      return;
    }
    e.preventDefault();
    api
      .confirm(form.getAttribute("data-confirm"), {
        danger: form.hasAttribute("data-confirm-danger"),
      })
      .then(function (ok) {
        if (ok) {
          form._confirmSkip = true;
          form.submit();
          setTimeout(function () {
            form._confirmSkip = false;
          }, 0);
        }
      });
  });
})();
