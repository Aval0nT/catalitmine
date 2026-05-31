# Project Log

---

## 2026-03-24 — MTA 一次文献入库 + 可视化体系建立 + 数据质量修复

### 语料库大幅扩充

在 `build_db.py` 的 REVIEWS dict 中新增 **16 篇一次文献**（MTA 方向）：

| 论文 | 类型 | 主要贡献 |
|---|---|---|
| Pinilla-Herrero 2018, J. Catal. | primary | Zn/Al 比对 MTA 脱氢 vs 氢转移的影响 |
| Ilias 2012, J. Catal. | primary | 烯烃/芳烃共进料调控 MTH 选择性 |
| Ilias 2013, J. Catal. | primary | 芳烃循环 vs 烯烃循环传播描述符 |
| Zhang 2015, ACS Catal. | primary | 表面改性 Zn/P/ZSM-5，p-xylene 选择性 |
| Gong 2021, I&ECR | primary | Zn 改性纳米片 HZSM-5，BTX 高效转化 |
| Gao 2018, ACS Catal. | primary | Ga/ZSM-5 MTA 机理研究 |
| Qiao 2020, RSC Adv. | primary | 磷酸锌基 HZSM-5，BTX 选择性与稳定性 |
| Yarulina 2016, ChemCatChem | primary | ZSM-5 后改性抑制芳烃循环 |
| Bjørgen 2007, J. Catal. | primary | MTH 烯烃物种起源 |
| Hereijgers 2009, J. Catal. | primary | H-SAPO-34 产物形状选择性 |
| Sun 2014a, J. Catal. | primary | 共进料对 MTO/ZSM-5 影响 |
| Sun 2014b, J. Catal. | primary | HZSM-5 反应路径 |
| Erichsen 2015, J. Catal. | primary | 酸强度与烷烃/芳烃反应性 |
| Muller 2015, J. Catal. | primary | ZSM-5 积炭失活路径 |
| Liang 2016, ACS Catal. | primary | 骨架 Al 位置与 MTH 路径关系 |
| Bhawe 2012, ACS Catal. | primary | 笼尺寸对轻烯烃选择性的控制 |
| Liu 2009, Catal. Comm. | primary | P 改性 HZSM-5 制丙烯 |
| Abubakar 2006, Langmuir | primary | 磷酸改性 HZSM-5 结构与机理 |

同时添加 **Li 2021 (ACS Catalysis)** 作为 MTA 方向唯一综述（前四篇均为 MTH/MTO 机理综述，不含 BTX 性能数据）。

### Li 2021 全流程处理（Stage A-D）

Li 2021 PDF 已下载（`/Users/avalont/Zotero/storage/URL47ZUR/`），建立 DOI slug 符号链接后运行完整 pipeline：

- Stage A（分块）：821 chunks
- Stage B（筛选）：高价值 chunk 筛选完成
- Stage B.5（CDE 富化）：完成
- Stage D（LLM 提取）：821 units，写入 `10.1021_acscatal.1c01422.llm_evidence.jsonl`

**JSONL 加载逻辑修复**：`build_db.py` 原只读 `.filtered.jsonl`，Li 2021 无 filtered 版本导致 0 条入库。修复为优先读 `.filtered.jsonl`，否则 fallback 到 `.llm_evidence.jsonl`。

### 数据库当前状态

| 表 | 行数 |
|---|---|
| `papers` | 25 |
| `evidence_units` | 6,211 |
| `table_rows` | 295 |

Evidence units 按 topic：
- `mta`: 3,669 条
- `co2a`: 2,542 条

### Schema 更新：methanol_sel_pct 字段

**问题发现**：Zhong 2020 ChemRev（CO₂→MeOH 综述）Table 2 的"selec/C-mol%"列是**甲醇选择性**，LLM 将其存入 `aromatic_sel_pct`，导致 CO₂ 双功能催化剂分析中出现 Cu/No-zeolite 显示 52% "芳烃选择性" 的严重异常（实为甲醇选择性）。

