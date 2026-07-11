/**
 * drag-drop-handler.js — Drag and drop file import handler.
 *
 * Modular, testable drag-and-drop functionality for importing plaintext files.
 * Only allows import in All Notes, Folder views. Shows visual feedback.
 */

(() => {
    "use strict";

    // State enum for drag zones
    const DragState = {
        ALLOWED: "allowed",
        DENIED: "denied"
    };

    let mainContentEl = null;
    let dragOverlayEl = null;
    let toastEl = null;

    // Track current view state (provided by app)
    let getCurrentSection = () => "all";
    let getCurrentFolderId = () => null;

    /**
     * Initialize the drag drop handler.
     * Pass callbacks to get current view state from app.
     */
    function init(options = {}) {
        mainContentEl = document.querySelector(".main-content");
        if (options.getSection) getCurrentSection = options.getSection;
        if (options.getFolderId) getCurrentFolderId = options.getFolderId;
        createDragOverlay();
        createToastContainer();
        bindDragEvents();
    }

    /**
     * Create the drag overlay element for visual feedback.
     */
    function createDragOverlay() {
        if (dragOverlayEl) return;
        dragOverlayEl = document.createElement("div");
        dragOverlayEl.id = "drag-overlay";
        dragOverlayEl.className = "drag-overlay";
        dragOverlayEl.hidden = true;
        dragOverlayEl.innerHTML = `
            <div class="drag-overlay__content">
                <div class="drag-overlay__icon">📄</div>
                <div class="drag-overlay__text">Drop file to import</div>
            </div>
        `;
        document.body.appendChild(dragOverlayEl);
    }

    /**
     * Create toast container for notifications.
     */
    function createToastContainer() {
        if (toastEl) return;
        toastEl = document.createElement("div");
        toastEl.id = "toast-notification";
        toastEl.className = "toast-notification";
        toastEl.hidden = true;
        toastEl.innerHTML = `
            <div class="toast-notification__icon" id="toast-icon"></div>
            <div class="toast-notification__message" id="toast-message"></div>
        `;
        document.body.appendChild(toastEl);
    }

    /**
     * Check if the current view allows drag and drop.
     */
    function isDropAllowed() {
        const section = getCurrentSection();
        const folderId = getCurrentFolderId();
        // Allow: all notes view, any folder view
        // Deny: trash, favorites
        if (section === "trash") return false;
        if (section === "favorites") return false;
        return true;
    }

    /**
     * Show the drag overlay with appropriate color.
     */
    function showDragOverlay() {
        if (!dragOverlayEl) return;
        const allowed = isDropAllowed();
        dragOverlayEl.classList.remove("drag-overlay--allowed", "drag-overlay--denied");
        dragOverlayEl.classList.add(allowed ? "drag-overlay--allowed" : "drag-overlay--denied");
        dragOverlayEl.hidden = false;
    }

    /**
     * Hide the drag overlay.
     */
    function hideDragOverlay() {
        if (!dragOverlayEl) return;
        dragOverlayEl.hidden = true;
    }

    /**
     * Show a toast notification.
     */
    function showToast(message, type = "info", duration = 3000) {
        if (!toastEl) {
            createToastContainer();
        }
        const iconEl = document.getElementById("toast-icon");
        const msgEl = document.getElementById("toast-message");
        
        if (iconEl) {
            const icons = {
                "success": "✓",
                "error": "✕",
                "info": "ℹ",
                "warning": "⚠"
            };
            iconEl.textContent = icons[type] || icons.info;
            iconEl.className = `toast-notification__icon toast-notification__icon--${type}`;
        }
        if (msgEl) {
            msgEl.textContent = message;
        }
        
        toastEl.className = "toast-notification";
        toastEl.hidden = true;
        toastEl.classList.add(`toast-notification--${type}`);
        toastEl.hidden = false;
        
        // Auto-hide after duration
        clearTimeout(hideToast._timer);
        hideToast._timer = setTimeout(() => hideToast(), duration);
    }

    /**
     * Hide the toast notification.
     */
    function hideToast() {
        if (!toastEl) return;
        toastEl.hidden = true;
    }

    /**
     * Bind drag and drop events to the main content area.
     */
    function bindDragEvents() {
        if (!mainContentEl) return;

        // Prevent default drag behaviors
        ["dragenter", "dragover", "dragleave", "drop"].forEach(eventName => {
            mainContentEl.addEventListener(eventName, preventDefaults, false);
            document.body.addEventListener(eventName, preventDefaults, false);
        });

        // Highlight drop zone when item is dragged over it
        mainContentEl.addEventListener("dragenter", () => {
            showDragOverlay();
        });

        mainContentEl.addEventListener("dragover", (e) => {
            // Show preview feedback
            if (e.dataTransfer) {
                if (isDropAllowed()) {
                    e.dataTransfer.dropEffect = "copy";
                } else {
                    e.dataTransfer.dropEffect = "none";
                }
            }
        });

        mainContentEl.addEventListener("dragleave", (e) => {
            // Only hide if we're leaving the main content area entirely
            if (!mainContentEl.contains(e.relatedTarget)) {
                hideDragOverlay();
            }
        });

        // Handle dropped files
        mainContentEl.addEventListener("drop", handleDrop);
    }

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    /**
     * Handle the drop event.
     */
    async function handleDrop(e) {
        hideDragOverlay();
        
        const dt = e.dataTransfer;
        if (!dt || !dt.files || dt.files.length === 0) {
            showToast("No files detected", "warning");
            return;
        }

        const files = Array.from(dt.files);
        if (files.length === 0) {
            showToast("No files detected", "warning");
            return;
        }

        // Only process single file for now
        const file = files[0];
        
        // Check if drop is allowed
        if (!isDropAllowed()) {
            showToast("Cannot import files to this view (Trash/Favorites not supported)", "error");
            return;
        }

        // Validate file type
        if (!window.FileParser || !window.FileParser.isSupportedFile(file)) {
            showToast(`"${file.name}" is not a supported plaintext file. Only .txt, .md, and similar text formats are supported.`, "error");
            return;
        }

        // Parse the file
        if (!window.FileParser || !window.FileParser.parseFile) {
            showToast("File parser not available", "error");
            return;
        }

        try {
            const parsed = await window.FileParser.parseFile(file);
            if (!parsed) {
                showToast(`Could not read "${file.name}"`, "error");
                return;
            }

            // Create note via API (folder hierarchy only, no tags/dates)
            const folderId = getCurrentFolderId();
            const noteData = {
                title: parsed.title,
                content: parsed.content,
                folder_id: folderId || null,
                editor_type: "lexical",
                original_extension: parsed.extension
            };

            // Call the API through app's api function or directly
            if (window.DragDropAPI && window.DragDropAPI.createNote) {
                await window.DragDropAPI.createNote(noteData);
                showToast(`Imported "${parsed.title}" as a note`, "success", 2500);
                
                // Trigger UI refresh
                if (window.DragDropAPI.refreshNotes) {
                    window.DragDropAPI.refreshNotes();
                }
                
                // Highlight the new note briefly
                highlightNewNote(parsed.title);
            } else {
                showToast("Import handler not connected to API", "error");
            }
        } catch (err) {
            console.error("Drop import failed:", err);
            showToast(`Failed to import "${file.name}": ${err?.message || "Unknown error"}`, "error");
        }
    }

    /**
     * Highlight the newly created note in the list.
     */
    function highlightNewNote(title) {
        // Find the note card and apply glow effect
        const noteCards = document.querySelectorAll(".note-card");
        for (const card of noteCards) {
            const cardTitle = card.querySelector(".note-card__title");
            if (cardTitle && cardTitle.textContent.trim() === title) {
                card.classList.add("note-card--glow");
                setTimeout(() => {
                    card.classList.remove("note-card--glow");
                }, 2000);
                break;
            }
        }
    }

    // Export to window
    window.DragDropHandler = {
        init,
        showToast,
        hideToast,
        showDragOverlay,
        hideDragOverlay,
        isDropAllowed,
        DragState
    };
})();