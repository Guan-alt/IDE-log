# 页面缓存与任务删除优化 Spec

## Why
当前每次切换页面都是完整的浏览器跳转（`href` 链接），切回时重新加载所有数据，体感卡顿。同时，任务删除功能虽已实现但限制过严（有关联 OTA 记录时无法删除），用户期望能更灵活地删除任务。

## What Changes
- **页面缓存**：将页面切换改为 AJAX 局部加载 + DOM 缓存，切换时缓存已加载的页面内容，切回时直接显示缓存而非重新请求，体感接近 SPA（单页应用）
- **任务删除放宽**：有关联 OTA 记录的任务也允许删除，删除时自动将关联记录的 `task_id` 置空（或级联删除关联记录，视用户选择）

## Impact
- Affected specs: ota-monitor-platform, test-task-grouping
- Affected code:
  - [base.html](file:///c:/Users/Nissy/Desktop/IDE/IDE-log/app/templates/base.html) — 导航栏改为 AJAX 加载
  - [app.js](file:///c:/Users/Nissy/Desktop/IDE/IDE-log/app/static/js/app.js) — 新增页面缓存机制
  - 所有页面模板 — 适配缓存机制（DOMContentLoaded 改为可重复触发的初始化函数）
  - [tasks.py](file:///c:/Users/Nissy/Desktop/IDE/IDE-log/app/api/tasks.py) — 放宽删除限制
  - [tasks.html](file:///c:/Users/Nissy/Desktop/IDE/IDE-log/app/templates/tasks.html) — 删除按钮始终显示

## ADDED Requirements
### Requirement: 页面缓存机制
系统 SHALL 提供基于 AJAX 的页面局部加载机制，切换页面时不触发完整浏览器跳转，而是用 fetch 获取目标页 HTML 并替换内容区。

#### Scenario: 首次访问页面
- **WHEN** 用户首次点击导航栏链接
- **THEN** 通过 AJAX 获取页面 HTML 并插入内容区，执行页面初始化函数加载数据
- **AND** 将加载后的 DOM 快照缓存到内存

#### Scenario: 再次访问已缓存页面
- **WHEN** 用户切回已访问过的页面
- **THEN** 直接从缓存恢复 DOM 快照，不重新请求页面 HTML 和初始数据
- **AND** 页面状态（筛选条件、滚动位置等）保持上次离开时的状态

#### Scenario: 手动刷新
- **WHEN** 用户点击页面内的"刷新"按钮或浏览器刷新
- **THEN** 重新加载当前页面数据和 DOM

#### Scenario: 浏览器前进/后退
- **WHEN** 用户使用浏览器前进/后退按钮
- **THEN** 同样从缓存恢复或 AJAX 加载对应页面

## MODIFIED Requirements
### Requirement: 任务删除
任务删除 SHALL 允许删除有关联 OTA 记录的任务。删除时，关联的 OTA 记录的 `task_id` 被置为 NULL（解除关联），不影响记录本身。

#### Scenario: 删除无关联记录的任务
- **WHEN** 用户删除一个没有 OTA 记录的任务
- **THEN** 任务被直接删除

#### Scenario: 删除有关联记录的任务
- **WHEN** 用户删除一个有 OTA 记录关联的任务
- **THEN** 弹出确认提示"该任务关联了 N 条 OTA 记录，删除后记录将解除关联，是否继续？"
- **AND** 确认后，关联记录的 task_id 置空，任务被删除

#### Scenario: 删除按钮显示
- **WHEN** 任务列表渲染
- **THEN** 所有任务都显示删除按钮（不再因有记录而隐藏）
