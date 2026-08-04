# Tasks

- [x] Task 1: 数据模型新增线上环境字段
  - [x] SubTask 1.1: 在 `models.py` 的 Setting 模型中新增 `ota_url_online` 和 `token_online` 字段
  - [x] SubTask 1.2: 在 `to_dict()` 方法中返回新字段
  - [x] SubTask 1.3: 执行数据库迁移（ALTER TABLE 添加两列）

- [x] Task 2: 后端接口支持环境参数
  - [x] SubTask 2.1: 修改 `get_ota_client(ota_type='offline')`，根据参数返回不同环境的 OtaClient
  - [x] SubTask 2.2: 修改 `start_ota` 接口，从请求中读取 `ota_type` 并传给 `get_ota_client`
  - [x] SubTask 2.3: 修改 `start_cycle`、`get_progress`、`_start_ota_leg`、`_continue_cycle` 等接口，同样支持 `ota_type` 参数
  - [x] SubTask 2.4: 修改 `settings.py` 的配置读写接口，支持新字段

- [x] Task 3: 前端设置页面新增线上环境配置
  - [x] SubTask 3.1: 在 `settings.html` 新增"线上OTA环境"配置区域（URL + Token 输入框）
  - [x] SubTask 3.2: 加载配置时填充线上环境字段，保存时提交新字段

- [x] Task 4: 前端监控页面新增环境切换
  - [x] SubTask 4.1: 在 `monitor.html` OTA模式切换区域旁新增"线下OTA"/"线上OTA"环境切换按钮
  - [x] SubTask 4.2: 环境选择持久化到 localStorage（key: `ota_env`）
  - [x] SubTask 4.3: 发起OTA（单次/循环）时在请求参数中携带 `ota_type`
  - [x] SubTask 4.4: 进度轮询请求中携带当前 `ota_type`
  - [x] SubTask 4.5: 页面加载时恢复上次选择的环境

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3 依赖 Task 1
- Task 4 依赖 Task 2
