# OTA 轮询调优与进度条自动恢复修复 Spec

## Why
1. OTA 进度轮询当前固定 5 秒一次，每次请求都穿透到外部 OTA 服务 `/ota/record/page`，后台压力大；用户希望降低拉取频率。
2. 最近发现只要进入 OTA 页面，进度条就会自动"跑起来"——根因是 `restoreOtaState()` 盲信 localStorage 中的 `ota_active` / `ota_cycle_active` 残留标记，未先向后端确认 OTA 是否仍在运行就进入运行态 UI 并启动轮询；进度条由 CSS `transition: width 0.5s ease` 驱动，从 0% 跳到后端返回值时视觉上就是"自动跑"。

## What Changes
- 将 OTA 进度轮询间隔由 5000ms 调整为 8000ms（提取为命名常量 `OTA_PROGRESS_POLL_MS`），同步将循环状态轮询间隔一并调到 8000ms，在降低后台压力的同时保留相对及时的进度反馈。
- 修复 `restoreOtaState()` 的盲信路径：进入 OTA 页面恢复状态时，统一通过 `checkDeviceOtaState(savedSn)` 先向后端 `/api/ota/check-status/<sn>` 确认 OTA 是否真的在运行，再决定是否进入运行态 UI 与启动轮询；移除单次模式下"不验证直接 enterRunningUI + startProgressPolling"的旁路逻辑。
- 修复 `doRestoreOtaProgress()` 循环模式 `.catch()` 兜底分支：API 失败时不再无条件进入运行态并启动轮询，改为保守地进入空闲态或保持当前 UI，避免错误状态下进度条动画。

## Impact
- 受影响代码：
  - `app/templates/monitor.html` — `startProgressPolling`、`startCycleStatusPolling`、`restoreOtaState`、`doRestoreOtaProgress`
- 受影响能力：
  - OTA 进度轮询频率
  - OTA 页面状态恢复
- 不涉及后端接口契约变更，仅前端行为调整。
- **BREAKING**：无（行为兼容：仍在运行的 OTA 仍会恢复显示，只是多了后端确认步骤）。

## ADDED Requirements

### Requirement: OTA 轮询间隔配置
系统 SHALL 将 OTA 进度轮询间隔与循环状态轮询间隔统一为 8000ms，并以命名常量形式集中定义，避免散落的魔法数字。

#### Scenario: 降低后台请求压力
- **WHEN** 用户在 OTA 页面查看正在进行的单次或循环 OTA 升级
- **THEN** 前端每 8 秒发起一次 `/api/ota/progress/<sn>` 请求（循环模式额外每 8 秒发一次 `/api/ota/cycle-status/<sn>`），而非每 5 秒一次

#### Scenario: 轮询间隔可统一调整
- **WHEN** 后续需要再次调整轮询频率
- **THEN** 只需修改一处命名常量 `OTA_PROGRESS_POLL_MS`（默认 8000），所有 OTA 进度/循环状态轮询点同步生效

## MODIFIED Requirements

### Requirement: OTA 页面状态恢复（原 `restoreOtaState`）
页面加载或从其他页面切回 OTA 页面时，系统 SHALL 先通过后端 `/api/ota/check-status/<sn>` 验证 localStorage 中保存的 SN 是否真的有正在进行的 OTA，再决定是否进入运行态 UI 与启动进度轮询；不得仅凭 localStorage 中的 `ota_active` / `ota_cycle_active` 标记直接进入运行态并启动轮询。

#### Scenario: 残留标记但 OTA 实际已结束
- **WHEN** 用户进入 OTA 页面，且 localStorage 中 `ota_active='1'`，但后端 `/api/ota/check-status/<sn>` 返回 `active=false`
- **THEN** 系统进入空闲态 UI（显示"暂无升级任务"、发起按钮可见、停止按钮隐藏），不启动进度轮询，进度条不显示、不动画
- **AND** 系统清理 localStorage 中残留的 `ota_active` / `ota_cycle_active` / `ota_sn` 标记

#### Scenario: 残留标记且 OTA 仍在运行
- **WHEN** 用户进入 OTA 页面，且 localStorage 中存在 `ota_active` 或 `ota_cycle_active`，且后端确认 OTA 仍在运行
- **THEN** 系统进入运行态 UI，启动进度轮询（8 秒间隔），进度条按后端返回值更新

#### Scenario: 循环状态查询接口失败
- **WHEN** `doRestoreOtaProgress` 在循环模式下调用 `/api/ota/cycle-status/<sn>` 失败（网络错误等）
- **THEN** 系统不再无条件进入运行态 UI 与启动轮询，改为保持当前 UI 不变或退回空闲态，避免在未知状态下让进度条动画误启动

#### Scenario: 无任何 localStorage 标记
- **WHEN** 用户进入 OTA 页面，localStorage 中无 `ota_sn` 或无 `ota_active` / `ota_cycle_active`
- **THEN** 系统行为保持现状（进入空闲态或走 `checkDeviceOtaState` 主动查询后端），不自动启动进度条

## REMOVED Requirements
无
