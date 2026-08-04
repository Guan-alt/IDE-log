# OTA 升级环境管理 Spec

## Why
当前系统仅支持两个硬编码的 OTA 环境（线下 `ota_url`/`token` 与线上 `ota_url_online`/`token_online`），用户无法按需增减环境。测试中常出现预发布、灰度、自建测试服务器等多个目标环境，需要让用户自行添加、编辑、删除 OTA 升级环境。

## What Changes
- 新增 `OtaEnvironment` 模型，存储用户自定义的 OTA 环境（name + ota_url + token + sort_order）
- 新增 `/api/ota-envs` CRUD 接口（GET 列表 / POST 新建 / PUT 编辑 / DELETE 删除）
- 数据迁移：首次启动时，将现有 `Setting.ota_url`/`token` 迁移为"线下"环境；`Setting.ota_url_online`/`token_online` 非空时迁移为"线上"环境
- 设置页面用"OTA 环境管理"列表替代原有 4 个硬编码输入框，支持增删改
- 实时监控页面 OTA 环境下拉从 `/api/ota-envs` 动态加载，按 `sort_order` 排序
- OTA 发起请求参数从 `ota_type=offline|online` 改为 `env_id=<integer>`
- `get_ota_client` 改为按 `env_id` 查询 `OtaEnvironment`，未找到时回退到 `Setting.ota_url`/`token`
- `Setting` 模型保留 `ota_url`/`token`/`ota_url_online`/`token_online` 字段作为迁移期回退，不再作为主数据源 **BREAKING**（前端不再使用，但字段保留）

## Impact
- Affected code: `app/models/models.py` — 新增 `OtaEnvironment` 模型
- Affected code: `app/__init__.py` — 注册新模型 + 迁移种子数据 + 注册新蓝图 + 页面路由（无）
- Affected code: `app/api/ota_envs.py` — **新建** CRUD 蓝图
- Affected code: `app/api/ota.py` — `get_ota_client` 改用 `env_id`；`start_ota` / `start_ota_cycle` / `_start_ota_leg` / `_continue_cycle` 接收 `env_id` 替代 `ota_type`
- Affected code: `app/api/settings.py` — `to_dict` 增加返回 `ota_envs` 列表（方便前端一次性加载）
- Affected code: `app/templates/settings.html` — 移除 4 个 OTA URL/Token 输入框，新增"OTA 环境管理"卡片（列表 + 新建/编辑/删除按钮 + 弹窗表单）
- Affected code: `app/templates/monitor.html` — OTA 环境下拉从硬编码改为动态加载；`submitSingleOta` / `submitCycleOta` 提交 `env_id`；`localStorage` 持久化改为 `env_id`
- Backward compat: 旧 `ota_type` 字段在 `Setting` 中保留作迁移回退；cycling_tasks 字典 `ota_type` 键改为 `env_id`，不读取旧值（重启即丢失，无需迁移）

## ADDED Requirements
### Requirement: OTA 环境模型
系统提供 `OtaEnvironment` 模型存储用户自定义的 OTA 环境，字段：`id` / `user_id` / `name` / `ota_url` / `token` / `sort_order` / `created_at` / `updated_at`。同一用户下 `name` 不重复。

#### Scenario: 字段约束
- **WHEN** 用户尝试创建同名环境
- **THEN** 返回 400 错误，提示名称重复

### Requirement: OTA 环境 CRUD 接口
系统提供以下 REST 接口（均需登录，仅能操作当前用户的环境）：
- `GET /api/ota-envs` — 返回当前用户所有环境，按 `sort_order` 升序
- `POST /api/ota-envs` — 新建环境，必填 `name` / `ota_url` / `token`，可选 `sort_order`
- `PUT /api/ota-envs/<id>` — 更新环境字段
- `DELETE /api/ota-envs/<id>` — 删除环境（无需校验关联记录，因 OTA 记录不存 env_id）

#### Scenario: 创建环境
- **WHEN** 用户提交 `{name: "预发布", ota_url: "https://pre.lockin.com", token: "xxx"}`
- **THEN** 创建成功，返回新环境对象
- **AND** 后续 OTA 请求可使用该环境的 id

#### Scenario: 跨用户隔离
- **WHEN** 用户 A 请求更新/删除用户 B 的环境
- **THEN** 返回 404

### Requirement: 数据迁移与种子
首次启动检测到当前用户无任何 `OtaEnvironment` 时，根据现有 `Setting` 自动种子：
- 用 `Setting.ota_url` + `Setting.token` 创建一个名为"线下"的环境，`sort_order=0`
- 若 `Setting.ota_url_online` 非空，再创建一个名为"线上"的环境，`sort_order=1`

#### Scenario: 老用户首次升级
- **WHEN** 用户已有 `Setting.ota_url` 但 `OtaEnvironment` 表为空时启动应用
- **THEN** 自动创建"线下"环境（来自 `Setting.ota_url`/`token`）
- **AND** 若 `Setting.ota_url_online` 非空，创建"线上"环境
- **AND** 迁移只执行一次，后续不重复

### Requirement: OTA 发起使用 env_id
监控页面发起 OTA 时提交 `env_id`（整数，指向 `OtaEnvironment.id`）。后端 `get_ota_client(env_id, user_id)` 查询对应环境的 `ota_url`/`token` 构造 `OtaClient`；未传或查不到时回退到当前用户的第一个环境或 `Setting.ota_url`/`token` 默认值。

#### Scenario: 使用自定义环境发起 OTA
- **WHEN** 用户在监控页选择"预发布"环境并发起 OTA
- **THEN** 后端使用该环境的 url+token 创建 OtaClient
- **AND** OTA 请求发往预发布服务器

#### Scenario: 持久化环境选择
- **WHEN** 用户选择某环境后切页再返回监控页
- **THEN** 下拉仍保持上次选择的环境

### Requirement: 设置页面环境管理 UI
设置页面"OTA 环境管理"卡片展示当前用户所有环境的列表，每行显示名称、URL（脱敏）、Token（脱敏）、编辑、删除按钮；顶部"新增环境"按钮打开弹窗表单（名称、URL、Token、排序）。

#### Scenario: 编辑环境
- **WHEN** 用户点击某环境的"编辑"按钮修改 URL 后保存
- **THEN** 立即生效，下次 OTA 请求使用新 URL

## MODIFIED Requirements
### Requirement: 实时监控页面 OTA 环境切换
原硬编码"线下/线上"二选一下拉改为从 `/api/ota-envs` 动态加载，按 `sort_order` 排序显示。切换后 `localStorage` 持久化 `env_id`。

### Requirement: get_ota_client 签名
原 `get_ota_client(ota_type='offline', user_id=None)` 改为 `get_ota_client(env_id=None, user_id=None)`。`ota_type` 参数在 API 层完全移除，调用方统一传 `env_id`。

## REMOVED Requirements
### Requirement: Setting 模型的 ota_url_online/token_online 作为主数据源
**Reason**: 已被 `OtaEnvironment` 替代，多环境由用户自行管理
**Migration**: 字段保留在 `Setting` 表中（不删列），仅作为迁移种子数据来源；前端不再读写这两个字段；新逻辑仅依赖 `OtaEnvironment` 表
