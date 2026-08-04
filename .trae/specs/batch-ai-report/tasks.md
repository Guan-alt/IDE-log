# Tasks

- [x] Task 1: 后端新增批量AI分析方法
  - [x] SubTask 1.1: 在 `ai_analyzer.py` 中新增 `analyze_batch(records)` 方法，汇总多条记录数据构造prompt，调用AI生成综合测试报告
  - [x] SubTask 1.2: 新增批量报告专用 system prompt，要求AI输出整体统计、常见问题、改进建议等

- [x] Task 2: 后端新增批量报告API
  - [x] SubTask 2.1: 在 `ai_routes.py` 中新增 `/api/ai/batch-report` POST 接口，接收 `{record_ids: [1,2,3]}` 
  - [x] SubTask 2.2: 查询所有 record_id 对应的 OtaRecord，调用 `analyze_batch`，返回报告内容

- [x] Task 3: 前端新增复选框和批量报告按钮
  - [x] SubTask 3.1: 在 records.html 表头新增全选复选框列
  - [x] SubTask 3.2: 每行记录前新增复选框，绑定 record id
  - [x] SubTask 3.3: 表格下方新增"生成测试报告"按钮，未选中时隐藏
  - [x] SubTask 3.4: 实现全选/取消全选逻辑，实现选中数量统计和按钮启用判断

- [x] Task 4: 前端实现批量报告生成逻辑
  - [x] SubTask 4.1: 新增 `generateBatchReport()` 函数，收集选中 record id，校验至少1条
  - [x] SubTask 4.2: 调用 `/api/ai/batch-report`，弹窗显示分析进度
  - [x] SubTask 4.3: 返回后在弹窗中以 Markdown 渲染展示综合测试报告

# Task Dependencies
- Task 2 依赖 Task 1
- Task 4 依赖 Task 2 和 Task 3
