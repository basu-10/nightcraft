import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { useState } from "react";

async function copyText(value) {
  const text = `${value || ""}`;
  if (!text) return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const node = document.createElement("textarea");
  node.value = text;
  node.setAttribute("readonly", "");
  node.style.position = "fixed";
  node.style.left = "-9999px";
  document.body.appendChild(node);
  node.select();
  document.execCommand("copy");
  document.body.removeChild(node);
}

export default function MessageBubble({ message, onRetry }) {
  const isUser = message.role === "user";
  const [copyStatus, setCopyStatus] = useState("idle");

  const handleCopy = async () => {
    try {
      await copyText(message.content);
      setCopyStatus("copied");
      window.setTimeout(() => setCopyStatus("idle"), 1200);
    } catch {
      setCopyStatus("error");
      window.setTimeout(() => setCopyStatus("idle"), 1200);
    }
  };

  return (
    <div className={`msg-bubble ${isUser ? "msg-user" : "msg-assistant"}`}>
      <div className="msg-content">
        {isUser ? (
          <span className="msg-text">{message.content}</span>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              table: ({ children, ...props }) => (
                <div className="md-table-wrapper">
                  <table {...props}>{children}</table>
                </div>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>
      <div className="msg-actions" role="group" aria-label="Message actions">
        <button className="msg-action-btn" onClick={handleCopy}>
          {copyStatus === "copied" ? "Copied" : copyStatus === "error" ? "Copy failed" : "Copy"}
        </button>
        {!isUser && (
          <button className="msg-action-btn" onClick={() => onRetry?.(message)}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
