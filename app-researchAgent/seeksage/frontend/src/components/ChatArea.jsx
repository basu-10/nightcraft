import { useState, useRef, useEffect, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import Spinner from "./Spinner";
import WorkspaceHeader from "./WorkspaceHeader";
import { api } from "../api";
import { useMessages } from "../hooks/useMessages";

export default function ChatArea({
  session,
  workspace,
  run,
  polling,
  pendingState,
  onRunStart,
  onPendingStateChange,
  onSessionRename,
  onFilesAdded,
  onCreateSession,
}) {
  const { messages, loading: msgLoading, reload: reloadMessages, appendMessage } = useMessages(session?.id);
  const [query, setQuery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const fileInputRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    setTitleDraft(session?.title || "");
  }, [session?.id, session?.title]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, polling]);

  // When run finishes, refresh messages to get the final assistant message
  useEffect(() => {
    if (run && (run.status === "done" || run.status === "error")) {
      reloadMessages();
    }
  }, [run, reloadMessages]);

  const deriveSessionTitleFromPrompt = useCallback((text) => {
    const normalized = (text || "").replace(/\s+/g, " ").trim();
    if (!normalized) return "";
    const max = 70;
    return normalized.length > max ? `${normalized.slice(0, max - 1)}...` : normalized;
  }, []);

  const shouldAutoTitleFromPrompt = useCallback(() => {
    const title = (session?.title || "").trim().toLowerCase();
    return !title || title === "new chat";
  }, [session?.title]);

  const sendQuery = useCallback(async (rawQuery) => {
    const text = `${rawQuery || ""}`.trim();
    if (!text || !session || polling || submitting) return;
    const isFirstUserPrompt = messages.filter((m) => m.role === "user").length === 0;

    setQuery("");
    setSubmitting(true);
    onPendingStateChange?.(session.id, {
      queryText: text,
      startedAt: new Date().toISOString(),
    });
    appendMessage({ id: Date.now(), role: "user", content: text });
    try {
      if (isFirstUserPrompt && shouldAutoTitleFromPrompt()) {
        const nextTitle = deriveSessionTitleFromPrompt(text);
        if (nextTitle) {
          onSessionRename?.(session.id, nextTitle).catch(() => {});
        }
      }
      const runData = await api.enqueueRun(session.id, text);
      onRunStart?.(runData.id);
    } catch (err) {
      appendMessage({ id: Date.now() + 1, role: "assistant", content: `⚠ Error: ${err.message}` });
    } finally {
      onPendingStateChange?.(session.id, null);
      setSubmitting(false);
    }
  }, [session, polling, submitting, messages, appendMessage, shouldAutoTitleFromPrompt, deriveSessionTitleFromPrompt, onSessionRename, onRunStart, onPendingStateChange]);

  const handleSend = useCallback(async () => {
    await sendQuery(query);
  }, [query, sendQuery]);

  const handleRetry = useCallback(async (assistantMessage) => {
    if (!assistantMessage?.id) return;
    const idx = messages.findIndex((m) => m.id === assistantMessage.id);
    if (idx <= 0) return;
    for (let i = idx - 1; i >= 0; i -= 1) {
      if (messages[i].role === "user" && messages[i].content?.trim()) {
        await sendQuery(messages[i].content);
        break;
      }
    }
  }, [messages, sendQuery]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  const busy = polling || submitting;

  const handleRenameCommit = async () => {
    const next = titleDraft.trim();
    if (!session || !next || next === session.title) return;
    await onSessionRename?.(session.id, next);
  };

  const handleSelectFiles = (e) => {
    const files = Array.from(e.target.files || []);
    onFilesAdded?.(files);
    e.target.value = "";
  };

  return (
    <div className="chat-area">
      <WorkspaceHeader workspace={workspace} />
      <div className="chat-session-bar">
        {session ? (
          <input
            className="chat-session-title-input"
            value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={handleRenameCommit}
            onKeyDown={(e) => e.key === "Enter" && handleRenameCommit()}
          />
        ) : (
          <div className="chat-session-empty-actions">
            <span className="chat-session-title">Select a session</span>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => onCreateSession?.()}
              disabled={!workspace || polling || submitting}
            >
              + New Chat
            </button>
          </div>
        )}
      </div>

      <div className="chat-messages">
        {msgLoading && <Spinner />}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onRetry={msg.role === "assistant" ? handleRetry : undefined}
          />
        ))}
        {(pendingState || polling) && (
          <div className="msg-bubble msg-assistant msg-thinking">
            <Spinner size={16} />
            {pendingState?.queryText
              ? `Working on: ${pendingState.queryText.slice(0, 90)}${pendingState.queryText.length > 90 ? "..." : ""}`
              : "Thinking..."}
          </div>
        )}
        {!session && !msgLoading && (
          <div className="chat-empty-state">
            <p>Select a session from Chat History to continue.</p>
            <button
              className="btn btn-primary"
              onClick={() => onCreateSession?.()}
              disabled={!workspace || polling || submitting}
            >
              Start New Chat In This Workspace
            </button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={handleSelectFiles}
        />
        <textarea
          className="chat-input"
          placeholder={session ? "Ask anything… (Ctrl+Enter to send)" : "Select a session to start chatting"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!session || busy}
          rows={3}
        />
        <div className="chat-input-actions">
          <button
            className="btn btn-secondary attach-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={!session || busy}
            title="Attach files"
            aria-label="Attach files"
          >
            + File
          </button>
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={!session || busy || !query.trim()}
          >
            {busy ? <Spinner size={16} /> : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
