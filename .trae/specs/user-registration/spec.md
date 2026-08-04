# 用户注册功能 Spec

## Why
当前系统只有登录功能，新用户无法自行注册账号，只能由管理员手动操作数据库创建。需要在登录页面提供注册入口，让新用户可以自助注册。

## What Changes
- 后端新增 `/api/auth/register` POST 接口，接收用户名+密码+显示名，创建普通用户
- 登录页面新增"注册"链接，点击切换到注册表单
- 注册表单包含用户名、密码、确认密码、显示名（可选），提交后自动登录跳转首页
- 用户名唯一性校验，密码长度校验（至少6位）

## Impact
- Affected code: `app/api/auth.py` — 新增 register 接口
- Affected code: `app/templates/login.html` — 新增注册表单和切换逻辑

## ADDED Requirements
### Requirement: 用户注册
用户可在登录页面点击"注册"切换到注册表单，填写用户名、密码、确认密码后提交注册。注册成功后自动登录并跳转首页。

#### Scenario: 注册成功
- **WHEN** 用户填写用户名（不重复）、密码（至少6位）、确认密码一致，点击注册
- **THEN** 后端创建普通用户（is_admin=False），写入 session 自动登录
- **AND** 跳转到首页

#### Scenario: 用户名已存在
- **WHEN** 用户填写已存在的用户名
- **THEN** 提示"用户名已存在"

#### Scenario: 密码过短
- **WHEN** 用户填写的密码少于6位
- **THEN** 提示"密码至少6个字符"

#### Scenario: 两次密码不一致
- **WHEN** 用户填写的密码和确认密码不一致
- **THEN** 提示"两次输入的密码不一致"