**修复方案**：
1. `CREATE TABLE` 新增 `methanol_sel_pct REAL` 字段（位于 `methanol_conv_pct` 之后）
2. INSERT 映射中加入该字段
3. 建库后执行 SQL UPDATE：对 Zhong 2020 来源、无分子筛、`aromatic_sel_pct IS NOT NULL` 的行，将 `aromatic_sel_pct` 值迁移至 `methanol_sel_pct`，并将 `aromatic_sel_pct` 置 NULL

迁移结果：**55 行**成功迁移，CO₂ 芳烃选择性数据降至 133 条（清洁真实数据）。

### 可视化体系建立（figures/）

新建 4 个可视化脚本，输出至 `figures/`：

| 脚本 | 图表 | 说明 |
|---|---|---|
| `visualize_mta_heatmap.py` | 3 张 | MTA: scatter/heatmap（催化剂组×分子筛→芳烃选择性）/stripplot |
| `visualize_co2_heatmap.py` | 3 张 | CO₂: 金属×分子筛→芳烃选择性、金属×载体→转化率、温度散点图 |
| `visualize_co2_conversion.py` | 3 张 | CO₂ 363 个转化率数据点：stripplot/heatmap/histogram（按金属分） |
| `visualize_co2_bifunctional.py` | 3 张 | 按功能分组（加氢组分×芳构化组分），heatmap+stripplot |

**关键分析结果（MTA）**：
- Zn/ZSM-5 平均芳烃选择性 68%（n 最高）
- Zn+P/ZSM-5 平均 53%
- Ga/ZSM-5 平均 47%

**关键分析结果（CO₂）**：
- 总体中位转化率 19%；Fe 最高（~34%），Cu 约 21%
- ZnCrOx/ZSM-5：31.2% 转化率（n=5），是文献中典型双功能 CO₂→芳烃体系
- In₂O₃/No-zeolite：80.2% 转化率（n=4），来自高转化率 CO₂→MeOH 体系

### Semantic Scholar API 集成

新脚本 `scripts/search/semantic_scholar.py`：
- 1 req/s 速率限制包装器
- 支持四种模式：`expand`（全库引用扩展）、`citations`、`search`、`recommendations`
- S2 API Key 存入 `.env`（`S2_API_KEY`）
- 输出：`data/04_search/s2_candidates.jsonl`

### Zotero 工作流完善

新脚本 `scripts/zotero/add_dois_to_zotero.py`：
- 输入 DOI 列表，自动从 Crossref 获取元数据
- Claude Haiku 分类至正确 collection + subcollection
- 无需上传 PDF，直接创建 Zotero item

分类体系（taxonomy）覆盖：
- `002_Methanol to Aromatic`：direct MTA / zeolite-selectivity / deactivation-coke / MeOH-mediated CO2-to-aromatics bridge / review
- `003_CO2 to Aromatic`：direct CO2→aromatics / bifunctional / CO2→MeOH→olefins
- `004_Other`：review / unrelated

---

## 2026-03-22 — SQLite 建库 + OpenAlex 解析 + ref_lookup 全覆盖

### ref_lookup：全部 5 篇完成（Vision OCR）

新脚本 `scripts/analysis/extract_ref_lookup_vision.py`：用 Claude Vision 对引用列表页做 OCR，绕过 pdfplumber 两栏乱码问题。

| 论文 | 方式 | 引文数 |
|---|---|---|
| Nature Catalysis MTA | Vision OCR（替换正则） | 117 条 |
| ChemRev (ACS) | Vision OCR（替换正则） | 343 条 |
| ChemPR | Vision OCR（新增） | 152 条 |
| apcatb | Vision OCR（替换正则） | 230 条 |
| ACS Catalysis 2016 | Vision OCR（新增） | 44 条 |
| **合计** | | **886 条** |

### OpenAlex DOI 解析（全部 5 篇完成，2026-03-24 更新）

脚本 `scripts/analysis/resolve_refs_openalex.py`：引文文本 → 标题提取 → OpenAlex title.search → DOI。
速率限制从 0.5s 改为 **1.0s/req**（避免 429 错误），重跑之前失败的 3 篇。

