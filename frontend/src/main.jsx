import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Download,
  Database,
  FileText,
  Grid2X2,
  GripVertical,
  Library,
  LoaderCircle,
  Moon,
  PanelLeft,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { api, subscribeToEvents } from "./api";
import { AgentEventLabel } from "./ai/AgentEventLabel";
import { SkillAuthorPanel } from "./ai/SkillAuthorPanel";
import { CommandPalette, EmptyState, PageHeader } from "./components";
import "./styles.css";
import "./ui/reference-theme.css";

const fmt = (date) =>
  date
    ? new Date(date).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      })
    : "—";
const iconFor = (type) =>
  type === "pdf" ? "PDF" : type === "docx" ? "DOC" : "TXT";
const PROJECT_TYPES = {
  knowledge_brief: { label: "Training Course", color: "#a78bfa" },
  training_guide: { label: "Training Course", color: "#a78bfa" },
  sop: { label: "SOP", color: "#f0b429" },
  technical_documentation: { label: "Technical Documentation", color: "#5b93f0" },
  research_report: { label: "Report", color: "#4ade80" },
  user_manual: { label: "User Manual", color: "#2dd4bf" },
};
const projectTypeMeta = (type) =>
  PROJECT_TYPES[type] || {
    label: String(type || "Project").replaceAll("_", " "),
    color: "#5b93f0",
  };
const projectStatusMeta = (project) => {
  const status = project.status || "outline";
  if (status === "completed" || status === "exported") {
    return { label: "Exported", color: "#4ade80", progress: 100 };
  }
  if (status === "review" || status === "waiting_for_approval") {
    return { label: "Review", color: "#f0b429", progress: 82 };
  }
  if (status === "outline") {
    return { label: "Outline", color: "#94a3b8", progress: 18 };
  }
  return {
    label: "Drafting",
    color: "#5b93f0",
    progress: project.latest_run_status === "completed" ? 64 : 38,
  };
};
const classifyError = (error) => {
  if (error?.code === "PERMISSION_DENIED" || error?.code === "UNAUTHENTICATED") {
    return "permission";
  }
  if (error?.retryable || error?.code === "DEPENDENCY_UNAVAILABLE") {
    return "retryable";
  }
  return "terminal";
};

async function fetchProjectPage(limit = 50, cursor = "") {
  const suffix = cursor
    ? `?limit=${limit}&cursor=${encodeURIComponent(cursor)}`
    : `?limit=${limit}`;
  try {
    return await api(`/v1/projects/page${suffix}`);
  } catch (error) {
    // Older local servers registered `/v1/projects/{project_id}` before the
    // paginated collection route and therefore interpret "page" as an ID.
    // Keep local development usable while the canonical paginated endpoint
    // remains the first and production path.
    if (cursor || error?.code !== "RESOURCE_NOT_FOUND") throw error;
    const items = await api("/v1/projects");
    return { items: items.slice(0, limit), next_cursor: null };
  }
}

