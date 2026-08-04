# 门锁OTA监控测试平台 Spec

## Why
当前 OTA 压测脚本（`S02Dota压测.py`）为命令行工具，无法实时可视化查看多设备 OTA 升级进度、历史记录和统计信息。需要一个 Web 平台来集中监控门锁 OTA 测试情况，提升测试效率与可观测性。

## What Changes
- 新增 Web 后端服务（Python Flask），封装 OTA 脚本中的 3 个核心 API 接口
- 新增 Web 前端页面，提供设备列表、实时进度监控、历史记录、统计看板
- 新增 SQLite 数据库，持久化存储 OTA 测试记录
- 新增实时进度轮询机制，前端定时拉取 OTA 升级/下载进度并渲染进度条
- 新增统计面板，展示成功率、平均耗时、失败原因分布
- 新增串口日志采集功能，支持在 OTA 升级时通过串口实时接收门锁日志
- 新增 AI 日志分析功能，OTA 失败时自动保存串口日志并调用 AI 分析失败原因

## Impact
- 参考代码: `c:\Users\Nissy\Desktop\自动化脚本\S02D\S02Dota压测.py`（API 接口定义、数据格式）
- 新项目目录: `C:\Users\Nissy\Desktop\IDE\IDE-log`

## OTA API 接口（来自参考脚本）

### 1. 查询设备版本
- **URL**: `GET {ota_url}/device/infoBySN?sn={SN}`
- **Header**: `x-access-token: {token}`
- **返回**: `result` 列表，其中 `pid == "ota_ver"` 的项的 `value` 为当前固件版本

### 2. 发起OTA升级
- **URL**: `POST {ota_url}/ota/version/forceUpgrade`
- **Header**: `x-access-token: {token}`
- **Body**: `{"sn": SN, "version": target_ver}`
- **返回**: `status == 200` 表示成功

### 3. 查询OTA进度
- **URL**: `POST {ota_url}/ota/record/page`
- **Header**: `x-access-token: {token}`
- **Body**: `{"pageIndex": 0, "pageSize": 1, "sn": SN, "terms": []}`
- **返回**: `result.data[0]` 包含 `upgradePercent`（升级进度）和 `downloadPercent`（下载进度）

## ADDED Requirements

### Requirement: 设备管理
系统 SHALL 提供设备管理功能，支持添加、查看、删除门锁设备（SN号）。

#### Scenario: 添加设备
- **WHEN** 用户在设备管理页面输入设备SN并点击添加
- **THEN** 设备保存到数据库，设备列表刷新显示新设备

#### Scenario: 查看设备列表
- **WHEN** 用户打开设备管理页面
- **THEN** 显示所有已添加设备的SN、当前固件版本、当前状态

#### Scenario: 删除设备
- **WHEN** 用户点击设备的删除按钮并确认
- **THEN** 从数据库删除该设备，列表刷新

### Requirement: OTA升级触发
系统 SHALL 支持对指定设备发起 OTA 升级或降级请求。

#### Scenario: 触发升级
- **WHEN** 用户选择设备并输入目标版本号，点击"发起升级"
- **THEN** 后端调用 `/ota/version/forceUpgrade` 接口，返回结果在前端展示

#### Scenario: 自动获取当前版本
- **WHEN** 用户选择设备后
- **THEN** 后端调用 `/device/infoBySN` 接口获取当前固件版本并展示

### Requirement: 实时进度监控
系统 SHALL 支持实时监控 OTA 升级进度，展示下载进度和升级进度。

#### Scenario: 实时进度展示
- **WHEN** 某设备正在 OTA 升级中
- **THEN** 前端每5秒轮询 `/ota/record/page` 接口，更新下载进度条和升级进度条

#### Scenario: 升级完成检测
- **WHEN** 升级进度达到100%或设备版本变更为目标版本
- **THEN** 标记该设备升级成功，停止轮询，记录完成时间和耗时

#### Scenario: 升级超时
- **WHEN** 升级耗时超过配置的超时时间（默认60分钟）
- **THEN** 标记该设备升级超时失败，停止轮询，记录失败

### Requirement: 历史记录
系统 SHALL 持久化存储所有 OTA 测试记录，支持查看历史。

#### Scenario: 查看历史记录
- **WHEN** 用户打开历史记录页面
- **THEN** 显示所有 OTA 测试记录列表，包含设备SN、目标版本、结果、耗时、时间点

#### Scenario: 筛选历史记录
- **WHEN** 用户按设备SN或结果状态筛选
- **THEN** 仅显示符合条件的记录

### Requirement: 统计看板
系统 SHALL 提供统计看板，展示 OTA 测试整体数据。

#### Scenario: 查看统计看板
- **WHEN** 用户打开看板页面
- **THEN** 显示：总测试次数、成功次数、失败次数、成功率、平均升级耗时

#### Scenario: 按设备统计
- **WHEN** 用户选择特定设备
- **THEN** 显示该设备的独立统计数据

### Requirement: 配置管理
系统 SHALL 支持配置 OTA 服务器地址和访问令牌。

#### Scenario: 修改服务器配置
- **WHEN** 用户在设置页面修改 ota_url 和 token
- **THEN** 配置保存到数据库，后续 API 调用使用新配置

### Requirement: 多串口日志采集
系统 SHALL 支持同时添加多个串口进行日志采集，每个串口可独立配置串口号、波特率、名称和关联设备。

