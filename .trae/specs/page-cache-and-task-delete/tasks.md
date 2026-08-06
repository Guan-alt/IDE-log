# Tasks

- [x] Task 1: 实现页面缓存机制（AJAX 局部加载 + DOM 缓存）
  - [x] SubTask 1.1: 在 app.js 中新增 `navigateTo(path)` 函数，用 fetch 获取页面 HTML，提取 content 区域插入 DOM，并维护 `pageCache` 内存缓存
  - [x] SubTask 1.2: 在 base.html 中将导航栏 `href` 改为 `onclick="navigateTo('/xxx')"` 并阻止默认跳转，同时用 `history.pushState` 更新浏览器地址栏
  - [x] SubTask 1.3: 将所有页面模板的 `DOMContentLoaded` 回调改为自执行函数，供 navigateTo 在插入 HTML 后执行
  - [x] SubTask 1.4: 实现 `popstate` 事件监听，支持浏览器前进/后退从缓存恢复或 AJAX 加载
  - [x] SubTask 1.5: 为每个页面新增/复用"刷新"按钮，点击时清除该页缓存并重新加载

- [x] Task 2: 放宽任务删除限制
  - [x] SubTask 2.1: 修改 [tasks.py](file:///c:/Users/Nissy/Desktop/IDE/IDE-log/app/api/tasks.py) 的 delete_task 接口：有关联记录时不再拒绝，而是将关联记录的 task_id 置空后删除任务
  - [x] SubTask 2.2: 修改 [tasks.html](file:///c:/Users/Nissy/Desktop/IDE/IDE-log/app/templates/tasks.html) 的删除按钮：始终显示，不再因 record_count 隐藏；确认提示中包含关联记录数量

# Task Dependencies
- Task 1 和 Task 2 相互独立，可并行实现
