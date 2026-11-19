# biology 方法迁移

参考：<https://github.com/Jaliiina/biology>，阅读版本 `1cdc64066a5a938326799f72faeef45905a3d4f2`。参考文件只保留在开发临时目录；平台没有导入或执行仓库中的硬编码脚本。

## 本轮能力

- `join_tables`：按明确编号一对一连接表；输出 `joined` 与 `join_audit`，拒绝重复编号、多对多和普通表自动行号连接。
- `baseline_table`：两组基线描述、缺失分母、Mann–Whitney/Welch、Fisher/适用的卡方与可选 BH；明确是未调整比较。参考 `0BaseTable.py` 的分析目的，未把其年龄调整模型冒充为已迁移。
- `partial_correlation`：单指标对多个结局、数值和分类协变量、标准偏 Spearman/偏 Pearson。`1macro.py`、`3atec3_subitem.py` 中先线性残差再 Spearman 的旧方法须显式选择 `residual_spearman`，结果单独标记。
- `adjusted_regression`：参考 `9taxa_clinic_p.py`、`11path_clinic.py`，增加可配置协变量、HC3/经典标准误、标准化效应、95% CI、完整模型结果和 BH；支持物种、通路或普通数值暴露。
- `association_heatmap`：已有结果的带符号效应与显著性热图。参考 `10tax_clinic_pic.R`、`12path_clinic_pic.R`、`14taxa_path_pic.R`。
- `effect_plot`：真实置信区间森林图；无置信区间可明确选择棒棒糖图。可为已有 LDA 结果绘图，不代表支持 LEfSe 计算。
- `association_network`：参考 `15build_chain*.R`、`16*`，连接菌种→通路→表型的两组关联结果；保留边符号、效应种类、p/q 与来源。不同效应量的边宽不能做跨层定量比较；图形表示关联，不作中介或因果解释。

所有能力均进入工具目录，可由用户选择字段或由智能体规划。推断方法需要确认独立观测；配对/重复测量不能直接套用。

## 结果作为下一步输入

方案步骤显式声明依赖与结果表，不依靠文件名猜测：

```json
{
  "id": "s3",
  "skill": "effect_plot",
  "depends_on": ["s2"],
  "inputs": {"data": {"step_id": "s2", "output": "associations"}}
}
```

- 分组筛选结果可通过 `inputs.candidates` 进入全样本回归；候选条件为真实特征及 `q <= alpha`。候选表的 `feature` 索引也可识别。
- 合并表使用 `inputs.data`；三层网络使用 `inputs.left/right`。
- 自定义分析程序使用 `results[alias]` 读取明确绑定的上游表，继续受隔离执行、输出约定、研究要求检查与模型审查约束。
- 规划时检查已声明的产物、引用顺序及依赖；执行时检查项目归属、文件哈希和成功状态；缓存包含上游产物哈希。
- 没有显著候选、没有交集、缺失 CI 或上游失败时明确停止该步骤，不更换目标或补造结果。
- 复现包按步骤顺序重新传递结果，不需要 LLM 即可复跑已确认的程序。

## 与旧脚本不同的处理

1. `/` 等缺失值不变成无症状或阴性；分类分母按实际有效值计算。
2. CLR 在完整同层级成分上计算后再选候选，避免候选集改变变换分母；物种与菌株不重复相加。
3. 通路默认要求真实群落总量。`stratified` 保留物种分层；`contribution_sum` 仅在明确选择时合计，并标为代理值。不会静默伪装 HUMAnN 群落总量。
4. 默认 BH；可选全部模型或每结局一个检验族。不在展示 Top N 后重算 q。
5. 每个模型保留有效样本数、排除数、协变量编码、不可估计原因与效应含义；不静默删除缺失协变量。
6. 桑基图不以极小伪权重补零边、不自动平均互相冲突的重复关联。

## 尚未迁移

仓库的 `4alpha_beta.R`、`5taxa_lefse.R`、`7path_lefse.R` 依赖 R 及相应分析包。平台已有 Alpha/Beta 多样性与探索性差异方法，但它们不等同 LEfSe、ANCOM-BC2 或 ALDEx2。当前无 R 执行器，不能声称已经完成这些方法或论文全分析的复现。

本轮没有实现校正二分类 Logistic、混合效应/重复测量模型、真正中介分析与多变量菌群差异算法；不能将 OLS 或网络图当成这些方法。

## 验证

`tests/test_research_methods.py` 以独立 HC3 sandwich 公式、秩相关矩阵逆矩阵、BH 全家族结果核对统计值；验证真实后台执行的跨表合并→校正分析→森林图，及哈希篡改、候选表索引、CLR 顺序、缺失分母、通路口径与桑基边筛选。

`tests/test_adaptive_analysis.py` 增加 `results[alias]` 的真实 OS 隔离集成验收。需要 `YANJI_TEST_OS_SANDBOX=1` 在支持的宿主环境运行；应用不提供无隔离降级。

本地验收记录：2026-11-18，全套回归 `146 passed, 2 skipped`（两项需显式启用的 OS 集成测试单独执行）；启用 OS 集成后 `test_adaptive_analysis.py` 为 `15 passed`。前端类型检查与生产构建通过。真实配置模型 + 120 条合成观测生成了 HC3 校正回归→森林图的结果依赖方案，并在确认后完成后台计算；确认前没有创建运行记录。浏览器核对了手动字段选择、待确认方案和实际图表结果。

在独立临时项目中使用本地原表运行：镁与 ATEC 总分、年龄/性别校正的偏相关匹配 200 条记录；物种 CLR→ATEC 总分、年龄/性别校正 HC3 回归匹配 191 个样本，估计 1,378 个物种模型。这里只验证可执行性与产物，不把该口径冒充论文完整队列、完整协变量设计或已复现论文结论。原始文件、用户项目和模型配置均未修改。