| 论文 | 命中/总数 | 命中率 | 说明 |
|---|---|---|---|
| ACS Catalysis 2016 (Guisnet) | 35/44 | 80% | 已完成 ✅ |
| Nature Catalysis (Yarulina 2018) | 47/117 | 40% | 已完成 ✅ |
| ChemRev (Zhong 2020) | 160/343 | 47% | 重跑完成 ✅ |
| ChemPR (Wang 2021) | 95/152 | 62% | 重跑完成 ✅ |
| apcatb 2021 | 9/230 | 4% | 完成（命中率低，CO₂还原类引文格式特殊） |
| **合计** | **346/886** | **39%** | |

- 输出：`data/03_evidence/*.ref_resolved.json`（得分阈值 ≥ 0.7 时写入 primary_paper_doi）

### primary_paper_doi 自动填充（新增）

`build_db.py` 新增 `fill_primary_paper_doi()` 函数：读取 `.ref_resolved.json` → 提取引文编号 → 写入 `evidence_units.primary_paper_doi`（仅 score ≥ 0.7 的高置信命中）。

| source_review_doi | 总 units | 已填充 |
|---|---|---|
| ChemRev (Zhong 2020) | 1594 | 254 |
| ChemPR (Wang 2021) | 439 | 69 |
| Yarulina 2018 | 346 | 30 |
| Guisnet 2016 | 66 | 13 |
| apcatb 2021 | 509 | 6 |
| **合计** | **6211** | **372 (6%)** |

Li 2021（821 units, 453 source_refs）尚无 ref_lookup.json，需先运行 `extract_ref_lookup_vision.py`。

### SQLite 数据库建立

新脚本 `scripts/db/build_db.py`，三表结构：

| 表 | 内容 | 行数 |
|---|---|---|
| `papers` | 5 篇综述元数据 | 5 |
| `evidence_units` | 文字提取（filtered） | 2,484 |
| `table_rows` | Vision 表格数据 | 200 |

- `temperature_K → temperature_c` 自动换算（K-273.15）
- `extra_fields` 存为 `extra_json` blob
- 索引：catalyst_system、zeolite_type、claim_type、source_review_doi

### 关键发现（数据质量）

- MTA evidence：269 条（机理为主，claim_type=mechanism 62%）
- **MTA 性能数字接近 0**：两篇 MTA 综述均为机理综述，无数据表格，数值在一次文献里
- CO₂ 加氢 evidence：2,215 条，表格数据 200 行（ChemPR + ChemRev + apcatb）
- MTA 分子筛分布：ZSM-5（72）> SAPO-34（21）> MFI（8）
- MTA 机理分布：hydrocarbon_pool（68）> dual_cycle（21）

### 下一步（优先级排序）

1. **完成 OpenAlex 解析**（等 rate limit 恢复后串行重跑）
2. **一次文献下载 + Pipeline**：从 ref_lookup 解析出的 DOI 下载 MTA 一次文献 PDF，跑完整 Stage A-D，获取真实性能数字
3. **可视化**：目前 CO₂ 数据可以先做（200 行表格数据），MTA 待一次文献补充后做

---

## 2026-03-21（续）— Phase 4 准备：数据质量审查 + 架构决策

### 数据质量审查结果

对 2511 条 filtered evidence units 做字段填充率分析，关键发现：

**全量（5篇）：**
- `catalyst_system` 90%、`claim_*` 53%、`source_reference` 45% — 核心字段质量合格
- `temperature_c` 0%：LLM 将温度写入 `extra_fields.temperature_K`，需后处理归一化
- 性能字段（`btx_selectivity_pct` 1.7%）：3 篇 CO₂ 加氢论文不含 MTA 性能数据，属正常

**MTA 专项（265 条）：**
- `zeolite_type` 52%、`proposed_mechanism` 42%、`claim_*` 76% — 机理层面信息丰富
- `active_metal` 1.5%：Nature Catalysis 讨论的是纯分子筛体系（ZSM-5、H-ZSM-5），无金属负载，字段为空是正确的
- 性能数字接近 0%：该综述为机理综述，数值在表格和一次文献里，文字提取不到是预期行为

### 架构决策（已确认）

1. **JSONL 永远是 source of truth**，不删除
2. **引入 SQLite**：因为下一步要做跨综述的关联查询（JOIN），关系型 DB 是必要的
3. **数据库三张核心表**：`papers`（一次文献 + 综述）/ `evidence_units`（文字提取）/ `table_rows`（Vision 表格）
4. **关联字段**：`primary_paper_doi`，通过 `source_reference → ref_lookup.json → OpenAlex API` 三步解析后回填

