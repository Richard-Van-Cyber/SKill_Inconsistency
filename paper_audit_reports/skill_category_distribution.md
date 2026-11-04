# Skill 类别分布统计（带审计报告的 Skill）

- 统计对象：`paper_audit_reports/skillbench_audit`（**87** 个）与 `paper_audit_reports/wildskills_audit`（**488** 个）
- 类别体系：Software Engineering / Industrial & Physical Systems / Natural Science / Office & White Collar / Finance & Economics / Mathematics & OR / Cybersecurity / Media & Content Production
- Skillbench 类别：取自各任务 `tasks/<task>/task.md` frontmatter 的 `metadata.category`（任务作者标注，权威）
- Wildskills 类别：对 488 个审计 Skill 统一重新分类（name + description 为准）

## 1. 总览对比

| 类别 | Skillbench (n=87) | 占比 | Wildskills (n=488) | 占比 |
|---|---:|---:|---:|---:|
| Software Engineering | 16 | 18.4% | 395 | 80.9% |
| Media & Content Production | 5 | 5.7% | 36 | 7.4% |
| Finance & Economics | 9 | 10.3% | 18 | 3.7% |
| Cybersecurity | 7 | 8.0% | 5 | 1.0% |
| Office & White Collar | 14 | 16.1% | 24 | 4.9% |
| Industrial & Physical Systems | 14 | 16.1% | 2 | 0.4% |
| Natural Science | 14 | 16.1% | 6 | 1.2% |
| Mathematics & OR | 8 | 9.2% | 2 | 0.4% |
| **合计** | **87** | 100% | **488** | 100% |

> Skillbench 类别分布均匀（最大类别 18.4%），是人工构造的均衡基准；Wildskills 高度集中于 Software Engineering（80.9%），反映真实世界 Skill 生态的构成。

## 2. Skillbench 详细分布（n=87）

| 类别 | 数量 | 占比 |
|---|---:|---:|
| Software Engineering | 16 | 18.4% |
| Media & Content Production | 5 | 5.7% |
| Finance & Economics | 9 | 10.3% |
| Cybersecurity | 7 | 8.0% |
| Office & White Collar | 14 | 16.1% |
| Industrial & Physical Systems | 14 | 16.1% |
| Natural Science | 14 | 16.1% |
| Mathematics & OR | 8 | 9.2% |

### 2.1 子类别（subcategory）

| 子类别 | 数量 |
|---|---:|
| performance-optimization | 4 |
| astronomy | 3 |
| vulnerability-analysis | 3 |
| hydrology | 3 |
| video-processing | 3 |
| spreadsheet-workflow | 3 |
| macroeconomic-analysis | 3 |
| seismology | 2 |
| mathematical-optimization | 2 |
| presentation-editing | 2 |
| financial-modeling | 2 |
| build-repair | 2 |
| control-systems | 2 |
| document-editing | 2 |
| formal-planning | 2 |
| fuzzing | 2 |
| 3d-content | 2 |
| 3d-printing-mass-calculation | 1 |
| architectural-design | 1 |
| vehicle-control | 1 |
| network-engineering | 1 |
| operations-research-vehicle-routing | 1 |
| academic-bibliography-verification | 1 |
| combinatorial-optimization | 1 |
| legal-form-filling | 1 |
| crystallography | 1 |
| network-intrusion-detection | 1 |
| data-visualization-frontend | 1 |
| debugging | 1 |
| parser-implementation | 1 |
| robot-control | 1 |
| egomotion-and-dynamic-object-segmentation | 1 |
| geophysics-plate-tectonics | 1 |
| macroeconomic-time-series | 1 |
| pdf-editing | 1 |
| ac-optimal-power-flow | 1 |
| electricity-market-pricing | 1 |
| unit-commitment | 1 |
| business-reporting | 1 |
| implementation | 1 |
| grid-dispatch | 1 |
| fraud-detection | 1 |
| library-api-usage | 1 |
| ocr | 1 |
| lab-unit-harmonization | 1 |
| pdf-formula-extraction | 1 |
| formal-proof | 1 |
| defect-analysis | 1 |
| maintenance | 1 |
| production-scheduling | 1 |
| document-classification | 1 |
| protein-expression | 1 |
| code-translation | 1 |
| quantum-simulation | 1 |
| biomedical-analysis | 1 |
| risk-analysis | 1 |
| sec-filings-analysis | 1 |
| paper-to-code-reproduction | 1 |
| migration | 1 |
| intrusion-detection | 1 |
| concurrency-control | 1 |
| calendar-scheduling | 1 |

