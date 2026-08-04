# Tasks

- [ ] Task 1: 新增 TestTask 模型与数据库迁移
  - [ ] SubTask 1.1: 在 `models.py` 新增 TestTask 模型（id, user_id, name, description, status, created_at, ended_at），含 `to_dict()` 返回关联OTA记录数
  - [ ] SubTask 1.2: OtaRecord 模型新增 `task_id` 字段（可空），`to_dict()` 返回
  - [ ] SubTask 1.3: 数据库迁移（CREATE TABLE test_tasks + ALTER TABLE ota_records ADD COLUMN task_id）
  - [ ] SubTask 1.4: 在 `__init__.py` import TestTask 并注册 tasks 蓝图和页面路由

- [ ] Task 2: 新增测试任务 CRUD API
  - [ ] SubTask 2.1: 新建 `app/api/tasks.py`，实现 GET `/api/tasks`（列表，按 user_id 过滤）、POST `/api/tasks`（创建）、POST `/api/tasks/<id>/end`（结束任务）
  - [ ] SubTask 2.2: 在 `__init__.py` 注册 tasks 蓝图

- [ ] Task 3: OTA发起逻辑关联任务
  - [ ] SubTask 3.1: `ota.py` 的 `start_ota` 从请求中读取 `task_id`，写入 OtaRecord
  - [ ] SubTask 3.2: `ota.py` 的 `_start_ota_leg` 接收 task_id 参数，写入 OtaRecord（循环OTA用）
  - [ ] SubTask 3.3: `start_ota_cycle` 从请求中读取 task_id，存入 cycling_tasks，传给 _start_ota_leg

- [ ] Task 4: 统计接口支持 task_id 过滤
  - [ ] SubTask 4.1: `stats.py` 所有接口新增 task_id 查询参数，有值时加 filter
  - [ ] SubTask 4.2: `records.py` 列表接口支持 task_id 查询参数过滤

- [ ] Task 5: 前端测试任务管理页面
  - [ ] SubTask 5.1: 新建 `tasks.html` 任务管理页面（任务列表卡片、新建任务弹窗、结束按钮）
  - [ ] SubTask 5.2: `base.html` 侧边栏新增"测试任务"导航项

- [ ] Task 6: 前端监控/统计/记录页面新增任务筛选
  - [ ] SubTask 6.1: `monitor.html` 新增"当前任务"下拉框（加载进行中的任务），发起OTA时携带 task_id
  - [ ] SubTask 6.2: `stats.html` 新增任务下拉框，选择后所有图表按 task_id 刷新
  - [ ] SubTask 6.3: `records.html` 新增任务下拉框，选择后按 task_id 过滤记录

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3 依赖 Task 1
- Task 4 依赖 Task 1
- Task 5 依赖 Task 2
- Task 6 依赖 Task 2 和 Task 3 和 Task 4