function App() {
  const [screen, setScreen] = useState("projects");
  const [projects, setProjects] = useState([]);
  const [sources, setSources] = useState([]);
  const [skills, setSkills] = useState([]);
  const [activeProject, setActiveProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingMoreProjects, setLoadingMoreProjects] = useState(false);
  const [projectCursor, setProjectCursor] = useState(null);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [palette, setPalette] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [sourceQuery, setSourceQuery] = useState("");
  const [projectQuery, setProjectQuery] = useState("");
  const [theme, setTheme] = useState("dark");

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const [p, s, k] = await Promise.all([
        fetchProjectPage(),
        api("/v1/sources"),
        api("/v1/skills"),
      ]);
      setProjects(p.items);
      setProjectCursor(p.next_cursor);
      setSources(s);
      setSkills(k);
    } catch (e) {
      setError({ message: e.message, code: e.code, retryable: e.retryable });
    } finally {
      setLoading(false);
    }
  };
  const loadMoreProjects = async () => {
    if (!projectCursor || loadingMoreProjects) return;
    setLoadingMoreProjects(true);
    try {
      const page = await fetchProjectPage(50, projectCursor);
      setProjects((current) => [...current, ...page.items]);
      setProjectCursor(page.next_cursor);
    } catch (e) {
      setError({ message: e.message, code: e.code, retryable: e.retryable });
    } finally {
      setLoadingMoreProjects(false);
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
    setError("");
    setPalette(false);
  };

  return (
    <div className="app-shell" data-theme={theme}>
      <Sidebar
        collapsed={collapsed}
        screen={screen}
        onNav={nav}
        onPalette={() => setPalette(true)}
        onSettings={() => setSettingsOpen(true)}
        onToggle={() => setCollapsed(!collapsed)}
        theme={theme}
        onTheme={() => setTheme((current) => current === "dark" ? "light" : "dark")}
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
            hasMore={Boolean(projectCursor)}
            loadingMore={loadingMoreProjects}
            onLoadMore={loadMoreProjects}
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
            onNavigateSources={() => nav("sources")}
            onRefresh={refresh}
          />
        )}
      </main>
      {newProjectOpen && (
          <NewProjectModal
            sources={sources}
            skills={skills}
            onRefresh={refresh}
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
  theme,
  onTheme,
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
        <div className="brand-copy">
          <span className="brand-name">groundloom</span>
          <span className="brand-subtitle">Knowledge Studio</span>
        </div>
      </div>
      <div className="nav-label">Workspace</div>
      <div className="nav-group">
        {item("projects", "Projects", Grid2X2)}
        {item("sources", "Sources", Database)}
        {item("skills", "Skills", Sparkles)}
      </div>
      <div className="nav-bottom">
        <button className="nav-item" onClick={onPalette}>
          <Search size={17} />
          <span>Search</span>
          <kbd>⌘K</kbd>
        </button>
        <button className="nav-item" onClick={onTheme}>
          {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
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

function ProjectsScreen({
  loading,
  projects,
  query,
  setQuery,
  onOpen,
  onNew,
  hasMore,
  loadingMore,
  onLoadMore,
}) {
  const [status, setStatus] = useState("all");
  const statuses = ["all", "outline", "drafting", "review", "exported"];
  const matchesStatus = (project, value) => {
    if (value === "all") return true;
    const normalized = projectStatusMeta(project).label.toLowerCase();
    return normalized === value;
  };
  const shown = projects.filter(
    (p) =>
      `${p.name} ${p.project_type}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      matchesStatus(p, status),
  );
  const statusCounts = Object.fromEntries(
    statuses.map((value) => [
      value,
      value === "all" ? projects.length : projects.filter((p) => matchesStatus(p, value)).length,
    ]),
  );
  return (
    <section className="page">
      <PageHeader
        title="Projects"
        meta={`${projects.length} total · ${projects.reduce((n, p) => n + p.source_count, 0)} sources`}
        action={
          <button className="primary-button" onClick={onNew}>
            <Plus size={15} /> New Project
          </button>
        }
      />
      <div className="toolbar projects-toolbar">
        <div className="search-box">
          <Search size={15} />
          <input
            aria-label="Search projects"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search projects…"
          />
        </div>
        <div className="project-filters" role="group" aria-label="Filter projects">
          {statuses.map((value) => (
            <button
              key={value}
              className={`filter-button ${status === value ? "selected" : ""}`}
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
            >
              {value[0].toUpperCase() + value.slice(1)}
              <span>{statusCounts[value]}</span>
            </button>
          ))}
        </div>
      </div>
      {loading ? (
        <LoadingRows />
      ) : shown.length === 0 ? (
        <EmptyState
          icon={Search}
          title={
            query || status !== "all"
              ? "Nothing matches that filter"
              : "Your studio is empty"
          }
          body={
            query || status !== "all"
              ? "Try a different status, clear the search, or start something new from your sources."
              : "Start with a brief, selected evidence, and a persistent collaborator."
          }
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
              style={{ "--type-color": projectTypeMeta(p.project_type).color }}
              onClick={() => onOpen(p)}
            >
              <div className="card-top">
                <span className="project-type-label">
                  <span className="project-type-dot" />
                  {projectTypeMeta(p.project_type).label}
                </span>
                <span className="card-date">{fmt(p.updated_at)}</span>
              </div>
              <h2>{p.name}</h2>
              <div className="project-status-row">
                <span
                  className={`status-dot ${p.status}`}
                  style={{ color: projectStatusMeta(p).color }}
                >
                  {projectStatusMeta(p).label}
                </span>
                <div className="progress-line">
                  <span
                    style={{
                      width: `${projectStatusMeta(p).progress}%`,
                      background: projectStatusMeta(p).color,
                    }}
                  />
                </div>
                <span className="project-progress-value">{projectStatusMeta(p).progress}%</span>
              </div>
              <div className="card-footer">
                <span>{p.source_count} sources</span>
                <span>{p.section_count} sections</span>
              </div>
            </button>
          ))}
        </div>
      )}
      {!loading && shown.length > 0 && hasMore && (
        <div className="pagination-actions">
          <button className="soft-button" onClick={onLoadMore} disabled={loadingMore}>
            {loadingMore ? <LoaderCircle className="spin" size={15} /> : <ChevronDown size={15} />}
            {loadingMore ? "Loading projects…" : "Load more projects"}
          </button>
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
        title="Sources"
        meta={`${sources.length} documents ingested`}
        action={<UploadButton label="Upload" onUploaded={onRefresh} />}
      />
      <div className="toolbar sources-toolbar">
        <div className="search-box">
          <Search size={15} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by filename…"
          />
        </div>
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
            <span>Filename</span>
            <span>Type</span>
            <span>Version</span>
            <span>Status</span>
            <span>Added</span>
          </div>
          {shown.map((s) => (
            <div className="table-row" key={s.id}>
              <div className="source-name">
                <span className={`file-badge ${s.source_type}`}>
                  {iconFor(s.source_type)}
                </span>
                <div>
                  <strong>{s.name}</strong>
                </div>
              </div>
              <span className="source-type-cell">{s.source_type.toUpperCase()}</span>
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

function UploadButton({ onUploaded, sourceId = null, label = "Upload source" }) {
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
        <Upload size={15} /> {label}
        <input type="file" accept=".txt,.md,.pdf,.docx" onChange={upload} />
      </label>
      {error && <ErrorNotice error={error} onDismiss={() => setError(null)} />}
    </>
  );
}

function SkillsScreen({ skills, onRefresh }) {
  const [open, setOpen] = useState(null);
  const [skillQuery, setSkillQuery] = useState("");
  const [newMenuOpen, setNewMenuOpen] = useState(false);
  const [openScopes, setOpenScopes] = useState({
    starter: true,
    organization: true,
    workspace: true,
  });
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
  const normalizedQuery = skillQuery.trim().toLowerCase();
  const visibleSkills = skills.filter(
    (skill) =>
      !normalizedQuery ||
      skill.name.toLowerCase().includes(normalizedQuery) ||
      skill.slug.toLowerCase().includes(normalizedQuery) ||
      skill.description.toLowerCase().includes(normalizedQuery),
  );
  const scopeGroups = [
    { id: "starter", name: "Starter", hint: "Built in and maintained with Groundloom" },
    { id: "organization", name: "Organization", hint: "Shared policy and reusable team guidance" },
    { id: "workspace", name: "Workspace", hint: ".groundloom/skills/ — private to this workspace" },
  ];
  const importSkill = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const content = String(reader.result || "");
      const stem = file.name.replace(/\.md$/i, "");
      setForm({
        slug: stem.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""),
        name: stem.replace(/[-_]+/g, " ").replace(/\b\w/g, (value) => value.toUpperCase()),
        description: "Imported workspace skill",
        content,
      });
      setCreating(true);
      setNewMenuOpen(false);
      event.target.value = "";
    };
    reader.onerror = () => setMessage("The selected skill file could not be read.");
    reader.readAsText(file);
  };
  return (
    <section className="page">
      <div className="skills-title-row">
        <h1>Skills</h1>
        <span>{skills.length}</span>
      </div>
      <p className="lede">
        Folders of instructions and reference material that Copilot loads when
        a drafting task calls for them. Each one is a <code>SKILL.md</code> file
        — YAML frontmatter for the name and trigger description, markdown below
        for the rules.
      </p>
      <div className="skills-controls">
        <label className="skills-search">
          <Search size={13} />
          <input
            aria-label="Search skills"
            value={skillQuery}
            onChange={(event) => setSkillQuery(event.target.value)}
            placeholder="Type to search…"
          />
        </label>
        <div className="new-skill-split">
          <button
            className="new-skill-main"
            onClick={() => {
              setCreating(true);
              setNewMenuOpen(false);
            }}
          >
            <Plus size={13} /> New Skill (Workspace)
          </button>
          <button
            className="new-skill-more"
            aria-label="More ways to create a skill"
            aria-expanded={newMenuOpen}
            onClick={() => setNewMenuOpen((current) => !current)}
          >
            <ChevronDown size={12} />
          </button>
          {newMenuOpen && (
            <div className="new-skill-menu">
              <button
                aria-label="AI author draft"
                onClick={() => {
                  setAuthoring(true);
                  setNewMenuOpen(false);
                }}
              >
                <Sparkles size={13} />
                <span><strong>AI author draft</strong><small>Describe the behaviour — Copilot writes the SKILL.md</small></span>
              </button>
              <button
                aria-label="Blank SKILL.md"
                onClick={() => {
                  setCreating(true);
                  setNewMenuOpen(false);
                }}
              >
                <FileText size={13} />
                <span><strong>Blank SKILL.md</strong><small>Start from the frontmatter skeleton</small></span>
              </button>
              <label className="skill-import-action">
                <Upload size={13} />
                <span><strong>Import a .md file</strong><small>Bring in an existing skill file</small></span>
                <input type="file" accept=".md,text/markdown,text/plain" onChange={importSkill} />
              </label>
            </div>
          )}
        </div>
      </div>
      {message && (
        <div className="error-banner" role="alert">
          <CircleHelp size={15} /> {message}
          <button onClick={() => setMessage("")}>Dismiss</button>
        </div>
      )}
      {authoring && (
        <SkillAuthorPanel
          authorForm={authorForm}
          setAuthorForm={setAuthorForm}
          busyAction={busyAction}
          onAuthor={author}
          onClose={() => setAuthoring(false)}
        />
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
      <div className="skill-list">
        {scopeGroups.map((group) => {
          const groupSkills = visibleSkills.filter((skill) => skill.scope === group.id);
          return (
          <section className="skill-scope-group" key={group.id}>
            <button
              className="skill-scope-heading"
              aria-expanded={openScopes[group.id]}
              onClick={() => setOpenScopes((current) => ({
                ...current,
                [group.id]: !current[group.id],
              }))}
            >
              <strong>{group.name}</strong>
              <span>{groupSkills.length}</span>
              <small>{group.hint}</small>
              <ChevronDown className={openScopes[group.id] ? "" : "closed"} size={12} />
            </button>
            {openScopes[group.id] && (
              <div className="skill-scope-items">
              {groupSkills.map((skill) => (
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
              {groupSkills.length === 0 && (
                <div className="skill-scope-empty">No match in this scope.</div>
              )}
              </div>
            )}
          </section>
          );
        })}
        {visibleSkills.length === 0 && skills.length === 0 && (
          <EmptyState
            icon={Sparkles}
            title="No skills yet"
            body="Create a workspace skill draft to add reusable instructions."
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

function Canvas({ project, sources, onBack, onNavigateSources, onRefresh }) {
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
  const [sourcePanelOpen, setSourcePanelOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [evidence, setEvidence] = useState(null);
  const [connection, setConnection] = useState("connecting");
  const [approvals, setApprovals] = useState([]);
  const [run, setRun] = useState(null);
  const [operationError, setOperationError] = useState(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState("pdf");
  const [exportBusy, setExportBusy] = useState(false);
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
    load().catch((e) => {
      if (e.code === "RESOURCE_NOT_FOUND") {
        onBack();
        return;
      }
      setOperationError(e);
    });
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
          load().catch((e) => {
            if (e.code === "RESOURCE_NOT_FOUND") onBack();
            else setOperationError(e);
          });
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
  const performExport = async () => {
    if (!content?.version?.id) return;
    setExportBusy(true);
    try {
      const job = await api("/v1/exports", {
        method: "POST",
        body: JSON.stringify({
          project_id: project.id,
          content_version_id: content.version.id,
          format: exportFormat,
        }),
      });
      window.open(job.download_url, "_blank");
      setExportOpen(false);
    } catch (e) {
      setOperationError(e);
    } finally {
      setExportBusy(false);
    }
  };
  const lastActivity = [...events]
    .reverse()
    .find((e) => e.type === "run.completed" || e.type === "artifact.delta") || events.at(-1);
  const cancellable = [
    "queued",
    "running",
    "waiting_for_user",
    "waiting_for_approval",
  ].includes(run?.status);
  const resumable = ["failed", "cancelled", "waiting_for_user"].includes(
    run?.status,
  );
  const selectedSources = sources.filter((source) =>
    project.config.source_version_ids.includes(source.current_version_id),
  );
  const typeMeta = projectTypeMeta(project.project_type);
  return (
    <section className="canvas reference-canvas">
      <div className="canvas-body">
        <aside className="source-rail">
          <button
            className={sourcePanelOpen ? "active" : ""}
            aria-label={sourcePanelOpen ? "Close Sources" : "Open Sources"}
            aria-expanded={sourcePanelOpen}
            onClick={() => setSourcePanelOpen((open) => !open)}
          >
            <PanelLeft size={16} />
          </button>
          <button
            className="source-rail-label"
            onClick={() => setSourcePanelOpen((open) => !open)}
          >
            Sources · {selectedSources.length}
          </button>
        </aside>

        {sourcePanelOpen && (
          <>
            <button
              className="source-flyout-scrim"
              aria-label="Close Sources"
              onClick={() => setSourcePanelOpen(false)}
            />
            <aside className="source-flyout">
              <div className="source-flyout-head">
                <button onClick={() => setSourcePanelOpen(false)}>
                  <ChevronRight size={14} /> Sources
                </button>
                <button className="soft-button compact" onClick={onNavigateSources}>
                  <Plus size={12} /> Add
                </button>
              </div>
              <div className="rail-tabs">
                <button className={rail === "sources" ? "selected" : ""} onClick={() => setRail("sources")}>Sources</button>
                <button className={rail === "search" ? "selected" : ""} onClick={() => setRail("search")}>Search</button>
              </div>
              {rail === "sources" ? (
                <div className="rail-content">
                  {selectedSources.map((source) => (
                    <button className="rail-source" key={source.id}>
                      <span className={`file-badge ${source.source_type}`}>{iconFor(source.source_type)}</span>
                      <span>{source.name}</span>
                      <small>v{source.versions?.[0]?.version_no || 1}</small>
                    </button>
                  ))}
                  {selectedSources.length === 0 && <div className="empty-mini">No sources selected.</div>}
                </div>
              ) : (
                <div className="rail-content rail-search-content">
                  <div className="search-box">
                    <Search size={14} />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      onKeyDown={(event) => event.key === "Enter" && search()}
                      placeholder="Search evidence…"
                    />
                  </div>
                  {evidence?.passages.map((passage) => (
                    <button className="evidence-item" key={passage.passage_id} onClick={() => setCitation(passage)}>
                      <strong>{passage.source_name}</strong>
                      <span>{passage.text}</span>
                      <small>p.{passage.page || "—"} · {Math.round(passage.score * 100)}% match</small>
                    </button>
                  ))}
                </div>
              )}
            </aside>
          </>
        )}

        <div className="canvas-main">
          <header className="canvas-header">
            <div className="canvas-breadcrumb">
              <button className="icon-button" aria-label="Back to projects" onClick={onBack}><ArrowLeft size={15} /></button>
              <button className="crumb-back" onClick={onBack}>Projects</button>
              <span>/</span>
              <span className="canvas-project-type" style={{ color: typeMeta.color }}>
                <i style={{ background: typeMeta.color }} /> {typeMeta.label}
              </span>
              <strong>{project.name}</strong>
            </div>
            <div className="canvas-actions">
              <button className="icon-button" aria-label="Refresh project canvas" onClick={load}><RefreshCw size={14} /></button>
              <div className="phase-switch" role="group" aria-label="Project phase">
                <button className={tab === "outline" ? "active" : ""} onClick={() => setTab("outline")}>Outline</button>
                <button className={tab === "content" ? "active" : ""} onClick={() => setTab("content")}>Content</button>
              </div>
              <button className="soft-button review-button" onClick={runValidation}><ShieldCheck size={14} /> Review</button>
              <button className="primary-button" onClick={() => setExportOpen(true)}><Download size={14} /> Export</button>
            </div>
          </header>
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
          <div className="editor-scroll">
            <div className="editor-document">
              {tab === "outline" ? <OutlineView outline={outline} /> : <ContentView content={content} onCitation={openCitation} />}
              {patches.filter((patch) => patch.status === "presented").map((patch) => (
                <DiffCard key={patch.id} patch={patch} onAccept={() => accept(patch)} onReject={() => reject(patch)} />
              ))}
            </div>
          </div>
          <footer className="canvas-stats">
            <div>
              <span>{outline?.items?.length || 0} modules</span>
              <span>{content?.blocks?.length || 0} blocks</span>
              <span>{selectedSources.length} sources</span>
            </div>
            <span>⌘K for commands</span>
          </footer>
        </div>

        <div className="canvas-divider" />

        <aside className="copilot">
          <div className="copilot-head">
            <span className="copilot-mark"><Sparkles size={13} /></span>
            <div>
              <strong>Copilot</strong>
              <small>{tab === "outline" ? "OUTLINE" : "CONTENT"} · PERSISTENT COLLABORATOR</small>
            </div>
            <span className={`live-dot ${connection}`} title={`Activity stream ${connection}`} aria-label={`Activity stream ${connection}`} />
            {run && <span className="run-status" role="status">Run {run.status}</span>}
          </div>
          <div className="activity-scroll">
            <div className="copilot-message assistant">
              <div className="message-author"><span><Sparkles size={9} /></span> Copilot</div>
              <p>{lastActivity?.payload?.summary || "I’m ready to shape the outline, draft grounded content, or revise the current project with you."}</p>
            </div>
            <div className="activity-summary">
              <button className="activity-summary-head" type="button">
                <span className="activity-icon"><Zap size={14} /></span>
                <strong>{run ? `Project run · ${run.status}` : "Project collaborator is ready"}</strong>
                <small>{events.length} events</small>
                <ChevronRight size={12} />
              </button>
              <div className="activity-log">
                <small>{events.length ? `${events.length} durable events · replayable · ${connection}` : `No activity yet · ${connection}`}</small>
                {(cancellable || resumable) && (
                  <div className="run-controls">
                    {cancellable && <button className="soft-button compact" onClick={cancel}>Cancel run</button>}
                    {resumable && <button className="primary-button compact" onClick={resume}>Resume run</button>}
                  </div>
                )}
                {events.slice(-6).map((event) => (
                  <div className="event-row" key={event.event_id}>
                    <span className="event-kind">{event.type.split(".")[0]}</span>
                    <span><AgentEventLabel event={event} /></span>
                  </div>
                ))}
              </div>
            </div>
            {approvals.filter((approval) => approval.status === "pending").map((approval) => (
              <div className="approval-card" key={approval.id}>
                <strong>Plan approval required</strong>
                <small>Review the proposed outline before the collaborator continues.</small>
                <div>
                  <button className="soft-button" onClick={() => resolveApproval(approval, "rejected")}>Reject plan</button>
                  <button className="primary-button" onClick={() => resolveApproval(approval, "approved")}>Approve plan</button>
                </div>
              </div>
            ))}
            {project.todos?.length > 0 && (
              <div className="review-checklist">
                <span>Review checklist</span>
                {project.todos.map((todo) => (
                  <div className="todo-row" key={todo.id}>
                    <span className={`todo-check ${todo.status}`}>{todo.status === "completed" ? <Check size={11} /> : <span />}</span>
                    <span>{todo.description}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="copilot-compose">
            <div className="composer-box">
              <textarea
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && (event.metaKey || event.ctrlKey) && send()}
                placeholder="Ask Copilot, or describe a change…"
              />
              <div className="composer-actions">
                <button className="icon-button" aria-label="Attach a source" onClick={onNavigateSources}><Plus size={15} /></button>
                <span>Groundloom Copilot</span>
                <i>⌘↵</i>
                <button className="send-button" aria-label="Send message" disabled={busy || !message.trim()} onClick={send}>
                  {busy ? <LoaderCircle className="spin" size={14} /> : <>Send <ArrowRight size={14} /></>}
                </button>
              </div>
            </div>
          </div>
        </aside>
      </div>
      {citation && (
        <CitationPanel citation={citation} onClose={() => setCitation(null)} />
      )}
      {validationOpen && validation && (
        <ValidationPanel validation={validation} onClose={() => setValidationOpen(false)} />
      )}
      {exportOpen && (
        <ExportPanel
          project={project}
          content={content}
          format={exportFormat}
          setFormat={setExportFormat}
          busy={exportBusy}
          onExport={performExport}
          onClose={() => setExportOpen(false)}
        />
      )}
    </section>
  );
}

function ExportPanel({ project, content, format, setFormat, busy, onExport, onClose }) {
  const formats = [
    ["pdf", "PDF", "Print-ready"],
    ["docx", "DOCX", "Editable"],
    ["html", "HTML", "Web"],
    ["md", "Markdown", "Plain text"],
  ];
  return (
    <div className="export-layer">
      <button className="export-scrim" aria-label="Close export preview" onClick={onClose} />
      <aside className="export-sheet" role="dialog" aria-modal="true" aria-label="Export and Preview">
        <header>
          <button className="soft-button compact" onClick={onClose}><ArrowLeft size={13} /> Editor</button>
          <h2>Export &amp; Preview</h2>
          <span>{project.name}</span>
        </header>
        <div className="export-body">
          <section className="export-preview">
            <div className="preview-page">
              <span className="preview-mark">G</span>
              <small>{projectTypeMeta(project.project_type).label}</small>
              <h1>{project.name}</h1>
              <p>Grounded project export · accepted content version {content?.version?.version_no || "—"}</p>
              <div className="preview-rule" />
              <h3>Document preview</h3>
              <p>The production renderer uses the selected accepted content version, pinned evidence, and deterministic export template.</p>
            </div>
          </section>
          <aside className="export-options">
            <label>Format</label>
            <div className="export-format-grid">
              {formats.map(([value, label, detail]) => (
                <button key={value} className={format === value ? "selected" : ""} onClick={() => setFormat(value)}>
                  <strong>{label}</strong><small>{detail}</small>
                </button>
              ))}
            </div>
            <label>Template</label>
            <select aria-label="Export template" defaultValue="groundloom">
              <option value="groundloom">Groundloom standard</option>
            </select>
            <div className="export-version">
              <span>Content version</span>
              <strong>v{content?.version?.version_no || "—"} · {content?.version?.status || "unavailable"}</strong>
            </div>
            <button className="primary-button export-submit" disabled={busy || !content?.version?.id} onClick={onExport}>
              {busy ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}
              Export {format.toUpperCase()}
            </button>
          </aside>
        </div>
      </aside>
    </div>
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
function listItemText(item) {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    return item.text || item.label || item.question || JSON.stringify(item);
  }
  return String(item ?? "");
}

function TypedBlockBody({ block }) {
  const payload = block.payload || {};
  if (block.type === "heading") {
    return <h1>{payload.text || ""}</h1>;
  }
  if (["ordered_procedure", "quiz"].includes(block.type)) {
    return (
      <ol>
        {(payload.items || []).map((item, index) => (
          <li key={`${block.id}-item-${index}`}>{listItemText(item)}</li>
        ))}
      </ol>
    );
  }
  if (["unordered_procedure", "objective_list", "checklist", "source_list"].includes(block.type)) {
    return (
      <ul>
        {(payload.items || []).map((item, index) => (
          <li key={`${block.id}-item-${index}`}>{listItemText(item)}</li>
        ))}
      </ul>
    );
  }
  if (block.type === "table") {
    const columns = Array.isArray(payload.columns) ? payload.columns : [];
    const rows = Array.isArray(payload.rows) ? payload.rows : [];
    return (
      <div className="typed-table" role="region" aria-label="Content table" tabIndex="0">
        <table>
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`${block.id}-row-${rowIndex}`}>
                {columns.map((_, columnIndex) => (
                  <td key={`${block.id}-cell-${rowIndex}-${columnIndex}`}>{String(row[columnIndex] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (block.type === "figure") {
    return (
      <figure className="figure-placeholder" role="img" aria-label={payload.alt_text || "Figure placeholder"}>
        <span>{payload.asset_ref ? `Asset: ${payload.asset_ref}` : "Figure placeholder"}</span>
        <figcaption>{payload.alt_text || ""}</figcaption>
      </figure>
    );
  }
  return <p>{payload.text || ""}</p>;
}

function ContentView({ content, onCitation }) {
  return (
    <div className="document-pane content-pane">
      {content?.blocks?.length ? (
        content.blocks.map((block) => (
          <article className={`content-block ${block.type}`} key={block.id}>
            <span className="block-label">{block.type}</span>
            <TypedBlockBody block={block} />
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

function NewProjectModal({ sources, skills, onRefresh, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "",
    project_type: "knowledge_brief",
    brief: "",
    source_version_ids: [],
    skill_version_ids: [],
  });
  const [busy, setBusy] = useState(false);
  const [uploadingSource, setUploadingSource] = useState(false);
  const [error, setError] = useState(null);
  const readySources = sources.filter((source) => source.latest_status === "ready");
  const publishedSkills = skills
    .map((skill) => ({
      ...skill,
      version: skill.versions?.find((version) => version.status === "published"),
    }))
    .filter((skill) => skill.version);
  const projectTypes = [
    { value: "knowledge_brief", label: "Training Course", color: "#a78bfa" },
    { value: "sop", label: "SOP", color: "#f0b429" },
    { value: "technical_documentation", label: "Technical Documentation", color: "#5b93f0" },
    { value: "user_manual", label: "User Manual", color: "#2dd4bf" },
  ];
  const uploadSource = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadingSource(true);
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        await api("/v1/sources/uploads", {
          method: "POST",
          body: JSON.stringify({
            name: file.name.replace(/\.[^.]+$/, ""),
            filename: file.name,
            content_base64: String(reader.result).split(",")[1],
            mime_type: file.type || "text/plain",
          }),
        });
        await onRefresh?.();
      } catch (uploadError) {
        setError(uploadError);
      } finally {
        setUploadingSource(false);
        event.target.value = "";
      }
    };
    reader.readAsDataURL(file);
  };
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
        aria-label="Start a grounded workspace"
      >
        <div className="modal-head">
          <h2 id="new-project-title">New Project</h2>
          <button
            className="icon-button"
            aria-label="Close new project dialog"
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </div>
        <div className="new-project-body">
          {error && <ErrorNotice error={error} onDismiss={() => setError(null)} />}
          <label className="modal-field">
            Project name
            <input
              aria-label="Project name"
              autoFocus
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Field maintenance guide"
            />
          </label>
          <div className="modal-field">
            <span>Content type</span>
            <select
              className="sr-only"
              aria-label="Project type"
              value={form.project_type}
              onChange={(e) => setForm({ ...form, project_type: e.target.value })}
            >
              {projectTypes.map((type) => (
                <option value={type.value} key={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
            <div className="content-type-grid" role="radiogroup" aria-label="Project type choices">
              {projectTypes.map((type) => (
                <button
                  type="button"
                  className={form.project_type === type.value ? "selected" : ""}
                  role="radio"
                  aria-checked={form.project_type === type.value}
                  onClick={() => setForm({ ...form, project_type: type.value })}
                  key={type.value}
                >
                  <span className="content-type-dot" style={{ background: type.color }} />
                  <strong>{type.label}</strong>
                </button>
              ))}
            </div>
          </div>
          <div className="modal-field">
            <span>Sources</span>
            <label className="source-dropzone">
              <Upload size={20} />
              <div>
                <strong>{uploadingSource ? "Uploading source…" : <>Drag &amp; drop files, or <em>browse</em></>}</strong>
                <small>PDF · DOCX · URL · up to 200MB each</small>
              </div>
              <input
                type="file"
                accept=".txt,.md,.pdf,.docx"
                aria-label="Upload source"
                disabled={uploadingSource}
                onChange={uploadSource}
              />
            </label>
            <span className="select-list source-selection-list">
              {readySources.map((source) => (
                <button
                  type="button"
                  className={form.source_version_ids.includes(source.current_version_id) ? "selected" : ""}
                  aria-pressed={form.source_version_ids.includes(source.current_version_id)}
                  onClick={() =>
                    setForm({
                      ...form,
                      source_version_ids: form.source_version_ids.includes(source.current_version_id)
                        ? form.source_version_ids.filter((id) => id !== source.current_version_id)
                        : [...form.source_version_ids, source.current_version_id],
                    })
                  }
                  key={source.id}
                >
                  <FileText size={14} />
                  <span className="selection-name">{source.name}</span>
                  <span>
                    {form.source_version_ids.includes(source.current_version_id) ? <Check size={14} /> : ""}
                  </span>
                </button>
              ))}
              {readySources.length === 0 && <span className="muted">No sources selected. Evidence gap is allowed.</span>}
            </span>
          </div>
          <label className="modal-field">
            Brief
            <textarea
              aria-label="Project brief"
              value={form.brief}
              onChange={(e) => setForm({ ...form, brief: e.target.value })}
              placeholder="Describe what you want to create, the target audience, and any constraints…"
            />
          </label>
          <div className="modal-field">
            <span>Active skills</span>
            <span className="select-list skill-selection-list">
              {publishedSkills.map((skill) => (
                <button
                  type="button"
                  className={form.skill_version_ids.includes(skill.version.id) ? "selected" : ""}
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
                  <span className="selection-name">{skill.name}</span>
                  <small>{skill.scope}</small>
                  <span>{form.skill_version_ids.includes(skill.version.id) ? <Check size={14} /> : ""}</span>
                </button>
              ))}
              {publishedSkills.length === 0 && (
                <span className="muted">Publish a skill first, or continue with the default harness.</span>
              )}
            </span>
          </div>
        </div>
        <div className="new-project-footer">
          <span className="new-project-summary">
            {form.source_version_ids.length} sources · {form.skill_version_ids.length} skills selected
          </span>
          <div className="modal-actions">
            <button className="soft-button" onClick={onClose}>Cancel</button>
            <button
              className="primary-button"
              aria-label="Create project"
              disabled={busy || !form.name || !form.brief}
              onClick={submit}
            >
              {busy ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />} Generate Outline
            </button>
          </div>
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