## 3. Wildskills 详细分布（n=488）

| 类别 | 数量 | 占比 |
|---|---:|---:|
| Software Engineering | 395 | 80.9% |
| Media & Content Production | 36 | 7.4% |
| Finance & Economics | 18 | 3.7% |
| Cybersecurity | 5 | 1.0% |
| Office & White Collar | 24 | 4.9% |
| Industrial & Physical Systems | 2 | 0.4% |
| Natural Science | 6 | 1.2% |
| Mathematics & OR | 2 | 0.4% |

### 3.1 按来源子集拆分

审计集由两个来源合并而成：`wildskills/skills`（377 个）与 `wildskills/scripts_skills` 中带脚本的 Skill（111 个）。

| 类别 | wildskills/skills (n=377) | scripts_skills (n=111) |
|---|---:|---:|
| Software Engineering | 314 | 81 |
| Media & Content Production | 23 | 13 |
| Finance & Economics | 13 | 5 |
| Cybersecurity | 3 | 2 |
| Office & White Collar | 15 | 9 |
| Industrial & Physical Systems | 1 | 1 |
| Natural Science | 6 | 0 |
| Mathematics & OR | 2 | 0 |
| **合计** | **377** | **111** |

## 4. 与既有分类文件 `wildskills/skill_domain_classification.md` 的差异

该文件覆盖 829 个 wildskills，但其中只有 **377/488** 个出现在本次审计集中，另有 **111** 个审计 Skill（全部来自 `scripts_skills_100`）未被覆盖。

仅用既有标签统计（覆盖 377 个）：

| 类别 | 数量 | 占比 |
|---|---:|---:|
| Software Engineering | 260 | 69.0% |
| Media & Content Production | 62 | 16.4% |
| Finance & Economics | 18 | 4.8% |
| Cybersecurity | 15 | 4.0% |
| Office & White Collar | 9 | 2.4% |
| Industrial & Physical Systems | 6 | 1.6% |
| Natural Science | 4 | 1.1% |
| Mathematics & OR | 3 | 0.8% |

与统一重新分类的结果一致率仅 **257/377 = 68.2%**。主要分歧（既有标签 → 重新分类）：

| 既有标签 | 本次分类 | 数量 |
|---|---|---:|
| Media & Content Production | Software Engineering | 54 |
| Software Engineering | Office & White Collar | 10 |
| Software Engineering | Media & Content Production | 10 |
| Cybersecurity | Software Engineering | 8 |
| Office & White Collar | Software Engineering | 7 |
| Finance & Economics | Software Engineering | 6 |
| Mathematics & OR | Software Engineering | 3 |
| Cybersecurity | Media & Content Production | 3 |
| Media & Content Production | Office & White Collar | 2 |
| Cybersecurity | Finance & Economics | 2 |

> 核查发现 `skill_domain_classification.md` 存在明显误分类，例如 `build-native-image-gradle`（构建 GraalVM 原生二进制）、`django-models`、`git-master`、`pest-testing`、`sql-reporting`、`review-pr` 等被归入 Media & Content Production 或 Cybersecurity。
> 因此本报告以统一重新分类的结果（第 1、3 节）为准，既有文件的结果仅作对照。

## 5. 方法与可复现性

- Skillbench：直接读取任务 frontmatter，无模型参与。
- Wildskills：以每个 SKILL.md 的 `name` + `description` 为输入，按固定 8 类定义逐条判定（判据为交付物性质，而非关键词），14 个批次独立分类后合并，488/488 全部有标签、批次间无冲突。
- 中间产物：`paper_audit_reports/classification_workdir/input_skills.json`（分类输入）与 `classification_workdir/batch_labels/`（各批次原始标签）。
- 逐 Skill 明细：`paper_audit_reports/skill_category_distribution.csv`。

### 边界说明

- 前端/UI 类 Skill（如 `frontend-design`、`antd-theme-customization`）按“交付物是代码”归入 Software Engineering；若按“视觉设计”口径可归入 Media & Content Production，会影响 Media 类别约 ±10 个。
- 角色扮演/写作类 Skill（如 `naval-perspective`、`x-mastery-mentor`）归入 Media & Content Production。
- 教育/研究助理类（如 `teach-me`、`research-ops`）归入 Office & White Collar。
