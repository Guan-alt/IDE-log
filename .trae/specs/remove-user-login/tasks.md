# Tasks

- [x] Task 1: 改造认证工具（decorators.py）
  - [x] `login_required` 直接放行（不再校验 session、不再返回 401）
  - [x] `get_current_user_id()` 固定返回默认用户（admin）ID：查 `User.query.filter_by(username='admin').first()`，不存在时返回 1
  - [x] `get_current_user()` 返回默认用户对象（同上兜底逻辑）
  - [x] 语法检查通过

- [x] Task 2: 精简 auth 蓝图（auth.py）
  - [x] 移除 `/api/auth/login`（GET 登录页 + POST 登录）、`/api/auth/logout`、`/api/auth/register`
  - [x] `/api/auth/current` 固定返回 `{logged_in: true, user: 默认用户.to_dict()}`（状态码 200）
  - [x] 移除不再使用的 import（render_template、login_required 等）
  - [x] 语法检查通过

- [x] Task 3: 移除前端登录交互
  - [x] `templates/base.html`：删除顶部认证检查脚本（fetch /api/auth/current 跳转逻辑）、userBox 用户面板、退出按钮及 doLogout 函数
  - [x] 删除 `templates/login.html`
  - [x] 确认无其他模板引用 login.html 或 /api/auth/login

- [x] Task 4: 验证（依赖 Task 1/2/3）
  - [x] 服务启动无报错，admin 初始化正常
  - [x] 无会话状态下访问 6 个页面（/devices /monitor /tasks /records /stats /settings）均 200 且正常渲染
  - [x] 无会话状态下核心 API 均 200：/api/devices、/api/ota/*、/api/stats/*、/api/records、/api/tasks、/api/ota-envs、/api/serial/configs、/api/settings
  - [x] 数据可见：设备/记录/任务/统计/环境数据正常返回（归属 admin）
  - [x] 确认 login 相关引用无残留（grep 'api/auth/login|logout|register|login.html' 仅剩 /api/auth/current 相关）

# Task Dependencies
- [Task 4] 依赖 [Task 1]、[Task 2]、[Task 3]
- [Task 2]、[Task 3] 不依赖 [Task 1]，可并行