### Vision 表格提取完成

- ChemPR（`10.1016_j.chempr.2021.02.024`）：7 页 → 7 张表，128 行数据
- ChemRev（`10.1021_acs.chemrev.9b00723`）：8 页 → 9 张表，多级表头已正确展开
- System prompt 更新：加入多行合并表头处理规则（父级/子级列名拼接）
- MTA 两篇综述：0 表格（Nature Catalysis 为纯机理综述，无数据表）

### Bug 修复

- Stage D `'str' object has no attribute 'get'`：LLM 偶尔在 `evidence_units` 数组里返回字符串而非 dict，在 `_call_pass()` 返回时过滤 + `_merge_units()` 迭代时双重防御
- 补跑 11 个因 bug 漏掉的 missing chunks（临时脚本 `scripts/tmp_rerun_missing.py`），新增 136 units，0 错误

### IDEAS.md 创建

新建 `IDEAS.md` 记录三个研究方向：
- Idea 001：MTA 参数空间探索（当前进行中）
- Idea 002：分子筛合成路径数据驱动研究（郭鹏 / Xiaodong Zou EDT 模板剂替换思路）
- Idea 003：跨方向催化剂结构-性能通用模型（远期）

### 下一步（Phase 4 推进顺序）

1. 修复 `ref_lookup` 对 ACS 括号格式的支持（ChemRev/ChemPR 目前漏检）
2. `source_reference → ref_lookup.json → OpenAlex API → primary_paper_doi`
3. 建 SQLite：三表结构，导入 evidence units + table rows
4. 回填 `primary_paper_doi` 外键
5. 可视化分析

---

## 2026-03-21 — Stage C NER + 引用页过滤 + 全文提取完成

### Stage C：MatSciBERT NER 部署（已完成）

- 模型：`nlp-magnets/matscibert-cner`（HuggingFace，CPU 推理）
- 新脚本：`scripts/extraction/ner_enrich_chunks.py`
- 输出：每个 chunk 追加 `matbert_entities`、`matbert_mat_list`、`matbert_version` 字段（in-place 更新 `data/02_enriched/`）
- 安装修复：NumPy 降至 1.26.4（兼容 scipy/sklearn），torch 升至 2.8.0（修复 CVE-2025-32434）

### Stage D：全部 MTA 文本 pipeline 完成

| 论文 | 原始 units | 过滤后 |
| --- | --- | --- |
| `10.1038_s41929-018-0078-5` | 315 | 202 |
| `10.1016_j.chempr.2021.02.024` | 417 | 417 |
| `10.1021_acs.chemrev.9b00723` | 1513 | 1513 |
| `10.1007_s13203-016-0156-z` | 63 | 63 |
| `10.1016_j.apcatb.2021.120073` | 421 | 316 |
| **合计** | **2729** | **2511** |

注：ChemRev（`chemrev.9b00723`）为 CO₂-to-alcohols 方向，非 MTA 核心，Phase 3 可按 topic 过滤。

### 引用页过滤（`filter_ref_chunks.py`，已完成）

- 新脚本：`scripts/analysis/filter_ref_chunks.py`
- 功能 1：检测来自参考文献列表页的 evidence units 并过滤，写入 `*.llm_evidence.filtered.jsonl`
- 功能 2：解析参考文献页为 `{编号: 引文文本}` 查找表，写入 `*.ref_lookup.json`
- 检测规则：`(ref_num >= 4 and et_al >= 2) or (ref_num >= 5 and j_abbrev >= 4)`
- 已知局限：ACS 括号格式 `(52) Author...` 和两栏 PDF 混排暂不支持（ChemRev/ChemPR 漏检）

### Pipeline 架构图（已完成）

- `outputs/reports/pipeline_scheme.md`：包含 Mermaid 流程图（Phase 1-5 含湿实验闭环）+ Napkin.ai 纯文字版

---

## 2026-03-20（续2）— Stage D 重写完成 + Schema 自动扩展机制

### Stage D：3-Pass 级联提取（已实现）

`scripts/extraction/extract_llm_evidence.py` 完全重写：

**架构变化：**

