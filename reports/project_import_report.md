# Project Website Import Report

## Input

- Input filename: `Project_Website_Import_Final_16.txt`
- Input SHA-256: `8af9dbcbfae6d73bea5cfd12c4623dcd4c1e4414973dddce57a7c7262e1b3a77`
- Schema version: 1
- Source workbook: `Project_Public_Summary_Direct_Edit_18(1).xlsx`
- Source worksheet: `项目公开摘要清单`
- Data source: 卓越工程师推荐申请表项目表，人工复核并按公开摘要型项目档案规范化
- Import date: 2026-07-25

## Counts

- Source projects: 18
- Public website projects: 16
- Excluded private projects: 2
- In progress: 5
- Completed: 11
- National: 1
- Provincial/Ministerial: 7
- Municipal/Departmental: 0
- Group: 4
- Enterprise: 4
- Other: 0

## Normalization

- 6项省级计划名称已从 `project_type` 迁移到 `project_program`，`project_type` 统一为“科研计划项目”。
- 首台（套）项目规范为“示范应用项目”。
- 2项不公开项目被排除，项目状态规范为“在研”/“已完成”。
- 未创建项目详情页。

## Stable ID Mapping

| Display Order | Stable ID | Project Title | Level | Status | Data File |
|---:|---|---|---|---|---|
| 1 | PRJ2020-06 | 便携式水下应急救援关键技术与装备研发 | 国家级 | 已完成 | data/projects/prj2020-06.json |
| 2 | PRJ2026-02 | 工业复杂场景下小样本多模态视觉检测理论方法和关键技术研究及具身智能应用示范 | 省部级 | 在研 | data/projects/prj2026-02.json |
| 3 | PRJ2026-01 | 海上风电平台智能巡检与遥操作检修机器人系统关键技术研究 | 省部级 | 在研 | data/projects/prj2026-01.json |
| 4 | PRJ2025-01 | 面向复杂场景的高端工业运维软件 | 省部级 | 在研 | data/projects/prj2025-01.json |
| 5 | PRJ2023-02 | 复杂地形特种作业机器人研发与应用 | 省部级 | 已完成 | data/projects/prj2023-02.json |
| 6 | PRJ2023-01 | 基于动态环境信息理解的智能服务机器人研发及应用 | 省部级 | 已完成 | data/projects/prj2023-01.json |
| 7 | PRJ2022-01 | 翻车机摘复钩智能化研究 | 省部级 | 已完成 | data/projects/prj2022-01.json |
| 8 | PRJ2021-01 | 高精度复合机器人整机研发及应用 | 省部级 | 已完成 | data/projects/prj2021-01.json |
| 9 | PRJ2020-04 | 物联网终端安全认证与动态接入管控技术研究与应用 | 集团级 | 已完成 | data/projects/prj2020-04.json |
| 10 | PRJ2020-03 | 物联网设备OPC-UA通信网络架构、技术与应用 | 集团级 | 已完成 | data/projects/prj2020-03.json |
| 11 | PRJ2020-02 | 能源领域机器人系统技术研究与应用 | 集团级 | 已完成 | data/projects/prj2020-02.json |
| 12 | PRJ2020-01 | 面向电厂环境的可见光通信定位一体化系统研究及应用 | 集团级 | 已完成 | data/projects/prj2020-01.json |
| 13 | PRJ2025-03 | 基于生成模型和规则引导的工业负样本生成技术研究与应用 | 企业级 | 在研 | data/projects/prj2025-03.json |
| 14 | PRJ2025-02 | 机器人多传感器感知装置标准化设计与研制 | 企业级 | 在研 | data/projects/prj2025-02.json |
| 15 | PRJ2023-03 | 基于机器人技术的煤堆深层测温智能装备研究与开发 | 企业级 | 已完成 | data/projects/prj2023-03.json |
| 16 | PRJ2022-02 | 立式中速磨煤机顶部巡检预警智能化研究 | 企业级 | 已完成 | data/projects/prj2022-02.json |

## Excluded Records

- 排除数量：2
- 排除原因：人工复核标记为不公开

## Sorting Verification

- Primary: `level_rank` descending
- Secondary: `start_date` descending
- Tertiary: `stable_id` descending
- Final order: PRJ2020-06, PRJ2026-02, PRJ2026-01, PRJ2025-01, PRJ2023-02, PRJ2023-01, PRJ2022-01, PRJ2021-01, PRJ2020-04, PRJ2020-03, PRJ2020-02, PRJ2020-01, PRJ2025-03, PRJ2025-02, PRJ2023-03, PRJ2022-02

## Duplicate Verification

- Duplicate Stable IDs: 0
- Duplicate titles: 0
- Duplicate output filenames: 0

## Public Data Boundaries

- Project amounts published: 0
- Project numbers published: 0
- Contract information published: 0
- Private projects published: 0
- Detail pages created: 0
- External data inferred: 0

## Changed Files

- `data/projects/prj2020-06.json`
- `data/projects/prj2026-02.json`
- `data/projects/prj2026-01.json`
- `data/projects/prj2025-01.json`
- `data/projects/prj2023-02.json`
- `data/projects/prj2023-01.json`
- `data/projects/prj2022-01.json`
- `data/projects/prj2021-01.json`
- `data/projects/prj2020-04.json`
- `data/projects/prj2020-03.json`
- `data/projects/prj2020-02.json`
- `data/projects/prj2020-01.json`
- `data/projects/prj2025-03.json`
- `data/projects/prj2025-02.json`
- `data/projects/prj2023-03.json`
- `data/projects/prj2022-02.json`
- `content/projects/_index.md`
- `layouts/_partials/hbx/blocks/project-feed/block.html`
- `layouts/_partials/hbx/blocks/project-feed/styles.html`
- `assets/js/project-filter.js`
- `scripts/import_projects.py`
- `reports/project_import_report.md`

## Validation Commands

- `python -m py_compile scripts/import_projects.py` — passed
- `python scripts/import_projects.py --input Project_Website_Import_Final_16.txt --data-dir data/projects --report reports/project_import_report.md` — passed
- `python scripts/import_projects.py --input Project_Website_Import_Final_16.txt --data-dir data/projects --report reports/project_import_report.md --apply` — passed
- `python scripts/import_projects.py --input Project_Website_Import_Final_16.txt --data-dir data/projects --report reports/project_import_report.md --check` — passed
- `git diff --check` — passed
- `hugo version` — unavailable in the local environment; no build or dependency changes were attempted

## Idempotency

- Second `--apply`: `files changed: 0`

## Temporary Input Cleanup

- `Project_Website_Import_Final_16.txt`已删除。
- 最终PR差异不包含输入TXT。
