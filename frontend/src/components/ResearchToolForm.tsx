import { useEffect, useState } from "react";
import { request } from "../api";
import type { Dataset, DatasetDetail, Parameters } from "../types";

export const researchInference = [
  "baseline_table",
  "partial_correlation",
  "adjusted_regression",
];
export function researchReady(
  skill: string,
  p: Parameters,
  datasets: Dataset[],
) {
  const source = datasets.find((d) => d.id === p.dataset_id);
  if (!source) return false;
  const selected = new Set(datasets.map((d) => d.id));
  if (
    p.right_dataset_id &&
    ["join_tables", "association_network"].includes(skill) &&
    !selected.has(p.right_dataset_id)
  )
    return false;
  if (skill === "join_tables")
    return (
      !!p.dataset_id &&
      !!p.right_dataset_id &&
      p.dataset_id !== p.right_dataset_id
    );
  if (skill === "baseline_table")
    return (
      !!p.dataset_id &&
      !!p.group_by &&
      !!p.fields?.length &&
      (!p.group_values?.length || p.group_values.length === 2)
    );
  if (["partial_correlation", "adjusted_regression"].includes(skill))
    return (
      !!p.metadata_id &&
      selected.has(p.metadata_id) &&
      (source.data_type === "taxonomy" ||
        source.data_type === "functional" ||
        !!p.predictors?.length) &&
      !!p.dataset_id &&
      !!p.outcome_dataset_id &&
      selected.has(p.outcome_dataset_id) &&
      !!p.outcomes?.length
    );
  return (
    !!p.dataset_id &&
    !!p.result_predictor &&
    !!p.result_effect &&
    !!p.effect_metric &&
    (skill === "effect_plot" || !!p.result_outcome) &&
    (skill !== "association_network" || !!p.right_dataset_id)
  );
}
export function ResearchToolForm({
  pid,
  skill,
  datasets,
  params: p,
  onChange,
}: {
  pid: string;
  skill: string;
  datasets: Dataset[];
  params: Parameters;
  onChange: (value: Parameters) => void;
}) {
  const [details, setDetails] = useState<Record<string, DatasetDetail>>({});
  const [error, setError] = useState("");
  const ids = [
    ...new Set(
      [
        p.dataset_id,
        p.metadata_id,
        p.outcome_dataset_id,
        p.right_dataset_id,
      ].filter((id): id is string => !!id),
    ),
  ]
    .sort()
    .join(",");
  useEffect(() => {
    let active = true;
    setError("");
    Promise.all(
      ids
        .split(",")
        .filter(Boolean)
        .map((id) => request<DatasetDetail>(`/projects/${pid}/datasets/${id}`)),
    )
      .then((items) => {
        if (active) setDetails(Object.fromEntries(items.map((d) => [d.id, d])));
      })
      .catch((e) => active && setError(String(e)));
    return () => {
      active = false;
    };
  }, [pid, ids]);
  function patch(values: Partial<Parameters>) {
    onChange({ ...p, ...values });
  }
  const tabular = datasets.filter((d) =>
    ["table", "metadata"].includes(d.data_type),
  );
  const columns = (id?: string | null) => details[id || ""]?.columns || [];
  const numeric = (id?: string | null) =>
    (details[id || ""]?.field_profile.fields || [])
      .filter(
        (f) =>
          f.numeric_candidate &&
          !["identifier", "subject", "time"].includes(f.role),
      )
      .map((f) => f.name);
  function file(
    label: string,
    key:
      "dataset_id" | "metadata_id" | "outcome_dataset_id" | "right_dataset_id",
    options: Dataset[] = tabular,
  ) {
    return (
      <label>
        {label}
        <select
          aria-label={label}
          value={p[key] || ""}
          onChange={(e) =>
            patch({
              [key]: e.target.value || null,
              ...(key === "dataset_id"
                ? { predictors: [], fields: [], group_by: null, left_key: null }
                : key === "outcome_dataset_id"
                  ? { outcomes: [] }
                  : key === "metadata_id"
                    ? { covariates: [], categorical_covariates: [] }
                    : { right_key: null }),
            })
          }
        >
          <option value="">请选择文件</option>
          {options.map((d) => (
            <option key={d.id} value={d.id}>
              {d.filename}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function field(
    label: string,
    key: keyof Parameters,
    values: string[],
    empty = "请选择",
  ) {
    return (
      <label>
        {label}
        <select
          aria-label={label}
          value={String(p[key] || "")}
          onChange={(e) =>
            patch({
              [key]: e.target.value || null,
              ...(key === "group_by" ? { group_values: [] } : {}),
            })
          }
        >
          <option value="">{empty}</option>
          {values.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function checks(
    label: string,
    key:
      | "predictors"
      | "outcomes"
      | "fields"
      | "covariates"
      | "categorical_covariates"
      | "group_values"
      | "baseline_categorical",
    values: string[],
  ) {
    return (
      <fieldset className="field-checks">
        <legend>{label}</legend>
        {values.map((c) => (
          <label key={c}>
            <input
              type="checkbox"
              checked={(p[key] || []).includes(c)}
              onChange={(e) => {
                const next = e.target.checked
                  ? [...(p[key] || []), c]
                  : (p[key] || []).filter((v) => v !== c);
                patch({
                  [key]: next,
                  ...(key === "covariates"
                    ? {
                        categorical_covariates: (
                          p.categorical_covariates || []
                        ).filter((v) => next.includes(v)),
                      }
                    : {}),
                });
              }}
            />
            {c}
          </label>
        ))}
        {!values.length && <span>选择文件后显示字段</span>}
      </fieldset>
    );
  }
  function option(
    label: string,
    key: keyof Parameters,
    options: [string, string][],
    fallback: string,
  ) {
    return (
      <label>
        {label}
        <select
          aria-label={label}
          value={String(p[key] ?? fallback)}
          onChange={(e) => patch({ [key]: e.target.value })}
        >
          {options.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
    );
  }
  const predictorMatrix = datasets.find(
    (d) =>
      d.id === p.dataset_id && ["taxonomy", "functional"].includes(d.data_type),
  );
  const statsTool = ["partial_correlation", "adjusted_regression"].includes(
    skill,
  );
  const plotTool = [
    "association_heatmap",
    "effect_plot",
    "association_network",
  ].includes(skill);
  return (
    <>
      {error && <p role="alert">{error}</p>}
      {skill === "join_tables" && (
        <>
          {file("左表", "dataset_id")}
          {file("右表", "right_dataset_id")}
          {field(
            "左表连接编号",
            "left_key",
            columns(p.dataset_id),
            "使用已登记的样本编号",
          )}
          {field(
            "右表连接编号",
            "right_key",
            columns(p.right_dataset_id),
            "使用已登记的样本编号",
          )}
          {option(
            "保留记录",
            "join_how",
            [
              ["inner", "两表匹配的记录"],
              ["left", "左表全部记录"],
            ],
            "inner",
          )}
        </>
      )}
      {skill === "baseline_table" && (
        <>
          {file("样本表", "dataset_id")}
          {field("比较哪两组", "group_by", columns(p.dataset_id))}
          {checks(
            "比较组（选择两组）",
            "group_values",
            (details[p.dataset_id || ""]?.field_profile.fields || []).find(
              (f) => f.name === p.group_by,
            )?.values || [],
          )}
          {checks(
            "纳入基线表的字段",
            "fields",
            columns(p.dataset_id).filter((c) => c !== p.group_by),
          )}
          {checks(
            "其中按分类统计的字段",
            "baseline_categorical",
            p.fields || [],
          )}
          {option(
            "数值字段比较方法",
            "baseline_test",
            [
              ["mannwhitney", "Mann–Whitney U"],
              ["welch", "Welch t 检验"],
            ],
            "mannwhitney",
          )}
        </>
      )}
      {statsTool && (
        <>
          {file("样本与协变量表", "metadata_id")}
          {file("暴露 / 特征所在文件", "dataset_id", datasets)}
          {predictorMatrix ? (
            <label>
              分析特征
              <select
                value={p.rank}
                onChange={(e) =>
                  patch({ rank: e.target.value as Parameters["rank"] })
                }
              >
                {[
                  ["species", "种"],
                  ["genus", "属"],
                  ["family", "科"],
                  ["phylum", "门"],
                ].map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
              <span>所选层级的全部特征</span>
            </label>
          ) : (
            checks("暴露 / 预测字段", "predictors", numeric(p.dataset_id))
          )}
          {file("结局所在文件", "outcome_dataset_id")}
          {checks("结局字段", "outcomes", numeric(p.outcome_dataset_id))}
          {checks("需要校正的协变量", "covariates", columns(p.metadata_id))}
          {checks(
            "其中按分类编码的协变量",
            "categorical_covariates",
            p.covariates || [],
          )}
          {skill === "partial_correlation" ? (
            option(
              "关联方法",
              "correlation_method",
              [
                ["spearman", "偏 Spearman"],
                ["pearson", "偏 Pearson"],
                ["residual_spearman", "先取线性残差再 Spearman（旧脚本）"],
              ],
              "spearman",
            )
          ) : (
            <>
              {option(
                "标准误",
                "standard_error",
                [
                  ["HC3", "HC3 稳健标准误"],
                  ["classical", "经典 OLS 标准误"],
                ],
                "HC3",
              )}
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={p.standardize ?? true}
                  onChange={(e) => patch({ standardize: e.target.checked })}
                />
                标准化暴露与结局
              </label>
            </>
          )}
          <details className="details">
            <summary>变换与校正范围</summary>
            <div className="form-grid">
              {option(
                "暴露变换",
                "transform",
                [
                  ["none", "不变换"],
                  ["log1p", "log(1+x)"],
                  ["clr", "CLR 成分变换"],
                ],
                "none",
              )}
              {option(
                "结局变换",
                "outcome_transform",
                [
                  ["none", "不变换"],
                  ["log1p", "log(1+x)"],
                ],
                "none",
              )}
              {option(
                "多重检验范围",
                "correction_family",
                [
                  ["all", "所有模型一起校正"],
                  ["outcome", "每个结局分别校正"],
                ],
                "all",
              )}
              {predictorMatrix?.data_type === "functional" &&
                option(
                  "通路数据口径",
                  "functional_mode",
                  [
                    ["community", "真实群落总通路"],
                    ["stratified", "物种分层通路"],
                    ["contribution_sum", "分层贡献合计（代理指标）"],
                  ],
                  "community",
                )}
            </div>
          </details>
        </>
      )}
      {plotTool && (
        <>
          {file(
            skill === "association_network"
              ? "第一层关联结果"
              : "已有分析结果表",
            "dataset_id",
          )}
          {skill === "association_network" &&
            file("第二层关联结果（相同列名）", "right_dataset_id")}
          {field("特征 / 起点列", "result_predictor", columns(p.dataset_id))}
          {skill !== "effect_plot" &&
            field("结局 / 终点列", "result_outcome", columns(p.dataset_id))}
          {field("效应量列", "result_effect", columns(p.dataset_id))}
          <label>
            效应量含义
            <input
              aria-label="效应量含义"
              value={p.effect_metric || ""}
              placeholder="例如 Spearman rho、标准化 beta"
              onChange={(e) => patch({ effect_metric: e.target.value })}
            />
          </label>
          {option(
            "显示筛选",
            "significance",
            [
              ["q", "按校正后 q 值"],
              ["p", "按原始 p 值"],
              ["all", "显示全部"],
            ],
            "q",
          )}
          {p.significance !== "all" &&
            field(
              p.significance === "p" ? "p 值列" : "q 值列",
              p.significance === "p" ? "result_p" : "result_q",
              columns(p.dataset_id),
            )}
          {skill === "effect_plot" && (
            <>
              {option(
                "图形",
                "effect_style",
                [
                  ["forest", "森林图（需要置信区间）"],
                  ["lollipop", "效应棒棒糖图"],
                ],
                "forest",
              )}
              {p.effect_style !== "lollipop" && (
                <>
                  {field(
                    "置信区间下界",
                    "result_ci_low",
                    columns(p.dataset_id),
                  )}
                  {field(
                    "置信区间上界",
                    "result_ci_high",
                    columns(p.dataset_id),
                  )}
                </>
              )}
            </>
          )}
          {skill === "association_network" &&
            [0, 1, 2].map((i) => (
              <label key={i}>
                第 {i + 1} 层名称
                <input
                  value={(p.network_stages || ["菌种", "通路", "表型"])[i]}
                  onChange={(e) => {
                    const stages = [
                      ...(p.network_stages || ["菌种", "通路", "表型"]),
                    ];
                    stages[i] = e.target.value;
                    patch({ network_stages: stages });
                  }}
                />
              </label>
            ))}
        </>
      )}
      {skill !== "join_tables" &&
        !plotTool &&
        option(
          "多重检验",
          "adjustment",
          [
            ["BH", "BH 校正"],
            ["none", "仅原始 p 值"],
          ],
          "BH",
        )}
      {plotTool && (
        <label>
          显示数量
          <input
            type="number"
            min="1"
            max="30"
            value={p.top_n}
            onChange={(e) => patch({ top_n: Number(e.target.value) })}
          />
        </label>
      )}
    </>
  );
}
