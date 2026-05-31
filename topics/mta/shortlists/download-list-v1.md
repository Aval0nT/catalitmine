# MTA Download List v1
Generated: 2026-03-20

Status legend: ✅ 已下载 | ⬇️ 待下载 | 📁 在shared/pdfs（需确认）

---

## Round 1 — 核心综述（必须先读）

| # | DOI | 期刊 | 年份 | 引用 | IF | 状态 |
|---|-----|------|------|------|----|------|
| 1 | `10.1038/s41929-018-0078-5` | Nature Catalysis | 2018 | 731 | S(42) | ✅ mta/pdfs |
| 2 | `10.1007/s13203-016-0156-z` | Applied Petrochemical Research | 2016 | — | C | ✅ mta/pdfs |
| 3 | `10.1021/acs.chemrev.9b00723` | Chemical Reviews | 2020 | — | S(60) | ⬇️ |
| 4 | `10.1016/j.chempr.2021.02.024` | Chem | 2021 | — | S(23) | ⬇️ |

备注：#3 是 MTH/MTA 机理和催化剂设计的顶级综述，优先级最高。

---

## Round 2 — 高引用 MTA 机理/催化剂一次文献

| # | DOI | 期刊 | 年份 | 引用 | 内容摘要 | 状态 |
|---|-----|------|------|------|---------|------|
| 5 | `10.1021/jacs.1c03475` | JACS | 2021 | 104 | 自催化反应路径机理，多技术表征 | ⬇️ |
| 6 | `10.1021/acscatal.9b01820` | ACS Catalysis | 2019 | 79 | 同步辐射 IR 解析 HZSM-5 表面甲氧基初始步骤 | ⬇️ |
| 7 | `10.1039/c8cy01734d` | Catal. Sci. Technol. | 2018 | 72 | Zn/ZSM-5 形貌对 MTA 活性/稳定性影响 | ⬇️ |
| 8 | `10.1021/acscatal.1c05481` | ACS Catalysis | 2022 | 51 | Ca,Ga 双金属修饰 ZSM-5，稳定性提升 | ⬇️ |
| 9 | `10.1021/acscatal.9b02259` | ACS Catalysis | 2019 | 49 | 糠醛+甲醇共芳构化，ZSM-5 反应机理 | ⬇️ |
| 10 | `10.1007/s11705-018-1778-8` | Front. Chem. Sci. Eng. | 2019 | 42 | 蒸汽碱处理 Al-rich HZSM-5 脱铝/脱硅 | ⬇️ |
| 11 | `10.1016/j.micromeso.2019.03.040` | Microporous Mesoporous Mater. | 2019 | 33 | 甲苯甲基化反应路径与微孔扩散机制 | ⬇️ |
| 12 | `10.1021/acs.iecr.0c06342` | Ind. Eng. Chem. Res. | 2021 | 32 | Zn 修饰纳米片 HZSM-5，高效 BTX 选择性 | ⬇️ |

---

## Round 3 — CO2-to-Aromatics 上下文综述（平行方向）

| # | DOI | 期刊 | 年份 | 内容摘要 | 状态 |
|---|-----|------|------|---------|------|
| 13 | `10.1016/j.ccr.2022.214982` | Coord. Chem. Reviews | 2022 | CO2 直接氢化制芳烃，最核心综述 | ✅ co2a/pdfs |
| 14 | `10.1080/01614940.2022.2099058` | Catalysis Reviews | 2022 | 多功能催化剂 CO2 → 芳烃 | ⬇️ |
| 15 | `10.1039/d2cs00456a` | Chem. Soc. Reviews | 2022 | 沸石/介孔材料 CO2 → 化学品 | ⬇️ |
| 16 | `10.1016/j.jcou.2022.101969` | J. CO2 Utilization | 2022 | 沸石催化 CO2 → C2+ 烃类 | ⬇️ |
| 17 | `10.1016/j.apcatb.2023.122535` | Appl. Catal. B | 2023 | Cr-ZrO2/HZSM-5@SiO2 串联，CO2 → 轻质芳烃，44引用 | ⬇️ |

---

## shared/pdfs 里已有文件（需确认归属）

这些在 `topics/shared/pdfs/` 里，下载时已存在但未分类：

| 文件 | 需要你确认 |
|------|-----------|
| `10.1002_anie.201507585.pdf` | MTA 还是其他？ |
| `10.1016_j.apcatb.2021.120073.pdf` | CO2加氢综述（pilot 用过）→ 建议移到 co2a/pdfs |
| `10.1016_j.chempr.2020.10.019.pdf` | 确认主题 |
| `10.1021_acs.chemrev.5b00197.pdf` | Chem Rev C1转化综述？ |
| `10.1021_acscatal.0c01184.pdf` | ACS Catal MTA？ |
| `10.1039_c3ee41272e.pdf` | Energy Environ Sci，主题？ |

---

## 下载优先顺序建议

```
立即下载（Round 1 缺两篇）：
  → 10.1021/acs.chemrev.9b00723
  → 10.1016/j.chempr.2021.02.024

然后 Round 2（按引用数排）：
  → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

CO2a 方向穿插进来：
  → 13（已有）→ 14 → 15 → 17
```

**总计待下载：14 篇**（Round 1×2 + Round 2×8 + Round 3×4）

---

## 下载路径

1. 优先用 DOI 在 Google Scholar 机构入口搜索
2. 右侧出现 `[PDF]` 链接则直接下载
3. 否则走 Unpaywall：`unpaywall.org/<DOI>`
4. 都没有则走图书馆 ScienceDirect/ACS 机构访问
5. 下载后存入 `topics/mta/pdfs/` 或 `topics/co2a/pdfs/`，文件名格式：`<doi_underscores>.pdf`
