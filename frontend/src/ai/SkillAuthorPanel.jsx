import React from "react";

/** Draft-only AI skill authoring form. Publication remains a backend command. */
export function SkillAuthorPanel({ authorForm, setAuthorForm, busyAction, onAuthor, onClose }) {
  return (
    <div className="inline-form" aria-label="AI skill author">
      <div className="eyebrow">AI SKILL AUTHOR / DRAFT ONLY</div>
      <textarea
        aria-label="Skill author objective"
        placeholder="Describe the reusable guidance this skill should provide…"
        value={authorForm.objective}
        onChange={(e) => setAuthorForm({ ...authorForm, objective: e.target.value })}
      />
      <div className="form-grid">
        <input
          aria-label="Suggested skill slug"
          placeholder="optional-slug"
          value={authorForm.suggested_slug}
          onChange={(e) => setAuthorForm({ ...authorForm, suggested_slug: e.target.value })}
        />
        <input
          aria-label="Suggested skill name"
          placeholder="Optional display name"
          value={authorForm.suggested_name}
          onChange={(e) => setAuthorForm({ ...authorForm, suggested_name: e.target.value })}
        />
        <select
          aria-label="AI skill scope"
          value={authorForm.scope}
          onChange={(e) => setAuthorForm({ ...authorForm, scope: e.target.value })}
        >
          <option value="workspace">Workspace</option>
          <option value="organization">Organization</option>
        </select>
      </div>
      <div className="form-actions">
        <button className="soft-button" onClick={onClose}>Cancel</button>
        <button
          className="primary-button"
          disabled={!authorForm.objective.trim() || busyAction === "author"}
          onClick={onAuthor}
        >
          {busyAction === "author" ? "Drafting…" : "Create AI draft"}
        </button>
      </div>
    </div>
  );
}
