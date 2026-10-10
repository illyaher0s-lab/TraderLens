# TraderLens 工作区索引

## 主线计划与规则

- [长期产品方向](TraderLens_Northstar.md)：目标、底线与长期边界。
- [产品总主线计划](TraderLens_MAINLINE_PLAN.md)：当前六阶段整体路线。
- [项目执行规则](AGENTS.md)
- [README](README.md)：当前概览与入口。
- [Alpha Gate 001 研究计划](TraderLens_MAINLINE_ALPHA_PLAN.md)：已归档的历史研究与 Gate 协议，不是当前整体路线。
- [Replay-001 历史专题归档](docs/archive/2026-10-07/TraderLens_PRODUCT_MAINLINE_PLAN.md)：用户确认的未来策略目标仍保存在归档正文中。

## 代码与数据入口

- 代码：[backend](backend/)、[contracts](contracts/)、[frontend](frontend/)、[scripts](scripts/)、[strategy_core](strategy_core/)、[tests](tests/)
- 数据与验证材料：[data](data/)、[不复权](不复权/)
- 本索引不指定唯一活动数据库路径；本轮未读取数据库内容或验证数据库真源。

## 已归档历史工作目录

15 项已移入 [.workspace_archive/2026-10-04/phase-a-001/legacy](.workspace_archive/2026-10-04/phase-a-001/legacy/)，共 599 个文件、14,084,579 字节。移动后逐文件 SHA-256 与归档前清单匹配：

- [.task2_isolated](.workspace_archive/2026-10-04/phase-a-001/legacy/.task2_isolated/)
- [.task2_phase_a_snapshots](.workspace_archive/2026-10-04/phase-a-001/legacy/.task2_phase_a_snapshots/)
- [.task2_phase_a_work](.workspace_archive/2026-10-04/phase-a-001/legacy/.task2_phase_a_work/)
- [.task2_phase_b_corrective_snapshots](.workspace_archive/2026-10-04/phase-a-001/legacy/.task2_phase_b_corrective_snapshots/)
- [.task2_phase_b_final_snapshots](.workspace_archive/2026-10-04/phase-a-001/legacy/.task2_phase_b_final_snapshots/)
- [.task2_phase_b_isolated_work](.workspace_archive/2026-10-04/phase-a-001/legacy/.task2_phase_b_isolated_work/)
- [.task2_snapshots](.workspace_archive/2026-10-04/phase-a-001/legacy/.task2_snapshots/)
- [.task2_workspace](.workspace_archive/2026-10-04/phase-a-001/legacy/.task2_workspace/)
- [.task3_b3_package_snapshots](.workspace_archive/2026-10-04/phase-a-001/legacy/.task3_b3_package_snapshots/)
- [.task3_v3_fk_fix_snapshots](.workspace_archive/2026-10-04/phase-a-001/legacy/.task3_v3_fk_fix_snapshots/)
- [.work_corrective4](.workspace_archive/2026-10-04/phase-a-001/legacy/.work_corrective4/)
- [.work_corrective4_test_isolation_parent_001](.workspace_archive/2026-10-04/phase-a-001/legacy/.work_corrective4_test_isolation_parent_001/)
- [.work_final_landing](.workspace_archive/2026-10-04/phase-a-001/legacy/.work_final_landing/)
- [.work_test_convergence](.workspace_archive/2026-10-04/phase-a-001/legacy/.work_test_convergence/)
- [.work_test_isolation](.workspace_archive/2026-10-04/phase-a-001/legacy/.work_test_isolation/)

## 保留目录与恢复入口

- [.task3_b3_package_work](.task3_b3_package_work/) 与 [.task3_v3_fk_fix_work](.task3_v3_fk_fix_work/) 保持原位；其中 data 子目录是 Junction。未读取链接目标内容，记录不构成这两个目录的完整备份。
- [批次完成记录](.workspace_archive/2026-10-04/phase-a-001/manifests/completion.json)
- [归档前清单](.workspace_archive/2026-10-04/phase-a-001/manifests/archive-manifest.json)
- [恢复说明](.workspace_archive/2026-10-04/phase-a-001/manifests/README.md)
- [恢复包索引草案](.workspace_archive/2026-10-04/phase-a-001/recovery/WORKSPACE_INDEX.md)
- [Git 状态、补丁与未跟踪文件副本](.workspace_archive/2026-10-04/phase-a-001/recovery/)

恢复归档目录时，按清单的 archivePath 移回 originalPath，并核对 SHA-256。Git 补丁只能在匹配的干净基线或专用恢复副本中应用，不能直接覆盖当前脏工作区。恢复包不是完整工作区备份。
