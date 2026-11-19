import {
  ArrowRight,
  Check,
  FileText,
  FolderOpen,
  MessageSquare,
  Plus,
  Trash2,
} from "lucide-react";
import type { WorkspacePageProps } from "./types";
export function ProjectPage({
  detail,
  setModal,
  setTab,
  setRunId,
  setFileId,
  onEdit,
  onDelete,
  busy,
}: WorkspacePageProps & { onEdit: () => void; onDelete: () => void }) {
  const hasFiles = detail.datasets.length > 0,
    hasRuns = detail.runs.length > 0;
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">项目概览</div>
          <h1>{detail.name}</h1>
        </div>
        <div className="project-heading-actions">
          <button className="secondary" onClick={onEdit}>
            编辑项目
          </button>
          <button
            className="text-button project-delete-action"
            disabled={!!busy}
            onClick={onDelete}
          >
            <Trash2 size={16} />
            删除项目
          </button>
        </div>
      </div>
      {detail.description ? (
        <p className="project-note">{detail.description}</p>
      ) : (
        <button className="text-button project-note" onClick={onEdit}>
          <MessageSquare size={16} />
          添加项目备注
        </button>
      )}
      <section className="project-next">
        <div>
          <span className="step-kicker">
            {hasFiles ? "下一步 · 开始分析" : "第一步 · 添加项目文件"}
          </span>
          <h2>
            {hasFiles ? "文件已放好，你想了解什么？" : "先把研究材料放进来"}
          </h2>
          <p>
            {hasFiles
              ? "围绕一个问题设计方案，确认后再执行。"
              : "上传表格后先看内容，不需要先填写一套分析设置。"}
          </p>
        </div>
        <button
          className="primary"
          onClick={() => (hasFiles ? setTab("overview") : setModal("upload"))}
        >
          {hasFiles ? "开始分析" : "添加文件"}
          <ArrowRight size={17} />
        </button>
      </section>
      <div className="project-route">
        {[
          {
            n: "1",
            title: "项目文件",
            text: hasFiles
              ? `${detail.datasets.length} 份文件`
              : "上传并查看内容",
            go: () => setTab("data"),
            done: hasFiles,
          },
          {
            n: "2",
            title: "开始分析",
            text: "提出问题，确认方案",
            go: () => setTab("overview"),
            done: hasRuns,
          },
          {
            n: "3",
            title: "研究成果",
            text: hasRuns
              ? `${detail.runs.length} 次分析记录`
              : "图表、结果与报告",
            go: () => setTab("analysis"),
            done: detail.runs.some((r) => r.status === "completed"),
          },
        ].map((s) => (
          <button key={s.n} onClick={s.go}>
            <span>{s.done ? <Check size={17} /> : s.n}</span>
            <div>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </div>
            <ArrowRight size={17} />
          </button>
        ))}
      </div>
      <div className="project-collections">
        <section>
          <div className="section-title">
            <h2>项目文件</h2>
            <button className="text-button" onClick={() => setModal("upload")}>
              <Plus size={16} />
              添加
            </button>
          </div>
          {hasFiles ? (
            <>
              {detail.datasets.slice(0, 5).map((d) => (
                <button
                  className="collection-row"
                  key={d.id}
                  onClick={() => setTab("data")}
                >
                  <FileText size={18} />
                  <strong>{d.filename}</strong>
                  <span>
                    {d.transformations?.find((t) => t.sheet)?.sheet ||
                      `${d.summary.rows || d.samples.length} 行`}
                  </span>
                </button>
              ))}
              <button className="text-button" onClick={() => setTab("data")}>
                查看全部文件 <ArrowRight size={15} />
              </button>
            </>
          ) : (
            <div className="collection-empty">
              <FolderOpen size={25} />
              <p>还没有文件</p>
            </div>
          )}
        </section>
        <section>
          <div className="section-title">
            <h2>最近分析</h2>
          </div>
          {hasRuns ? (
            [...detail.runs]
              .reverse()
              .slice(0, 4)
              .map((r) => (
                <button
                  className="collection-row"
                  key={r.id}
                  onClick={() => {
                    setRunId(r.id);
                    setTab("analysis");
                  }}
                >
                  <strong>{r.plan.objective}</strong>
                  <span>
                    {{
                      completed: r.partial ? "部分完成" : "已完成",
                      queued: "排队中",
                      running: "执行中",
                      failed: "失败",
                      interrupted: "中断",
                      cancelled: "已取消",
                    }[r.status] || r.status}
                  </span>
                </button>
              ))
          ) : (
            <div className="collection-empty">
              <p>
                {hasFiles
                  ? "还没有分析，准备好后就可以开始。"
                  : "添加文件后，开始第一次分析"}
              </p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
