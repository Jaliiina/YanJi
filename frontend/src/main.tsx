import {
  Activity,
  ChevronRight,
  Database,
  Download,
  FileText,
  FlaskConical,
  Folder,
  Layers3,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { artifactUrl, post, put, request } from "./api";
import { AnalysisPage } from "./pages/AnalysisPage";
import { DataPage } from "./pages/DataPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SkillsPage } from "./pages/SkillsPage";
import "./styles.css";
import type {
  ChatBody,
  DatasetDetail,
  Detail,
  Evidence,
  Parameters,
  Plan,
  Project,
  Run,
  Skill,
} from "./types";

import { Modal } from "./components/Common";
import { DatasetPanel, UploadPanel } from "./components/DataWorkspace";
import { ReportEditor } from "./components/ReportEditor";
import { ProjectPage } from "./pages/ProjectPage";
import { ProjectForm } from "./components/ProjectForm";
import { SettingsPanel } from "./components/SettingsPanel";
type Tab = "project" | "overview" | "data" | "analysis" | "report" | "skills";
const defaults: Parameters = {
  rank: "species",
  top_n: 15,
  palette: "forest",
  title: "",
  group_order: [],
  pathway: null,
  prevalence: 0.1,
  permutations: 999,
  seed: 42,
  group_a: null,
  group_b: null,
  variable: null,
  fields: [],
  samples: [],
  group_values: [],
  group_by: null,
};
function App() {
  const [projects, setProjects] = useState<Project[]>([]),
    [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null),
    [tab, setTab] = useState<Tab>("project"),
    [skills, setSkills] = useState<Skill[]>([]);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [modal, setModal] = useState<"new" | "upload" | "settings" | null>(null);
  const [editingProject, setEditingProject] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Pick<
    Project,
    "id" | "name"
  > | null>(null);
  const [deleteError, setDeleteError] = useState("");
  function askDelete(project: Pick<Project, "id" | "name">) {
    setDeleteError("");
    setDeleteTarget(project);
  }
  async function deleteProject() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    await action("delete-project", async () => {
      try {
        await request(`/projects/${target.id}`, { method: "DELETE" });
      } catch (error) {
        setDeleteError(error instanceof Error ? error.message : String(error));
        return;
      }
      if (detailRef.current === target.id) goHome();
      setProjects((previous) =>
        previous.filter((project) => project.id !== target.id),
      );
      setDeleteTarget(null);
      setNotice(`已删除项目「${target.name}」。`);
    });
  }
  const [busy, setBusy] = useState(""),
    [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [fileId, setFileId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null),
    [evidence, setEvidence] = useState<Evidence | null>(null);
  const detailRef = useRef(selected);
  useEffect(() => {
    const updated = (event: Event) => {
      if (event instanceof CustomEvent && event.detail?.datasetId)
        setFileId(event.detail.datasetId);
      setDataset(null);
      refresh().catch((e) => setError(e.message));
    };
    window.addEventListener("yanji:dataset-updated", updated);
    return () => window.removeEventListener("yanji:dataset-updated", updated);
  }, [selected]);
  detailRef.current = selected;
  async function refresh() {
    const ps = await request<Project[]>("/projects");
    if (detailRef.current !== selected) return;
    setProjects(ps.filter((p) => !p.synthetic));
    if (ps.find((p) => p.id === selected)?.synthetic) {
      setSelected(null);
      localStorage.removeItem("yanji-project");
      setDetail(null);
      return;
    }
    if (selected && !ps.some((p) => p.id === selected)) {
      setSelected(null);
      localStorage.removeItem("yanji-project");
      setDetail(null);
      return;
    }
    if (selected) {
      const d = await request<Detail>(`/projects/${selected}`);
      if (detailRef.current === selected) setDetail(d);
    } else setDetail(null);
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    request<Skill[]>("/skills")
      .then(setSkills)
      .catch((e) => setError(e.message));
  }, [selected]);
  useEffect(() => {
    if (!detail?.runs.some((r) => ["running", "queued"].includes(r.status)))
      return;
    const id = setInterval(() => refresh().catch(() => {}), 1800);
    return () => clearInterval(id);
  }, [detail?.runs.map((r) => r.status).join(","), selected]);
  function select(id: string) {
    detailRef.current = id;
    setDetail(null);
    setNotice("");
    setEvidence(null);
    setSelected(id);
    setRunId(null);
    setDataset(null);
    setFileId(null);
    setTab("project");
    setError("");
  }
  function goHome() {
    detailRef.current = null;
    setSelected(null);
    setDetail(null);
    setRunId(null);
    setDataset(null);
    setEvidence(null);
    setFileId(null);
    setModal(null);
    setError("");
    setNotice("");
    setTab("data");
    localStorage.removeItem("yanji-project");
  }
  async function action(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }
  function startResearch() {
    setEditingProject(false);
    setModal("new");
  }
  function editProject() {
    setEditingProject(true);
    setModal("new");
  }
  async function plan(
    mode: ChatBody["mode"],
    message: string,
    parameters = defaults,
    skillId?: string,
    datasetIds?: string[],
    study?: Project["study"],
  ) {
    if (!selected) return;
    await action("plan", async () => {
      await post<Plan>(`/projects/${selected}/chat`, {
        mode,
        message,
        include_report: false,
        dataset_ids: datasetIds || detail?.datasets.map((d) => d.id),
        ...(study ? { study } : {}),
        parameters:
          mode === "agent"
            ? Object.fromEntries(
                Object.entries(parameters).filter(
                  ([key, value]) =>
                    JSON.stringify(value) !==
                    JSON.stringify(defaults[key as keyof Parameters]),
                ),
              )
            : parameters,
        ...(skillId ? { skill_id: skillId } : {}),
      });
      await refresh();
      if (detailRef.current === selected) {
        setRunId(null);
        setTab("overview");
      }
    });
  }
  async function confirm(p: Plan) {
    if (!selected) return;
    await action("run", async () => {
      const run = await post<Run>(`/projects/${selected}/runs`, {
        plan_id: p.id,
      });
      if (detailRef.current !== selected) return;
      setRunId(run.id);
      setTab("analysis");
      await refresh();
    });
  }
  async function openDataset(id: string) {
    if (!selected) return;
    await action("dataset", async () =>
      setDataset(
        await request<DatasetDetail>(`/projects/${selected}/datasets/${id}`),
      ),
    );
  }
  const currentRun =
    detail?.runs.find((r) => r.id === runId) || detail?.runs.at(-1);
  const latestReport = currentRun
    ? detail?.reports.find((r) => r.run_id === currentRun?.id)
    : detail?.reports.at(-1);
  const names = Object.fromEntries(skills.map((s) => [s.id, s.name]));
  const pageProps = {
    detail: detail!,
    fileId,
    setFileId,
    busy,
    confirm,
    setModal,
    plan,
    setTab,
    setRunId,
    selected,
    refresh,
    setNotice,
    setError,
    names,
    action,
    currentRun,
    setEvidence,
    skills,
    defaults,
    openDataset,
  };
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            goHome();
          }}
        >
          <span className="brand-mark">
            <FlaskConical size={23} />
          </span>
          <span>
            研迹<small>智能科研工作台</small>
          </span>
        </a>
        <div className="sidebar-label">
          我的项目{" "}
          <button aria-label="新建项目" onClick={() => void startResearch()}>
            <Plus size={16} />
          </button>
        </div>
        <button className="new-project" onClick={() => void startResearch()}>
          <Plus size={16} /> 新建项目
        </button>
        <nav className="project-list">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => select(p.id)}
              className={selected === p.id ? "project active" : "project"}
            >
              <Folder size={17} />
              <span>{p.name}</span>
              {p.synthetic && <i>示例</i>}
            </button>
          ))}
        </nav>
        {detail && (
          <>
            <div className="sidebar-label section-label">当前项目</div>
            <nav className="section-nav">
              {(
                [
                  ["project", Folder, "项目概览"],
                  ["data", Database, "项目文件"],
                  ["overview", Activity, "开始分析"],
                  ["analysis", Layers3, "研究成果"],
                ] as const
              ).map(([id, Icon, label]) => (
                <button
                  key={id}
                  className={
                    tab === id ||
                    (id === "overview" && tab === "skills") ||
                    (id === "analysis" && tab === "report")
                      ? "selected"
                      : ""
                  }
                  onClick={() => setTab(id)}
                >
                  <Icon size={17} />
                  {label}
                </button>
              ))}
            </nav>
          </>
        )}
        <div className="sidebar-bottom">
          <div className="local-badge">
            <span /> 本地研究环境 <ShieldCheck size={14} />
          </div>
          <button onClick={() => setModal("settings")}>
            <Settings2 size={17} />
            模型与连接
          </button>
          <div className="profile">
            <div>研</div>
            <span>
              个人工作台<small>数据保存在这台电脑</small>
            </span>
          </div>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            项目空间 <ChevronRight size={14} />
            <strong>{detail?.name || "欢迎使用研迹"}</strong>
            {projects.length > 0 && (
              <select
                aria-label="切换研究"
                className="mobile-project-selector"
                value={selected || ""}
                onChange={(e) => select(e.target.value)}
              >
                <option value="" disabled>
                  选择研究
                </option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
            {detail?.synthetic && <span className="badge">合成示例</span>}
          </div>
          <div className="top-actions">
            <button
              className="mobile-new-project"
              aria-label="新建项目"
              onClick={() => void startResearch()}
            >
              <Plus size={17} />
            </button>
            <span className="saved">
              <span /> 本地保存
            </span>
            <button
              title="刷新"
              onClick={() => refresh().catch((e) => setError(e.message))}
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </header>
        {error && (
          <div role="alert" className="alert error">
            <span>{error}</span>
            <button onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {notice && (
          <div className="alert info">
            <span>{notice}</span>
            <button onClick={() => setNotice("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {!detail ? (
          <div className="welcome research-welcome project-home">
            <div className="page-heading">
              <div>
                <div className="eyebrow">研迹 · 个人科研工作台</div>
                <h1>我的项目</h1>
              </div>
              <button className="primary" onClick={() => startResearch()}>
                <Plus size={18} />
                新建项目
              </button>
            </div>
            {projects.length ? (
              <div className="project-home-grid">
                {projects.map((p) => (
                  <div className="project-card-shell" key={p.id}>
                    <button
                      onClick={() => select(p.id)}
                      className="project-home-card"
                    >
                      <Folder size={23} />
                      <h2>{p.name}</h2>
                      <p>{p.description || "暂无备注"}</p>
                      <span>
                        打开项目 <ChevronRight size={15} />
                      </span>
                    </button>
                    <button
                      className="project-card-delete"
                      aria-label={`删除项目「${p.name}」`}
                      title="删除项目"
                      disabled={!!busy}
                      onClick={() => askDelete(p)}
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="first-project">
                <Folder size={36} />
                <h2>从一个项目开始</h2>
                <p>给研究起个名字，把文件、分析和成果放在一起。</p>
                <button className="primary" onClick={() => startResearch()}>
                  创建第一个项目
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="work-columns full">
            <div className="main-scroll">
              {tab === "project" && (
                <ProjectPage
                  {...pageProps}
                  onEdit={editProject}
                  onDelete={() => askDelete(detail)}
                />
              )}
              {tab !== "project" && (
                <>
                  {tab === "overview" && (
                    <OverviewPage key={detail.id} {...pageProps} />
                  )}
                  {tab === "data" && <DataPage {...pageProps} />}
                  {tab === "analysis" && <AnalysisPage {...pageProps} />}
                  {tab === "report" && (
                    <>
                      <div className="page-heading">
                        <h1>研究成果</h1>
                      </div>
                      <div className="workspace-switch">
                        <button onClick={() => setTab("analysis")}>
                          分析结果
                        </button>
                        <button className="selected">论文与报告</button>
                      </div>
                      {latestReport ? (
                        <ReportEditor
                          key={`${detail.id}-${currentRun?.id || "latest"}`}
                          initialRunId={currentRun?.id}
                          reports={detail.reports}
                          pid={detail.id}
                          onSave={refresh}
                          onError={setError}
                          onEvidence={setEvidence}
                        />
                      ) : (
                        <div className="writing-start">
                          <FileText size={34} />
                          <h2>把研究结果整理成报告</h2>
                          {currentRun?.status === "completed" ? (
                            <button
                              className="primary"
                              disabled={!!busy}
                              onClick={() =>
                                void action("report", async () => {
                                  await post(
                                    `/projects/${detail.id}/runs/${currentRun.id}/report`,
                                  );
                                  await refresh();
                                })
                              }
                            >
                              {busy === "report"
                                ? "正在整理…"
                                : "使用本次结果生成报告"}
                            </button>
                          ) : (
                            <button
                              className="secondary"
                              onClick={() => setTab("overview")}
                            >
                              先完成一次分析
                            </button>
                          )}
                        </div>
                      )}
                    </>
                  )}
                  {tab === "skills" && <SkillsPage {...pageProps} />}
                </>
              )}
            </div>
          </div>
        )}
      </main>
      {deleteTarget && (
        <Modal
          title="删除项目"
          onClose={() => {
            if (!busy) setDeleteTarget(null);
          }}
        >
          <p>删除项目「{deleteTarget.name}」？</p>
          <p className="project-delete-note">
            项目、上传文件、分析结果和报告会从本机删除，不能恢复。
          </p>
          {deleteError && (
            <p role="alert" className="small-warning">
              {deleteError}
            </p>
          )}
          <div className="form-actions">
            <button
              className="secondary"
              disabled={!!busy}
              onClick={() => setDeleteTarget(null)}
            >
              取消
            </button>
            <button
              className="danger-button"
              disabled={!!busy}
              onClick={() => void deleteProject()}
            >
              {busy === "delete-project" ? "正在删除…" : "确认删除"}
            </button>
          </div>
        </Modal>
      )}
      {modal === "new" && (
        <Modal
          title={editingProject ? "编辑项目" : "新建项目"}
          onClose={() => setModal(null)}
        >
          <ProjectForm
            initial={editingProject ? detail : null}
            onSubmit={async (name, description) => {
              if (editingProject && selected) {
                await put(`/projects/${selected}`, { name, description });
                await refresh();
                setModal(null);
              } else {
                const p = await post<Project>("/projects", {
                  name,
                  description,
                });
                select(p.id);
                setModal(null);
              }
            }}
          />
        </Modal>
      )}
      {modal === "upload" && selected && (
        <Modal title="添加项目文件" onClose={() => setModal(null)}>
          <UploadPanel
            pid={selected}
            onDone={async () => {
              await refresh();
              setModal(null);
              setTab("data");
              setNotice("");
            }}
          />
        </Modal>
      )}
      {modal === "settings" && (
        <Modal title="模型与连接" onClose={() => setModal(null)}>
          <SettingsPanel />
        </Modal>
      )}
      {dataset && selected && (
        <Modal
          wide
          title="文件读取设置"
          subtitle={dataset.filename + " · 版本 " + dataset.revision}
          onClose={() => setDataset(null)}
        >
          <DatasetPanel
            dataset={dataset}
            onConfirm={async (mapping, excluded) => {
              const mapped = await post<DatasetDetail>(
                `/projects/${selected}/datasets/${dataset.id}/mapping`,
                { mapping, excluded_samples: excluded },
              );
              setFileId(mapped.id);
              await refresh();
              setDataset(null);
              setNotice("已保存新的数据版本。");
            }}
            onRemove={async () => {
              await request(`/projects/${selected}/datasets/${dataset.id}`, {
                method: "DELETE",
              });
              await refresh();
              setDataset(null);
            }}
          />
        </Modal>
      )}
      {evidence && (
        <Modal
          wide
          title="结论依据"
          subtitle="来源与实际结果"
          onClose={() => setEvidence(null)}
        >
          <p className="evidence-statement">{evidence.statement}</p>
          <h3>计算结果</h3>
          <pre>{JSON.stringify(evidence.values, null, 2)}</pre>
          <h3>参数</h3>
          <pre>{JSON.stringify(evidence.parameters, null, 2)}</pre>
          <div className="template-row">
            {evidence.artifact_ids.map((id) => (
              <a className="secondary" href={artifactUrl(id)} download key={id}>
                <Download size={14} />
                结果表
              </a>
            ))}
          </div>
          <details className="details">
            <summary>数据版本</summary>
            <p>{evidence.dataset_ids.join(" · ")}</p>
          </details>
        </Modal>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
