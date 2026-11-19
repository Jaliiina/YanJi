# 数据与科学方法约定

## 数据模型

输入文件永不修改。每份成功导入的数据保存 SHA-256、来源、单位、样本、特征、整理操作和独立版本 ID。内部使用压缩 JSON 矩阵，CSV/TSV 为入口和结果导出格式。不会反序列化用户提供的 pickle 或执行上传代码。

分类表允许多层级共存，但计算一次只使用种或属。缺少属级行时，可以对已列出的同属种级行进行汇总，界面明确说明覆盖范围；不会跨父子层级重复相加。标准矩阵的 species 表示用户提供的原始特征层级，没有分类路径时不推断属级。

HUMAnN 的无分层通路行、物种分层行、UNMAPPED/UNINTEGRATED 等特殊行分别识别。仅分层文件不能转换成群落总通路表。总量文件与仅分层文件可同时作为当前输入保存。

## 单位与零值

百分比除以一百转为比例。比例值应位于零到一；计数必须为非负整数。HUMAnN 其他归一化尺度可选“其他标准化丰度”，但不要误标为比例。

分类组成、多样性和 Bray–Curtis 基于所选分类层级内重新归一化的比例；这不是全部测序 reads 的占比。全零样本在相关数值分析中标记不可计算，并在输入体检与警告中保留。原始零值不使用伪计数替代。

功能概览与差异筛查保留输入尺度；物种贡献占比的分母是该表中该通路已观测贡献之和，绝不是群落总通路量。

## 指标与检验

- Shannon：自然对数；Simpson：1−Σp²；Pielou：Shannon/ln(S)，S 小于二时为 NA。
- 检出特征数：当前文件与过滤条件下大于零的特征数，不是总生态丰富度。
- Bray–Curtis：SciPy 距离；PCoA：scikit-bio，保留负特征值警告。
- Alpha 组间检验：双侧 Mann–Whitney U；同次全部可检验指标做 BH 校正。
- 探索性特征筛查：默认检出率至少 10%；全部可检验特征统一 BH 校正。报告两组中位数、差值、p 和 q。常量特征不生成伪 p 值。
- 群落整体检验：scikit-bio PERMANOVA 和 PERMDISP；默认 999 次置换、种子 42。离散度差异影响解读，不能只凭 PERMANOVA 或排序图判断组中心变化。
- 首版只做两独立组推断。零距离、无法获得有限统计量、每组不足三个有效样本等情况明确跳过。

这些是软件支持的方法，不能代替针对具体研究设计的统计方法论证。相对丰度、组成效应、协变量、测序深度和检测偏差均可能影响解释；当前单变量筛查定位为探索性分析。

## 方法来源

- [MetaPhlAn](https://huttenhower.sph.harvard.edu/metaphlan)
- [HUMAnN 文档及分层通路说明](https://github.com/biobakery/humann)
- [SciPy Mann–Whitney U](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html)
- [SciPy 多重检验校正](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html)
- [scikit-bio PERMANOVA](https://scikit.bio/docs/latest/generated/skbio.stats.distance.permanova.html)