- 单次 LLM call（40 字段，CO2 加氢 schema）→ 3-Pass 级联提取（MTA schema v1）
- Pass 1（催化剂身份）→ Pass 2（性能指标）→ Pass 3（条件+机理）
- **级联门控**：Pass 1 返回空（无催化剂实体）→ 跳过 Pass 2/3，节省约 40% token

**各 Pass 字段：**

| Pass | Tool name | 字段数 | 核心字段 |
| --- | --- | --- | --- |
| 1 | `extract_catalyst_identity` | 10 | active_metal, support, zeolite_type, si_al_ratio, metal_loading_wt, morphology, preparation_method |
| 2 | `extract_performance_metrics` | 17 | methanol_conversion_pct, btx_selectivity_pct, benzene/toluene/xylene_pct, tos_h, coke_content_wt, BET, 酸性 |
| 3 | `extract_conditions_mechanism` | 18 | temperature_C, pressure_MPa, whsv, claim triple, proposed_mechanism, evidence_type, confidence |

**合并策略：** 三个 Pass 结果按 `catalyst_system` 名称（case-insensitive）匹配合并，孤儿记录单独追加。

**Prompt caching 保留**：三个 system prompt 均加 `cache_control: ephemeral`。

### Schema 自动扩展机制（方案 A）

- 三个 Pass 的 schema 各加 `extra_fields: object`（自由 KV dict）
- LLM 遇到正式字段覆盖不到的内容（如 `crystal_size_nm`, `b_l_ratio`, `regeneration_temp_C`）会写入 `extra_fields`
- `scripts/analysis/aggregate_extra_fields.py`：统计所有 evidence JSONL 中 `extra_fields` key 出现频率，输出 promotion checklist

运行方式：

```bash
python3 scripts/analysis/aggregate_extra_fields.py           # 默认：>=2 次
python3 scripts/analysis/aggregate_extra_fields.py --min-count 5
```

### 关于 NULL 字段的设计原则（已确认）

Optional 字段在对应 chunk 没有相关信息时**不出现在 JSON 记录里**，Phase 3 写入 SQLite 时为 `NULL`。这是正确行为，不需要补 `null` 或 `"N/A"`。稀疏记录是颗粒度对齐的正常结果。

---

## 2026-03-20（续）— Pipeline 架构重设计

### 背景

在对 MTA 方向字段做完整审查后，发现原有单层 LLM 提取架构存在根本性问题：

- 字段维度实际应为 **30-40 维**（催化剂身份 ~10 + 性能指标 ~10 + 反应条件 ~8 + 表征参数 ~8）
- 一次 LLM call 塞入 40 个字段 → 模型准确率显著下降，张冠李戴风险高
- 现有 `co2_conversion_pct`、`h2_co2_ratio` 等字段为 CO2 加氢方向设计，不适用于 MTA
- **颗粒度对齐**是优先问题：字段太多且未标准化，Phase 3 归一化将极难处理

### 新 Pipeline 架构（分层提取）

```text
PDF
 ↓ Stage A: pdfplumber 文本提取 + 句子级分块
   → 两栏 PDF 用句子边界分割（已实现）
   → 表格页标记 chunk_type="table"（待实现）

 ↓ Stage B: 高价值 chunk 筛选（正则评分）

 ↓ Stage B.5: 正则预标注（扩展版）
   原有：提取数字+单位
   新增：为每个数值附加上下文窗口（前后20字符），作为 LLM 的锚点
   新增：轻量催化剂 token 提取（Cu/ZnO, Zn/ZSM-5 格式）

 ↓ Stage C: NER 模型（MatBERT，待部署）
   → 化学实体识别：拆解 "5wt%Zn/ZSM-5" → metal=Zn, loading=5%, support=ZSM-5
   → 先于 LLM 运行，输出结构化 token，减轻 LLM 负担
   → 暂时跳过，Stage B.5 正则结果直接传入 Stage D

 ↓ Stage D: LLM 分组提取（3 Pass，每 Pass 7-8 个字段）

   Pass 1 — 催化剂身份组（Claude Haiku）
     active_metal, promoter, support, zeolite_type,
     si_al_ratio, metal_loading_wt, morphology,
     preparation_method

   Pass 2 — 性能指标组（Claude Haiku）
     methanol_conversion_pct, btx_selectivity_pct,
     benzene_pct, toluene_pct, xylene_pct,
     c9plus_pct, btx_yield_pct,
     tos_h, coke_content_wt

   Pass 3 — 条件 + 机理组（Claude Haiku）
     temperature_C, pressure_MPa, whsv, ghsv,
     feed_methanol_conc,
     claim_type, claim_subject, claim_predicate, claim_object,
     mechanism_text, evidence_type, confidence

 ↓ Stage A.5（并行）: Vision 表格提取（Claude Sonnet）
   → 表格页渲染为 PNG → Vision 提取结构化行列
   → 输出 data/03_evidence/<doi>.tables.jsonl
   → 覆盖 Pass 1+2 的大量数值字段（表格是主要数据来源）

合并 → data/03_evidence/<doi>.llm_evidence.jsonl
     → Phase 3: db/catalysis.db
```

