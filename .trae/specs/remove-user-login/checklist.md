# Checklist

- [x] login_required 装饰器直接放行，不再返回 401
- [x] get_current_user_id() 固定返回默认用户（admin）ID
- [x] get_current_user() 返回默认用户对象
- [x] /api/auth/current 固定返回 {logged_in: true, user: 默认用户}，状态码 200
- [x] /api/auth/login（GET/POST）、logout、register 路由已移除
- [x] templates/base.html 无认证检查脚本、无用户面板、无退出按钮
- [x] templates/login.html 已删除
- [x] 代码中无 login.html 或 /api/auth/login 残留引用（grep 验证）
- [x] 服务无会话启动正常，admin 初始化无报错
- [x] 无会话访问 6 个页面均 200 正常渲染
- [x] 无会话调用核心 API（devices/ota/stats/records/tasks/ota-envs/serial/settings）均 200
- [x] 原有数据（设备/记录/任务/统计/环境）正常可见、可读写
