# 多用户支持 Spec

## Why
当前平台所有数据（设备、OTA记录、日志配置、系统设置）全局共享，无法区分不同用户。需要支持多用户登录，每个用户拥有独立的数据空间，实现完全的数据隔离。

## What Changes
- 新增 User 模型（id, username, password_hash, display_name, created_at）
- Device、OtaRecord、LogConfig、Setting 模型新增 user_id 外键，实现数据隔离
- 新增登录/注销 API（`/api/auth/login`、`/api/auth/logout`、`/api/auth/current`）
- 新增登录页面 `/login`
- 所有 API 请求需认证，后端通过 session 获取当前 user_id 过滤数据
- 内存中的 `cycling_tasks` 和 `jlink_loggers` 按 user_id 隔离
- 前端所有页面增加登录状态检查，未登录跳转登录页
- 新增用户管理功能（仅管理员可创建用户）

## Impact
- Affected code: `app/models/models.py` — 新增 User 模型，所有模型新增 user_id
- Affected code: `app/__init__.py` — 注册 auth 蓝图，初始化默认管理员
- Affected code: `app/api/auth.py` — **新增** 登录/注销/当前用户接口
- Affected code: `app/api/devices.py` — 按 user_id 过滤
- Affected code: `app/api/ota.py` — cycling_tasks 按 user_id 隔离，接口按 user_id 过滤
- Affected code: `app/api/records.py` — 按 user_id 过滤
- Affected code: `app/api/settings.py` — Setting 按 user_id 隔离
- Affected code: `app/api/serial.py` — jlink_loggers 按 user_id 隔离
- Affected code: `app/api/stats.py` — 按 user_id 过滤
- Affected code: `app/templates/login.html` — **新增** 登录页面
- Affected code: 所有模板 — 增加登录检查和导航栏用户名显示
- **BREAKING**: 现有数据需要关联到默认管理员用户（数据迁移）

## ADDED Requirements
### Requirement: 用户模型与认证
系统支持用户注册和登录，使用用户名+密码认证，密码以 hash 形式存储。session 管理登录状态。

#### Scenario: 用户登录
- **WHEN** 用户输入正确的用户名和密码并点击登录
- **THEN** 后端验证通过，session 中记录 user_id
- **AND** 跳转到首页

#### Scenario: 登录失败
- **WHEN** 用户输入错误的用户名或密码
- **THEN** 提示"用户名或密码错误"

#### Scenario: 未登录访问
- **WHEN** 未登录用户访问任何页面
- **THEN** 跳转到登录页

### Requirement: 数据隔离
所有业务数据（设备、OTA记录、日志配置、设置）按 user_id 隔离。用户只能看到自己的数据。内存中的 OTA 循环任务和日志采集器也按用户隔离。

#### Scenario: 用户A的设备不可见
- **WHEN** 用户A登录后查看设备列表
- **THEN** 只显示用户A的设备，不显示用户B的设备

#### Scenario: OTA任务隔离
- **WHEN** 用户A和用户B同时对不同设备发起循环OTA
- **THEN** 各自的循环任务互不干扰

### Requirement: 默认管理员
系统首次启动时自动创建默认管理员账号（admin/admin），并迁移现有数据关联到管理员。

#### Scenario: 首次启动
- **WHEN** 数据库中无用户记录
- **THEN** 自动创建 admin 用户
- **AND** 现有 Device/OtaRecord/LogConfig/Setting 关联到 admin

## MODIFIED Requirements
### Requirement: 设备管理
设备列表、添加、删除等操作均按当前登录用户的 user_id 过滤。

### Requirement: OTA升级
OTA 发起、进度查询、循环OTA任务均按 user_id 隔离。cycling_tasks 改为嵌套字典 `{user_id: {sn: task}}`。

### Requirement: 日志采集
日志采集器（jlink_loggers/serial_loggers）按 user_id 隔离。

### Requirement: 系统设置
Setting 改为每用户一条记录，各用户独立配置 OTA URL、Token、AI Key 等。