### MTA 完整字段清单（v1）

#### 催化剂身份（Pass 1 / 表格）

```text
active_metal          # Cu, Zn, Ga, Mo, ...
promoter              # K, Na, Ca, ...（可多个）
support               # ZSM-5, Beta, SAPO-34, Al2O3, ...
zeolite_type          # ZSM-5 / Beta / SAPO-34 / MCM-22 / ...
si_al_ratio           # 硅铝比
metal_loading_wt      # 金属负载量 wt%
morphology            # nanosheet / hierarchical / conventional
modification_method   # dealumination / desilication / steaming
preparation_method    # impregnation / ion-exchange / coprecipitation
```

#### 催化剂表征（主要来自表格 Vision）

```text
bet_surface_area      # m²/g
pore_volume           # cm³/g
micropore_volume      # cm³/g
crystal_size_nm       # nm
bronsted_acid_mmol_g  # mmol/g
lewis_acid_mmol_g     # mmol/g
b_l_ratio             # B/L 酸比
```

#### 反应条件（Pass 3 / 表格）

```text
temperature_C         # °C
pressure_MPa          # MPa（或 bar，归一化到 MPa）
whsv                  # g_MeOH/(g_cat·h)
ghsv                  # mL/(g_cat·h)
feed_methanol_conc    # 甲醇进料浓度或分压
carrier_gas           # N2 / He / 无
reactor_type          # fixed-bed / batch / flow
```

#### 性能指标（Pass 2 / 表格）

```text
methanol_conversion_pct    # %（主指标，取代 co2_conversion_pct）
btx_selectivity_pct        # BTX 总选择性 %
benzene_pct                # %
toluene_pct                # %
xylene_pct                 # %
c9plus_pct                 # C9+ 芳烃 %（副产物）
olefin_pct                 # 烯烃 %
paraffin_pct               # 烷烃 %
btx_yield_pct              # = 转化率 × BTX选择性
```

#### 稳定性（Pass 2 / 表格）

```text
tos_h                      # 实验持续时间 h
conversion_drop_pct        # 失活后转化率下降 %
coke_content_wt            # 积炭量 wt%
regeneration_temp_C        # 再生温度 °C
```

#### 机理 / Claim（Pass 3）

```text
claim_type            # performance / mechanism / trend / comparison
claim_subject         # 催化剂或实体
claim_predicate       # increases / suppresses / shifts / enables / ...
claim_object          # 被影响的指标或现象
mechanism_text        # 自由文本机理描述
proposed_mechanism    # hydrocarbon pool / paring / side-chain / ...
key_intermediates     # [polymethylbenzenes, carbenium ions, ...]
evidence_type         # experimental / DFT / operando / review_synthesis
evidence_strength     # strong / medium / weak
confidence            # high / medium / low
contradiction_flag    # bool
source_reference      # 被综述引用的一次文献
```

### 颗粒度对齐原则（重要）

在开始批量提取前，**必须先对齐以下颗粒度**，否则后期归一化极难处理：

1. **一条 evidence unit = 一个催化剂系统 × 一组反应条件 × 一套性能数据**
   - 不同温度下同一催化剂 → 两条记录，不合并
   - 同温度下不同催化剂 → 两条记录，不合并

2. **数值字段优先从表格提取**，文本提取的数值作为补充（表格精度高，文本易张冠李戴）

