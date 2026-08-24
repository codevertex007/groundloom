import React, { useState } from "react";
import {
  ArrowLeft,
  ChevronRight,
  FolderOpen,
  Library,
  Plus,
  Search,
  Sparkles,
} from "lucide-react";

export function PageHeader({ eyebrow, title, meta, action, onBack }) {
  return (
    <header className="page-header">
      {onBack && (
        <button className="icon-button" aria-label="Go back" onClick={onBack}>
          <ArrowLeft size={17} />
        </button>
      )}
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {meta && <span className="header-meta">{meta}</span>}
      </div>
      {action}
    </header>
  );
}

export function CommandPalette({ onClose, onChoose, onNew }) {
  const [query, setQuery] = useState("");
  const commands = [
    { id: "projects", label: "Open Projects", icon: FolderOpen },
    { id: "sources", label: "Open Sources", icon: Library },
    { id: "skills", label: "Open Skills", icon: Sparkles },
  ].filter((x) => x.label.toLowerCase().includes(query.toLowerCase()));
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="palette-search">
          <Search size={16} />
          <input
            aria-label="Search commands"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search commands…"
          />
          <kbd>ESC</kbd>
        </div>
        <div className="palette-section">
          <small>NAVIGATION</small>
          {commands.map((command) => (
            <button key={command.id} onClick={() => onChoose(command.id)}>
              <command.icon size={16} />
              <span>{command.label}</span>
              <ChevronRight size={14} />
            </button>
          ))}
          <button onClick={onNew}>
            <Plus size={16} />
            <span>New Project</span>
            <ChevronRight size={14} />
          </button>
          {commands.length === 0 && (
            <span role="status" className="muted">
              No commands match that search.
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, body, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon size={24} />
      </div>
      <h2>{title}</h2>
      <p>{body}</p>
      {action}
    </div>
  );
}
