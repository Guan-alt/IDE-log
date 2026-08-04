# 测试任务分组统计 Spec

## Why
当前所有OTA记录混在一起统计，无法按"一次测试任务"分组查看。用户需要像管理项目任务一样，手动创建测试任务（命名、描述），在任务下进行OTA测试，所有OTA记录归属到该任务，统计时按任务筛选。

## What Changes
- 新增 TestTask 模型（id, user_id, name, description, status, created_at, ended_at），用户手动创建
- OtaRecord 模型新增 `task_id` 字段，关联到 TestTask
- 新增测试任务管理页面 `/tasks`，支持创建、查看、结束任务
- 监控页面新增"当前任务"选择，发起OTA时将记录关联到选中的任务
- 统计仪表盘新增"测试任务"下拉筛选，选择后所有图表只统计该任务下的记录
- 后端统计接口支持 `task_id` 查询参数过滤
- 历史记录页面支持按任务筛选
- 侧边栏新增"测试任务"导航项

## Impact
- Affected code: `app/models/models.py` — 新增 TestTask 模型，OtaRecord 新增 task_id
- Affected code: `app/api/ota.py` — 发起OTA时从请求中读取 task_id 写入 OtaRecord
- Affected code: `app/api/stats.py` — 所有统计接口支持 task_id 过滤
- Affected code: `app/api/records.py` — 列表支持 task_id 过滤
- Affected code: `app/api/tasks.py` — **新增** 测试任务 CRUD 接口
- Affected code: `app/templates/tasks.html` — **新增** 测试任务管理页面
- Affected code: `app/templates/stats.html` — 新增任务下拉筛选
- Affected code: `app/templates/monitor.html` — 新增当前任务选择
- Affected code: `app/templates/records.html` — 新增任务筛选
- Affected code: `app/templates/base.html` — 侧边栏新增"测试任务"

## ADDED Requirements
### Requirement: 测试任务管理
用户可手动创建测试任务（名称+描述），任务状态为"进行中"。任务可被结束（状态变为"已完成"）。每个任务显示关联的OTA记录数。

#### Scenario: 创建测试任务
- **WHEN** 用户在测试任务页面点击"新建任务"，填写名称和描述
- **THEN** 创建一条 TestTask 记录，状态为"进行中"
- **AND** 该任务出现在任务列表中

#### Scenario: 结束测试任务
- **WHEN** 用户点击任务的"结束"按钮
- **THEN** 任务状态变为"已完成"，记录结束时间

### Requirement: OTA关联任务
监控页面新增"当前任务"下拉框（显示所有进行中的任务）。发起OTA（单次/循环）时，选中的 task_id 随请求发送，OtaRecord 写入 task_id。

#### Scenario: 选择任务后发起OTA
- **WHEN** 用户选择某个进行中的任务并发起OTA
- **THEN** OtaRecord 关联到该 task_id
- **AND** 统计和记录页面可按此任务筛选

#### Scenario: 不选择任务发起OTA
- **WHEN** 用户未选择任务（或选择"无任务"）发起OTA
- **THEN** OtaRecord 的 task_id 为空

### Requirement: 统计按任务筛选
统计仪表盘页面新增"测试任务"下拉框，列出当前用户的所有测试任务。选择后所有统计只统计该任务下的记录。不选择时统计全部。

### Requirement: 历史记录按任务筛选
历史记录页面新增任务筛选下拉框，选择后只显示该任务下的记录。
