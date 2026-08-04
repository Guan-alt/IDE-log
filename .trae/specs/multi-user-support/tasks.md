# Tasks

- [x] Task 1: 新增 User 模型与数据库迁移
  - [x] SubTask 1.1: 在 `models.py` 新增 User 模型（id, username, password_hash, display_name, is_admin, created_at），含 `set_password`/`check_password` 方法
  - [x] SubTask 1.2: 为 Device、OtaRecord、LogConfig、Setting 模型新增 `user_id` 字段（外键关联 users.id）
  - [x] SubTask 1.3: 在 `__init__.py` 的 `create_app` 中初始化默认 admin 用户（admin/admin），并将现有无 user_id 的数据关联到 admin
  - [x] SubTask 1.4: 数据库迁移（CREATE TABLE users + ALTER TABLE 添加 user_id 列）

- [x] Task 2: 后端新增认证模块
  - [x] SubTask 2.1: 新建 `app/api/auth.py`，实现 `/api/auth/login`（POST）、`/api/auth/logout`（POST）、`/api/auth/current`（GET）
  - [x] SubTask 2.2: 新建 `app/utils/decorators.py`，实现 `@login_required` 装饰器和 `get_current_user_id()`/`get_current_user()` 函数
  - [x] SubTask 2.3: 在 `__init__.py` 注册 auth 蓝图，配置 secret_key，CORS 支持 credentials

- [x] Task 3: 所有 API 加上认证和数据隔离
  - [x] SubTask 3.1: `devices.py` — 所有查询加 user_id 过滤
  - [x] SubTask 3.2: `ota.py` — cycling_tasks 改为 `{user_id: {sn: task}}`，所有接口加认证
  - [x] SubTask 3.3: `records.py` — 查询加 user_id 过滤
  - [x] SubTask 3.4: `settings.py` — Setting 按 user_id 隔离，首次访问自动创建
  - [x] SubTask 3.5: `serial.py` — jlink_loggers 改为 `{user_id: {config_id: logger}}`
  - [x] SubTask 3.6: `stats.py` — 统计查询加 user_id 过滤
  - [x] SubTask 3.7: `ai_routes.py` — 按 user_id 过滤记录

- [x] Task 4: 前端登录页面与认证
  - [x] SubTask 4.1: 新建 `login.html` 登录页面
  - [x] SubTask 4.2: auth 蓝图提供 `/api/auth/login` GET 路由
  - [x] SubTask 4.3: `base.html` 中注入认证检查 JS，未登录跳转登录页
  - [x] SubTask 4.4: 导航栏显示当前用户名和注销按钮
  - [x] SubTask 4.5: 所有页面通过 base.html 继承自动获得认证检查

- [x] Task 5: 数据迁移与测试验证
  - [x] SubTask 5.1: 数据库迁移已完成，现有数据关联到 admin 用户
  - [x] SubTask 5.2: 验证 admin 登录正常、数据可见
  - [x] SubTask 5.3: 验证未登录访问被拦截（返回401）

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3 依赖 Task 2
- Task 4 依赖 Task 2
- Task 5 依赖 Task 3 和 Task 4
