import { useEffect, useState } from "react";
import { ArrowRight, BarChart3, Network, Search } from "lucide-react";
import { SourcePicker, StudyQuestions } from "../components/AnalysisInputs";
import {
  ResearchToolForm,
  researchInference,
  researchReady,
} from "../components/ResearchToolForm";
import { request } from "../api";
import type { DatasetDetail, Parameters, Skill, Project } from "../types";
import type { WorkspacePageProps } from "./types";
const groups = [
  {
    title: "研究分析与结果绘图",
    ids: [
      "join_tables",
      "baseline_table",
      "partial_correlation",
      "adjusted_regression",
      "association_heatmap",
      "effect_plot",
      "association_network",
    ],
  },
  {
    title: "关联与绘图",
    ids: [
      "table_overview",
      "field_distribution",
      "table_correlation",
      "group_numeric_compare",
      "sankey",
      "variable_distribution",
    ],
  },
  {
    title: "菌群研究",
    ids: [
      "composition",
      "sample_profile",
      "sample_comparison",
      "core_taxa",
      "alpha_diversity",
      "beta_diversity",
      "taxa_association",
      "diversity_association",
      "alpha_comparison",
      "community_comparison",
      "differential",
    ],
  },
  {
    title: "功能研究",
    ids: [
      "functional_overview",
      "functional_association",
      "functional_differential",
      "pathway_contribution",
    ],
  },
];
export function SkillsPage({
  detail,
  skills,
  busy,
  plan,
  defaults,
  setTab,
  setModal,
}: WorkspacePageProps) {
  const [chosen, setChosen] = useState<Skill | null>(null),
    [params, setParams] = useState<Parameters>(defaults),
    [table, setTable] = useState<DatasetDetail | null>(null),
    [search, setSearch] = useState("");
  const [sources, setSources] = useState(detail.datasets.map((d) => d.id));
  const [study, setStudy] = useState<Project["study"]>({
    group_column: null,
    independent: false,
    excluded_samples: [],
  });
  const selectedFiles = detail.datasets.filter((d) => sources.includes(d.id));
  const tabular = selectedFiles.filter((d) =>
    ["metadata", "table"].includes(d.data_type),
  );
  const datasetId = chosen?.requires.endsWith("_numeric")
    ? selectedFiles.find((d) => d.data_type === "metadata")?.id || ""
    : (sources.includes(params.dataset_id || "")
        ? params.dataset_id
        : undefined) ||
      tabular[0]?.id ||
      "";
  useEffect(() => {
    let active = true;
    setTable(null);
    if (datasetId)
      request<DatasetDetail>(
        `/projects/${detail.id}/datasets/${datasetId}`,
      ).then((d) => active && setTable(d));
    return () => {
      active = false;
    };
  }, [datasetId, detail.id]);
  function choose(s: Skill) {
    setChosen(s);
    setParams({
      ...defaults,
      dataset_id: tabular[0]?.id || null,
      metadata_id: tabular[0]?.id || null,
      outcome_dataset_id: tabular[0]?.id || null,
      result_predictor: "predictor",
      result_outcome: "outcome",
      result_effect: "effect",
      result_p: "p",
      result_q: "q",
      result_ci_low: "ci_low",
      result_ci_high: "ci_high",
    });
  }
  function selectField(
    label: string,
    key: keyof Parameters,
    columns: string[],
  ) {
    return (
      <label>
        {label}
        <select
          aria-label={label}
          value={String(params[key] || "")}
          onChange={(e) =>
            setParams({ ...params, [key]: e.target.value || null })
          }
        >
          <option value="">请选择</option>
          {columns.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
    );
  }
  const numeric = (table?.field_profile.fields || [])
    .filter(
      (f) =>
        (f.numeric_candidate &&
          !["categorical", "identifier", "subject", "time"].includes(f.role)) ||
        // An ordinal column with a confirmed level order can be rank-correlated.
        (f.role === "ordinal" && !!f.encoding && f.encoding !== "未指定顺序"),
    )
    .map((f) => f.name);
  const [showAll, setShowAll] = useState(false);
  const compatible = (skill: Skill) => {
    const has = (type: string) =>
      selectedFiles.some((d) => d.data_type === type);
    if (skill.requires === "research")
      return skill.id === "join_tables" || skill.id === "association_network"
        ? tabular.length > 1
        : tabular.length > 0;
    if (skill.requires === "table") return tabular.length > 0;
    if (skill.requires === "metadata" || skill.requires === "metadata_numeric")
      return has("metadata");
    if (["taxonomy", "groups", "taxa_numeric"].includes(skill.requires))
      return (
        has("taxonomy") &&
        (!["groups", "taxa_numeric"].includes(skill.requires) ||
          has("metadata"))
      );
    if (skill.requires === "functional_stratified")
      return selectedFiles.some(
        (d) => d.data_type === "functional" && d.summary.stratified_rows,
      );
    if (skill.requires.startsWith("functional"))
      return (
        selectedFiles.some(
          (d) => d.data_type === "functional" && d.summary.total_pathways,
        ) &&
        (!["functional_groups", "functional_numeric"].includes(
          skill.requires,
        ) ||
          has("metadata"))
      );
    return true;
  };
  const columns = table?.columns || [];
  return (
    <>
      <div className="page-heading">
        <h1>开始分析</h1>
        <div className="tool-search">
          <Search size={17} />
          <input
            aria-label="搜索工具"
            placeholder="搜索工具"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      <div className="workspace-switch">
        <button onClick={() => setTab("overview")}>描述研究问题</button>
        <button className="selected">选择分析工具</button>
      </div>
      <SourcePicker
        datasets={detail.datasets}
        selected={sources}
        onChange={setSources}
      />
      {!detail.datasets.length && (
        <button className="primary" onClick={() => setModal("upload")}>
          先添加数据
        </button>
      )}
      {!chosen && (
        <div className="tools-filter">
          <span>{showAll ? "全部工具" : "适用于本次文件"}</span>
          <button className="text-button" onClick={() => setShowAll((x) => !x)}>
            {showAll ? "只看适用工具" : "查看全部工具"}
          </button>
        </div>
      )}
      {chosen ? (
        <section className="tool-config">
          <div className="section-title">
            <h2>{chosen.name}</h2>
            <button className="text-button" onClick={() => setChosen(null)}>
              返回工具
            </button>
          </div>
          <p className="tool-purpose">{chosen.description}</p>
          <div className="form-grid">
            {chosen.requires === "research" && (
              <ResearchToolForm
                pid={detail.id}
                skill={chosen.id}
                datasets={selectedFiles}
                params={params}
                onChange={setParams}
              />
            )}
            {chosen.requires === "table" && (
              <>
                <label>
                  数据
                  <select
                    value={datasetId}
                    onChange={(e) =>
                      setParams({ ...defaults, dataset_id: e.target.value })
                    }
                  >
                    {tabular.map((d) => (
                      <option value={d.id} key={d.id}>
                        {d.filename}
                      </option>
                    ))}
                  </select>
                </label>
                {chosen.id === "field_distribution" ? (
                  <fieldset className="field-checks">
                    <legend>分布字段</legend>
                    {(table?.field_profile.fields || [])
                      .filter(
                        (field) =>
                          !["identifier", "subject"].includes(field.role),
                      )
                      .map((field) => (
                        <label key={field.name}>
                          <input
                            type="checkbox"
                            checked={(params.fields || []).includes(field.name)}
                            onChange={(event) =>
                              setParams({
                                ...params,
                                fields: event.target.checked
                                  ? [...(params.fields || []), field.name]
                                  : (params.fields || []).filter(
                                      (name) => name !== field.name,
                                    ),
                              })
                            }
                          />
                          {field.name}
                        </label>
                      ))}
                  </fieldset>
                ) : chosen.id === "table_correlation" ? (
                  <>
                    {selectField("指标 X", "x", numeric)}
                    {selectField("指标 Y", "y", numeric)}
                  </>
                ) : chosen.id === "group_numeric_compare" ? (
                  <>
                    {selectField(
                      "分组字段",
                      "group_by",
                      (table?.field_profile.fields || [])
                        .filter(
                          (f) =>
                            ![
                              "identifier",
                              "subject",
                              "time",
                              "numeric",
                            ].includes(f.role),
                        )
                        .map((f) => f.name),
                    )}
                    {selectField("数值指标", "variable", numeric)}
                  </>
                ) : chosen.id === "sankey" ? (
                  <>
                    {selectField("起点", "source", columns)}
                    {selectField("终点", "target", columns)}
                    {selectField("权重", "weight", columns)}
                  </>
                ) : null}
              </>
            )}
            {chosen.requires.endsWith("_numeric") &&
              selectField(
                "分析指标",
                "variable",
                table?.field_profile.fields
                  .filter(
                    (f) =>
                      f.numeric_candidate &&
                      ![
                        "categorical",
                        "identifier",
                        "subject",
                        "time",
                      ].includes(f.role),
                  )
                  .map((f) => f.name) || [],
              )}
            {chosen.id === "pathway_contribution" && (
              <label>
                通路名称
                <input
                  value={params.pathway || ""}
                  onChange={(e) =>
                    setParams({ ...params, pathway: e.target.value || null })
                  }
                  placeholder="留空先查看贡献概览"
                />
              </label>
            )}
            {[
              "composition",
              "sample_profile",
              "sample_comparison",
              "core_taxa",
              "alpha_diversity",
              "beta_diversity",
              "differential",
              "alpha_comparison",
              "community_comparison",
              "taxa_association",
            ].includes(chosen.id) && (
              <label>
                分类层级
                <select
                  aria-label="分类层级"
                  value={params.rank || "species"}
                  onChange={(e) =>
                    setParams({
                      ...params,
                      rank: e.target.value as Parameters["rank"],
                    })
                  }
                >
                  {["species", "genus", "family", "phylum"].map((rank) => (
                    <option key={rank} value={rank}>
                      {rank}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {[
              "sample_profile",
              "sample_comparison",
              "core_taxa",
              "composition",
            ].includes(chosen.id) && (
              <fieldset className="field-checks">
                <legend>
                  {chosen.id.startsWith("sample")
                    ? "选择样本（必选）"
                    : "限定样本（可选）"}
                </legend>
                {(
                  selectedFiles.find((d) => d.data_type === "taxonomy")
                    ?.samples || []
                )
                  .slice(0, 80)
                  .map((sample) => (
                    <label key={sample}>
                      <input
                        type="checkbox"
                        checked={(params.samples || []).includes(sample)}
                        onChange={(event) =>
                          setParams({
                            ...params,
                            samples: event.target.checked
                              ? [...(params.samples || []), sample]
                              : (params.samples || []).filter(
                                  (name) => name !== sample,
                                ),
                          })
                        }
                      />
                      {sample}
                    </label>
                  ))}
              </fieldset>
            )}
          </div>
          {["groups", "functional_groups"].includes(chosen.requires) && (
            <StudyQuestions
              pid={detail.id}
              datasets={selectedFiles}
              study={study}
              params={params}
              onChange={(s, p) => {
                setStudy(s);
                setParams(p);
              }}
            />
          )}
          {researchInference.includes(chosen.id) && (
            <label className="inline-check">
              <input
                type="checkbox"
                checked={study.independent}
                onChange={(e) =>
                  setStudy({ ...study, independent: e.target.checked })
                }
              />
              本次每行来自不同受试者，样本相互独立
            </label>
          )}
          <button
            className="primary"
            disabled={
              !!busy ||
              !sources.length ||
              (chosen.requires === "research" &&
                !researchReady(chosen.id, params, selectedFiles))
            }
            onClick={() =>
              void plan(
                "skill",
                chosen.requires === "table"
                  ? `${chosen.name}：${
                      chosen.id === "sankey"
                        ? `${params.source || "起点"} → ${params.target || "终点"}`
                        : chosen.id === "field_distribution"
                          ? (params.fields || []).join("、") || "未选字段"
                          : `${params.x || "指标X"}与${params.y || "指标Y"}`
                    }`
                  : ["sample_profile", "sample_comparison"].includes(chosen.id)
                    ? `${chosen.name}：${(params.samples || []).join("、") || "未选样本"}`
                    : chosen.name,
                {
                  ...params,
                  ...(chosen.requires === "table"
                    ? { dataset_id: datasetId }
                    : {}),
                },
                chosen.id,
                sources,
                ["groups", "functional_groups"].includes(chosen.requires) ||
                  researchInference.includes(chosen.id)
                  ? study
                  : undefined,
              )
            }
          >
            查看执行方案 <ArrowRight size={16} />
          </button>
        </section>
      ) : (
        groups.map((g) => {
          const items = skills.filter(
            (s) =>
              g.ids.includes(s.id) &&
              `${s.name} ${s.description}`.includes(search) &&
              (showAll || compatible(s)),
          );
          return (
            items.length > 0 && (
              <section className="tool-section" key={g.title}>
                <h2>{g.title}</h2>
                <div className="tool-grid">
                  {items.map((s) => (
                    <button
                      className="tool-tile"
                      key={s.id}
                      onClick={() => choose(s)}
                    >
                      <span className="tool-symbol">
                        {s.id === "sankey" ? (
                          <Network size={22} />
                        ) : (
                          <BarChart3 size={22} />
                        )}
                      </span>
                      <strong>{s.name}</strong>
                      <ArrowRight size={17} />
                    </button>
                  ))}
                </div>
              </section>
            )
          );
        })
      )}
    </>
  );
}
