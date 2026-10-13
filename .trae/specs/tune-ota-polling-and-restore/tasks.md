# Tasks

- [x] Task 1: 引入 OTA 轮询间隔常量并替换硬编码值
  - [x] SubTask 1.1: 在 `app/templates/monitor.html` 顶部 OTA 相关变量声明区（`progressTimer` 声明附近）新增常量 `var OTA_PROGRESS_POLL_MS = 8000;`
  - [x] SubTask 1.2: 将 `startProgressPolling` 中的 `setInterval(..., 5000)` 改为 `setInterval(..., OTA_PROGRESS_POLL_MS)`
  - [x] SubTask 1.3: 将 `startCycleStatusPolling` 中的 `setInterval(..., 5000)` 改为 `setInterval(..., OTA_PROGRESS_POLL_MS)`

- [x] Task 2: 修复 `restoreOtaState` 盲信 localStorage 标记的问题
  - [x] SubTask 2.1: 修改 `restoreOtaState()`，不再根据 `ota_active` / `ota_cycle_active` 直接调用 `doRestoreOtaProgress`，而是统一走 `checkDeviceOtaState(savedSn)` 由后端确认
  - [x] SubTask 2.2: `checkDeviceOtaState` 内部已有 `data.active` 分支处理；确认其循环模式分支调用 `doRestoreOtaProgress(sn, true)` 时传入的 `isCycleActive` 来源是后端返回的 `data.mode === 'cycle'`，而非 localStorage 标记
  - [x] SubTask 2.3: 保留 `switchOtaMode(actualMode)` 的 UI 模式恢复逻辑（按 localStorage 中的模式还原 tab，但进度恢复必须等后端确认）—— 由 `restoreOtaMode()`（页面初始化时调用）+ `doRestoreOtaProgress` 内的 `switchOtaMode` 共同覆盖

- [x] SubTask 2.4: 修复 `doRestoreOtaProgress` 单次模式分支（`else` 分支），删除"无条件 enterRunningUI + startProgressPolling"的旁路，改为不主动进入运行态（由 `checkDeviceOtaState` 的 `data.active` 分支统一驱动），或在后端未确认前不启动轮询 —— 该分支现仅由 checkDeviceOtaState 在后端确认 active 后调用，已加注释说明

- [x] Task 3: 修复 `doRestoreOtaProgress` 循环模式 `.catch()` 兜底分支
  - [x] SubTask 3.1: 删除 catch 分支中"无条件 enterRunningUI + startProgressPolling + startCycleStatusPolling"的逻辑
  - [x] SubTask 3.2: catch 分支改为保守处理：调用 `enterIdleUI()` 或保持当前 UI，并通过 toast/状态文本提示"循环状态查询失败，请刷新重试"

- [x] Task 4: 验证修复效果（静态代码审查）
  - [x] SubTask 4.1: 构造残留 `ota_active='1'` 但后端 OTA 已结束的场景，进入 OTA 页面，确认进度条不再动画、不进入运行态、localStorage 标记被清理 —— 静态审查：restoreOtaState → checkDeviceOtaState → data.active=false → enterIdleUI（清理 ota_active/ota_cycle_active、停止轮询、隐藏进度区），无 enterRunningUI 调用
  - [x] SubTask 4.2: 构造 OTA 仍在运行的场景，进入页面，确认进度条正常按 8 秒间隔更新 —— 静态审查：checkDeviceOtaState → data.active=true → doRestoreOtaProgress → enterRunningUI + startProgressPolling（setInterval 间隔 OTA_PROGRESS_POLL_MS=8000）
  - [x] SubTask 4.3: 观察浏览器 Network 面板，确认 `/api/ota/progress/<sn>` 请求间隔约为 8 秒 —— 静态审查：startProgressPolling 中 setInterval(..., OTA_PROGRESS_POLL_MS=8000)，请求间隔≈8s

> 注：SubTask 4.1~4.3 受静态审查通过；运行时验证建议用户在浏览器中实测确认。

# Task Dependencies
- Task 2 与 Task 3 可并行（修改不同分支）
- Task 1 独立，可与其他任务并行
- Task 4 依赖 Task 1 / 2 / 3 全部完成
