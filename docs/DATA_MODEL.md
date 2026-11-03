# Phase 1 数据模型

## 存储边界

正式数据默认存放于 `%LOCALAPPDATA%\LifeOS\data\` 下的 SQLite 数据库，具体路径由 Settings 提供并允许覆盖。测试使用临时目录和独立数据库。数据库模块负责 Engine、Session、连接检查与 Repository；UI 不直接访问数据库。

## 基础设置

Phase 1 的 `app_settings` 表支持设置的插入、查询和修改，并在进程重启后保留。实现和初始 Alembic 迁移已合入，验证结果见 `docs/INTEGRATION.md`。

结构演进通过 Alembic 迁移管理。迁移须在独立临时数据库上验证，测试不得修改正式数据库。Phase 2 的任务数据模型和验收要求见 `docs/PHASE2_TASKS.md`。
