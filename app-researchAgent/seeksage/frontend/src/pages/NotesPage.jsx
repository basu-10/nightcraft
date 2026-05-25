import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

export default function NotesPage() {
  const [notes, setNotes] = useState([]);
  const [query, setQuery] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [form, setForm] = useState({ title: "", body: "", tags: "", workspace: "", project: "", session: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    api.listNotes().then(setNotes).catch((err) => setError(err.message));
  }, []);

  const filtered = useMemo(() => {
    return notes
      .filter((n) => !query || `${n.title} ${n.body}`.toLowerCase().includes(query.toLowerCase()))
      .filter((n) => !tagFilter || (n.tags || []).some((t) => t.toLowerCase().includes(tagFilter.toLowerCase())))
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }, [notes, query, tagFilter]);

  const saveNote = async () => {
    if (!form.title.trim()) return;
    const payload = {
      title: form.title.trim(),
      body: form.body.trim(),
      tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      workspace_id: form.workspace.trim() || null,
      project_id: form.project.trim() || null,
      chat_session_id: form.session.trim() || null,
    };
    try {
      const note = await api.createNote(payload);
      setNotes((prev) => [note, ...prev]);
    } catch (err) {
      setError(err.message);
      return;
    }
    setForm({ title: "", body: "", tags: "", workspace: "", project: "", session: "" });
  };

  const remove = async (id) => {
    try {
      await api.deleteNote(id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
    } catch (err) {
      setError(err.message);
    }
  };

  const exportNotes = () => {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "seeksage-notes.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="settings-page">
      <h2>Notes</h2>
      <p className="muted">Unified notes index across workspaces, projects, and chat sessions.</p>
      {error && <p className="error-msg">{error}</p>}

      <div className="form-section">
        <label className="form-label">Title</label>
        <input className="form-input" value={form.title} onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))} />
        <label className="form-label">Body</label>
        <textarea className="form-input" rows={4} value={form.body} onChange={(e) => setForm((p) => ({ ...p, body: e.target.value }))} />
        <label className="form-label">Tags</label>
        <input className="form-input" placeholder="research, bug, todo" value={form.tags} onChange={(e) => setForm((p) => ({ ...p, tags: e.target.value }))} />
        <div className="row gap">
          <input className="form-input" placeholder="Workspace" value={form.workspace} onChange={(e) => setForm((p) => ({ ...p, workspace: e.target.value }))} />
          <input className="form-input" placeholder="Project" value={form.project} onChange={(e) => setForm((p) => ({ ...p, project: e.target.value }))} />
          <input className="form-input" placeholder="Session" value={form.session} onChange={(e) => setForm((p) => ({ ...p, session: e.target.value }))} />
        </div>
        <div className="row gap">
          <button className="btn btn-primary" onClick={saveNote}>Save Note</button>
          <button className="btn btn-secondary" onClick={exportNotes}>Export Notes</button>
        </div>
      </div>

      <div className="row gap" style={{ marginTop: 16 }}>
        <input className="form-input" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} />
        <input className="form-input" placeholder="Filter by tag" value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} />
      </div>

      <table className="data-table" style={{ marginTop: 12 }}>
        <thead><tr><th>Title</th><th>Tags</th><th>Location</th><th>Created</th><th>Actions</th></tr></thead>
        <tbody>
          {filtered.map((n) => (
            <tr key={n.id}>
              <td>{n.title}</td>
              <td>{(n.tags || []).join(", ")}</td>
              <td>{[n.workspace_id, n.project_id, n.chat_session_id].filter(Boolean).join(" / ")}</td>
              <td>{new Date(n.created_at).toLocaleString()}</td>
              <td><button className="btn btn-sm btn-danger" onClick={() => remove(n.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
