import { useEffect, useState } from "react";
import { ArrowRight, Check, LoaderCircle, Play, Sparkles } from "lucide-react";
import { post, request } from "../api";
import { SourcePicker } from "./AnalysisInputs";
import { ClarifyForm } from "./ClarifyForm";
import type { WorkspacePageProps } from "../pages/types";
export function Workflow({
  detail,
  busy,
  plan,
  confirm,
  setTab,
  setRunId,
  setModal,
  names,
  defaults,
  action,
  refresh,
}: WorkspacePageProps) {
  const [goal, setGoal] = useState(""),
    [revision, setRevision] = useState(""),
    [configured, setConfigured] = useState<boolean | null>(null),
    [sources, setSources] = useState(() =>
      Object.values(detail.plans.at(-1)?.snapshot?.datasets || {}).length
        ? Object.values(detail.plans.at(-1)!.snapshot!.datasets).filter((id) =>
            detail.datasets.some((d) => d.id === id),
          )
        : detail.datasets.map((d) => d.id),
    ),
    [seen, setSeen] = useState(detail.plans.at(-1)?.id);
  useEffect(() => {
    request<{ configured: boolean }>("/settings/model")
      .then((x) => setConfigured(x.configured))
      .catch(() => setConfigured(false));
  }, []);
  const latest = detail.plans.at(-1),
    run = detail.runs.find((r) => r.plan_id === latest?.id);
  const staleFiles =
    !!latest &&
    JSON.stringify(Object.values(latest.snapshot?.datasets || {}).sort()) !==
      JSON.stringify([...sources].sort());
  // Answering a question can change the files a plan uses (one of several tables,
  // a re-matched sample table); the selection follows the plan it produced.
  useEffect(() => {
    if (!latest || latest.id === seen) return;
    setSeen(latest.id);
    const used = Object.values(latest.snapshot?.datasets || {}).filter((id) =>
      detail.datasets.some((d) => d.id === id),
    );
    if (used.length) setSources(used);
  }, [latest, seen, detail.datasets]);
  async function propose() {
    const target = goal.trim() || latest?.objective;
    if (!target) return;
    if (configured === false) {
      setModal("settings");
      return;
    }
    await plan("agent", target, defaults, undefined, sources);
  }
  return (
    <>
      <SourcePicker
        datasets={detail.datasets}
        selected={sources}
        onChange={setSources}
      />
      <section className="question-composer">
        <h2>你希望从这些数据中了解什么？</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void propose();
          }}
        >
          <textarea
            id="research-goal"
            aria-label="研究问题"
            rows={3}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="例如：比较两组的菌群差异，或分析年龄与某项指标的关系。"
          />
          <div className="composer-actions">
            <button
              type="button"
              className="text-button"
              disabled={!!busy || !sources.length}
              onClick={() =>
                void plan(
                  configured ? "agent" : "overview",
                  "请根据所选文件及已保存背景，设计最少必要的描述性探索分析。不要推测分组，不进行没有研究目标的批量检验。",
                  defaults,
                  undefined,
                  sources,
                )
              }
            >
              <Sparkles size={16} />
              还没想好，请推荐分析
            </button>
            <button
              className="primary"
              disabled={
                !!busy ||
                !sources.length ||
                (!goal.trim() && !latest?.questions.length)
              }
            >
              {busy === "plan" ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              生成分析方案
            </button>
          </div>
        </form>
      </section>
      {latest && (
        <section className="analysis-design">
          <div className="section-title">
            <h2>{run ? "已执行的方案" : "核对这份分析方案"}</h2>
            <span className="badge">{run ? "已提交" : "等待你确认"}</span>
          </div>
          <h3>{latest.objective}</h3>
          {latest.summary.length > 220 ? (
            <details className="details">
              <summary>查看方案说明</summary>
              <p className="plan-summary">{latest.summary}</p>
            </details>
          ) : (
            <p className="plan-summary">{latest.summary}</p>
          )}
          {latest.research_design && (
            <div className="research-aims">
              <strong>这份方案将回答</strong>
              <ol>
                {latest.research_design.aims.map((aim) => (
                  <li key={aim.id}>{aim.question}</li>
                ))}
              </ol>
              {latest.research_design.interpretation && (
                <details className="details">
                  <summary>分析范围与解释</summary>
                  <p>{latest.research_design.interpretation}</p>
                </details>
              )}
            </div>
          )}
          <ol className="design-steps">
            {latest.steps.map((s, i) => (
              <li key={s.id}>
                <span>{i + 1}</span>
                <div>
                  <strong>{names[s.skill] || s.skill}</strong>
                  <p>{s.reason}</p>
                  {s.program && (
                    <div className="cohort-preview">
                      <strong>本次交付</strong>
                      <div className="step-bindings">
                        {s.program.outputs.map((output) => (
                          <span key={output.name}>
                            {output.kind === "chart" ? "图" : "表"} ·{" "}
                            {output.title}
                          </span>
                        ))}
                      </div>
                      <details className="details">
                        <summary>核对方法与完成要求</summary>
                        <p>{s.program.method}</p>
                        {s.program.requirements.map((requirement) => (
                          <p key={requirement.id}>{requirement.description}</p>
                        ))}
                      </details>
                      <details className="details">
                        <summary>
                          {run ? "查看确认时的程序" : "查看待执行程序"}
                        </summary>
                        <pre>{s.program.code}</pre>
                      </details>
                    </div>
                  )}
                  {Object.entries(s.inputs || {}).map(([alias, input]) => (
                    <div className="step-bindings" key={alias}>
                      <span>
                        使用步骤{" "}
                        {latest.steps.findIndex(
                          (step) => step.id === input.step_id,
                        ) + 1}{" "}
                        的
                        {input.output === "joined"
                          ? "合并数据"
                          : input.output === "associations"
                            ? "关联结果"
                            : input.output === "differential"
                              ? "差异结果"
                              : "结果表"}
                      </span>
                    </div>
                  ))}
                  {["partial_correlation", "adjusted_regression"].includes(
                    s.skill,
                  ) && (
                    <div className="step-bindings">
                      <span>
                        {s.parameters.predictors?.join("、") ||
                          s.parameters.x ||
                          "全部所选层级特征"}{" "}
                        → {s.parameters.outcomes?.join("、") || s.parameters.y}
                      </span>
                      <span>
                        {s.skill === "adjusted_regression"
                          ? `${s.parameters.standard_error || "HC3"} · ${s.parameters.standardize === false ? "原始尺度" : "标准化效应"}`
                          : s.parameters.correlation_method || "spearman"}
                      </span>
                      <span>
                        {s.parameters.adjustment === "none"
                          ? "原始 p 值"
                          : "BH 校正"}
                      </span>
                    </div>
                  )}
                  {["partial_correlation", "adjusted_regression"].includes(
                    s.skill,
                  ) &&
                    !!s.parameters.covariates?.length && (
                      <div className="step-bindings">
                        <span>校正 {s.parameters.covariates.join("、")}</span>
                      </div>
                    )}
                  {s.cohort_from && (
                    <div className="step-bindings">
                      <span>
                        使用步骤{" "}
                        {latest.steps.findIndex(
                          (step) => step.id === s.cohort_from,
                        ) + 1}{" "}
                        的分析队列
                      </span>
                    </div>
                  )}
                  {latest.preparation_preview
                    ?.filter((p) => p.step_id === s.id)
                    .map((p) => (
                      <div className="cohort-preview" key={p.step_id}>
                        {p.operations.map((op, index) => (
                          <div key={index}>
                            <strong>
                              {op.column}
                              {op.output ? ` → ${op.output}` : ""}
                            </strong>
                            {op.low_threshold !== undefined && (
                              <p>
                                下阈值 {op.low_threshold.toPrecision(5)} ·
                                上阈值 {op.high_threshold?.toPrecision(5)}
                              </p>
                            )}
                            {op.counts && (
                              <div className="step-bindings">
                                {Object.entries(op.counts).map(
                                  ([name, count]) => (
                                    <span key={name}>
                                      {name} · {count} 个样本
                                    </span>
                                  ),
                                )}
                              </div>
                            )}
                            {op.boundary && <p>{op.boundary}</p>}
                          </div>
                        ))}
                        <p>
                          纳入 {p.included} 个 · 未纳入 {p.excluded} 个
                        </p>
                        {Object.entries(p.exclusion_reasons).map(
                          ([reason, count]) => (
                            <p key={reason}>
                              {reason}：{count} 个
                            </p>
                          ),
                        )}
                      </div>
                    ))}

                  {!["data_check", "report"].includes(s.skill) && (
                    <div className="step-bindings">
                      {[
                        ...(s.parameters.fields || []),
                        s.parameters.group_by,
                        s.parameters.variable,
                        s.parameters.x,
                        s.parameters.y,
                        s.parameters.group_a,
                        s.parameters.group_b,
                      ]
                        .filter(Boolean)
                        .map((v, i) => (
                          <span key={i}>{v}</span>
                        ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
          {staleFiles ? (
            <div className="plan-questions">
              <p>本次选择的文件已变化，请重新生成方案。</p>
            </div>
          ) : latest.clarifications?.length ? (
            <ClarifyForm
              datasets={detail.datasets}
              cards={latest.clarifications}
              busy={!!busy}
              onOpenFiles={() => setTab("data")}
              onSubmit={(answers) =>
                void action("plan", async () => {
                  await post(
                    `/projects/${detail.id}/plans/${latest.id}/clarify`,
                    {
                      answers,
                    },
                  );
                  await refresh();
                })
              }
            />
          ) : latest.questions.length ? (
            // Plans stored before questions carried their own inputs.
            <div className="plan-questions">
              <h3>还有几项需要补充</h3>
              {latest.questions.map((q) => (
                <p key={q}>{q}</p>
              ))}
              <p>这份方案是旧版本生成的。重新生成后，可以直接在这里回答。</p>
              <div className="form-actions">
                <button
                  className="primary"
                  disabled={!!busy}
                  onClick={() => void propose()}
                >
                  重新生成方案
                </button>
              </div>
            </div>
          ) : (
            <div className="plan-confirm">
              {!run && (
                <div className="plan-revise">
                  <label htmlFor="plan-revision">
                    方案不符合预期？说明希望怎么改，可再次规划
                  </label>
                  <textarea
                    id="plan-revision"
                    rows={2}
                    value={revision}
                    onChange={(e) => setRevision(e.target.value)}
                    placeholder="例如：不要只看分布，请按性别对 Zinc 做组间显著性检验。"
                  />
                  <button
                    type="button"
                    className="text-button"
                    disabled={!!busy || !revision.trim()}
                    onClick={() =>
                      void action("plan", async () => {
                        if (configured === false) {
                          setModal("settings");
                          return;
                        }
                        await post(
                          `/projects/${detail.id}/plans/${latest.id}/revise`,
                          { message: revision.trim() },
                        );
                        setRevision("");
                        await refresh();
                      })
                    }
                  >
                    按说明重新规划
                  </button>
                </div>
              )}
              <button
                className="primary"
                disabled={!!busy}
                onClick={() => {
                  if (run) {
                    setRunId(run.id);
                    setTab("analysis");
                  } else void confirm(latest);
                }}
              >
                {run ? <Check size={16} /> : <Play size={16} />}{" "}
                {run ? "查看本次成果" : "认可方案，开始分析"}
              </button>
            </div>
          )}
          {!!latest.clarification_log?.length && (
            <details className="details">
              <summary>
                已按你的 {latest.clarification_log.length} 项说明生成
              </summary>
              {latest.clarification_log.map((note, index) => (
                <p key={index}>
                  {note.question}
                  <br />
                  <strong>{note.answer}</strong>
                </p>
              ))}
            </details>
          )}
          <details className="details">
            <summary>查看使用的文件和参数</summary>
            {Object.values(latest.snapshot?.datasets || {}).map((id) => (
              <p key={id}>
                {detail.datasets.find((d) => d.id === id)?.filename ||
                  "历史文件版本"}
              </p>
            ))}
            {latest.steps.map((s) => (
              <div key={s.id}>
                <strong>{names[s.skill]}</strong>
                <pre>{JSON.stringify(s.parameters, null, 2)}</pre>
              </div>
            ))}
          </details>
        </section>
      )}
    </>
  );
}
