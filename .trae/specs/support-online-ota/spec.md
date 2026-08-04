# 支持线上OTA Spec

## Why
当前系统仅支持单一OTA服务器环境（通过 `ota_url` + `token` 配置），用户需要在测试环境（线下）和生产环境（线上）之间灵活切换发起OTA，以验证不同环境下的升级表现。

## What Changes
- Setting 模型新增 `ota_url_online` 和 `token_online` 字段，存储线上环境配置
- 设置页面新增线上OTA URL和Token输入框
- 实时监控页面新增"OTA环境"切换（线下/线上），切换后所有OTA请求使用对应环境的 url+token
- 后端 `get_ota_client` 支持根据 `ota_type` 参数返回不同环境的 OtaClient
- OTA发起和进度查询接口新增 `ota_type` 参数（`offline`/`online`）

## Impact
- Affected code: `app/models/models.py` — Setting 模型新增字段
- Affected code: `app/services/ota_client.py` — 无需修改，OtaClient 已支持参数化
- Affected code: `app/api/ota.py` — `get_ota_client` 支持环境参数，start/start-cycle/progress 接口传递环境
- Affected code: `app/templates/settings.html` — 新增线上环境配置输入框
- Affected code: `app/templates/monitor.html` — 新增环境切换按钮，localStorage 持久化选择
- Affected code: `app/api/settings.py` — 配置读写接口支持新字段

## ADDED Requirements
### Requirement: 线上OTA环境配置
系统支持配置两套OTA环境：线下（测试）和线上（生产），各有独立的 `ota_url` 和 `token`。设置页面提供两套配置的输入框。

#### Scenario: 配置线上环境
- **WHEN** 用户在设置页面填写线上OTA URL和Token并保存
- **THEN** 配置持久化到数据库
- **AND** 可在监控页面切换到线上环境发起OTA

### Requirement: OTA环境切换
实时监控页面新增"线下OTA"/"线上OTA"切换按钮。选择的环境持久化到 localStorage，切页返回不丢失。发起OTA时使用当前选中环境的 url+token。

#### Scenario: 切换到线上环境发起OTA
- **WHEN** 用户在监控页面选择"线上OTA"并发起升级
- **THEN** 后端使用 `ota_url_online` + `token_online` 创建 OtaClient
- **AND** OTA请求发往线上服务器

#### Scenario: 切页返回保持环境选择
- **WHEN** 用户选择线上OTA后切到其他页面再返回
- **THEN** 环境选择仍为线上OTA，不会重置为线下
