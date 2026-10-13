# Checklist

- [x] OTA 进度轮询间隔由 5000ms 调整为 8000ms，并以命名常量 `OTA_PROGRESS_POLL_MS` 集中定义
- [x] 循环状态轮询间隔同步调整为 8000ms（共用同一常量）
- [x] `restoreOtaState()` 不再仅凭 localStorage 中的 `ota_active` / `ota_cycle_active` 标记直接进入运行态 UI 并启动轮询
- [x] `restoreOtaState()` 统一通过 `checkDeviceOtaState(savedSn)` → `/api/ota/check-status/<sn>` 后端确认后再决定是否进入运行态
- [x] 当后端返回 `active=false` 时，进入空闲态 UI 并清理 localStorage 中残留的 `ota_active` / `ota_cycle_active` 标记（注：`ota_sn` 为设备 SN 持久化，非"运行中"标记，`enterIdleUI` 有意保留，不清理）
- [x] `doRestoreOtaProgress` 单次模式分支不再"无条件 enterRunningUI + startProgressPolling"（现仅由 checkDeviceOtaState 后端确认后调用）
- [x] `doRestoreOtaProgress` 循环模式 `.catch()` 兜底分支不再无条件进入运行态并启动轮询
- [x] 循环模式 catch 分支改为保守处理（保持 UI 或进入空闲态）并给用户提示
- [x] OTA 真在运行时，进入页面后进度条仍能按 8 秒间隔正常更新（静态审查：checkDeviceOtaState → doRestoreOtaProgress → enterRunningUI + startProgressPolling 间隔 8000ms）
- [x] Network 面板观察 `/api/ota/progress/<sn>` 请求间隔约为 8 秒（静态审查：setInterval(..., OTA_PROGRESS_POLL_MS=8000)）

> 运行时实测建议：用户在浏览器中打开 OTA 页面，观察 Network 面板确认请求间隔≈8s；构造残留 `ota_active` 标记但 OTA 已结束的场景确认进度条不再自动跑。
