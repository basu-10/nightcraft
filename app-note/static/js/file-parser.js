/**
 * file-parser.js — Plaintext file parser for drag-and-drop imports.
 *
 * Exports:
 *   - isSupportedFile(file): boolean - Check if file type is supported
 *   - parseFile(file): Promise<{title: string, content: string, extension: string} | null>
 */

(() => {
    "use strict";

    // Supported plaintext extensions (lowercase without dot)
    const SUPPORTED_EXTENSIONS = new Set([
        "txt", "md", "markdown", "text", "log", "json", "jsonl",
        "yaml", "yml", "xml", "html", "htm", "css", "js", "ts",
        "py", "rb", "go", "rs", "java", "c", "cpp", "h", "hpp",
        "sh", "bash", "zsh", "sql", "csv", "tsv", "ini", "cfg",
        "conf", "toml", "ini", "env", "dockerfile", "makefile"
    ]);

    /**
     * Check if the file has a supported plaintext extension.
     * Returns false for files without extension or unsupported binary formats.
     */
    function isSupportedFile(file) {
        if (!file || !file.name) return false;
        const ext = getFileExtension(file.name);
        if (!ext) return false;
        return SUPPORTED_EXTENSIONS.has(ext);
    }

    /**
     * Extract file extension without the leading dot.
     * Handles compound extensions like .tar.gz (returns 'gz') and files with no extension.
     */
    function getFileExtension(filename) {
        if (!filename || typeof filename !== "string") return "";
        const lastDot = filename.lastIndexOf(".");
        if (lastDot === -1 || lastDot === filename.length - 1) return "";
        const ext = filename.slice(lastDot + 1).toLowerCase();
        // Handle dotfiles (e.g., .env, .gitignore) - treat as no extension but allow
        if (filename.indexOf(".") === 0 && lastDot === 0) return ext;
        // Handle Dockerfile, Makefile - no extension but treat as supported
        if (lastDot === 0) return ext;
        return ext;
    }

    /**
     * Parse a file and extract title, content, and extension.
     * Returns null if parsing fails.
     */
    async function parseFile(file) {
        if (!file) return null;
        if (!isSupportedFile(file)) return null;

        try {
            const content = await file.text();
            const title = getFileNameWithoutExtension(file.name);
            const extension = getFileExtension(file.name);
            return {
                title: title || "Untitled",
                content: content || "",
                extension: extension || ""
            };
        } catch (err) {
            console.error("Failed to parse file:", err);
            return null;
        }
    }

    /**
     * Get filename without extension.
     */
    function getFileNameWithoutExtension(filename) {
        if (!filename) return "Untitled";
        const lastDot = filename.lastIndexOf(".");
        if (lastDot === -1) return filename;
        return filename.slice(0, lastDot);
    }

    // Export to window for non-module usage (app.js uses vanilla JS without build)
    window.FileParser = {
        isSupportedFile,
        parseFile,
        getFileExtension,
        getFileNameWithoutExtension,
        SUPPORTED_EXTENSIONS
    };
})();