#### Scenario: 添加多个串口
- **WHEN** 用户在串口管理页面点击"添加串口"，选择串口号（如 COM3）、输入波特率（默认 115200）、输入串口名称/备注（如"门锁主控"）、选择关联设备SN
- **THEN** 串口配置保存到数据库 SerialConfig 表，前端显示新增的串口配置卡片

#### Scenario: 同时采集多串口日志
- **WHEN** 用户勾选多个串口配置的"启用"开关并点击"开始采集"
- **THEN** 后端为每个已启用的串口分别创建独立的 SerialLogger 实例和后台读取线程，同时采集日志

#### Scenario: 查看多串口实时日志
- **WHEN** 多个串口正在采集中，用户在实时监控页面切换不同串口标签页
- **THEN** 展示对应串口的实时日志流，各串口日志独立缓冲互不干扰

#### Scenario: OTA 升级中持续采集
- **WHEN** OTA 升级进行中，多个串口持续接收各自设备的日志
- **THEN** 后端将每个串口的日志分别追加到独立内存缓冲区，前端可切换查看

#### Scenario: 升级成功停止采集
- **WHEN** OTA 升级成功
- **THEN** 停止所有已启用串口的采集，日志可选保存到文件，不触发 AI 分析

#### Scenario: 升级失败保存多串口日志
- **WHEN** OTA 升级失败（超时或版本未变更）
- **THEN** 自动将所有已启用串口的日志分别保存到文件（`logs/serial_{串口名}_{SN}_{timestamp}.log`），并在数据库记录中关联所有日志文件路径（JSON数组）

#### Scenario: 删除串口配置
- **WHEN** 用户点击串口配置的删除按钮并确认
- **THEN** 从数据库删除该串口配置，如正在采集则先停止

#### Scenario: 单个串口异常处理
- **WHEN** 某个串口打开失败或读取异常
- **THEN** 仅停止该串口采集，其他串口不受影响，OTA 测试继续执行，fail_reason 标注"串口{串口名}采集异常"

### Requirement: JLink日志采集
系统 SHALL 支持通过 JLink 调试器采集设备 RTT 日志，与串口日志采集并行运行，用于 OTA 失败时根因分析。

#### Scenario: 添加JLink配置
- **WHEN** 用户在日志管理页面点击"添加JLink"，输入设备名称/备注（如"门锁主控JLink"）、输入JLink路径（可选，默认使用系统PATH中的JLink.exe）、输入RTT通道号（默认0）、选择关联设备SN
- **THEN** JLink配置保存到数据库 LogConfig 表（log_type="jlink"），前端显示新增的JLink配置卡片

#### Scenario: 启动JLink采集
- **WHEN** 用户勾选JLink配置的"启用"开关并点击"开始采集"
- **THEN** 后端通过调用 JLink.exe 命令行工具启动 RTT 日志捕获，后台线程持续读取输出并缓存到内存

#### Scenario: 同时采集串口和JLink日志
- **WHEN** 用户同时启用了串口和JLink配置
- **THEN** 串口和JLink各自独立后台线程同时采集日志，互不干扰

#### Scenario: 查看JLink实时日志
- **WHEN** JLink正在采集中，用户在实时监控页面切换到JLink标签页
- **THEN** 展示对应JLink的实时日志流

#### Scenario: 升级失败保存JLink日志
- **WHEN** OTA 升级失败
- **THEN** 自动将JLink日志保存到文件（`logs/jlink_{名称}_{SN}_{timestamp}.log`），与串口日志一起关联到数据库记录

#### Scenario: JLink异常处理
- **WHEN** JLink.exe 不存在或启动失败
- **THEN** 记录错误日志，OTA 测试继续执行，fail_reason 标注"JLink{名称}采集异常"

### Requirement: AI 日志分析
系统 SHALL 在 OTA 失败时自动调用 AI 分析所有已保存的日志（串口+JLink），输出失败原因分析报告。

#### Scenario: 自动触发 AI 分析
- **WHEN** OTA 升级失败且存在已保存的日志文件（串口或JLink）
- **THEN** 后端自动读取所有关联的日志文件，合并后调用 AI 接口分析失败原因，将分析结果保存到 OtaRecord 的 ai_analysis 字段

#### Scenario: 手动重新分析
- **WHEN** 用户在历史记录页面点击某条失败记录的"重新分析"按钮
- **THEN** 后端重新读取该记录关联的所有日志文件（串口+JLink），合并后调用 AI 重新分析，更新 ai_analysis 字段

#### Scenario: 查看分析报告
- **WHEN** 用户点击历史记录中某条失败记录的"查看分析"
- **THEN** 展示 AI 分析报告，包含：失败原因总结、各日志源（串口/JLink）关键日志片段、建议解决方案

#### Scenario: AI 分析失败处理
- **WHEN** AI 接口调用失败或日志文件不存在
- **THEN** ai_analysis 字段记录"分析失败：{原因}"，不影响其他流程

### Requirement: AI 配置管理
系统 SHALL 支持配置 AI 服务的 API Key 和模型类型。

#### Scenario: 配置 AI 服务
- **WHEN** 用户在设置页面配置 AI API Key、模型类型（如 doubao）、API 地址
- **THEN** 配置保存到数据库，AI 分析功能使用新配置
