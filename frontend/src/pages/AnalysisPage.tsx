import {
  ArrowUpRight,
  Check,
  FileText,
  Layers3,
  LoaderCircle,
  RefreshCw,
  Square,
} from "lucide-react";
import { useState } from "react";
import { post } from "../api";
import { Empty, PageHead } from "../components/Common";
import { ResultCard, RunLog } from "../components/Results";
import type { WorkspacePageProps } from "./types";
function time(s: string) {
  return new Date(s.endsWith("Z") ? s : s + "Z").toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
const stateLabels: Record<string, string> = {
  queued: "等待执行",
  running: "正在分析",
  completed: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
export function AnalysisPage({
  detail,
  busy,
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
}: WorkspacePageProps) {
  const [revising, setRevising] = useState(false);
  const [revision, setRevision] = useState("");
  return (
    <>
      <PageHead title="研究成果" />
      <div className="workspace-switch">
        <button className="selected">分析结果</button>
        <button onClick={() => setTab("report")}>论文与报告</button>
      </div>
      <div className="run-selector">
        <select
          value={currentRun?.id || ""}
          onChange={(e) => setRunId(e.target.value)}
        >
          <option value="" disabled>
            选择分析运行
          </option>
          {[...detail.runs].reverse().map((r) => (
            <option key={r.id} value={r.id}>
              {time(r.created_at)} · {r.plan.objective.slice(0, 45)}
            </option>
          ))}
        </select>
        {currentRun && (
          <span className={"status " + currentRun.status}>
            {currentRun.partial ? "部分完成" : stateLabels[currentRun.status]}
          </span>
        )}
      </div>
      {currentRun ? (
        <>
          <details className="details run-source">
            <summary>数据来源 · {detail.name}</summary>
            {Object.values(
              (currentRun.snapshot as { datasets?: Record<string, string> })
                ?.datasets || {},
            ).map((id) => (
              <p key={id}>
                {detail.datasets.find((d) => d.id === id)?.filename ||
                  "历史数据版本"}
              </p>
            ))}
            {detail.synthetic && <p>合成示例，不能作为真实研究结果。</p>}
          </details>
          <div className="run-summary">
            <h2>{currentRun.plan.objective}</h2>
            <div className="progress">
              <i style={{ width: currentRun.progress + "%" }} />
            </div>
            <div className="run-meta">
              <span>
                {currentRun.progress}% · {currentRun.plan.steps.length} 个步骤
              </span>
              <div>
                {["queued", "running"].includes(currentRun.status) && (
                  <button
                    className="text-button"
                    disabled={!!busy}
                    onClick={() =>
                      action("cancel", async () => {
                        await post(
                          `/projects/${selected}/runs/${currentRun.id}/cancel`,
                        );
                        await refresh();
                      })
                    }
                  >
                    <Square size={12} />
                    停止
                  </button>
                )}
                {["failed", "interrupted", "cancelled"].includes(
                  currentRun.status,
                ) && (
                  <button
                    className="text-button"
                    disabled={!!busy}
                    onClick={() =>
                      action("retry", async () => {
                        await post(
                          `/projects/${selected}/runs/${currentRun.id}/retry`,
                        );
                        await refresh();
                      })
                    }
                  >
                    <RefreshCw size={14} />
                    修复并继续
                  </button>
                )}
              </div>
            </div>
            {currentRun.error && (
              <div className="recovery-panel">
                <strong>
                  已保留{" "}
                  {
                    currentRun.results.filter((r) => r.status === "success")
                      .length
                  }{" "}
                  项完成结果
                </strong>
                <p>
                  {currentRun.results
                    .filter((r) => r.status === "failed")
                    .map((r) => r.failure?.message || r.summary)
                    .filter(Boolean)
                    .join(" ") ||
                    "修复后从未完成处继续；需要改变分析方法时，可调整方案后重新确认。"}
                </p>
                <button
                  className="text-button"
                  onClick={() => setRevising((v) => !v)}
                >
                  调整方案
                </button>
                {revising && (
                  <div className="revision-form">
                    <textarea
                      aria-label="希望如何调整分析"
                      placeholder="说明希望如何调整，也可直接让智能体重新设计未完成部分"
                      value={revision}
                      onChange={(e) => setRevision(e.target.value)}
                    />
                    <button
                      className="primary"
                      disabled={!!busy}
                      onClick={() =>
                        void plan(
                          "agent",
                          `${currentRun.plan.objective}\n方案调整：${revision || "根据原研究目标重新设计未完成环节，检查数据关系和结果传递，保留可以复用的计算。"}\n上次未完成步骤：${currentRun.plan.steps
                            .filter(
                              (s) =>
                                !currentRun.results.some(
                                  (r) =>
                                    r.step_id === s.id &&
                                    r.status === "success",
                                ),
                            )
                            .map(
                              (s) =>
                                `${names[s.skill]}：${s.program?.method || s.reason || ""}`,
                            )
                            .join("；")}`,
                          defaults,
                          undefined,
                          Object.values(
                            (
                              currentRun.snapshot as {
                                datasets: Record<string, string>;
                              }
                            ).datasets,
                          ),
                          (
                            currentRun.snapshot as {
                              study: WorkspacePageProps["detail"]["study"];
                            }
                          ).study,
                        )
                      }
                    >
                      生成调整方案
                    </button>
                  </div>
                )}
                <details className="details">
                  <summary>技术详情</summary>
                  <pre>
                    {currentRun.results
                      .filter((r) => r.status === "failed")
                      .map((r) => r.failure?.detail || r.summary)
                      .join("\n\n") || currentRun.error}
                  </pre>
                </details>
              </div>
            )}
          </div>
          <div className="step-track">
            {currentRun.plan.steps.map((s, i) => {
              const r = currentRun.results.find(
                (result) => result.step_id === s.id,
              );
              return (
                <div
                  className={
                    r
                      ? r.status !== "success"
                        ? r.status === "failed"
                          ? "failed"
                          : "skipped"
                        : "done"
                      : currentRun.current_step === i &&
                          currentRun.status === "running"
                        ? "doing"
                        : ""
                  }
                  key={s.id}
                >
                  <span>
                    {r?.status === "success" ? <Check size={12} /> : i + 1}
                  </span>
                  <div>{names[s.skill] || s.skill}</div>
                </div>
              );
            })}
          </div>
          {currentRun.results
            .filter(
              (r) =>
                r.skill !== "report" &&
                (r.skill !== "data_check" || currentRun.results.length === 1),
            )
            .map((r) => (
              <ResultCard
                key={`${currentRun.id}-${r.step_id}`}
                result={r}
                name={names[r.skill]}
                onEvidence={setEvidence}
                parameters={
                  currentRun.plan.steps.find((s) => s.id === r.step_id)
                    ?.parameters || defaults
                }
                onReconfigure={(p) =>
                  plan(
                    "skill",
                    `重新运行${names[r.skill]}，按新参数生成图表和报告。`,
                    p,
                    r.skill,
                    Object.values(
                      (
                        currentRun.snapshot as
                          { datasets?: Record<string, string> } | undefined
                      )?.datasets || {},
                    ),
                    (
                      currentRun.snapshot as {
                        study?: WorkspacePageProps["detail"]["study"];
                      }
                    )?.study,
                  )
                }
              />
            ))}
          {currentRun.status === "running" && (
            <div className="working">
              <LoaderCircle className="spin" size={21} />
              <div>
                <strong>
                  正在执行{" "}
                  {names[
                    currentRun.plan.steps[currentRun.current_step]?.skill
                  ] || "分析"}
                </strong>
                <p>离开页面后继续执行。</p>
              </div>
            </div>
          )}
          {currentRun.status === "completed" && (
            <button className="report-ready" onClick={() => setTab("report")}>
              <FileText size={25} />
              <div>
                <strong>
                  {detail.reports.some((r) => r.run_id === currentRun.id)
                    ? "查看研究报告"
                    : "将本次结果整理为报告"}
                </strong>
              </div>
              <ArrowUpRight size={20} />
            </button>
          )}
          <details className="details">
            <summary>查看执行事件与日志</summary>
            <RunLog pid={detail.id} run={currentRun} />
          </details>
        </>
      ) : (
        <Empty
          icon={<Layers3 size={30} />}
          title="还没有分析成果"
          text="在“开始分析”中提出问题，确认方案后，这里会保存结果与图表。"
        />
      )}
      {!currentRun && (
        <button
          className="primary"
          onClick={() => setTab(detail.datasets.length ? "overview" : "data")}
        >
          {detail.datasets.length ? "开始第一次分析" : "先添加项目文件"}
        </button>
      )}
    </>
  );
}
