# Skills 开发手册

## 一个 Skill 的约定

注册表提供名称、版本、说明与必要输入，Pydantic SkillParams 是受校验的参数集合。执行函数接收 Context，返回统一 SkillResult：状态、摘要、指标、证据、产物、方法和警告。

Context 提供不可变输入快照、数据矩阵、受检查的分组、结果目录、表格写入、PNG/SVG 与交互图表注册、证据生成。不要在 Skill 中读取任意外部路径、调用语言模型计算数值或执行用户字符串。

新增：taxa_association、diversity_association、functional_association、variable_distribution。需要指定 SkillParams.variable，必须是当前项目样本信息中的数值列。关联 Skills 输出匹配观测、相关系数、校正结果及图表，不接受分层通路代替总通路。

当前支持：data_check、metadata_overview、composition、sample_profile、sample_comparison、core_taxa、alpha_diversity、beta_diversity、alpha_comparison、community_comparison、differential、functional_overview、functional_differential、pathway_contribution、report。各能力的参数和条件可在 /api/v1/skills 中查询。

`SkillParams.samples` 把组成类工具限定到具名样本；点名样本对比必须走 `sample_comparison`（描述性，不做显著性），不能用全体队列的 `composition` 冒充。`group_values` 支持三组及以上；`alpha_comparison` / `community_comparison` / `differential` 在多组时分别使用 Kruskal–Wallis 与多组 PERMANOVA，并输出按组名区分的表头与丰度对比图。`rank` 可选 species / genus / family / phylum。

`group_numeric_compare` 用于样本表/普通表：按分类列（如性别）比较数值列（如 Zinc、年龄），两组 Mann–Whitney、三组及以上 Kruskal–Wallis。参数为 `dataset_id`、`group_by`、`variable`。问「男女锌是否显著」「年龄与性别相关」时必须用它，不能用 `field_distribution` 代替。

## 增加能力

1. 在 registry 中添加 Spec，描述使用目的和必要输入，版本从 1.0.0 开始。
2. 在 analysis 或独立模块中实现函数，加入静态 HANDLERS。算法复用成熟库；输入不满足时使用 DataError，执行层会明确标为 skipped。
3. 使用 Context.table/chart 保存结果并注册产物，使用 Context.evidence 输出可检查的声明与指标。
4. 新增复杂输入参数时扩展 Pydantic 定义与适用条件检查，同步更新 frontend/src/generated-api.d.ts 中的前端类型。
5. 在 reports 的解释片段适用表中声明该 Skill 可使用的已审阅解释。新能力不能直接插入模型自由文本。
6. 添加已知数值、失败条件和集成测试，再将新能力加入可选方案。

如果改变数值算法、过滤或输入语义，应递增版本以使旧缓存失效。仅修复界面文字不必使计算缓存失效。

## 最小执行示例

```python
from yanji.contracts import SkillResult


def example_skill(ctx):
    matrix = ctx.matrix("taxonomy")
    summary = f"本次包含 {len(matrix)} 个可计算样本。"
    evidence = ctx.evidence("sample_count", summary, {"samples": len(matrix)})
    return SkillResult(
        skill="example_skill",
        version="1.0.0",
        summary=summary,
        metrics={"samples": len(matrix)},
        evidence=[evidence],
        method="从已选择层级的有效样本矩阵直接计数。",
        warnings=ctx.warnings,
    ).model_dump()
```

新增 Skill 后应能通过固定入口独立运行，再允许 Agent 选择。Skills 的 Markdown 说明是开发文档，执行权限始终来自静态注册表与程序，不能由上传的说明文字扩大。

## 普通表格工具

`table_correlation` 使用 dataset_id、x、y，在本项目表格或样本表上做完整观测双侧 Spearman 检验。输出 n、rho、p、参与观测及静态/交互散点图。重复受试者与非连续角色会阻断。有序等级字段在确认至少三个等级的顺序后，按该顺序编码为 1 起的序号参与秩相关，结果摘要写明序号方向。

`sankey` 使用 dataset_id、source、target、weight。权重必须有限非负，重复起终点按权重相加并保留原始边表。左右同名节点分开，不自动赋予因果或守恒含义。

`field_distribution` 使用 dataset_id 和 fields。可同时描述一张样本表或普通表格上的多个字段：数值字段输出直方图和分位数，类别字段输出频数，有序字段按已保存编码顺序排列。研究说法会先对应到真实列；对不上、缺单位或缺等级顺序时，方案给出可填写的补充项，写回字段说明后再生成该步骤。

`ChatRequest.include_report=false` 可仅执行工具。报告通过运行结果整理入口按需生成。执行 Context 和缓存绑定认可时的字段说明快照，上游未成功则阻断依赖步骤。

## 派生队列与动态编排

`prepare_cohort` 的 `parameters.preparation` 接收有类型的顺序操作，支持筛选、算术、重编码、分位数及阈值分组。后续 Step 使用 `cohort_from` 引用该步骤，并声明 `depends_on`。编译器将引用解析为同一不可变规则；预览和执行复用 preparation.py 的解释器。`group_feature_summary` 在各组独立排名，`differential` 另外保存按方向拆分的富集候选表。

扩展准备操作时更新 Preparation、prepare、预览审计与测试；扩展分析时登记 Spec 和 handler，并声明正确输入前提。规划器可以组合已有能力，不能把不具备的能力替换成相近的研究问题。完整契约见 DYNAMIC_ANALYSIS.md。
