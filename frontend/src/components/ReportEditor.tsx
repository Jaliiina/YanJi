import { useEffect, useState } from "react";
import { post, request } from "../api";
import { LiteraturePanel } from "./LiteraturePanel";
import type { Run } from "../types";

import {
  ArrowDown,
  ArrowUp,
  Download,
  Plus,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { API, artifactUrl, put } from "../api";
import type { Evidence, Report, ReportSection } from "../types";

function time(s: string) {
  return new Date(s.endsWith("Z") ? s : s + "Z").toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
export function ReportEditor({
  reports,
  initialRunId,
  pid,
  onSave,
  onError,
  onEvidence,
}: {
  reports: Report[];
  initialRunId?: string;
  pid: string;
  onSave: () => Promise<void>;
  onError: (s: string) => void;
  onEvidence: (e: Evidence) => void;
}) {
  const [report, setReport] = useState(
      reports.find((r) => r.run_id === initialRunId) || reports.at(-1)!,
    ),
    [edited, setEdited] = useState(false),
    [saving, setSaving] = useState(false),
    [editMode, setEditMode] = useState(false);
  const [draft, setDraft] = useState<{
      section: string;
      text: string;
      evidence_ids: string[];
      report_revision: number;
    } | null>(null),
    [drafting, setDrafting] = useState("");
  const options = [...reports].reverse();
  const [availableFigures, setAvailableFigures] = useState<string[]>([]);
  const stale = reports.find((r) => r.id === report.id)?.stale ?? report.stale;
  useEffect(() => {
    request<Run>(`/projects/${pid}/runs/${report.run_id}`)
      .then((run) =>
        setAvailableFigures(
          Array.from(
            new Set(
              run.results.flatMap((r) =>
                r.artifacts
                  .filter((a) => a.artifact_type === "png")
                  .map((a) => a.id),
              ),
            ),
          ),
        ),
      )
      .catch(() =>
        setAvailableFigures(
          Array.from(new Set(report.sections.flatMap((s) => s.artifact_ids))),
        ),
      );
  }, [pid, report.run_id]);
  function change(index: number, patch: Partial<ReportSection>) {
    setReport({
      ...report,
      sections: report.sections.map((s, i) =>
        i === index ? { ...s, ...patch } : s,
      ),
    });
    setEdited(true);
  }
  function move(i: number, d: number) {
    const ss = [...report.sections];
    [ss[i], ss[i + d]] = [ss[i + d], ss[i]];
    setReport({ ...report, sections: ss });
    setEdited(true);
  }
  return (
    <>
      <div className="report-toolbar">
        <select
          value={report.id}
          disabled={!!drafting || saving}
          onChange={(e) => {
            if (edited && !confirm("切换会放弃未保存修改，继续吗？")) return;
            setReport(reports.find((r) => r.id === e.target.value)!);
            setEdited(false);
          }}
        >
          {options.map((r) => (
            <option key={r.id} value={r.id}>
              {time(r.created_at)} · {r.title} · 运行 {r.run_id.slice(0, 8)} ·
              版本 {r.revision}
            </option>
          ))}
        </select>
        <button className="secondary" onClick={() => setEditMode((x) => !x)}>
          {editMode ? "阅读模式" : "编辑报告"}
        </button>
        {editMode && (
          <button
            className="primary"
            disabled={saving || !edited}
            onClick={async () => {
              setSaving(true);
              try {
                const updated = await put<Report>(
                  `/projects/${pid}/reports/${report.id}`,
                  {
                    title: report.title,
                    sections: report.sections,
                    expected_revision: report.revision,
                  },
                );
                setReport({ ...updated, stale: report.stale });
                setEdited(false);
                await onSave();
              } catch (e) {
                onError((e as Error).message);
              } finally {
                setSaving(false);
              }
            }}
          >
            保存修改
          </button>
        )}
      </div>
      {stale && (
        <div className="alert info">
          数据或样本设置已更新，此报告关联旧版本。请重新分析；原报告内容仍保留。
        </div>
      )}
      {edited && (
        <p className="small-warning">有未保存修改，请保存后再导出。</p>
      )}
      <div className="export-row">
        {[
          ["docx", "Word 文档"],
          ["pdf", "PDF 报告"],
          ["zip", "分析复现包"],
        ].map(([kind, t]) => (
          <a
            className={"secondary " + (edited ? "disabled" : "")}
            href={`${API}/projects/${pid}/reports/${report.id}/export/${kind}`}
            key={kind}
          >
            <Download size={15} />
            {t}
          </a>
        ))}
        <span className="badge">
          {report.ai_status === "assisted" ? "已整理结果" : "计算结果草稿"}
        </span>
      </div>
      <LiteraturePanel
        pid={pid}
        report={report}
        disabled={edited}
        onUpdate={(r) => {
          setReport({ ...r, stale: report.stale });
          void onSave();
        }}
      />
      <article className="report-paper">
        {editMode ? (
          <input
            className="report-title-input"
            value={report.title}
            onChange={(e) => {
              setReport({ ...report, title: e.target.value });
              setEdited(true);
            }}
          />
        ) : (
          <h1>{report.title}</h1>
        )}
        <div className="report-subtitle">
          研迹 · 研究分析报告 <span>版本 {report.revision}</span>
        </div>
        {report.sections.map((s, i) => (
          <section className="report-section" key={s.id}>
            {editMode ? (
              <>
                <div className="edit-section-head">
                  <input
                    value={s.title}
                    onChange={(e) => change(i, { title: e.target.value })}
                  />
                  <button
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                    title="上移"
                  >
                    <ArrowUp size={15} />
                  </button>
                  <button
                    disabled={i === report.sections.length - 1}
                    onClick={() => move(i, 1)}
                    title="下移"
                  >
                    <ArrowDown size={15} />
                  </button>
                  <button
                    title="删除章节"
                    onClick={() => {
                      setReport({
                        ...report,
                        sections: report.sections.filter((_, j) => j !== i),
                      });
                      setEdited(true);
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <div className="section-writing-actions">
                  <button
                    className="text-button"
                    disabled={edited || !!drafting}
                    onClick={async () => {
                      setDrafting(s.id);
                      try {
                        const result = await post<{
                          text: string;
                          evidence_ids: string[];
                          report_revision: number;
                        }>(`/projects/${pid}/reports/${report.id}/draft`, {
                          section_id: s.id,
                          instruction:
                            "将本节整理为连贯、准确的中文论文段落。保留证据与局限，不添加缺失的研究细节。",
                          expected_revision: report.revision,
                        });
                        setDraft({ section: s.id, ...result });
                      } catch (e) {
                        onError((e as Error).message);
                      } finally {
                        setDrafting("");
                      }
                    }}
                  >
                    {drafting === s.id ? "正在起草…" : "起草本节"}
                  </button>
                </div>
                {draft?.section === s.id && (
                  <div className="writing-draft">
                    <h3>待审核草稿</h3>
                    <p>{draft.text}</p>
                    <div className="form-actions">
                      <button
                        className="secondary"
                        onClick={() => setDraft(null)}
                      >
                        不用这稿
                      </button>
                      <button
                        className="primary"
                        disabled={
                          edited || draft.report_revision !== report.revision
                        }
                        onClick={() => {
                          change(i, {
                            text: draft.text,
                            evidence_ids: draft.evidence_ids,
                          });
                          setDraft(null);
                        }}
                      >
                        采用并继续编辑
                      </button>
                    </div>
                  </div>
                )}
                <textarea
                  rows={Math.max(
                    3,
                    Math.min(12, s.text.split("\n").length + 2),
                  )}
                  value={s.text}
                  onChange={(e) => change(i, { text: e.target.value })}
                />
              </>
            ) : (
              <>
                <h2>{s.title}</h2>
                <p className="report-text">{s.text}</p>
              </>
            )}
            {editMode && availableFigures.length > 0 && (
              <details className="details">
                <summary>选择本节图表</summary>
                <div className="figure-picker">
                  {availableFigures.map((aid, index) => (
                    <label className="check-label" key={aid}>
                      <input
                        type="checkbox"
                        checked={s.artifact_ids.includes(aid)}
                        onChange={(e) =>
                          change(i, {
                            artifact_ids: e.target.checked
                              ? [...s.artifact_ids, aid]
                              : s.artifact_ids.filter((x) => x !== aid),
                          })
                        }
                      />
                      <img src={artifactUrl(aid)} alt={"图表 " + (index + 1)} />
                      <span>图表 {index + 1}</span>
                    </label>
                  ))}
                </div>
              </details>
            )}
            {s.evidence_ids.map((id) => {
              const e = report.evidence.find((x) => x.id === id);
              return (
                e && (
                  <button
                    key={id}
                    className="evidence-ref"
                    onClick={() => onEvidence(e)}
                  >
                    <ShieldCheck size={12} />
                    {e.parameters?.source === "literature"
                      ? "文献依据"
                      : "计算依据"}
                  </button>
                )
              );
            })}
            {s.artifact_ids.map((id) => (
              <div className="report-figure" key={id}>
                <img src={artifactUrl(id)} alt={s.title} />
                {editMode && (
                  <button
                    className="text-button"
                    onClick={() =>
                      change(i, {
                        artifact_ids: s.artifact_ids.filter((x) => x !== id),
                      })
                    }
                  >
                    <X size={13} />
                    从本节移除图表
                  </button>
                )}
              </div>
            ))}
          </section>
        ))}
        {editMode && (
          <button
            className="secondary"
            onClick={() => {
              setReport({
                ...report,
                sections: [
                  ...report.sections,
                  {
                    id: "custom_" + crypto.randomUUID().slice(0, 8),
                    title: "补充说明",
                    text: "",
                    evidence_ids: [],
                    artifact_ids: [],
                  },
                ],
              });
              setEdited(true);
            }}
          >
            <Plus size={15} />
            添加章节
          </button>
        )}
      </article>
    </>
  );
}
