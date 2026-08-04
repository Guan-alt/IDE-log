# Tasks

- [x] Task 1: 在 `stop-cycle` 接口中将循环任务状态改为 `stopping`
  - [x] SubTask 1.1: 修改 `stop-cycle` 路由，设置 `task['state'] = 'stopping'` 而非 'stopped'
  - [x] SubTask 1.2: 确保返回信息不变，仍提示用户"当前OTA完成后不再继续"

- [x] Task 2: 在 `get_progress` 的 `is_finished` 处理中检查 `stopping` 标志
  - [x] SubTask 2.1: 当 `is_finished=True` 时，检查 `cycling_tasks` 中是否有该 sn 的 `state=='stopping'` 任务
  - [x] SubTask 2.2: 如果检测到 stopping 标志，删除当前刚完成的 OtaRecord（通过 `db.session.delete(record)`）
  - [x] SubTask 2.3: 将循环任务状态改为 `stopped`，触发循环AI分析
  - [x] SubTask 2.4: 确保不调用 `_continue_cycle_after_wait`，不发起下一轮OTA

- [x] Task 3: 处理等待中停止的场景
  - [x] SubTask 3.1: 在 `_continue_cycle_after_wait` 的 sleep 结束后、调用 `_continue_cycle` 前检查 `stopping` 标志
  - [x] SubTask 3.2: 如果检测到 stopping，直接终止循环（设 state='stopped'），不发起下一轮OTA

# Task Dependencies
- Task 2 依赖 Task 1（需要 stop-cycle 先设置 stopping 状态）
- Task 3 依赖 Task 1
