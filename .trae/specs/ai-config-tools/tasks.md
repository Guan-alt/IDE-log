# Tasks

- [x] Task 1: 后端 AI 连通性测试接口
  - [x] 在 `app/services/ai_analyzer.py` 新增 `test_connection(api_key, model, base_url)` 方法：调用 `{base_url}/chat/completions` 发送最小化请求（如 "ping"），返回 `{ok, status, latency_ms, message}`；区分鉴权失败/连接超时/模型不存在/网络错误等错误类型
  - [x] 在 `app/api/ai_routes.py` 新增 `POST /api/ai/test-connection`：从请求体读取 api_key/model/base_url（优先用表单临时值，缺省回退 Setting 已存配置），返回测试结果 JSON
- [x] Task 2: 后端 AI 模型列表接口
  - [x] 在 `app/services/ai_analyzer.py` 新增 `list_models(api_key, base_url)` 方法：请求 `GET {base_url}/models`，返回模型 id 列表；对 OpenAI 兼容格式（data[].id）解析
  - [x] 在 `app/api/ai_routes.py` 新增 `POST /api/ai/models`：读取 api_key/base_url（缺省回退 Setting），返回 `{models: [{id, name}]}`；失败时返回错误信息
- [x] Task 3: 前端设置页 AI 配置卡片改造
  - [x] 模型输入框改为 `<select>` 下拉 + "手动输入"选项（选中后显示文本输入框）
  - [x] 新增"获取模型列表"按钮：调用 `/api/ai/models`，成功后填充下拉框，失败提示并可手动输入
  - [x] 新增"测试连通性"按钮：调用 `/api/ai/test-connection`，用表单当前值，结果内联展示（成功绿色/失败红色+原因）
  - [x] 保存逻辑保持不变（保存时读取当前选中的模型值）

# Task Dependencies
- [Task 3] 依赖 [Task 1] 和 [Task 2]（前端按钮依赖后端接口）
- [Task 1]、[Task 2] 相互独立，可并行
