import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Archive,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Command,
  Download,
  FileText,
  Filter,
  FolderOpen,
  Gauge,
  GripVertical,
  Library,
  LoaderCircle,
  Menu,
  MoreHorizontal,
  PanelLeft,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { api, subscribeToEvents } from "./api";
import { CommandPalette, EmptyState, PageHeader } from "./components";
import "./styles.css";

const fmt = (date) =>
  date
    ? new Date(date).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      })
    : "—";
const iconFor = (type) =>
  type === "pdf" ? "PDF" : type === "docx" ? "DOC" : "TXT";
const classifyError = (error) => {
  if (error?.code === "PERMISSION_DENIED" || error?.code === "UNAUTHENTICATED") {
    return "permission";
  }
  if (error?.retryable || error?.code === "DEPENDENCY_UNAVAILABLE") {
    return "retryable";
  }
  return "terminal";
};

function App() {
  const [screen, setScreen] = useState("projects");
  const [projects, setProjects] = useState([]);
  const [sources, setSources] = useState([]);
  const [skills, setSkills] = useState([]);
  const [activeProject, setActiveProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [palette, setPalette] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [sourceQuery, setSourceQuery] = useState("");
  const [projectQuery, setProjectQuery] = useState("");

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const [p, s, k] = await Promise.all([
        api("/v1/projects"),
        api("/v1/sources"),
        api("/v1/skills"),
      ]);
      setProjects(p);
      setSources(s);
      setSkills(k);
    } catch (e) {
      setError({ message: e.message, code: e.code, retryable: e.retryable });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    const key = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
      }
      if (e.key === "Escape") {
        setPalette(false);
        setSettingsOpen(false);
        setNewProjectOpen(false);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const openProject = async (project) => {
    try {
      setActiveProject(await api(`/v1/projects/${project.id}`));
      setScreen("canvas");
    } catch (e) {
      setError({ message: e.message, code: e.code, retryable: e.retryable });
    }
  };
  const nav = (target) => {
    setScreen(target);
    setActiveProject(null);
    setPalette(false);
  };

  return (
    <div className="app-shell">
      <Sidebar
        collapsed={collapsed}
        screen={screen}
        onNav={nav}
        onPalette={() => setPalette(true)}
        onSettings={() => setSettingsOpen(true)}
        onToggle={() => setCollapsed(!collapsed)}
      />
      <main className="main-shell">
        {error && (
          <div className="error-banner" data-error-kind={classifyError(error)} role="alert">
            <CircleHelp size={15} />
            <span>
              <strong>
                {classifyError(error) === "permission"
                  ? "Permission denied"
                  : classifyError(error) === "retryable"
                    ? "Temporary service issue"
                    : "Request failed"}
              </strong>{" "}
              {error.message}
            </span>
            {classifyError(error) === "retryable" ? (
              <button onClick={refresh}>
                <RefreshCw size={14} /> Retry
              </button>
            ) : (
              <button onClick={() => setError("")}>Dismiss</button>
            )}
          </div>
        )}
        {screen === "projects" && (
          <ProjectsScreen
            loading={loading}
            projects={projects}
            query={projectQuery}
            setQuery={setProjectQuery}
            onOpen={openProject}
            onNew={() => setNewProjectOpen(true)}
          />
        )}
        {screen === "sources" && (
          <SourcesScreen
            sources={sources}
            query={sourceQuery}
            setQuery={setSourceQuery}
            onRefresh={refresh}
          />
        )}
        {screen === "skills" && (
          <SkillsScreen skills={skills} onRefresh={refresh} />
        )}
        {screen === "canvas" && activeProject && (
          <Canvas
            project={activeProject}
            sources={sources}
            onBack={() => nav("projects")}
            onRefresh={refresh}
          />
        )}
      </main>
      {newProjectOpen && (
          <NewProjectModal
            sources={sources}
            skills={skills}
            onClose={() => setNewProjectOpen(false)}
          onCreated={async (project) => {
            setNewProjectOpen(false);
            await refresh();
            openProject(project);
          }}
        />
      )}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
      {palette && (
        <CommandPalette
          onClose={() => setPalette(false)}
          onChoose={(target) => nav(target)}
          onNew={() => {
            setPalette(false);
            setNewProjectOpen(true);
          }}
        />
      )}
    </div>
  );
}

function Sidebar({
  collapsed,
  screen,
  onNav,
  onPalette,
  onSettings,
  onToggle,
}) {
  const item = (id, label, Icon) => (
    <button
      className={`nav-item ${screen === id ? "active" : ""}`}
      aria-current={screen === id ? "page" : undefined}
      title={label}
      onClick={() => onNav(id)}
    >
      <Icon size={17} />
      <span>{label}</span>
    </button>
  );
  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="brand">
        <div className="brand-mark">G</div>
        {!collapsed && (
          <>
            <span>groundloom</span>
            <span className="beta">STUDIO</span>
          </>
        )}
      </div>
      <div className="nav-group">
        {item("projects", "Projects", FolderOpen)}
        {item("sources", "Sources", Library)}
        {item("skills", "Skills", Sparkles)}
      </div>
      <div className="nav-bottom">
        <button className="nav-item" onClick={onPalette}>
          <Command size={17} />
          <span>Command palette</span>
          <kbd>⌘K</kbd>
        </button>
        <button className="nav-item" onClick={onSettings}>
          <Settings size={17} />
          <span>Settings</span>
        </button>
        <button className="nav-item collapse-btn" onClick={onToggle}>
          <PanelLeft size={17} />
          <span>{collapsed ? "Expand" : "Collapse"}</span>
        </button>
      </div>
    </aside>
  );
}

