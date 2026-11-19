import { useEffect, useRef, useState } from "react";

import { BarChart, ScatterChart, SankeyChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import {
  CheckCircle2,
  Download,
  RefreshCw,
  ShieldCheck,
  Table2,
} from "lucide-react";
import { artifactUrl, request } from "../api";
import type {
  Artifact,
  Evidence,
  Parameters,
  Preview,
  Result,
  Run,
} from "../types";
echarts.use([
  SankeyChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);

import { DataTable } from "./DataWorkspace";
function time(s: string) {
  return new Date(s.endsWith("Z") ? s : s + "Z").toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
export function Chart({
  artifact,
  fallbackUrl,
  title,
}: {
  artifact: Artifact;
  fallbackUrl?: string;
  title?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let chart: ReturnType<typeof echarts.init> | undefined;
    let gone = false;
    setFailed(false);
    request<Record<string, unknown>>(`/artifacts/${artifact.id}`)
      .then((option) => {
        if (!ref.current || gone) return;
        chart = echarts.init(ref.current);
        chart.setOption(option);
        const observer = new ResizeObserver(() => chart?.resize());
        observer.observe(ref.current!);
        cleanup = () => {
          observer.disconnect();
          chart?.dispose();
        };
      })
      .catch(() => {
        if (!gone) setFailed(true);
      });
    let cleanup = () => chart?.dispose();
    return () => {
      gone = true;
      cleanup();
    };
  }, [artifact.id]);
  if (failed && fallbackUrl) {
    return (
      <img src={fallbackUrl} alt={title || artifact.title} loading="lazy" />
    );
  }
  return <div className="interactive-chart" ref={ref} />;
}
export function ResultCard({
  result,
  name,
  onEvidence,
  parameters,
  onReconfigure,
}: {
  result: Result;
  name: string;
  onEvidence: (e: Evidence) => void;
  parameters: Parameters;
  onReconfigure: (p: Parameters) => Promise<void>;
}) {
  const [preview, setPreview] = useState<Preview | null>(null),
    [viewTable, setViewTable] = useState("");
  const [editing, setEditing] = useState(false),
    [settings, setSettings] = useState(parameters),
    [submitting, setSubmitting] = useState(false);
  const pngs = result.artifacts.filter((a) => a.artifact_type === "png");
  return (
    <section className="result-card">
      <div className="result-head">
        <span className={"result-icon " + result.status}>
          {result.status === "success" ? (
            <CheckCircle2 size={18} />
          ) : (
            <ShieldCheck size={18} />
          )}
        </span>
        <h2>{name}</h2>
        <span className="badge">
          {result.reused_from
            ? "复用已验证结果"
            : result.status === "failed"
              ? "待修复"
              : result.status === "skipped"
                ? "条件未满足"
                : "已完成"}
        </span>
      </div>
      <p className="result-summary">{result.summary}</p>
      <div className="result-numbers">
        {Object.entries({
          ...result.metrics,
          ...((result.metrics.means || {}) as Record<string, unknown>),
        })
          .filter(([, v]) => typeof v === "number" || typeof v === "string")
          .slice(0, 10)
          .map(([k, v]) => (
            <div key={k}>
              <small>
                {(
                  {
                    matched_samples: "匹配样本",
                    requested_models: "计划模型",
                    not_estimable: "不可估计",
                    predictors: "暴露 / 特征",
                    outcomes: "结局",
                    rho: "相关系数 ρ",
                    p: "p 值",
                    edges: "关系",
                    nodes: "节点",
                    included: "纳入样本",
                    samples: "有效样本",
                    tested: "实际检验特征",
                    significant: "通过校正阈值",
                    variable: "分析指标",
                    features: "特征数",
                    group_a: "比较组 A",
                    group_b: "比较组 B",
                    pathway: "分析通路",
                  } as Record<string, string>
                )[k] || k}
              </small>
              <strong>
                {typeof v === "number"
                  ? Number.isInteger(v)
                    ? v.toLocaleString()
                    : v.toPrecision(4)
                  : String(v)}
              </strong>
            </div>
          ))}
      </div>
      {!!(result.metrics.group_counts || result.metrics.counts) && (
        <div className="step-bindings">
          {Object.entries(
            (result.metrics.group_counts || result.metrics.counts) as Record<
              string,
              number
            >,
          ).map(([group, count]) => (
            <span key={group}>
              {group} · {count} 个样本
            </span>
          ))}
        </div>
      )}
      {!!result.metrics.enriched_by_group && (
        <div className="step-bindings">
          {Object.entries(
            result.metrics.enriched_by_group as Record<string, unknown[]>,
          ).map(([group, rows]) => (
            <span key={group}>
              {group} · {rows.length} 个富集候选
            </span>
          ))}
        </div>
      )}
      {pngs.length > 0 &&
        result.skill !== "custom_analysis" &&
        !result.evidence.some(
          (e) => Object.keys(e.upstream_inputs || {}).length > 0,
        ) && (
          <details className="details">
            <summary>调整图表并生成新分析方案</summary>
            <div className="form-grid">
              <label>
                图表标题
                <input
                  value={settings.title}
                  onChange={(e) =>
                    setSettings({ ...settings, title: e.target.value })
                  }
                />
              </label>
              <label>
                显示数量
                <input
                  type="number"
                  min={3}
                  max={30}
                  value={settings.top_n}
                  onChange={(e) =>
                    setSettings({ ...settings, top_n: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                配色
                <select
                  value={settings.palette}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      palette: e.target.value as Parameters["palette"],
                    })
                  }
                >
                  <option value="forest">森林</option>
                  <option value="ocean">海洋</option>
                  <option value="earth">大地</option>
                </select>
              </label>
              <label>
                分组显示顺序
                <input
                  value={settings.group_order.join(",")}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      group_order: e.target.value
                        .split(",")
                        .map((x) => x.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </label>
            </div>
            <button
              className="secondary"
              disabled={submitting}
              onClick={async () => {
                setSubmitting(true);
                try {
                  await onReconfigure(settings);
                } finally {
                  setSubmitting(false);
                }
              }}
            >
              <RefreshCw size={13} />
              生成新方案
            </button>
            <p className="muted">需要再次确认；原图与原报告会保留。</p>
          </details>
        )}
      {pngs.map((a) => {
        const chart = result.artifacts.find(
          (c) => c.artifact_type === "chart" && c.title === a.title,
        );
        return (
          <div className="figure" key={a.id}>
            <div className="figure-title">
              <strong>{a.title}</strong>
              <div>
                <a href={artifactUrl(a.id)} download={a.filename}>
                  PNG
                </a>
                {result.artifacts
                  .filter(
                    (x) => x.artifact_type === "svg" && x.title === a.title,
                  )
                  .map((svg) => (
                    <a
                      key={svg.id}
                      href={artifactUrl(svg.id)}
                      download={svg.filename}
                    >
                      SVG
                    </a>
                  ))}
              </div>
            </div>
            {chart ? (
              <Chart
                artifact={chart}
                fallbackUrl={artifactUrl(a.id)}
                title={a.title}
              />
            ) : (
              <img src={artifactUrl(a.id)} alt={a.title} loading="lazy" />
            )}
          </div>
        );
      })}
      <div className="result-tools">
        {result.evidence.map((e) => (
          <button
            className="evidence-button"
            key={e.id}
            onClick={() => onEvidence(e)}
          >
            <ShieldCheck size={14} />
            查看依据
          </button>
        ))}
        {result.artifacts
          .filter((a) => ["code", "audit"].includes(a.artifact_type))
          .map((a) => (
            <a
              key={a.id}
              className="text-button"
              href={artifactUrl(a.id)}
              download={a.filename}
            >
              {a.title}
            </a>
          ))}
        {result.artifacts
          .filter((a) => a.artifact_type === "table")
          .map((a) => (
            <button
              className="text-button"
              key={a.id}
              onClick={async () => {
                if (viewTable === a.id) {
                  setViewTable("");
                  return;
                }
                setPreview(
                  await request<Preview>(`/artifacts/${a.id}/preview`),
                );
                setViewTable(a.id);
              }}
            >
              <Table2 size={14} />
              {a.title}
            </button>
          ))}
      </div>
      {preview && viewTable && (
        <>
          <DataTable preview={preview} />
          <a className="text-button" href={artifactUrl(viewTable)} download>
            <Download size={14} />
            下载完整结果表
          </a>
        </>
      )}
      {result.warnings.length > 0 && (
        <details className="details warning-details">
          <summary>方法限制与提示（{result.warnings.length}）</summary>
          {result.warnings.map((w, i) => (
            <p key={i}>{w}</p>
          ))}
        </details>
      )}
      <details className="details">
        <summary>计算方法</summary>
        <p>{result.method}</p>
      </details>
    </section>
  );
}
export function RunLog({ pid, run }: { pid: string; run: Run }) {
  const [events, setEvents] = useState<
      { id: string; message: string; created_at: string }[]
    >([]),
    [log, setLog] = useState("");
  useEffect(() => {
    request<typeof events>(`/projects/${pid}/runs/${run.id}/events`).then(
      setEvents,
    );
  }, [run.id, run.status, run.progress]);
  return (
    <div className="run-log">
      {events.map((e) => (
        <p key={e.id}>
          <small>{time(e.created_at)}</small> {e.message}
        </p>
      ))}
      <select
        defaultValue=""
        onChange={(e) => {
          if (e.target.value)
            request<{ text: string }>(
              `/projects/${pid}/runs/${run.id}/logs/${e.target.value}`,
            ).then((d) => setLog(d.text));
        }}
      >
        <option value="">查看步骤日志</option>
        {run.plan.steps.map((s) => (
          <option key={s.id} value={s.id}>
            {s.id} · {s.skill}
          </option>
        ))}
      </select>
      {log && <pre>{log}</pre>}
    </div>
  );
}
