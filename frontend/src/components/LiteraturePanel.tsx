import { useEffect, useState } from "react";
import { BookOpen, Check, LoaderCircle, Search } from "lucide-react";
import { post, request } from "../api";
import type { Report } from "../types";
interface Retrieval {
  id: string;
  query: string;
  status: string;
  error?: string;
  items: {
    id: string;
    title: string;
    snippet: string;
    url: string;
    level: string;
  }[];
  steps: { step: number; action: string; observation: string }[];
}
export function LiteraturePanel({
  pid,
  report,
  onUpdate,
  disabled,
}: {
  pid: string;
  report: Report;
  onUpdate: (r: Report) => void;
  disabled: boolean;
}) {
  const [query, setQuery] = useState(""),
    [mode, setMode] = useState("fixed"),
    [run, setRun] = useState<Retrieval | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [configured, setConfigured] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true;
    request<{ configured: boolean }>("/settings/literature").then(
      (x) => active && setConfigured(x.configured),
    );
    request<Retrieval[]>(`/projects/${pid}/literature`).then(
      (xs) => active && setRun(xs.at(-1) || null),
    );
    return () => {
      active = false;
    };
  }, [pid]);
  return (
    <details className="literature-panel">
      <summary>
        <BookOpen size={17} />
        补充文献证据
      </summary>
      <div className="literature-body">
        {configured === false ? (
          <div className="connection-empty">
            文献服务尚未连接。在“模型与连接”查看接入方式。
          </div>
        ) : (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                const r = await post<Retrieval>(`/projects/${pid}/literature`, {
                  query,
                  mode,
                });
                setRun(r);
                if (r.error) setError(r.error);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="literature-query">
              <input
                aria-label="文献检索问题"
                placeholder="研究背景、方法依据或需要解释的发现"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <select
                aria-label="文献检索方式"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="fixed">固定检索</option>
                <option value="agent">智能检索</option>
              </select>
              <button className="primary" disabled={busy || !query.trim()}>
                {busy ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Search size={16} />
                )}
                检索
              </button>
            </div>
          </form>
        )}
        {error && <p className="form-error">{error}</p>}
        {run && (
          <>
            <div className="section-title">
              <strong>{run.query}</strong>
              <span className="badge">
                {{
                  completed: "已完成",
                  no_results: "无结果",
                  budget_exhausted: "达到步数上限",
                  time_limit: "达到时限",
                  repeated_action: "重复动作结束",
                  failed: "检索失败",
                  running: "处理中",
                }[run.status] || run.status}
              </span>
            </div>
            {run.items.map((item) => (
              <article className="literature-item" key={item.id}>
                <h3>{item.title}</h3>
                <span className="badge">{item.level}</span>
                <details>
                  <summary>查看证据片段</summary>
                  <p>{item.snippet || "无可用片段"}</p>
                  {item.url && (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      打开来源 ↗
                    </a>
                  )}
                </details>
                <button
                  className="text-button"
                  disabled={disabled || busy || !item.snippet}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    try {
                      const r = await post<Report>(
                        `/projects/${pid}/reports/${report.id}/literature`,
                        {
                          retrieval_id: run.id,
                          paper_id: item.id,
                          expected_revision: report.revision,
                        },
                      );
                      onUpdate(r);
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <Check size={15} />
                  加入本报告
                </button>
              </article>
            ))}
            {!!run.steps.length && (
              <details className="details">
                <summary>检索过程 · {run.steps.length} 步</summary>
                {run.steps.map((s) => (
                  <p key={s.step}>
                    {s.step}.{" "}
                    {
                      (
                        {
                          search: "搜索",
                          get: "读取",
                          finish: "结束",
                        } as Record<string, string>
                      )[s.action]
                    }{" "}
                    · {s.observation}
                  </p>
                ))}
              </details>
            )}
          </>
        )}
      </div>
    </details>
  );
}
