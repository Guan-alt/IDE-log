# -*- coding: utf-8 -*-
"""临时脚本：查看当前记录状态 + 直接调用progress接口分析"""
import sqlite3, json, sys
sys.path.insert(0, '.')

conn = sqlite3.connect('instance/ota_monitor.db')
sn = 'lkcq00bp260800000502'
rows = conn.execute(
    "SELECT id, device_sn, result, upgrade_percent, start_time, end_time, "
    "target_version, fail_reason FROM ota_records WHERE device_sn=? ORDER BY id DESC LIMIT 5", (sn,)
).fetchall()
print('=== 最近记录 ===')
for r in rows:
    print(r)

# 直接调用OTA网关看进度
from app import create_app
app = create_app()
with app.app_context():
    from app.api.ota import get_ota_client, resolve_env_id, get_current_user_id, cycling_tasks
    from app.models.models import Device
    user_id = get_current_user_id()
    device = Device.query.filter_by(sn=sn, user_id=user_id).first()
    env_id = device.env_id if device else None
    print(f'\n=== 设备信息 ===')
    print(f'device env_id: {env_id}')
    
    client = get_ota_client(env_id, user_id)
    progress = client.get_progress(sn)
    print(f'\n=== 网关返回进度 ===')
    print(json.dumps(progress, indent=2, ensure_ascii=False))
    
    # 查版本
    ver = client.get_version(sn)
    print(f'\n=== 设备当前版本 ===')
    print(f'当前版本: {ver}')
    
    # 查循环任务状态
    task = cycling_tasks.get(user_id, {}).get(sn)
    print(f'\n=== 循环任务状态 ===')
    if task:
        print(f'state: {task["state"]}')
        print(f'current_cycle: {task["current_cycle"]}')
        print(f'current_direction: {task["current_direction"]}')
        print(f'_pending: {task.get("_pending")}')
        print(f'upgrade_version: {task["upgrade_version"]}')
        print(f'downgrade_version: {task["downgrade_version"]}')
        print(f'records: {task["records"]}')
    else:
        print('无循环任务')
