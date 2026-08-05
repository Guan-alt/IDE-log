# 移除用户登录功能 Spec

## Why
当前系统每次访问都需要登录（认证检查、跳转登录页、多用户隔离），用户希望去掉登录交互，打开即用，所有数据全局共享。采用"保留 user_id 字段、后台固定归属默认用户"方案，改动小、数据不变。

## What Changes
- **BREAKING**: 移除登录/注册/退出交互（登录页、base.html 认证检查与用户面板、退出按钮）
- `login_required` 装饰器改为直接放行（保留装饰器本身，避免改动 9 个 API 文件的 48 处调用点）
- `get_current_user_id()` 固定返回默认用户（admin）ID；`get_current_user()` 返回默认用户对象
- `/api/auth/current` 固定返回 `{logged_in: true}` + 默认用户信息（兼容旧前端）
- 移除 `/api/auth/login`（GET 登录页 + POST 登录）、`/api/auth/logout`、`/api/auth/register` 路由
- `templates/login.html` 删除
- `User` 表保留（作为数据归属），admin 初始化逻辑保留

## Impact
- Affected specs: multi-user-support（多用户隔离被移除）、user-registration（注册功能被移除）
- Affected code:
  - `app/utils/decorators.py` — login_required 放行、get_current_user_id/get_current_user 固定默认用户
  - `app/api/auth.py` — 精简为仅保留 /api/auth/current
  - `app/templates/base.html` — 移除认证脚本、用户面板、退出按钮
  - `app/templates/login.html` — 删除
  - `app/__init__.py` — 保留 admin 初始化与 auth_bp 注册（仅 /current）
  - 所有 API 文件（devices/ota/records/stats/settings/serial/ai/tasks/ota_envs）— 无需改动，通过 decorators 自动生效

## ADDED Requirements
### Requirement: 全局单用户访问
系统 SHALL 使所有 API 与页面在无登录会话时均可直接访问，所有数据查询与写入固定归属默认用户（admin），不再按会话用户隔离。

#### Scenario: 无会话访问
- **WHEN** 用户未登录直接访问任意页面（/devices、/monitor、/records、/stats、/settings、/tasks）或任意 API
- **THEN** 请求正常返回（不再 401，不跳转登录页）

## MODIFIED Requirements
### Requirement: 认证装饰器
系统 SHALL 保留 `login_required` 装饰器但使其直接放行；`get_current_user_id` SHALL 固定返回默认用户 ID，`get_current_user` SHALL 返回默认用户对象。

#### Scenario: 接口调用
- **WHEN** 任意 API 接口被调用（无论是否登录）
- **THEN** `get_current_user_id()` 均返回默认用户（admin）的 ID，数据按该用户读写

### Requirement: 认证状态接口
系统 SHALL 保留 `/api/auth/current`，始终返回已登录状态与默认用户信息。

#### Scenario: 前端状态查询
- **WHEN** 前端请求 `/api/auth/current`
- **THEN** 返回 `{logged_in: true, user: <默认用户>}`，状态码 200

## REMOVED Requirements
### Requirement: 登录交互
**Reason**: 用户要求砍掉登录功能，系统改为打开即用。
**Migration**: 无需登录，直接访问各页面；原有登录页跳转逻辑全部移除。

### Requirement: 注册与退出
**Reason**: 登录体系移除，注册/退出随之移除。
**Migration**: 删除 `/api/auth/register`、`/api/auth/logout` 路由及前端退出按钮。

### Requirement: 多用户数据隔离
**Reason**: 登录移除后无多用户概念，所有数据全局共享。
**Migration**: user_id 字段保留但不再隔离，全部数据归属默认用户（admin）。
