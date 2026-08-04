# Tasks

- [x] Task 1: 后端新增注册接口
  - [x] SubTask 1.1: 在 `auth.py` 新增 `/api/auth/register` POST 接口，接收 username/password/display_name
  - [x] SubTask 1.2: 校验用户名唯一性、密码长度（≥6），创建普通用户（is_admin=False），写入 session 自动登录

- [x] Task 2: 前端登录页新增注册表单
  - [x] SubTask 2.1: 在 `login.html` 新增注册表单（用户名、密码、确认密码、显示名），默认隐藏
  - [x] SubTask 2.2: 新增"注册"链接切换到注册表单，"返回登录"链接切换回登录表单
  - [x] SubTask 2.3: 实现前端校验（密码≥6位、两次密码一致），调用 `/api/auth/register`，成功后跳转首页

# Task Dependencies
- Task 2 依赖 Task 1
