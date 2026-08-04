# 循环OTA停止时跳过当前记录 Spec

## Why
循环OTA过程中，用户点击"停止OTA"后，当前正在进行的OTA升级虽然会继续执行完毕，但该次OTA的记录不应被保存到历史记录中，因为用户已主动中止，记录它没有意义且会干扰统计数据。

## What Changes
- 循环OTA停止后，当前正在进行的OTA升级完成后（成功或失败），不保存该条OtaRecord记录
- 如果当前OTA升级尚未发起（只在等待中），直接终止循环
- 循环AI分析照常触发（基于已完成的各轮记录）

## Impact
- Affected code: `app/api/ota.py` — `stop-cycle` 接口和 `_continue_cycle` 函数、`get_progress` 函数
- 受影响逻辑：循环OTA的状态管理和记录保存

## MODIFIED Requirements
### Requirement: 循环OTA停止时跳过当前记录
循环OTA中用户点击停止后，系统标记循环任务为 `stopping` 状态。当前正在进行的OTA升级继续执行完毕后，系统检测到 `stopping` 标志，不保存该条OTA记录到数据库，并终止循环。

#### Scenario: 停止时当前OTA已发起且最终成功
- **WHEN** 用户点击停止，当前OTA升级正在进行中
- **THEN** 当前OTA升级继续执行直到成功或失败
- **AND** 完成后检测到 stopping 标志，删除或不保存该条OtaRecord
- **AND** 不继续发起下一轮OTA

#### Scenario: 停止时当前OTA已发起但最终失败
- **WHEN** 用户点击停止，当前OTA升级正在进行中
- **THEN** 当前OTA升级继续执行直到失败
- **AND** 完成后检测到 stopping 标志，删除或不保存该条OtaRecord
- **AND** 不继续发起下一轮OTA

#### Scenario: 停止时当前OTA等待中
- **WHEN** 用户点击停止，且循环处于随机等待间隔中（尚未发起下一轮OTA）
- **THEN** 等待结束后不发起新的OTA，直接终止循环
