# Tasks

- [x] Task 1: 后端新增统计 API
  - [x] SubTask 1.1: 新增 `/api/stats/overview` 接口，返回总次数/成功/失败/成功率/平均耗时 + 前一天环比数据
  - [x] SubTask 1.2: 新增 `/api/stats/trend` 接口，按天聚合近N天的成功/失败次数，支持 days 参数（默认7）
  - [x] SubTask 1.3: 新增 `/api/stats/fail-reasons` 接口，按 fail_reason 分组统计失败次数和占比
  - [x] SubTask 1.4: 新增 `/api/stats/version-stats` 接口，按 target_version 分组统计成功/失败次数
  - [x] SubTask 1.5: 新增 `/api/stats/device-ranking` 接口，按设备聚合测试次数/成功/失败/成功率，按次数降序
  - [x] SubTask 1.6: 所有接口支持可选 sn 参数筛选特定设备

- [x] Task 2: 前端重构仪表盘布局
  - [x] SubTask 2.1: 引入 Chart.js CDN（base.html 或 stats.html）
  - [x] SubTask 2.2: 页面标题改为"数据仪表盘"，调整顶部筛选栏样式
  - [x] SubTask 2.3: 优化5个数据卡片，增加环比变化指示器（↑/↓ + 百分比，红绿色区分）
  - [x] SubTask 2.4: 新增趋势折线图区域（成功/失败双线），带7天/30天切换按钮
  - [x] SubTask 2.5: 新增失败原因饼图区域
  - [x] SubTask 2.6: 新增版本升级柱状图区域（成功/失败堆叠）
  - [x] SubTask 2.7: 新增设备排行表格区域
  - [x] SubTask 2.8: 前端 JS 调用新 API 并渲染所有图表，设备筛选时联动刷新

- [x] Task 3: CSS 样式优化
  - [x] SubTask 3.1: 新增仪表盘网格布局样式（图表区域两列排列，响应式适配）
  - [x] SubTask 3.2: 新增卡片环比变化指示器样式（↑绿色/↓红色）
  - [x] SubTask 3.3: 新增图表容器卡片样式（标题+canvas区域）
  - [x] SubTask 3.4: 新增设备排行表格样式

# Task Dependencies
- Task 2 依赖 Task 1（前端调用后端新 API）
- Task 3 可与 Task 2 并行