function ProjectsScreen({ loading, projects, query, setQuery, onOpen, onNew }) {
  const [status, setStatus] = useState("all");
  const statuses = ["all", "draft", "active", "completed"];
  const shown = projects.filter(
    (p) =>
      `${p.name} ${p.project_type}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (status === "all" || p.status === status),
  );
  const cycleStatus = () =>
    setStatus(
      (current) => statuses[(statuses.indexOf(current) + 1) % statuses.length],
    );
  return (
    <section className="page">
      <PageHeader
        eyebrow="WORKSPACE / PROJECTS"
        title="Projects"
        meta={`${projects.length} total · ${projects.reduce((n, p) => n + p.source_count, 0)} sources`}
        action={
          <button className="primary-button" onClick={onNew}>
            <Plus size={15} /> New Project
          </button>
        }
      />
      <div className="toolbar">
        <div className="search-box">
          <Search size={15} />
          <input
            aria-label="Search projects"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search projects…"
          />
        </div>
        <button
          className="soft-button"
          aria-label={`Filter projects, currently ${status}`}
          aria-pressed={status !== "all"}
          onClick={cycleStatus}
        >
          <Filter size={14} /> {status === "all" ? "Filter" : status}{" "}
          <ChevronDown size={13} />
        </button>
      </div>
      {loading ? (
        <LoadingRows />
      ) : shown.length === 0 ? (
        <EmptyState
          icon={Search}
          title={
            query || status !== "all"
              ? "No matching projects"
              : "Your studio is empty"
          }
          body="Start with a brief, selected evidence, and a persistent collaborator."
          action={
            <button className="primary-button" onClick={onNew}>
              <Plus size={15} /> New Project
            </button>
          }
        />
      ) : (
        <div className="project-grid">
          {shown.map((p) => (
            <button
              key={p.id}
              className="project-card"
              onClick={() => onOpen(p)}
            >
              <div className="card-top">
                <div className="project-icon">
                  <BookOpen size={18} />
                </div>
                <span className={`status-dot ${p.status}`}>{p.status}</span>
                <MoreHorizontal size={17} className="muted" />
              </div>
              <h2>{p.name}</h2>
              <p>{p.brief}</p>
              <div className="card-footer">
                <span>{p.source_count} sources</span>
                <span>{p.section_count} sections</span>
                <span className="card-date">{fmt(p.updated_at)}</span>
              </div>
              <div className="progress-line">
                <span
                  style={{
                    width: p.latest_run_status === "completed" ? "100%" : "28%",
                  }}
                />
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function SourcesScreen({ sources, query, setQuery, onRefresh }) {
  const [selected, setSelected] = useState(null);
  const shown = sources.filter((s) =>
    s.name.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <section className="page">
      <PageHeader
        eyebrow="LIBRARY / EVIDENCE"
        title="Sources"
        meta={`${sources.length} indexed`}
        action={<UploadButton onUploaded={onRefresh} />}
      />
      <div className="toolbar">
        <div className="search-box">
          <Search size={15} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by filename…"
          />
        </div>
        <button className="soft-button" onClick={onRefresh}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
      {shown.length === 0 ? (
        <EmptyState
          icon={Library}
          title="No sources yet"
          body="Upload a PDF, DOCX, TXT, or Markdown source to create an immutable evidence version."
          action={<UploadButton onUploaded={onRefresh} />}
        />
      ) : (
        <div className="table-card">
          <div className="table-head">
            <span>Source</span>
            <span>Version</span>
            <span>Status</span>
            <span>Updated</span>
          </div>
          {shown.map((s) => (
            <div className="table-row" key={s.id}>
              <div className="source-name">
                <span className={`file-badge ${s.source_type}`}>
                  {iconFor(s.source_type)}
                </span>
                <div>
                  <strong>{s.name}</strong>
                  <small>
                    {s.source_type.toUpperCase()} · {s.versions.length} version
                    {s.versions.length === 1 ? "" : "s"}
                  </small>
                </div>
              </div>
              <span>v{s.versions[0]?.version_no || 1}</span>
              <span>
                <span className={`status-pill ${s.latest_status}`}>
                  {s.latest_status || "unknown"}
                </span>
              </span>
              <div className="source-row-actions">
                <span className="muted">{fmt(s.versions[0]?.created_at)}</span>
                <button
                  className="soft-button compact"
                  aria-label={`Open ${s.name} versions`}
                  onClick={() => setSelected(s)}
                >
                  Versions
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {selected && (
        <div className="modal-backdrop">
          <div className="modal wide" role="dialog" aria-modal="true" aria-labelledby="source-versions-title">
            <div className="modal-head">
              <div>
                <span className="eyebrow">IMMUTABLE SOURCE HISTORY</span>
                <h2 id="source-versions-title">{selected.name}</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close source versions dialog"
                onClick={() => setSelected(null)}
              >
                <X size={17} />
              </button>
            </div>
            <div className="version-history">
              {selected.versions.map((version) => (
                <div className="version-row" key={version.id}>
                  <span>v{version.version_no}</span>
                  <span className={`status-pill ${version.status}`}>{version.status}</span>
                  <span>{version.size_bytes.toLocaleString()} bytes</span>
                  <span className="muted">{fmt(version.created_at)}</span>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <UploadButton
                sourceId={selected.id}
                onUploaded={() => {
                  setSelected(null);
                  onRefresh();
                }}
              />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function UploadButton({ onUploaded, sourceId = null }) {
  const [error, setError] = useState(null);
  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        await api(sourceId ? `/v1/sources/${sourceId}/versions` : "/v1/sources/uploads", {
          method: "POST",
          body: JSON.stringify({
            name: file.name.replace(/\.[^.]+$/, ""),
            filename: file.name,
            content_base64: String(reader.result).split(",")[1],
            mime_type: file.type || "text/plain",
          }),
        });
        onUploaded();
      } catch (err) {
        setError(err);
      }
    };
    reader.readAsDataURL(file);
  };
  return (
    <>
      <label className="primary-button upload-button">
        <Upload size={15} /> Upload source
        <input type="file" accept=".txt,.md,.pdf,.docx" onChange={upload} />
      </label>
      {error && <ErrorNotice error={error} onDismiss={() => setError(null)} />}
    </>
  );
}

function SkillsScreen({ skills, onRefresh }) {
  const [open, setOpen] = useState(null);
  const [form, setForm] = useState({
    slug: "",
    name: "",
    description: "",
    content: "",
  });
  const [authorForm, setAuthorForm] = useState({
    objective: "",
    suggested_slug: "",
    suggested_name: "",
    scope: "workspace",
  });
  const [repair, setRepair] = useState(null);
  const [repairForm, setRepairForm] = useState({ description: "", content: "" });
  const [scopeFilter, setScopeFilter] = useState("all");
  const [creating, setCreating] = useState(false);
  const [authoring, setAuthoring] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [message, setMessage] = useState("");
  const toggle = (id) => setOpen((current) => (current === id ? null : id));
  const create = async () => {
    setBusyAction("create");
    setMessage("");
    try {
      await api("/v1/skills", { method: "POST", body: JSON.stringify(form) });
      setCreating(false);
      setForm({ slug: "", name: "", description: "", content: "" });
      onRefresh();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusyAction("");
    }
  };
  const author = async () => {
    setBusyAction("author");
    setMessage("");
    try {
      await api("/v1/skills/ai-drafts", {
        method: "POST",
        body: JSON.stringify({
          ...authorForm,
          suggested_slug: authorForm.suggested_slug || null,
          suggested_name: authorForm.suggested_name || null,
        }),
      });
      setAuthoring(false);
      setAuthorForm({ objective: "", suggested_slug: "", suggested_name: "", scope: "workspace" });
      onRefresh();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusyAction("");
    }
  };
  const validate = async (version) => {
    setBusyAction(`validate:${version.id}`);
    setMessage("");
    try {
      await api(`/v1/skill-versions/${version.id}/validate`, { method: "POST" });
      onRefresh();
    } catch (e) {
      setMessage(e.message);
      onRefresh();
    } finally {
      setBusyAction("");
    }
  };
  const publish = async (version) => {
    setBusyAction(`publish:${version.id}`);
    setMessage("");
    try {
      await api(`/v1/skill-versions/${version.id}/publish`, { method: "POST" });
      onRefresh();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusyAction("");
    }
  };
  const openRepair = (skill, version) => {
    setRepair({ skill, version });
    setRepairForm({ description: version.description || skill.description, content: "" });
    setMessage("");
  };
  const submitRepair = async () => {
    if (!repair) return;
    setBusyAction("repair");
    setMessage("");
    try {
      await api(`/v1/skill-versions/${repair.version.id}/repair`, {
        method: "PUT",
        headers: { "Idempotency-Key": `ui-repair-${repair.version.id}-${crypto.randomUUID()}` },
        body: JSON.stringify(repairForm),
      });
      setRepair(null);
      onRefresh();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusyAction("");
    }
  };
  const fork = async (skill) => {
    setBusyAction(`fork:${skill.id}`);
    setMessage("");
    try {
      await api(`/v1/skills/${skill.id}/fork`, {
        method: "POST",
        headers: { "Idempotency-Key": `ui-fork-${skill.id}-${crypto.randomUUID()}` },
        body: JSON.stringify({}),
      });
      onRefresh();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusyAction("");
    }
  };
  const visibleSkills = skills.filter(
    (skill) => scopeFilter === "all" || skill.scope === scopeFilter,
  );
  return (
    <section className="page">
      <PageHeader
        eyebrow="HARNESS / INSTRUCTIONS"
        title="Skills"
        meta={`${visibleSkills.length}/${skills.length} packages`}
        action={
          <div className="header-actions">
            <button className="soft-button" onClick={() => setAuthoring(!authoring)}>
              <Sparkles size={15} /> AI author draft
            </button>
            <button className="primary-button" onClick={() => setCreating(!creating)}>
              <Plus size={15} /> New skill
            </button>
          </div>
        }
      />
      <p className="lede">
        Versioned folders of instructions that the collaborator loads when a
        drafting task calls for them. Published bytes stay immutable and runs
        pin exact versions.
      </p>
      {message && (
        <div className="error-banner" role="alert">
          <CircleHelp size={15} /> {message}
          <button onClick={() => setMessage("")}>Dismiss</button>
        </div>
      )}
      {authoring && (
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
            <button className="soft-button" onClick={() => setAuthoring(false)}>Cancel</button>
            <button className="primary-button" disabled={!authorForm.objective.trim() || busyAction === "author"} onClick={author}>
              {busyAction === "author" ? "Drafting…" : "Create AI draft"}
            </button>
          </div>
        </div>
      )}
      {creating && (
        <div className="inline-form">
          <div className="form-grid">
            <input
              aria-label="Skill slug"
              placeholder="slug, e.g. editorial-style"
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
            />
            <input
              aria-label="Skill name"
              placeholder="Skill name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <input
            aria-label="Skill trigger description"
            placeholder="Trigger description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <textarea
            aria-label="Skill instructions"
            placeholder="SKILL.md body"
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
          />
          <div className="form-actions">
            <button className="soft-button" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button className="primary-button" disabled={busyAction === "create"} onClick={create}>
              {busyAction === "create" ? "Creating…" : "Create draft"}
            </button>
          </div>
        </div>
      )}
      <div className="toolbar" role="group" aria-label="Filter skills by scope">
        {["all", "starter", "organization", "workspace"].map((scope) => (
          <button
            className={`soft-button ${scopeFilter === scope ? "selected" : ""}`}
            aria-pressed={scopeFilter === scope}
            key={scope}
            onClick={() => setScopeFilter(scope)}
          >
            {scope === "all" ? "All scopes" : scope}
          </button>
        ))}
      </div>
      <div className="skill-list">
        {visibleSkills.map((skill) => (
          <div
            className={`skill-card ${open === skill.id ? "expanded" : ""}`}
            key={skill.id}
            role="button"
            tabIndex="0"
            aria-expanded={open === skill.id}
            aria-label={`${skill.name}, ${skill.versions.length} versions`}
            onClick={() => toggle(skill.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggle(skill.id);
              }
            }}
          >
            <div className="skill-symbol">
              <Sparkles size={16} />
            </div>
            <div className="skill-main">
              <div className="skill-title">
                <h2>{skill.name}</h2>
                <span className={`scope-badge ${skill.scope}`}>
                  {skill.scope}
                </span>
              </div>
              <p>{skill.description}</p>
              <div className="skill-meta">
                {skill.slug} · {skill.versions.length} version
                {skill.versions.length === 1 ? "" : "s"}
              </div>
            </div>
            <ChevronRight
              size={17}
              className={`skill-chevron ${open === skill.id ? "turn" : ""}`}
            />
            {open === skill.id && (
              <div className="skill-detail">
                <strong>Version history</strong>
                {skill.versions.map((v) => (
                  <div className="version-row" key={v.id}>
                    <span>v{v.version_no}</span>
                    <span className={`status-pill ${v.status}`}>
                      {v.status}
                    </span>
                    <span>{v.description}</span>
                    <div className="version-actions">
                      {skill.scope !== "workspace" && v.status === "published" && (
                        <button
                          className="soft-button compact"
                          disabled={busyAction === `fork:${skill.id}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            fork(skill);
                          }}
                        >
                          {busyAction === `fork:${skill.id}` ? "Forking…" : "Fork to workspace"}
                        </button>
                      )}
                      {(v.status === "draft" || v.status === "invalid") && (
                        <button
                          className="soft-button compact"
                          disabled={busyAction === `validate:${v.id}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            validate(v);
                          }}
                        >
                          {busyAction === `validate:${v.id}` ? "Checking…" : "Validate"}
                        </button>
                      )}
                      {v.status !== "published" && (
                        <button
                          className="soft-button compact"
                          onClick={(event) => {
                            event.stopPropagation();
                            openRepair(skill, v);
                          }}
                        >
                          Repair draft
                        </button>
                      )}
                      {v.status === "valid" && (
                        <button
                          className="primary-button compact"
                          disabled={busyAction === `publish:${v.id}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            publish(v);
                          }}
                        >
                          {busyAction === `publish:${v.id}` ? "Publishing…" : "Publish"}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {visibleSkills.length === 0 && (
          <EmptyState
            icon={Sparkles}
            title="No skills in this scope"
            body="Choose another scope or create a workspace skill draft."
          />
        )}
      </div>
      {repair && (
        <div className="modal-backdrop">
          <div className="modal wide" role="dialog" aria-modal="true" aria-labelledby="repair-skill-title">
            <div className="modal-head">
              <div>
                <span className="eyebrow">REPAIR / NEW IMMUTABLE VERSION</span>
                <h2 id="repair-skill-title">Repair {repair.skill.name}</h2>
              </div>
              <button className="icon-button" aria-label="Close skill repair dialog" onClick={() => setRepair(null)}>
                <X size={17} />
              </button>
            </div>
            <p className="muted">Version {repair.version.version_no} remains unchanged. Your repair creates the next draft version.</p>
            <label>
              Description
              <input
                aria-label="Repaired skill description"
                value={repairForm.description}
                onChange={(e) => setRepairForm({ ...repairForm, description: e.target.value })}
              />
            </label>
            <label>
              SKILL.md content
              <textarea
                aria-label="Repaired skill instructions"
                value={repairForm.content}
                onChange={(e) => setRepairForm({ ...repairForm, content: e.target.value })}
                placeholder="Write safe, scoped instructions…"
              />
            </label>
            <div className="modal-actions">
              <button className="soft-button" onClick={() => setRepair(null)}>Cancel</button>
              <button className="primary-button" disabled={!repairForm.description.trim() || !repairForm.content.trim() || busyAction === "repair"} onClick={submitRepair}>
                {busyAction === "repair" ? "Saving…" : "Create repaired draft"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function Canvas({ project, sources, onBack, onRefresh }) {
  const [tab, setTab] = useState("outline");
  const [events, setEvents] = useState([]);
  const [outline, setOutline] = useState(null);
  const [content, setContent] = useState(null);
  const [patches, setPatches] = useState([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [citation, setCitation] = useState(null);
  const [validation, setValidation] = useState(null);
  const [validationOpen, setValidationOpen] = useState(false);
  const [rail, setRail] = useState("sources");
  const [query, setQuery] = useState("");
  const [evidence, setEvidence] = useState(null);
  const [connection, setConnection] = useState("connecting");
  const [approvals, setApprovals] = useState([]);
  const [run, setRun] = useState(null);
  const [operationError, setOperationError] = useState(null);
  const loadApprovals = async (runId = run?.id || project.current_run_id) => {
    if (!runId) {
      setApprovals([]);
      return;
    }
    try {
      setApprovals(await api(`/v1/runs/${runId}/approvals`));
    } catch (_) {
      setApprovals([]);
    }
  };
  const load = async (runIdOverride = null) => {
    const runId = runIdOverride || run?.id || project.current_run_id;
    const [o, c, p, ev, currentRun] = await Promise.all([
      api(`/v1/projects/${project.id}/outline`),
      api(`/v1/projects/${project.id}/content`),
      api(`/v1/projects/${project.id}/patches`),
      api(`/v1/threads/${project.thread_id}/events`),
      runId ? api(`/v1/runs/${runId}`) : Promise.resolve(null),
    ]);
    setOutline(o);
    setContent(c);
    setPatches(p);
    setEvents(ev);
    if (currentRun) setRun(currentRun);
    await loadApprovals(runId);
  };
  useEffect(() => {
    load().catch((e) => setOperationError(e));
    const stop = subscribeToEvents(
      `/v1/threads/${project.thread_id}/events/stream`,
      (event) => {
        setEvents((current) =>
          current.some((item) => item.event_id === event.event_id)
            ? current
            : [...current, event].sort((a, b) => a.seq - b.seq),
        );
        if (
          event.type === "run.completed" ||
          event.type === "run.cancelled" ||
          event.type === "assistant.message" ||
          event.type === "approval.required" ||
          event.type === "approval.resolved"
        ) {
          load().catch((e) => setOperationError(e));
          loadApprovals().catch(() => {});
        }
      },
      setConnection,
    );
    return stop;
  }, [project.id, project.thread_id]);
  const send = async () => {
    if (!message.trim()) return;
    setBusy(true);
    try {
      const nextRun = await api(`/v1/projects/${project.id}/threads/messages`, {
        method: "POST",
        headers: { "Idempotency-Key": `ui-${crypto.randomUUID()}` },
        body: JSON.stringify({ text: message }),
      });
      setRun(nextRun);
      setMessage("");
      await load(nextRun.id);
      await loadApprovals(nextRun.id);
      onRefresh();
    } catch (e) {
      setOperationError(e);
    } finally {
      setBusy(false);
    }
  };
  const cancel = async () => {
    if (!run) return;
    try {
      setRun(await api(`/v1/runs/${run.id}/cancel`, { method: "POST" }));
      await load();
    } catch (e) {
      setOperationError(e);
    }
  };
  const resume = async () => {
    if (!run) return;
    try {
      setRun(await api(`/v1/runs/${run.id}/resume`, { method: "POST" }));
      await load();
    } catch (e) {
      setOperationError(e);
    }
  };
  const accept = async (patch) => {
    try {
      await api(`/v1/patches/${patch.id}/accept`, {
        method: "POST",
        body: JSON.stringify({
          expected_current_version_id: content.version.id,
        }),
      });
      await load();
    } catch (e) {
      setOperationError(e);
    }
  };
  const resolveApproval = async (approval, decision) => {
    try {
      await api(`/v1/approvals/${approval.id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      await load();
      await loadApprovals(approval.run_id);
      onRefresh();
    } catch (e) {
      setOperationError(e);
    }
  };
  const reject = async (patch) => {
    try {
      await api(`/v1/patches/${patch.id}/reject`, {
        method: "POST",
        body: JSON.stringify({
          expected_current_version_id: content.version.id,
          reason: "Rejected in review",
        }),
      });
      await load();
    } catch (e) {
      setOperationError(e);
    }
  };
  const search = async () => {
    if (!query.trim()) return;
    try {
      setEvidence(
        await api(
          `/v1/projects/${project.id}/sources/search?q=${encodeURIComponent(query)}`,
        ),
      );
    } catch (e) {
      setOperationError(e);
    }
  };
  const openCitation = async (passageId) => {
    for (const versionId of project.config.source_version_ids || []) {
      try {
        setCitation(
          await api(`/v1/source-versions/${versionId}/passages/${passageId}`),
        );
        return;
      } catch (_) {
        // A passage ID is only meaningful within its immutable source version;
        // try the other authorized pinned versions without broadening scope.
      }
    }
    setOperationError({
      message: "This citation is no longer available in the project's pinned evidence.",
      code: "CITATION_NOT_FOUND",
    });
  };
  const runValidation = async () => {
    try {
      setValidation(
        await api(`/v1/projects/${project.id}/validate`, { method: "POST" }),
      );
      setValidationOpen(true);
    } catch (e) {
      setOperationError(e);
    }
  };
  const lastActivity = [...events]
    .reverse()
    .find((e) => e.type === "run.completed" || e.type === "artifact.delta");
  const cancellable = [
    "queued",
    "running",
    "waiting_for_user",
    "waiting_for_approval",
  ].includes(run?.status);
  const resumable = ["failed", "cancelled", "waiting_for_user"].includes(
    run?.status,
  );
  return (
    <section className="canvas">
      <div className="canvas-header">
        <button className="crumb-back" onClick={onBack}>
          <ArrowLeft size={15} /> Projects
        </button>
        <div className="canvas-title">
          <span className="project-icon small">
            <BookOpen size={15} />
          </span>
          <div>
            <strong>{project.name}</strong>
            <small>{project.project_type} · persistent collaborator</small>
          </div>
        </div>
        <div className="canvas-actions">
          <button
            className="soft-button"
            aria-label="Refresh project canvas"
            onClick={load}
          >
            <RefreshCw size={14} />
          </button>
          <button className="soft-button" onClick={runValidation}>
            <ShieldCheck size={14} /> Review
          </button>
          <button
            className="primary-button"
            onClick={() =>
              api("/v1/exports", {
                method: "POST",
                body: JSON.stringify({
                  project_id: project.id,
                  content_version_id: content.version.id,
                  format: "pdf",
                }),
              })
                .then((j) => window.open(j.download_url, "_blank"))
                .catch((e) => setOperationError(e))
            }
          >
            <Download size={14} /> Export
          </button>
        </div>
      </div>
      {operationError && (
        <ErrorNotice
          error={operationError}
          onRetry={() => {
            setOperationError(null);
            load().catch((e) => setOperationError(e));
          }}
          onDismiss={() => setOperationError(null)}
        />
      )}
      <div className="canvas-body">
        <aside className="canvas-rail">
          <div className="rail-tabs">
            <button
              className={rail === "sources" ? "selected" : ""}
              onClick={() => setRail("sources")}
            >
              Sources
            </button>
            <button
              className={rail === "search" ? "selected" : ""}
              onClick={() => setRail("search")}
            >
              Search
            </button>
          </div>
          {rail === "sources" ? (
            <div className="rail-content">
              {sources
                .filter((s) =>
                  project.config.source_version_ids.includes(
                    s.current_version_id,
                  ),
                )
                .map((s) => (
                  <div className="rail-source" key={s.id}>
                    <FileText size={14} />
                    <span>{s.name}</span>
                    <ChevronRight size={13} />
                  </div>
                ))}
              {sources.length === 0 && (
                <div className="empty-mini">No sources selected.</div>
              )}
            </div>
          ) : (
            <div className="rail-content">
              <div className="search-box">
                <Search size={14} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && search()}
                  placeholder="Search evidence…"
                />
              </div>
              {evidence?.passages.map((p) => (
                <button
                  className="evidence-item"
                  key={p.passage_id}
                  onClick={() => setCitation(p)}
                >
                  <strong>{p.source_name}</strong>
                  <span>{p.text}</span>
                  <small>
                    p.{p.page || "—"} · {Math.round(p.score * 100)}% match
                  </small>
                </button>
              ))}
            </div>
          )}
        </aside>
        <div className="canvas-main">
          <div className="canvas-tabs">
            <button
              className={tab === "outline" ? "active" : ""}
              onClick={() => setTab("outline")}
            >
              Outline <span>{outline?.items?.length || 0}</span>
            </button>
            <button
              className={tab === "content" ? "active" : ""}
              onClick={() => setTab("content")}
            >
              Content <span>{content?.blocks?.length || 0}</span>
            </button>
            <div className="tab-spacer" />
            <span className="version-label">
              {content?.version?.status} · v{content?.version?.version_no}
            </span>
          </div>
          {tab === "outline" ? (
            <OutlineView outline={outline} />
          ) : (
          <ContentView content={content} onCitation={openCitation} />
          )}
          {patches
            .filter((p) => p.status === "presented")
            .map((p) => (
              <DiffCard
                key={p.id}
                patch={p}
                onAccept={() => accept(p)}
                onReject={() => reject(p)}
              />
            ))}
        </div>
        <aside className="copilot">
          <div className="copilot-head">
            <div>
              <span className="eyebrow">COPILOT</span>
              <strong>Project collaborator</strong>
              {run && (
                <small className="run-status" role="status">
                  Run {run.status}
                </small>
              )}
            </div>
            <span
              className={`live-dot ${connection}`}
              title={`Activity stream ${connection}`}
              aria-label={`Activity stream ${connection}`}
            />
          </div>
          <div className="activity-scroll">
            <div className="activity-summary">
              <span className="activity-icon">
                <Zap size={15} />
              </span>
              <div>
                <strong>
                  {lastActivity?.payload?.summary || "Ready for direction"}
                </strong>
                <small>
                  {events.length
                    ? `${events.length} durable events · replayable · ${connection}`
                    : `No activity yet · ${connection}`}
                </small>
                {(cancellable || resumable) && (
                  <div className="run-controls">
                    {cancellable && (
                      <button className="soft-button" onClick={cancel}>
                        Cancel run
                      </button>
                    )}
                    {resumable && (
                      <button className="primary-button" onClick={resume}>
                        Resume run
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
            {approvals
              .filter((approval) => approval.status === "pending")
              .map((approval) => (
                <div className="approval-card" key={approval.id}>
                  <strong>Plan approval required</strong>
                  <small>
                    Review the proposed outline before the collaborator
                    continues.
                  </small>
                  <div>
                    <button
                      className="soft-button"
                      onClick={() => resolveApproval(approval, "rejected")}
                    >
                      Reject plan
                    </button>
                    <button
                      className="primary-button"
                      onClick={() => resolveApproval(approval, "approved")}
                    >
                      Approve plan
                    </button>
                  </div>
                </div>
              ))}
            {project.todos?.map((todo) => (
              <div className="todo-row" key={todo.id}>
                <span className={`todo-check ${todo.status}`}>
                  {todo.status === "completed" ? <Check size={11} /> : <span />}
                </span>
                <span>{todo.description}</span>
              </div>
            ))}
            {events.slice(-8).map((event) => (
              <div className="event-row" key={event.event_id}>
                <span className="event-kind">{event.type.split(".")[0]}</span>
                <span>
                  {event.payload?.summary ||
                    event.payload?.name ||
                    event.payload?.text ||
                    event.type}
                </span>
              </div>
            ))}
          </div>
          <div className="copilot-compose">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" && (e.metaKey || e.ctrlKey) && send()
              }
              placeholder="Ask Copilot, or describe a change…"
            />
            <button
              className="send-button"
              aria-label="Send message"
              disabled={busy}
              onClick={send}
            >
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Send size={16} />
              )}
            </button>
            <small>⌘↵ to send · proposals stay reviewable</small>
          </div>
        </aside>
      </div>
      {citation && (
        <CitationPanel citation={citation} onClose={() => setCitation(null)} />
      )}
      {validationOpen && validation && (
        <ValidationPanel validation={validation} onClose={() => setValidationOpen(false)} />
      )}
    </section>
  );
}

function OutlineView({ outline }) {
  return (
    <div className="document-pane">
      {outline?.items?.length ? (
        <>
          {outline.items.map((item, index) => (
            <div className="outline-item" key={item.id}>
              <span className="outline-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <h2>{item.title}</h2>
                <p>{item.description}</p>
                <span className="module-status">{item.status}</span>
              </div>
              <GripVertical size={16} className="muted" />
            </div>
          ))}
        </>
      ) : (
        <EmptyState
          icon={BookOpen}
          title="No outline yet"
          body="Ask the collaborator to generate an outline from the brief and selected evidence."
        />
      )}
    </div>
  );
}
function ContentView({ content, onCitation }) {
  return (
    <div className="document-pane content-pane">
      {content?.blocks?.length ? (
        content.blocks.map((block) => (
          <article className={`content-block ${block.type}`} key={block.id}>
            <span className="block-label">{block.type}</span>
            {block.type === "heading" ? (
              <h1>{block.payload.text}</h1>
            ) : (
              <p>{block.payload.text}</p>
            )}
            {block.citations?.map((citation) => (
              <button
                className="citation"
                key={citation}
                onClick={() =>
                    onCitation(citation)
                }
              >
                ◉ cited
              </button>
            ))}
          </article>
        ))
      ) : (
        <EmptyState
          icon={FileText}
          title="Content is empty"
          body="Approve an outline or ask Copilot for a reviewable draft."
        />
      )}
    </div>
  );
}

function ValidationPanel({ validation, onClose }) {
  const summary = validation.summary || {};
  return (
    <div className="modal-backdrop">
      <div className="modal wide" role="dialog" aria-modal="true" aria-labelledby="validation-title">
        <div className="modal-head">
          <div>
            <span className="eyebrow">QUALITY / REVIEW</span>
            <h2 id="validation-title">Validation checklist</h2>
          </div>
          <button className="icon-button" aria-label="Close validation dialog" onClick={onClose}>
            <X size={17} />
          </button>
        </div>
        <div className="validation-summary" role="status">
          <ShieldCheck size={18} />
          <strong>{validation.status === "passed" ? "Ready for review" : "Needs revision"}</strong>
          <span>
            {summary.finding_count || 0} findings · {summary.error_count || 0} errors · {summary.warning_count || 0} warnings
          </span>
        </div>
        {validation.findings?.length ? (
          <div className="validation-findings">
            {validation.findings.map((finding) => (
              <div className={`finding-row ${finding.severity}`} key={finding.id}>
                <span className="status-pill">{finding.severity}</span>
                <div>
                  <strong>{finding.category}</strong>
                  <p>{finding.message}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Check}
            title="All deterministic checks passed"
            body="Structure and citation checks found no actionable findings for this immutable content version."
          />
        )}
        <div className="modal-actions">
          <button className="primary-button" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}

function ErrorNotice({ error, onRetry, onDismiss }) {
  const normalized = typeof error === "string" ? { message: error } : error;
  const kind = classifyError(normalized);
  return (
    <div className="error-banner" data-error-kind={kind} role="alert">
      <CircleHelp size={15} />
      <span>
        <strong>
          {kind === "permission"
            ? "Permission denied"
            : kind === "retryable"
              ? "Temporary service issue"
              : "Request failed"}
        </strong>{" "}
        {normalized?.message || "The request could not be completed."}
      </span>
      {kind === "retryable" && onRetry ? (
        <button onClick={onRetry}>
          <RefreshCw size={14} /> Retry
        </button>
      ) : (
        <button onClick={onDismiss}>Dismiss</button>
      )}
    </div>
  );
}
function DiffCard({ patch, onAccept, onReject }) {
  return (
    <div className="diff-card">
      <div className="diff-head">
        <span className="diff-badge">PROPOSED CHANGE</span>
        <strong>{patch.summary}</strong>
        <span className="diff-base">
          against v{patch.base_content_version_id.slice(-5)}
        </span>
      </div>
      <div className="diff-body">
        {patch.operations.map((op, i) => (
          <div className="diff-line" key={i}>
            <span className="diff-sign">
              {op.op === "delete_block" ? "−" : "+"}
            </span>
            <span>{op.payload?.text || op.payload?.block_type || op.op}</span>
          </div>
        ))}
      </div>
      <div className="diff-actions">
        <button className="soft-button" onClick={onReject}>
          <X size={14} /> Reject
        </button>
        <button className="primary-button" onClick={onAccept}>
          <Check size={14} /> Accept changes
        </button>
      </div>
    </div>
  );
}
function CitationPanel({ citation, onClose }) {
  return (
    <div className="citation-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">IMMUTABLE EVIDENCE</span>
          <strong>{citation.source_name}</strong>
        </div>
        <button
          className="icon-button"
          aria-label="Close citation panel"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </div>
      <div className="citation-meta">
        Passage {citation.passage_id} · page {citation.page || "—"}
      </div>
      <blockquote>{citation.text}</blockquote>
      <button
        className="soft-button"
        aria-label="Close evidence panel"
        onClick={onClose}
      >
        <ArrowRight size={14} /> Close evidence panel
      </button>
    </div>
  );
}

function NewProjectModal({ sources, skills, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "",
    project_type: "knowledge_brief",
    brief: "",
    source_version_ids: [],
    skill_version_ids: [],
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const submit = async () => {
    setBusy(true);
    try {
      const project = await api("/v1/projects", {
        method: "POST",
        body: JSON.stringify(form),
      });
      onCreated(project);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-backdrop">
      <div
        className="modal wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-project-title"
      >
        <div className="modal-head">
          <div>
            <span className="eyebrow">NEW PROJECT</span>
            <h2 id="new-project-title">Start a grounded workspace</h2>
          </div>
          <button
            className="icon-button"
            aria-label="Close new project dialog"
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </div>
        {error && <ErrorNotice error={error} onDismiss={() => setError(null)} />}
        <label>
          Project name
          <input
            aria-label="Project name"
            autoFocus
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Field maintenance guide"
          />
        </label>
        <label>
          Project type
          <select
            aria-label="Project type"
            value={form.project_type}
            onChange={(e) => setForm({ ...form, project_type: e.target.value })}
          >
            <option value="knowledge_brief">Knowledge brief</option>
            <option value="training_guide">Training guide</option>
            <option value="research_report">Research report</option>
          </select>
        </label>
        <label>
          Brief
          <textarea
            aria-label="Project brief"
            value={form.brief}
            onChange={(e) => setForm({ ...form, brief: e.target.value })}
            placeholder="What should the collaborator help you produce? Include audience and intended outcome."
          />
        </label>
        <label>
          Selected evidence
          <span className="select-list">
            {sources
              .filter((s) => s.latest_status === "ready")
              .map((s) => (
                <button
                  type="button"
                  className={
                    form.source_version_ids.includes(s.current_version_id)
                      ? "selected"
                      : ""
                  }
                  aria-pressed={form.source_version_ids.includes(
                    s.current_version_id,
                  )}
                  onClick={() =>
                    setForm({
                      ...form,
                      source_version_ids: form.source_version_ids.includes(
                        s.current_version_id,
                      )
                        ? form.source_version_ids.filter(
                            (id) => id !== s.current_version_id,
                          )
                        : [...form.source_version_ids, s.current_version_id],
                    })
                  }
                  key={s.id}
                >
                  <FileText size={14} />
                  {s.name}
                  <span>
                    {form.source_version_ids.includes(s.current_version_id) ? (
                      <Check size={14} />
                    ) : (
                      ""
                    )}
                  </span>
                </button>
              ))}
            {sources.filter((s) => s.latest_status === "ready").length ===
              0 && (
              <span className="muted">
                Upload a source first, or continue with an evidence gap.
              </span>
            )}
          </span>
        </label>
        <label>
          Active skills
          <span className="select-list">
            {skills
              .map((skill) => ({
                ...skill,
                version: skill.versions?.find((version) => version.status === "published"),
              }))
              .filter((skill) => skill.version)
              .map((skill) => (
                <button
                  type="button"
                  className={
                    form.skill_version_ids.includes(skill.version.id) ? "selected" : ""
                  }
                  aria-pressed={form.skill_version_ids.includes(skill.version.id)}
                  onClick={() =>
                    setForm({
                      ...form,
                      skill_version_ids: form.skill_version_ids.includes(skill.version.id)
                        ? form.skill_version_ids.filter((id) => id !== skill.version.id)
                        : [...form.skill_version_ids, skill.version.id],
                    })
                  }
                  key={skill.id}
                >
                  <Sparkles size={14} />
                  {skill.name}
                  <small>{skill.scope}</small>
                  <span>
                    {form.skill_version_ids.includes(skill.version.id) ? <Check size={14} /> : ""}
                  </span>
                </button>
              ))}
            {skills.filter((skill) =>
              skill.versions?.some((version) => version.status === "published"),
            ).length === 0 && (
              <span className="muted">Publish a skill first, or continue with the default harness.</span>
            )}
          </span>
        </label>
        <div className="modal-actions">
          <button className="soft-button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="primary-button"
            disabled={busy || !form.name || !form.brief}
            onClick={submit}
          >
            {busy ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Sparkles size={15} />
            )}{" "}
            Create project
          </button>
        </div>
      </div>
    </div>
  );
}
function SettingsModal({ onClose }) {
  const empty = {
    review_ai_edits: true,
    require_citations: true,
    default_export: "pdf",
    require_plan_approval: false,
    daily_token_budget: 100000,
    daily_cost_budget_usd: 25,
  };
  const [prefs, setPrefs] = useState(null);
  const [draft, setDraft] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => {
    let live = true;
    api("/v1/workspace/preferences")
      .then((value) => {
        if (live) {
          setPrefs(value);
          setDraft({
            review_ai_edits: value.review_ai_edits,
            require_citations: value.require_citations,
            default_export: value.default_export,
            require_plan_approval: value.require_plan_approval,
            daily_token_budget: value.daily_token_budget,
            daily_cost_budget_usd: value.daily_cost_budget_usd,
          });
        }
      })
      .catch((e) => {
        if (live) {
          setError(e);
        }
      });
    return () => {
      live = false;
    };
  }, [onClose]);
  const update = (key, value) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const save = async () => {
    setBusy(true);
    try {
      await api("/v1/workspace/preferences", {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-backdrop">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="workspace-settings-title"
      >
        <div className="modal-head">
          <div>
            <span className="eyebrow">WORKSPACE</span>
            <h2 id="workspace-settings-title">Settings</h2>
            {prefs && (
              <small className="muted">
                Preference version {prefs.version_no}
              </small>
            )}
          </div>
          <button
            className="icon-button"
            aria-label="Close settings dialog"
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </div>
        {error && <ErrorNotice error={error} onDismiss={() => setError(null)} />}
        {!prefs ? (
          <div role="status" className="loading-settings">
            Loading workspace preferences…
          </div>
        ) : (
          <>
            <div className="settings-row">
              <div>
                <strong>Review AI edits before applying</strong>
                <small>
                  Copilot proposes changes as a diff you accept or reject.
                </small>
              </div>
              <input
                aria-label="Review AI edits before applying"
                type="checkbox"
                checked={draft.review_ai_edits}
                onChange={(e) => update("review_ai_edits", e.target.checked)}
              />
            </div>
            <div className="settings-row">
              <div>
                <strong>Require citations for factual claims</strong>
                <small>
                  Unsupported paragraphs appear in validation findings.
                </small>
              </div>
              <input
                aria-label="Require citations for factual claims"
                type="checkbox"
                checked={draft.require_citations}
                onChange={(e) => update("require_citations", e.target.checked)}
              />
            </div>
            <div className="settings-row">
              <div>
                <strong>Require plan approval</strong>
                <small>
                  Pause the persistent collaborator before it drafts after an
                  outline.
                </small>
              </div>
              <input
                aria-label="Require plan approval"
                type="checkbox"
                checked={draft.require_plan_approval}
                onChange={(e) =>
                  update("require_plan_approval", e.target.checked)
                }
              />
            </div>
            <div className="settings-row">
              <div>
                <strong>Daily token budget</strong>
                <small>
                  Maximum estimated tokens used by this workspace per day.
                </small>
              </div>
              <input
                aria-label="Daily token budget"
                type="number"
                min="1000"
                value={draft.daily_token_budget}
                onChange={(e) =>
                  update("daily_token_budget", Number(e.target.value))
                }
              />
            </div>
            <div className="settings-row">
              <div>
                <strong>Daily cost budget</strong>
                <small>Maximum estimated provider cost in USD per day.</small>
              </div>
              <input
                aria-label="Daily cost budget"
                type="number"
                min="0.01"
                step="0.01"
                value={draft.daily_cost_budget_usd}
                onChange={(e) =>
                  update("daily_cost_budget_usd", Number(e.target.value))
                }
              />
            </div>
            <div className="settings-row">
              <div>
                <strong>Default export</strong>
                <small>
                  Deterministic render template for accepted content.
                </small>
              </div>
              <select
                aria-label="Default export format"
                value={draft.default_export}
                onChange={(e) => update("default_export", e.target.value)}
              >
                <option value="pdf">PDF</option>
                <option value="docx">DOCX</option>
                <option value="html">HTML</option>
                <option value="md">Markdown</option>
              </select>
            </div>
          </>
        )}
        <div className="modal-actions">
          <button className="soft-button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="primary-button"
            disabled={!prefs || busy}
            onClick={save}
          >
            {busy ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Check size={15} />
            )}{" "}
            Save settings
          </button>
        </div>
      </div>
    </div>
  );
}
function LoadingRows() {
  return (
    <div className="loading-list">
      {[1, 2, 3].map((i) => (
        <div className="skeleton-row" key={i}>
          <span />
          <div>
            <i />
            <i />
          </div>
        </div>
      ))}
    </div>
  );
}
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
