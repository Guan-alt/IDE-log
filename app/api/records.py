from flask import Blueprint, request, jsonify
from app import db
from app.models.models import OtaRecord
from app.utils.decorators import login_required, get_current_user_id
import math
import os
import json

records_bp = Blueprint('records', __name__, url_prefix='/api/records')

@records_bp.route('', methods=['GET'])
@login_required
def get_records():
    sn = request.args.get('sn')
    result = request.args.get('result')
    task_id = request.args.get('task_id', type=int)
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 15, type=int)

    query = OtaRecord.query.filter(OtaRecord.user_id == get_current_user_id())
    if sn:
        query = query.filter_by(device_sn=sn)
    if task_id:
        query = query.filter_by(task_id=task_id)
    if result:
        if result == 'success':
            query = query.filter(OtaRecord.result.contains('成功'))
        elif result == 'fail':
            query = query.filter(
                (OtaRecord.result.contains('失败')) |
                (OtaRecord.result.contains('超时')) |
                (OtaRecord.result == 'OTA请求失败')
            )

    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))

    records = query.order_by(OtaRecord.id.desc()) \
        .offset((page - 1) * page_size) \
        .limit(page_size) \
        .all()

    return jsonify({
        'records': [r.to_dict() for r in records],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages
    })

@records_bp.route('/<int:record_id>', methods=['GET'])
@login_required
def get_record(record_id):
    record = OtaRecord.query.filter_by(id=record_id, user_id=get_current_user_id()).first()
    if not record:
        return jsonify({'error': '记录不存在或无权访问'}), 404
    return jsonify(record.to_dict())

@records_bp.route('/<int:record_id>', methods=['DELETE'])
@login_required
def delete_record(record_id):
    record = OtaRecord.query.filter_by(id=record_id, user_id=get_current_user_id()).first()
    if not record:
        return jsonify({'error': '记录不存在或无权操作'}), 404
    db.session.delete(record)
    db.session.commit()
    return jsonify({'message': '删除成功'})

@records_bp.route('', methods=['DELETE'])
@login_required
def clear_records():
    OtaRecord.query.filter(OtaRecord.user_id == get_current_user_id()).delete()
    db.session.commit()
    return jsonify({'message': '已清空所有记录'})


@records_bp.route('/<int:record_id>/open-log-folder', methods=['GET'])
@login_required
def open_log_folder(record_id):
    """打开该记录存放日志的文件夹（在服务器/本机用系统资源管理器打开）"""
    record = OtaRecord.query.filter_by(id=record_id, user_id=get_current_user_id()).first()
    if not record:
        return jsonify({'error': '记录不存在或无权访问'}), 404

    # 1. 优先打开约定目录 logs/ota_logs/record_<id>/（使用绝对路径）
    log_dir = os.path.abspath(os.path.join('logs', 'ota_logs', f"record_{record_id}"))
    # 2. 若不存在，回退到 log_paths 中第一个文件的父目录
    if not os.path.isdir(log_dir):
        log_dir = ''
        try:
            paths = json.loads(record.log_paths) if record.log_paths else []
            for p in paths:
                if p and os.path.exists(p):
                    log_dir = os.path.dirname(p)
                    break
        except Exception:
            pass

    if not log_dir or not os.path.isdir(log_dir):
        return jsonify({'error': '该记录暂无日志文件夹'}), 404

    try:
        if os.name == 'nt':
            _open_folder_topmost_win(log_dir)
        else:
            import subprocess
            subprocess.Popen(['xdg-open', log_dir])  # noqa: S603
    except Exception as e:
        return jsonify({'error': f'打开文件夹失败: {e}'}), 500

    return jsonify({'success': True, 'folder': log_dir})


def _open_folder_topmost_win(folder):
    """Windows：打开资源管理器并把窗口置顶到最上层"""
    import subprocess
    import time
    import ctypes
    from ctypes import wintypes

    abs_folder = os.path.abspath(folder)
    # 记录打开前的顶层窗口集合，用于识别新窗口
    user32 = ctypes.windll.user32
    before = set()

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _collect(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            before.add(hwnd)
        return True
    user32.EnumWindows(EnumWindowsProc(_collect), 0)

    # 启动资源管理器打开该目录
    subprocess.Popen(['explorer.exe', abs_folder])

    # 轮询最多 ~3 秒，找到新出现的可见窗口并置顶
    found_hwnd = None
    title_buf = ctypes.create_unicode_buffer(512)
    for _ in range(15):
        time.sleep(0.2)
        def _find_new(hwnd, _lparam):
            nonlocal found_hwnd
            if user32.IsWindowVisible(hwnd) and hwnd not in before:
                n = user32.GetWindowTextW(hwnd, title_buf, 512)
                if n > 0:
                    title = title_buf.value
                    # 资源管理器标题通常为目录名或完整路径
                    if abs_folder in title or os.path.basename(abs_folder) in title:
                        found_hwnd = hwnd
                        return False  # 停止枚举
            return True
        user32.EnumWindows(EnumWindowsProc(_find_new), 0)
        if found_hwnd:
            break

    if found_hwnd:
        # 置顶：先恢复最小化状态，再提到前台并置顶
        SW_RESTORE = 9
        user32.ShowWindow(found_hwnd, SW_RESTORE)
        user32.BringWindowToTop(found_hwnd)
        user32.SetForegroundWindow(found_hwnd)
        # HWND_TOPMOST / SWP_NOMOVE|SWP_NOSIZE
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        user32.SetWindowPos(found_hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE)