3. **化学名称标准化**在 Phase 3 统一处理，提取阶段保留原文写法，不强制规范

4. **选择性字段**：始终记录分母（基于碳 / 基于产物总量），不同基准的数值不可混用

---

## 2026-03-20（上午）— 项目结构重组 + Stage A-B.5 完成

### 项目结构重组

将分散的文件夹整合为标准化目录结构，并创建 `STRUCTURE.md` 作为 agent 可读的路径规范文档：

```text
旧结构问题：
  - PDFs 散落在 pdfs/、Methanol to Aromatic/pdfs/、CO2 to Aromatic/pdfs/ 三处
  - data/ 下无编号，pipeline 顺序不可见
  - log.txt、tde_log.txt 飘在根目录

新结构：
  topics/mta|co2a|shared/pdfs/    ← 按研究方向的 PDF
  data/00_raw → 01_chunks → 02_enriched → 03_evidence → 04_search → 05_normalized
  outputs/viz|reports|models|candidates/
  scripts/search|extraction|db|analysis|ml/
  logs/
```

### Script 更新

| 脚本 | 变更 |
| --- | --- |
| `chunk_review_pdf.py` | 完全重写：新路径、支持 `--topic/--doi/--all`、两栏 PDF 句子级分割 |
| `select_high_value_chunks.py` | 重写为标准 CLI，读写路径更新 |
| `enrich_chunks_cde.py` | 路径更新：`review_evidence` → `01_chunks`，`review_evidence_enriched` → `02_enriched` |
| `extract_llm_evidence.py` | 路径更新：`review_evidence_enriched` → `02_enriched`，`review_evidence` → `03_evidence` |
| `search_openalex.py` | 移至 `scripts/search/`，路径无变化 |

### Stage A-B.5 运行结果（MTA 4篇综述）

| 论文 DOI | 总 chunks | 高价值 | 占比 |
| --- | --- | --- | --- |
| `10.1021_acs.chemrev.9b00723` | 190 | 157 | 83% |
| `10.1038_s41929-018-0078-5` | 58 | 54 | 93% |
| `10.1016_j.chempr.2021.02.024` | 92 | 49 | 53% |
| `10.1007_s13203-016-0156-z` | 20 | 19 | 95% |

注：两栏 PDF 原本每页合并为 1 个超大 chunk（6000-10000字），加入句子分割后恢复为正常颗粒度（每 chunk ~500-1500字）。

---

## 2026-03-20（早）— Schema 设计与 MTA 方向确认

发现现有字段（针对 CO2 加氢制醇）无法适配 MTA，主要问题：

- `co2_conversion_pct` → 应为 `methanol_conversion_pct`
- `selectivity_pct`（单值）→ 需要 BTX 各组分分别记录
- `h2_co2_ratio` → MTA 不适用，应为 `whsv` / `feed_methanol_conc`
- 缺少催化剂表征字段（Si/Al、BET、酸性）
- 缺少积炭/失活字段

决定：在开始 Stage D 批量提取**之前**，先完成字段体系设计，避免后期大规模返工。

---

## 2026-03-16 — Pilot 提取 + Vision 表格方案确定

### 人工审查与 Schema 重设计

发现问题：

- 表格内容未进入 chunk pipeline（pdfplumber 无法处理无框线表格）
- `selectivity_pct` 单字段无法记录多产物选择性分布

调查过程：

- pdfplumber lines strategy → 失败（PDF 无边框线）
- camelot stream 模式 → 可识别，但误识别两栏正文为表格
- 最终选定：**Claude Vision**（页面渲染为 PNG → base64 → 多模态提取）

执行操作：

1. 旧版结果备份至 `data/03_evidence/10.1016_j.apcatb.2021.120073.llm_evidence.v1.jsonl`
2. 更新 Stage D schema，新增 `claim_subject/predicate/object`、`active_metal`、`promoter`、`support`、`performance_data` dict
3. 重跑 Stage D → 421 条 evidence units

---

## 待办（当前优先级）

### 已完成 ✅

