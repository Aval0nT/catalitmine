# Research Ideas

记录未来值得探索的研究方向。每个 idea 独立追踪，标注来源和当前状态。

---

## Idea 001 — MTA 催化剂参数空间探索（当前进行中）

**方向**：利用文本挖掘 pipeline 系统提取 MTA 文献中的催化剂性能数据，发现尚未被实验覆盖的参数组合。

**核心问题**：在已知的催化剂体系（金属/分子筛/Si-Al比/制备方法）和反应条件（温度/WHSV）空间中，哪些区域数据稀疏但可能有高 BTX 选择性？

**技术路线**：
- Stage A-D：PDF → 结构化 evidence units（已完成）
- Phase 3：SQLite / DuckDB 归一化数据库
- Phase 4：参数空间热图 + Gap detection + Random Forest / SHAP
- Phase 5：湿实验验证（Petra de Jongh 课题组，Utrecht）

**状态**：`进行中` — 文本提取完成，待建库和分析

---

## Idea 002 — 分子筛合成路径的数据驱动研究

**方向**：将类似的文本挖掘方法迁移到分子筛合成文献，系统提取合成条件与结构的关系，辅助发现低成本合成路线。

**背景**：
- 分子筛合成文献高度格式化（晶化温度、模板剂、Si/Al、时间 → 骨架结构），天然适合结构化提取
- IZA 分子筛数据库已有骨架结构的标准化资源，可与提取数据对齐
- Xiaodong Zou 课题组（Stockholm University）+ 学生郭鹏：利用 X 射线电子晶体衍射（EDT）将昂贵模板剂替换为廉价替代品，仍能合成目标骨架 — 这个方向说明合成路径存在可替换性，值得系统挖掘

**两个子方向**：

### (a) 分子筛改性（Modification）
- 脱铝 / 脱硅 / 蒸汽处理 / 碱处理 → 介孔引入、酸性调控
- 条件 → 性质（Si/Al、BET、孔体积、酸量）的映射关系
- 问题：哪种改性方式对 MTA 最有利？

### (b) 分子筛合成（Synthesis）
- 模板剂 → 骨架类型的映射（高度格式化，适合提取）
- 核心 idea（来自郭鹏报告）：能否用 LLM + 晶体学数据，系统发现"廉价模板剂替代昂贵模板剂"的可行路线？
- 相关资源：IZA Structure Database、ICSD、现有合成文献

**所需 pipeline 改动**：
- 新 topic：`zeolite_synthesis`
- 新字段体系：template_agent, crystallization_temp, gel_composition, aging_time, target_framework...
- 可能需要对接晶体学数据库（IZA API 或本地镜像）

**状态**：`想法阶段` — 尚未开始，等 MTA pipeline 稳定后启动

---

## Idea 003 — 跨方向的催化剂结构-性能通用模型

**方向**：在 MTA 和 CO₂ 加氢两个方向的数据积累到足够规模后，探索跨反应体系的催化剂描述符与性能的通用关系。

**核心问题**：ZSM-5 的 Si/Al 比和酸性分布，在 MTA 和其他芳构化反应中是否有共通的构效规律？

**状态**：`远期想法` — 依赖 Idea 001 和 002 的数据积累

---

## Idea 004 — 图表抽取 route B：全图型解释（含产物分布）

**方向**：`chart_extractor` 已能抽取**所有图型**的原始数据（折线/散点/柱状，含产物分布柱状图的 PX/OX/MX 等系列）。当前 demo（route A）只整合"结构描述符 vs 性能"这一类干净图；route B 是把**其余图型也解释、归类、入库**。

**为什么先搁置**：
- 产物分布、TOS 失活曲线等需要更多判别/归一逻辑，噪声大、要人工核对
- 原始数据**已经在抓**（不丢），缺的只是下游解释层

**未来要做的**：
- 产物分布柱状 → 每个催化剂的产物谱（BTX 分布、p/o 比）
- TOS 曲线 → 稳定性/失活速率指标
- 把这些并入 catalyst_records

**状态**：`已预留` — 数据已捕获，等 route A demo 稳定后开 `feat/chart-route-b` 分支正式做。**现在不开空分支**（避免陈旧）。

---

## 参考资源

| 资源 | 说明 |
|---|---|
| IZA Structure Database | 分子筛骨架标准库，zeolite_synthesis topic 的重要对齐资源 |
| Xiaodong Zou / 郭鹏 (Stockholm) | EDT 替换模板剂的合成路线研究，Idea 002 的关键参考 |
| Petra de Jongh group (Utrecht) | MTA 湿实验验证合作方，Idea 001 Phase 5 |
