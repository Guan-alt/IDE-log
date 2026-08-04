# Tasks

- [x] Task 1: 初始化项目结构与依赖
  - [x] SubTask 1.1: 创建项目目录结构（app/, app/static/, app/templates/, app/models/, instance/, logs/）
  - [x] SubTask 1.2: 创建 requirements.txt（Flask, requests, flask-cors, flask-sqlalchemy, pyserial, openai）
  - [x] SubTask 1.3: 创建 config.py 配置文件（OTA URL、Token、数据库路径、AI API Key、AI 模型、串口默认配置等）

- [x] Task 2: 数据库模型与初始化
  - [x] SubTask 2.1: 创建 Device 模型（id, sn, name, current_version, status, created_at）
  - [x] SubTask 2.2: 创建 OtaRecord 模型（id, device_sn, target_version, result, duration, upgrade_percent, download_percent, start_time, end_time, fail_reason, serial_log_paths, ai_analysis）
  - [x] SubTask 2.3: 创建 SerialConfig 模型（id, port, baudrate, name, device_sn, enabled, created_at）
  - [x] SubTask 2.4: 创建 Setting 模型（id, ota_url, token, ota_timeout, ai_api_key, ai_model, ai_base_url, serial_default_baudrate）
  - [x] SubTask 2.5: 创建数据库初始化脚本

- [x] Task 3: 后端 API 开发
  - [x] SubTask 3.1: 封装 OTA API 客户端类（get_version, ota_start, get_progress），复用参考脚本逻辑
  - [x] SubTask 3.2: 实现设备管理接口（GET/POST/DELETE /api/devices）
  - [x] 3.3: 实现获取设备当前版本接口（GET /api/devices/<sn>/version）
  - [x] SubTask 3.4: 实现发起OTA升级接口（POST /api/ota/start），支持传入串口配置参数
  - [x] SubTask 3.5: 实现查询OTA进度接口（GET /api/ota/progress/<sn>）
  - [x] SubTask 3.6: 实现历史记录接口（GET /api/records，支持筛选）
  - [x] SubTask 3.7: 实现统计接口（GET /api/stats，支持按设备筛选）
  - [x] SubTask 3.8: 实现配置管理接口（GET/POST /api/settings）
  - [x] SubTask 3.9: 实现多串口管理接口（GET /api/serial/ports 列出可用串口, GET/POST/DELETE /api/serial/configs 管理串口配置, POST /api/serial/start 批量开始采集, POST /api/serial/stop 批量停止采集, GET /api/serial/logs/<config_id> 获取指定串口实时日志）
  - [x] SubTask 3.10: 实现 AI 分析接口（POST /api/ai/analyze/<record_id> 自动分析, GET /api/ai/report/<record_id> 查看分析报告）

- [x] Task 4: 多串口日志采集模块
  - [x] SubTask 4.1: 创建 SerialLogger 类，封装单个串口的打开、读取、关闭逻辑（使用 pyserial）
  - [x] SubTask 4.2: 创建 SerialManager 管理器类，管理多个 SerialLogger 实例（添加/删除/批量启动/批量停止）
  - [x] SubTask 4.3: 实现每个串口独立后台线程读取数据到独立内存缓冲区
  - [x] SubTask 4.4: 实现日志保存到文件功能（logs/serial_{串口名}_{SN}_{timestamp}.log，每个串口一个文件）
  - [x] SubTask 4.5: 实现单个串口异常处理（仅停止异常串口，其他串口不受影响）

- [x] Task 5: AI 日志分析模块
  - [x] SubTask 5.1: 封装 AI 客户端类，调用 AI API 分析串口日志（使用 openai SDK，支持 doubao 等模型）
  - [x] SubTask 5.2: 构造分析 prompt（系统提示词：你是固件OTA分析专家，分析多串口日志中失败原因，输出原因总结+各串口关键日志片段+建议方案）
  - [x] SubTask 5.3: 实现 OTA 失败时自动触发 AI 分析的逻辑（读取并合并所有关联串口日志文件）
  - [x] SubTask 5.4: 实现分析结果解析与存储到 OtaRecord.ai_analysis 字段
  - [x] SubTask 5.5: 实现 AI 分析失败处理（接口超时/文件不存在等）

- [x] Task 6: 前端页面开发
  - [x] SubTask 6.1: 创建基础布局模板（导航栏：设备管理、实时监控、历史记录、统计看板、设置）
  - [x] SubTask 6.2: 实现设备管理页面（设备列表、添加/删除设备、查看当前版本）
  - [x] SubTask 6.3: 实现实时监控页面（设备进度卡片、下载进度条、升级进度条、5秒轮询、多串口配置管理、多串口实时日志标签页切换）
  - [x] SubTask 6.4: 实现历史记录页面（记录表格、按设备/结果筛选、结果颜色标识、失败记录"查看分析"和"重新分析"按钮）
  - [x] SubTask 6.5: 实现统计看板页面（总数/成功/失败/成功率/平均耗时卡片，按设备筛选）
  - [x] SubTask 6.6: 实现设置页面（OTA URL、Token、超时时间、串口默认波特率、AI API Key、AI 模型、AI API 地址配置表单）
  - [x] SubTask 6.7: 实现 AI 分析报告弹窗（展示失败原因总结、各串口关键日志片段、建议解决方案）

- [x] Task 7: 集成与启动
  - [x] SubTask 7.1: 创建 app.py 主入口，注册蓝图和路由
  - [x] SubTask 7.2: 创建数据库自动初始化逻辑
  - [x] SubTask 7.3: 验证平台启动，确认所有页面可访问

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 2
- Task 4 depends on Task 2
- Task 5 depends on Task 4
- Task 6 depends on Task 3 and Task 5
- Task 7 depends on Task 6
