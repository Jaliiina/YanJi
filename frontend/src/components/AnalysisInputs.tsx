import { useEffect, useState } from "react";
import { request } from "../api";
import type { Dataset, DatasetDetail, Parameters, Project } from "../types";

export function SourcePicker({
  datasets,
  selected,
  onChange,
}: {
  datasets: Dataset[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  return (
    <section className="analysis-inputs">
      <div className="section-title">
        <h3>本次使用的文件</h3>
        <span>{selected.length} 份已选择</span>
      </div>
      <div className="input-file-list">
        {datasets.map((d) => (
          <label key={d.id}>
            <input
              type="checkbox"
              checked={selected.includes(d.id)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...selected, d.id]
                    : selected.filter((id) => id !== d.id),
                )
              }
            />
            <span>
              {d.filename}
              {d.transformations?.find((t) => t.sheet)?.sheet &&
                ` · ${d.transformations.find((t) => t.sheet)?.sheet}`}
            </span>
          </label>
        ))}
      </div>
    </section>
  );
}

export function StudyQuestions({
  pid,
  datasets,
  study,
  params,
  onChange,
}: {
  pid: string;
  datasets: Dataset[];
  study: Project["study"];
  params: Parameters;
  onChange: (study: Project["study"], params: Parameters) => void;
}) {
  const metadata = datasets.filter((d) => d.data_type === "metadata");
  const [file, setFile] = useState<DatasetDetail | null>(null),
    [values, setValues] = useState<{ value: string; count: number }[]>([]),
    [error, setError] = useState("");
  const md = metadata.length === 1 ? metadata[0] : null;
  useEffect(() => {
    let live = true;
    setFile(null);
    if (md)
      request<DatasetDetail>(`/projects/${pid}/datasets/${md.id}`)
        .then((d) => live && setFile(d))
        .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [pid, md?.id]);
  useEffect(() => {
    let live = true;
    setValues([]);
    if (md && study.group_column)
      request<{ items: { value: string; count: number }[] }>(
        `/projects/${pid}/datasets/${md.id}/values?column=${encodeURIComponent(study.group_column)}`,
      )
        .then((d) => {
          if (live) setValues(d.items);
        })
        .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [pid, md?.id, study.group_column]);
  if (!md)
    return (
      <div className="task-question">
        <h3>这项任务要比较两组样本</h3>
        <p>
          {metadata.length > 1
            ? "请在本次文件中只选一份记录样本分组的信息表。"
            : "需要一份记录每个样本属于哪一组的表。请先在项目文件中添加，或在读取设置里指定这类文件。"}
        </p>
      </div>
    );
  return (
    <section className="task-question">
      <h3>你想比较哪些组？</h3>
      <p>分组从「{md.filename}」的实际内容中选择，只用于本次比较。至少选两组，也可选三组及以上。</p>
      <label>
        哪一列记录了组别？
        <select
          aria-label="记录组别的列"
          value={study.group_column || ""}
          onChange={(e) =>
            onChange(
              { ...study, group_column: e.target.value || null },
              { ...params, group_a: null, group_b: null, group_values: [] },
            )
          }
        >
          <option value="">从这份文件中选择一列</option>
          {file?.columns.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      {study.group_column && (
        <>
          <div className="group-value-preview">
            {values.length
              ? values.slice(0, 8).map((v) => (
                  <span key={v.value}>
                    {v.value} · {v.count} 条记录
                  </span>
                ))
              : "正在读取这一列…"}
          </div>
          <fieldset className="field-checks">
            <legend>勾选本次要比较的组别（至少两组）</legend>
            {values.map((v) => {
              const selected = (params.group_values || []).length
                ? (params.group_values || []).includes(v.value)
                : [params.group_a, params.group_b].includes(v.value);
              return (
                <label key={v.value}>
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={(event) => {
                      const current = (params.group_values || []).length
                        ? [...(params.group_values || [])]
                        : [params.group_a, params.group_b].filter(
                            (x): x is string => !!x,
                          );
                      const next = event.target.checked
                        ? [...current, v.value]
                        : current.filter((name) => name !== v.value);
                      onChange(study, {
                        ...params,
                        group_values: next,
                        group_a: next[0] || null,
                        group_b: next[1] || null,
                      });
                    }}
                  />
                  {v.value}（{v.count} 条）
                </label>
              );
            })}
          </fieldset>
        </>
      )}
      <fieldset className="observation-question">
        <legend>同一人或同一研究对象，有没有多次记录？</legend>
        <label>
          <input
            type="checkbox"
            checked={study.independent}
            onChange={(e) =>
              onChange({ ...study, independent: e.target.checked }, params)
            }
          />
          没有，每个研究对象只记录一次，也不属于配对样本
        </label>
      </fieldset>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
    </section>
  );
}