- [x] 运行 `extract_tables_vision.py` 提取表格
- [x] 修复 Stage D `'str' object has no attribute 'get'` bug
- [x] Phase 3：构建 SQLite 数据库（6,211 units）
- [x] Li 2021 ACS Catalysis 全流程处理（Stage A-D）
- [x] MTA 一次文献入库（16 篇）
- [x] methanol_sel_pct 字段 + Zhong 2020 迁移（55 行）
- [x] 可视化体系建立（4 个脚本，12 张图）
- [x] Semantic Scholar API 集成
- [x] Zotero DOI 批量添加脚本
- [x] Semantic Scholar 引用扩展：Li 2021 → 172 引用 → 筛出 30 篇 MTA 一次文献，添加至 Zotero PENDING 文件夹
- [x] OpenAlex DOI 解析：全部 5 篇完成（速率 1s/req）；命中率 4-80%
- [x] `fill_primary_paper_doi()` 加入 `build_db.py`：372/6211 units（6%）已填充 primary_paper_doi

### 🔧 Pipeline 优化（设计中，勿改现有脚本）

**背景**：当前 Stage B 按关键词评分，不区分章节。对一次文献来说，Introduction 包含大量文献引用式描述，是主要噪声来源。核心问题不是 token 成本，而是**信噪比**：LLM 的 context window 里塞满 Introduction，真正的实验数据（Results/Activity）反而被稀释，导致提取精度下降、有效信息密度低。目标是在更短时间内从每篇文章里拿到更多有用信息。

**设计决策（已确认）**：
- Introduction：可完全跳过（用户已明确，不需要 intro 内容）
- Methods/Experimental：**必须保留**（反应条件 T、P、WHSV 在此）
- Results & Discussion：核心目标，优先处理
- 综述文章（review）：无明确章节结构，维持现有逻辑不变

**计划**：写一个平行版脚本 `select_high_value_chunks_v2.py`，在现有评分基础上加入章节检测：
- 检测到 Introduction 标志 → 该 chunk 降权至阈值以下（实际跳过）
- 检测到 Results / Activity 标志 → 提权
- 新增 `paper_type` 参数：`primary`（启用章节过滤）vs `review`（维持原逻辑）
- 旧脚本 `select_high_value_chunks.py` 保持不变，作为 fallback

**预计收益**：一次文献 token 消耗减少 30-40%；Introduction 噪声引起的张冠李戴提取减少。

**实现前提**：先用已有的一篇一次文献（如 Pinilla-Herrero 2018 或 Gong 2021）做对照实验，测量章节过滤前后的 chunk 数量和 token 变化。

### 近期（语料库扩充）

- [ ] Zotero PENDING 文件夹（30 篇）人工筛选 → 下载 PDF → 运行 Stage A-D（用新 v2 脚本）
- [ ] Li 2021 ref_lookup 提取：运行 `extract_ref_lookup_vision.py` → 再跑 resolve_refs → 填充 primary_paper_doi（453 source_refs 待解析）

### 近期（数据质量）

- [ ] Unit 对齐问题：同一实验的性能（Pass 2）和条件（Pass 3）散落在不同 evidence units；需按 `(source_chunk_id, catalyst_system)` GROUP BY + COALESCE 合并
- [ ] Unknown active_metal 问题：多金属复合氧化物（In₂O₃-ZnZrOx 等）未被识别
- [ ] 扩展 `is_ref_chunk()` 支持 ACS 括号格式 `(52) Author...`

### 研究设计方向（待讨论）

- [ ] MTA idea 细化：Zn 活性物种 × 空间分布 × 脱氢耦合机制（ZSM-5 / SAPO-5 对比）
- [ ] 从 DB 中提炼 structure-property gap map（哪些 catalyst combination 未被实验探索）

---

## 阶段里程碑总览

| 阶段 | 交付物 | 对应 PeroMAS |
| --- | --- | --- |
| Phase 1 | 单篇高质量提取 + 评分基准（**当前**） | Miner Agent（单篇验证） |
| Phase 2 | 全批次 JSONL 原始提取 | Miner Agent（批量） |
| Phase 3 | SQLite DB（三级结构，归一化） | 共享 Memory |
| Phase 4 | SHAP 报告 + Pareto 图 + gap_candidates | Analyst Agent |
| Phase 5 | ML 预测模型 + top_candidates | Emulator Agent（Dry-lab） |
| Phase 6 | 实验验证 + 闭环更新 | Wet-lab + 闭环 |
