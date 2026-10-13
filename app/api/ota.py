from flask import Blueprint, request, jsonify, session, current_app
from app import db
from app.models.models import Device, OtaRecord, Setting, TestTask
from app.services.ota_client import OtaClient
from app.services.ai_analyzer import get_ai_analyzer
from app.utils.decorators import login_required, get_current_user_id
from datetime import datetime
import logging
import json
import os
import threading
import time
import random

logger = logging.getLogger(__name__)
ota_bp = Blueprint('ota', __name__, url_prefix='/api/ota')

# 循环OTA任务追踪（内存中，服务重启丢失）
# 嵌套字典: {user_id: {device_sn: task}}
cycling_tasks = {}
cycle_lock = threading.Lock()

def get_ota_client(env_id=None, user_id=None):
    """根据 env_id 返回对应的 OtaClient。
    env_id: OtaEnvironment.id；未传或查不到时回退到该用户第一个环境；都没有时回退到 Setting 默认"""
    from app.models.models import OtaEnvironment
    if user_id is None:
        user_id = get_current_user_id()
    # 1. 按 env_id 查找
    if env_id:
        env = OtaEnvironment.query.filter_by(id=env_id, user_id=user_id).first()
        if env:
            return OtaClient(env.ota_url, env.token, 10, region=env.region or 'cn')
    # 2. 回退到该用户第一个环境
    first_env = OtaEnvironment.query.filter_by(user_id=user_id).order_by(OtaEnvironment.sort_order.asc()).first()
    if first_env:
        return OtaClient(first_env.ota_url, first_env.token, 10, region=first_env.region or 'cn')
    # 3. 最终回退到 Setting
    setting = Setting.query.filter_by(user_id=user_id).first()
    if setting:
        return OtaClient(setting.ota_url, setting.token, 10)
    return OtaClient('https://test-lkadmin-lockin-management.lockin.com', '', 10)

def resolve_env_id(sn, env_id=None, user_id=None):
    """设备已关联OTA环境时优先使用设备环境，否则使用传入的env_id"""
    if user_id is None:
        user_id = get_current_user_id()
    device = Device.query.filter_by(sn=sn, user_id=user_id).first()
    if device and device.env_id:
        return device.env_id
    return env_id

def save_logs_for_record(record, device_sn):
    """保存采集器日志到文件，并更新record.log_paths
    保存条件：采集器运行中 OR buffer中有数据（即使已停止但仍有日志也保存）
    只截取该轮 OTA 期间(start_time)的日志，往前多留10秒上下文"""
    from app.api.serial import serial_manager, jlink_loggers
    # 使用绝对路径，避免不同线程/上下文CWD差异导致AI分析时找不到日志文件
    log_dir = os.path.abspath(os.path.join('logs', 'ota_logs', f"record_{record.id}"))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    saved_paths = []
    start_time = record.start_time
    pre_seconds = 10  # 往前多留10秒上下文

    # 收集所有活跃的采集器，保存前做 drain-until-quiet，确保 buffer 数据完整
    active_serial = [lg for lg in serial_manager.loggers.values() if lg.is_running]
    user_id = record.user_id
    user_jlink_loggers = jlink_loggers.get(user_id, {})
    active_jlink = [lg for lg in user_jlink_loggers.values() if lg.is_running]
    if active_serial or active_jlink:
        for _ in range(3):
            total_new = 0
            for lg in active_serial:
                total_new += lg.drain()
            for lg in active_jlink:
                total_new += lg.drain()
            if total_new == 0:
                break
            time.sleep(0.3)
        logger.info(f"记录 {record.id} drain完成，准备保存日志")

    # 串口日志：保存所有有数据的采集器（不限于 is_running）
    serial_count = 0
    for cid, s_logger in list(serial_manager.loggers.items()):
        try:
            buf = s_logger.get_logs_since(start_time, pre_seconds) if start_time else s_logger.get_logs()
        except Exception:
            buf = ''
        if s_logger.is_running or buf:
            serial_count += 1
            try:
                if start_time:
                    filepath = s_logger.save_to_file_since(log_dir, start_time, pre_seconds)
                else:
                    filepath = s_logger.save_to_file(log_dir)
                saved_paths.append(filepath)
            except Exception as e:
                logger.error(f"保存串口日志失败: {e}")

    # JLink日志：当前用户的所有有数据的采集器
    jlink_count = 0
    for cid, j_logger in list(user_jlink_loggers.items()):
        try:
            buf = j_logger.get_logs_since(start_time, pre_seconds) if start_time else j_logger.get_logs()
        except Exception:
            buf = ''
        if j_logger.is_running or buf:
            jlink_count += 1
            try:
                if start_time:
                    filepath = j_logger.save_to_file_since(log_dir, start_time, pre_seconds)
                else:
                    filepath = j_logger.save_to_file(log_dir)
                saved_paths.append(filepath)
            except Exception as e:
                logger.error(f"保存JLink日志失败: {e}")

    logger.info(f"记录 {record.id} save_logs: 串口有数据={serial_count} JLink有数据={jlink_count} 已保存={len(saved_paths)} (时间窗口 start={start_time})")

    if saved_paths:
        record.log_paths = json.dumps(saved_paths, ensure_ascii=False)
        logger.info(f"记录 {record.id} 已保存 {len(saved_paths)} 个日志文件")
    else:
        logger.warning(f"记录 {record.id} 无日志采集器数据，log_paths 为空")

def trigger_ai_analysis(record):
    """触发AI分析OTA失败日志"""
    try:
        analyzer = get_ai_analyzer()
        result = analyzer.analyze_record(record)
        record.ai_analysis = result
        db.session.commit()
        logger.info(f"记录 {record.id} AI分析完成")
        return result
    except Exception as e:
        logger.error(f"记录 {record.id} AI分析失败: {e}")
        return None


def trigger_cycle_ai_analysis(user_id, sn, app=None):
    """循环OTA结束后，触发AI分析所有失败的leg记录（异步，避免阻塞主流程）
    app: 复用已有的 Flask app 实例，避免 create_app() 重复初始化导致数据库冲突"""
    task = cycling_tasks.get(user_id, {}).get(sn)
    if not task:
        return

    def _analyze():
        try:
            # 优先复用传入的 app 实例，避免 create_app() 重复初始化
            if app:
                ctx = app.app_context()
                ctx.push()
            else:
                from app import create_app
                _app = create_app()
                ctx = _app.app_context()
                ctx.push()
            try:
                for rid in task.get('records', []):
                    rec = OtaRecord.query.get(rid)
                    if rec and rec.result and ('失败' in rec.result or 'OTA请求失败' in rec.result):
                        # 允许重新分析之前失败的记录（ai_analysis 含错误信息时）
                        if not rec.ai_analysis or '分析失败' in rec.ai_analysis:
                            trigger_ai_analysis(rec)
            finally:
                ctx.pop()
        except Exception as e:
            logger.error(f"循环OTA AI分析失败: {e}")

    t = threading.Thread(target=_analyze, daemon=True)
    t.start()

# ===== 单次OTA接口 =====

@ota_bp.route('/start', methods=['POST'])
@login_required
def start_ota():
    data = request.get_json()
    sn = data.get('sn')
    target_version = data.get('target_version')
    env_id = data.get('env_id')
    task_id = data.get('task_id')  # 关联的测试任务ID，必填
    if not sn or not target_version:
        return jsonify({'error': '缺少sn或target_version参数'}), 400
    if not task_id:
        return jsonify({'error': '请先选择测试任务'}), 400

    user_id = get_current_user_id()
    # 校验测试任务存在且属于当前用户
    if not TestTask.query.filter_by(id=task_id, user_id=user_id).first():
        return jsonify({'error': '测试任务不存在或无权使用'}), 400
    # 设备已关联环境时优先使用设备环境
    env_id = resolve_env_id(sn, env_id, user_id)
    client = get_ota_client(env_id, user_id)
    result = client.ota_start(sn, target_version)
    success = result[0]
    message = result[1]
    token_expired = result[2] if len(result) > 2 else False

    if token_expired:
        return jsonify({'error': 'OTA Token已过期，请更新', 'token_expired': True}), 403

    # 检查是否设备已是目标版本（forceUpgrade支持任意版本，仅同版本时返回此错误）
    already_target = not success and '最新版本' in message

    if already_target:
        device = Device.query.filter_by(sn=sn, user_id=user_id).first()
        if device:
            device.status = 'idle'
            db.session.commit()
        return jsonify({
            'success': True,
            'message': '设备已是最新版本，无需升级',
            'record_id': None
        })
    elif success:
        record = OtaRecord(
            user_id=user_id,
            task_id=task_id,
            device_sn=sn,
            target_version=target_version,
            result='OTA升级中',
            start_time=datetime.now(),
            upgrade_percent=0,
            download_percent=0,
            fail_reason=None
        )
        db.session.add(record)
        device = Device.query.filter_by(sn=sn, user_id=user_id).first()
        if device:
            device.status = 'upgrading'
        db.session.commit()
        return jsonify({
            'success': True,
            'message': message,
            'record_id': record.id
        })
    else:
        record = OtaRecord(
            user_id=user_id,
            task_id=task_id,
            device_sn=sn,
            target_version=target_version,
            result='OTA请求失败',
            start_time=datetime.now(),
            upgrade_percent=0,
            download_percent=0,
            fail_reason=message
        )
        db.session.add(record)
        device = Device.query.filter_by(sn=sn, user_id=user_id).first()
        if device:
            device.status = 'failed'
        db.session.commit()
        return jsonify({
            'success': False,
            'message': message,
            'record_id': record.id
        })

@ota_bp.route('/versions/<string:sn>', methods=['GET'])
@login_required
def get_versions(sn):
    user_id = get_current_user_id()
    # 设备已关联环境时使用设备环境查询版本列表
    env_id = resolve_env_id(sn, None, user_id)
    client = get_ota_client(env_id, user_id)
    versions = client.get_available_versions(sn)
    if isinstance(versions, dict) and versions.get('token_expired'):
        return jsonify({'error': 'OTA Token已过期，请更新', 'token_expired': True}), 403
    return jsonify({'success': True, 'versions': versions})

# ===== 循环OTA接口 =====

def _start_ota_leg(sn, target_version, tag='', env_id=None, user_id=None, task_id=None):
    """发起单次OTA，返回(record_id, success)。
    当设备已是最新版本时，视为跳过（ok=True），记录为'已是目标版本'"""
    if user_id is None:
        user_id = get_current_user_id()
    client = get_ota_client(env_id, user_id)
    result = client.ota_start(sn, target_version)
    success = result[0]
    message = result[1]
    token_expired = result[2] if len(result) > 2 else False
    if token_expired:
        logger.error(f"[CycleOTA] {sn} Token过期，中断循环")
        return None, False, True  # record_id=None, success=False, token_expired=True

    # 检查是否设备已是最新版本（升级已到目标版本或降级已到目标版本）
    already_target = not success and '最新版本' in message

    if already_target:
        device = Device.query.filter_by(sn=sn, user_id=user_id).first()
        if device:
            device.status = 'idle'
            db.session.commit()
        logger.info(f"[循环OTA] {sn} {tag} -> {target_version} 已是目标版本，跳过")
        return None, True
    elif success:
        record = OtaRecord(
            user_id=user_id,
            task_id=task_id,
            device_sn=sn,
            target_version=target_version,
            result='OTA升级中',
            start_time=datetime.now(),
            upgrade_percent=0,
            download_percent=0,
            fail_reason=None
        )
        db.session.add(record)
        device = Device.query.filter_by(sn=sn, user_id=user_id).first()
        if device:
            device.status = 'upgrading'
        db.session.commit()
        logger.info(f"[循环OTA] {sn} {tag} -> {target_version} record_id={record.id}")
        return record.id, True
    else:
        record = OtaRecord(
            user_id=user_id,
            task_id=task_id,
            device_sn=sn,
            target_version=target_version,
            result='OTA请求失败',
            start_time=datetime.now(),
            upgrade_percent=0,
            download_percent=0,
            fail_reason=message
        )
        db.session.add(record)
        device = Device.query.filter_by(sn=sn, user_id=user_id).first()
        if device:
            device.status = 'failed'
        db.session.commit()
        logger.info(f"[循环OTA] {sn} {tag} -> {target_version} 请求失败: {message}")
        return record.id, False

def _verify_ota_success_by_version(sn, target_version, env_id, user_id, max_retries=8, interval=5):
    """通过查询设备当前版本是否到达目标版本来确认OTA是否真正成功。
    首次等待10秒让设备完成重启上报，之后每隔 interval 秒查一次，最多查 max_retries 次。
    返回: (confirmed: bool, token_expired: bool)"""
    client = get_ota_client(env_id, user_id)
    time.sleep(10)  # 首次等待10秒，让设备完成重启和版本上报
    for i in range(max_retries):
        time.sleep(interval)
        try:
            info = client.get_device_info(sn)
            if info.get('token_expired'):
                logger.error(f"[循环OTA] {sn} 版本确认时Token过期")
                return False, True
            current_ver = info.get('version', '')
            logger.info(f"[循环OTA] {sn} 版本确认第{i+1}/{max_retries}次: 当前={current_ver} 目标={target_version}")
            if current_ver and target_version and current_ver.strip() == target_version.strip():
                return True, False
        except Exception as e:
            logger.warning(f"[循环OTA] {sn} 版本确认第{i+1}次查询异常: {e}")
    return False, False

def _wait_ota_terminal(sn, env_id, user_id, record_id, timeout=3600):
    """轮询OTA网关，等待终态（成功/失败/超时）。
    返回 (state_is_success, state_is_fail, is_timeout, state_str)"""
    client = get_ota_client(env_id, user_id)
    SUCCESS_STATES = ('success', 'burn_done', 'done', 'finish', 'finished')
    FAIL_STATES = ('burn_fail', 'down_fail', 'fail', 'failed', 'error', 'timeout')
    start_time = datetime.now()
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 10

    while True:
        time.sleep(5)  # 5秒轮询间隔，减少网关压力

        # 检查是否用户已停止
        with cycle_lock:
            user_tasks = cycling_tasks.get(user_id, {})
            task = user_tasks.get(sn)
            if not task or task['state'] in ('stopping', 'stopped'):
                return False, False, False, 'stopped'

        try:
            progress = client.get_progress(sn)
            consecutive_errors = 0  # 重置错误计数
        except Exception as e:
            consecutive_errors += 1
            logger.warning(f"[循环OTA] {sn} 轮询进度异常({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error(f"[循环OTA] {sn} 连续{MAX_CONSECUTIVE_ERRORS}次轮询异常，判定为超时")
                return False, False, True, 'timeout'
            continue

        if progress.get('token_expired'):
            logger.error(f"[循环OTA] {sn} 轮询进度时Token过期")
            return False, False, False, 'token_expired'

        state = progress.get('upgrade_state', '')
        upgrade_pct = progress.get('upgrade_percent', 0)

        # 更新数据库中的进度
        try:
            rec = OtaRecord.query.get(record_id)
            if rec:
                rec.upgrade_percent = upgrade_pct
                rec.download_percent = progress.get('download_percent', 0)
                src_ver = progress.get('current_version', '')
                if src_ver and not rec.source_version:
                    rec.source_version = src_ver
                db.session.commit()
        except Exception:
            pass
        
        state_is_success = False
        state_is_fail = False
        
        if state in SUCCESS_STATES:
            if state == 'burn_done' and upgrade_pct < 100:
                pass  # 烧录完成但整体进度未满，继续等待
            else:
                state_is_success = True
        elif state in FAIL_STATES:
            state_is_fail = True
        
        # 超时检测
        is_timeout = False
        if not state_is_success and not state_is_fail:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                is_timeout = True
        
        if state_is_success or state_is_fail or is_timeout:
            logger.info(f"[循环OTA] {sn} 网关终态: state={state} pct={upgrade_pct} success={state_is_success} fail={state_is_fail} timeout={is_timeout}")
            return state_is_success, state_is_fail, is_timeout, state

def _cycle_worker(user_id, sn):
    """循环OTA后台线程：独立驱动整个循环流程。
    不依赖前端轮询progress接口，自己轮询网关、确认版本、更新记录、继续下一轮。"""
    logger.info(f"[循环OTA] {sn} 后台线程启动")

    def _interruptible_sleep(seconds, user_id, sn):
        """可中断的sleep，每3秒检查一次停止状态"""
        elapsed = 0
        while elapsed < seconds:
            time.sleep(min(3, seconds - elapsed))
            elapsed += min(3, seconds - elapsed)
            with cycle_lock:
                task = cycling_tasks.get(user_id, {}).get(sn)
                if not task or task['state'] in ('stopping', 'stopped'):
                    return False
        return True

    try:
        from app import create_app
        app = create_app()
        with app.app_context():
            while True:
                with cycle_lock:
                    user_tasks = cycling_tasks.get(user_id, {})
                    task = user_tasks.get(sn)
                    if not task:
                        logger.info(f"[循环OTA] {sn} 任务丢失，退出")
                        return
                    if task['state'] in ('stopping', 'stopped'):
                        task['state'] = 'stopped'
                        logger.info(f"[循环OTA] {sn} 用户已停止，退出")
                        trigger_cycle_ai_analysis(user_id, sn, app)
                        return
                    if task['state'] in ('done', 'failed'):
                        logger.info(f"[循环OTA] {sn} 已完成/失败，退出")
                        return

                    env_id = task.get('env_id')
                    task_id = task.get('task_id')
                    current_cycle = task['current_cycle']
                    current_direction = task['current_direction']
                    upgrade_version = task['upgrade_version']
                    downgrade_version = task['downgrade_version']
                    total_cycles = task['total_cycles']
                    records = task['records']
                    current_record_id = task.get('current_record_id')

                # 如果有当前正在进行的OTA记录，等待它完成
                if current_record_id:
                    rec = OtaRecord.query.get(current_record_id)
                    if rec and rec.result == 'OTA升级中':
                        logger.info(f"[循环OTA] {sn} 等待OTA完成 record_id={current_record_id} direction={current_direction} cycle={current_cycle}")

                        # 1. 等待网关返回终态
                        state_success, state_fail, is_timeout, state = _wait_ota_terminal(
                            sn, env_id, user_id, current_record_id
                        )

                        if state == 'token_expired':
                            with cycle_lock:
                                task = cycling_tasks.get(user_id, {}).get(sn)
                                if task:
                                    task['state'] = 'failed'
                                    task['fail_reason'] = 'OTA Token已过期'
                                    task['current_record_id'] = None
                            logger.error(f"[循环OTA] {sn} Token过期，中断循环")
                            return

                        if state == 'stopped':
                            with cycle_lock:
                                task = cycling_tasks.get(user_id, {}).get(sn)
                                if task:
                                    task['state'] = 'stopped'
                                    task['current_record_id'] = None
                            trigger_cycle_ai_analysis(user_id, sn, app)
                            return

                        # 检查是否用户已停止
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if not task or task['state'] in ('stopping', 'stopped'):
                                task['state'] = 'stopped' if task else 'stopped'
                                logger.info(f"[循环OTA] {sn} 等待期间用户已停止")
                                trigger_cycle_ai_analysis(user_id, sn, app)
                                return

                        # 2. 版本确认（无论网关报成功还是失败，都查版本）
                        target_ver = rec.target_version if rec else ''
                        version_confirmed, ver_token_expired = _verify_ota_success_by_version(sn, target_ver, env_id, user_id)

                        if ver_token_expired:
                            with cycle_lock:
                                task = cycling_tasks.get(user_id, {}).get(sn)
                                if task:
                                    task['state'] = 'failed'
                                    task['fail_reason'] = 'OTA Token已过期'
                                    task['current_record_id'] = None
                            logger.error(f"[循环OTA] {sn} 版本确认时Token过期，中断循环")
                            return

                        # 3. 更新记录结果
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if not task or task['state'] in ('stopping', 'stopped'):
                                task['state'] = 'stopped' if task else 'stopped'
                                logger.info(f"[循环OTA] {sn} 版本确认后用户已停止")
                                trigger_cycle_ai_analysis(user_id, sn, app)
                                return

                        if version_confirmed:
                            rec.result = 'OTA升级成功'
                            rec.end_time = datetime.now()
                            if rec.start_time:
                                rec.duration = round((rec.end_time - rec.start_time).total_seconds(), 2)
                            if not rec.log_paths:
                                save_logs_for_record(rec, sn)
                            db.session.commit()
                            logger.info(f"[循环OTA] {sn} 版本确认成功 record_id={current_record_id}")
                            # 成功时重置重试计数
                            with cycle_lock:
                                task = cycling_tasks.get(user_id, {}).get(sn)
                                if task:
                                    task['retry_count'] = 0
                        else:
                            rec.result = 'OTA升级失败'
                            rec.fail_reason = f"版本确认失败: 设备版本未到达目标 {target_ver} (网关状态: {state})"
                            rec.end_time = datetime.now()
                            if rec.start_time:
                                rec.duration = round((rec.end_time - rec.start_time).total_seconds(), 2)
                            if not rec.log_paths:
                                save_logs_for_record(rec, sn)
                            db.session.commit()
                            logger.info(f"[循环OTA] {sn} 版本确认失败 record_id={current_record_id}")

                            # 重试逻辑：失败后等待并重试同一leg，连续3次失败才停止
                            with cycle_lock:
                                task = cycling_tasks.get(user_id, {}).get(sn)
                                if not task or task['state'] in ('stopping', 'stopped'):
                                    if task:
                                        task['state'] = 'stopped'
                                    trigger_cycle_ai_analysis(user_id, sn, app)
                                    return
                                task['retry_count'] = task.get('retry_count', 0) + 1
                                if task['retry_count'] >= 3:
                                    task['state'] = 'failed'
                                    task['fail_reason'] = f"第{current_cycle}轮 {current_direction} 连续{task['retry_count']}次失败"
                                    task['current_record_id'] = None
                                    trigger_cycle_ai_analysis(user_id, sn, app)
                                    return
                                task['current_record_id'] = None
                            logger.info(f"[循环OTA] {sn} 第{current_cycle}轮 {current_direction} 第{task['retry_count']}次失败，等待后重试...")
                            continue

                        # 4. 清除当前记录ID
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if task:
                                task['current_record_id'] = None

                    # 5. 随机等待30~60秒后继续下一轮（可中断）
                    wait_time = random.randint(30, 60)
                    logger.info(f"[循环OTA] {sn} 等待{wait_time}秒后继续")
                    if not _interruptible_sleep(wait_time, user_id, sn):
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if task:
                                task['state'] = 'stopped'
                                task['current_record_id'] = None
                        logger.info(f"[循环OTA] {sn} 等待期间用户已停止")
                        trigger_cycle_ai_analysis(user_id, sn, app)
                        return

                # 6. 发起下一轮OTA
                with cycle_lock:
                    task = cycling_tasks.get(user_id, {}).get(sn)
                    if not task or task['state'] in ('stopping', 'stopped'):
                        task['state'] = 'stopped' if task else 'stopped'
                        return

                    # 推进方向
                    if task.get('retry_count', 0) > 0:
                        # 重试模式：不推进方向，使用同一方向和目标
                        next_direction = current_direction
                        next_target = upgrade_version if current_direction == 'upgrade' else downgrade_version
                        next_cycle = current_cycle
                    elif current_direction == 'upgrade':
                        # 升级完成 → 切换到降级
                        task['current_direction'] = 'downgrade'
                        next_direction = 'downgrade'
                        next_target = downgrade_version
                        next_cycle = current_cycle
                    else:
                        # 降级完成 → 轮次+1，检查是否还有下一轮
                        if current_cycle < total_cycles:
                            task['current_cycle'] = current_cycle + 1
                            task['current_direction'] = 'upgrade'
                            next_direction = 'upgrade'
                            next_target = upgrade_version
                            next_cycle = current_cycle + 1
                        else:
                            # 全部完成
                            task['state'] = 'done'
                            logger.info(f"[循环OTA] {sn} 全部{total_cycles}轮完成")
                            trigger_cycle_ai_analysis(user_id, sn, app)
                            return

                # 发起下一轮OTA
                tag = f"{next_direction} 第{next_cycle}轮"
                logger.info(f"[循环OTA] {sn} 发起 {tag} -> {next_target}")
                leg_result = _start_ota_leg(sn, next_target, tag, env_id, user_id, task_id)
                rid = leg_result[0] if leg_result[0] else None
                ok = leg_result[1]
                leg_token_expired = leg_result[2] if len(leg_result) > 2 else False

                if leg_token_expired:
                    with cycle_lock:
                        task = cycling_tasks.get(user_id, {}).get(sn)
                        if task:
                            task['state'] = 'failed'
                            task['fail_reason'] = 'OTA Token已过期'
                            task['current_record_id'] = None
                    logger.error(f"[循环OTA] {sn} 发起OTA时Token过期，中断循环")
                    return

                if ok and rid is not None:
                    with cycle_lock:
                        task = cycling_tasks.get(user_id, {}).get(sn)
                        if task:
                            task['records'].append(rid)
                            task['current_record_id'] = rid
                    logger.info(f"[循环OTA] {sn} {tag} 已发起 record_id={rid}")
                elif ok and rid is None:
                    # 已是目标版本，跳过，等待后继续下一轮（避免快速循环）
                    logger.info(f"[循环OTA] {sn} {tag} 已是目标版本，跳过")
                    # 重置重试计数
                    with cycle_lock:
                        task = cycling_tasks.get(user_id, {}).get(sn)
                        if task:
                            task['retry_count'] = 0
                    # 等待10秒后继续，避免快速循环
                    if not _interruptible_sleep(10, user_id, sn):
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if task:
                                task['state'] = 'stopped'
                                task['current_record_id'] = None
                        logger.info(f"[循环OTA] {sn} 跳过等待期间用户已停止")
                        trigger_cycle_ai_analysis(user_id, sn, app)
                        return
                    continue
                else:
                    # OTA请求失败 - 保存日志并重试
                    if rid:
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if task:
                                task['records'].append(rid)
                        rec_fail = OtaRecord.query.get(rid)
                        if rec_fail and not rec_fail.log_paths:
                            save_logs_for_record(rec_fail, sn)
                            db.session.commit()

                    with cycle_lock:
                        task = cycling_tasks.get(user_id, {}).get(sn)
                        if not task or task['state'] in ('stopping', 'stopped'):
                            if task:
                                task['state'] = 'stopped'
                            trigger_cycle_ai_analysis(user_id, sn, app)
                            return
                        task['retry_count'] = task.get('retry_count', 0) + 1
                        if task['retry_count'] >= 3:
                            task['state'] = 'failed'
                            task['fail_reason'] = f"{next_direction}请求失败 连续{task['retry_count']}次 (第{next_cycle}轮)"
                            task['current_record_id'] = None
                            trigger_cycle_ai_analysis(user_id, sn, app)
                            return
                    logger.info(f"[循环OTA] {sn} {next_direction}请求失败(第{task['retry_count']}次)，等待后重试...")
                    continue

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"[循环OTA] {sn} 后台线程异常: {e}\n{tb}")
        try:
            with open('logs/cycle_worker_errors.log', 'a', encoding='utf-8') as f:
                f.write(f"\n[{datetime.now()}] {sn} user={user_id} 异常: {e}\n{tb}\n")
        except Exception:
            pass
        with cycle_lock:
            task = cycling_tasks.get(user_id, {}).get(sn)
            if task:
                task['state'] = 'failed'
                task['fail_reason'] = f"后台线程异常: {e}"
                task['current_record_id'] = None

@ota_bp.route('/start-cycle', methods=['POST'])
@login_required
def start_ota_cycle():
    data = request.get_json()
    sn = data.get('sn')
    upgrade_version = data.get('upgrade_version')
    downgrade_version = data.get('downgrade_version')
    cycle_count = int(data.get('cycle_count', 1))
    env_id = data.get('env_id')
    task_id = data.get('task_id')  # 关联的测试任务ID，必填

    if not sn or not upgrade_version or not downgrade_version:
        return jsonify({'error': '缺少sn、upgrade_version或downgrade_version参数'}), 400
    if cycle_count < 1:
        return jsonify({'error': '循环次数至少为1'}), 400

    user_id = get_current_user_id()

    # 校验测试任务存在且属于当前用户
    if not task_id:
        return jsonify({'error': '请先选择测试任务'}), 400
    if not TestTask.query.filter_by(id=task_id, user_id=user_id).first():
        return jsonify({'error': '测试任务不存在或无权使用'}), 400

    # 设备已关联环境时优先使用设备环境
    env_id = resolve_env_id(sn, env_id, user_id)

    # 检查是否已有循环任务
    with cycle_lock:
        user_tasks = cycling_tasks.setdefault(user_id, {})
        existing = user_tasks.get(sn)
        if existing and existing['state'] == 'running':
            return jsonify({'error': f'设备 {sn} 已有循环OTA任务进行中'}), 409

        user_tasks[sn] = {
            'upgrade_version': upgrade_version,
            'downgrade_version': downgrade_version,
            'total_cycles': cycle_count,
            'current_cycle': 1,
            'current_direction': 'upgrade',
            'state': 'running',
            'records': [],
            'started_at': datetime.now().isoformat(),
            'env_id': env_id,
            'user_id': user_id,
            'task_id': task_id,
            'current_record_id': None,
            'retry_count': 0
        }

    # 发起第一轮升级；如果是"已是目标版本"则跳过并自动发起降级
    first_rid = None
    leg1 = _start_ota_leg(sn, upgrade_version, f"升级 第1轮", env_id, user_id, task_id)
    rid = leg1[0]
    ok = leg1[1]
    leg1_te = leg1[2] if len(leg1) > 2 else False
    if leg1_te:
        cycling_tasks[user_id][sn]['state'] = 'failed'
        cycling_tasks[user_id][sn]['fail_reason'] = 'OTA Token已过期'
    elif ok:
        if rid is not None:
            cycling_tasks[user_id][sn]['records'].append(rid)
            cycling_tasks[user_id][sn]['current_record_id'] = rid
            first_rid = rid
        else:
            # 已是最新版本，跳过升级，直接发起降级
            cycling_tasks[user_id][sn]['current_direction'] = 'downgrade'
            leg2 = _start_ota_leg(sn, downgrade_version, f"降级 第1轮", env_id, user_id, task_id)
            downgrade_rid = leg2[0]
            downgrade_ok = leg2[1]
            leg2_te = leg2[2] if len(leg2) > 2 else False
            if leg2_te:
                cycling_tasks[user_id][sn]['state'] = 'failed'
                cycling_tasks[user_id][sn]['fail_reason'] = 'OTA Token已过期'
            elif downgrade_ok:
                if downgrade_rid is not None:
                    cycling_tasks[user_id][sn]['records'].append(downgrade_rid)
                    cycling_tasks[user_id][sn]['current_record_id'] = downgrade_rid
                    first_rid = downgrade_rid
                else:
                    cycling_tasks[user_id][sn]['state'] = 'done'
            else:
                # 降级请求失败 - 保存日志，由后台线程重试
                if downgrade_rid:
                    cycling_tasks[user_id][sn]['records'].append(downgrade_rid)
                    rec_fail = OtaRecord.query.get(downgrade_rid)
                    if rec_fail and not rec_fail.log_paths:
                        save_logs_for_record(rec_fail, sn)
                        db.session.commit()
                cycling_tasks[user_id][sn]['retry_count'] = 1
                logger.info(f"[循环OTA] {sn} 降级请求失败(第1次)，将由后台线程重试")
    else:
        # 升级请求失败 - 保存日志，由后台线程重试
        if rid:
            cycling_tasks[user_id][sn]['records'].append(rid)
            rec_fail = OtaRecord.query.get(rid)
            if rec_fail and not rec_fail.log_paths:
                save_logs_for_record(rec_fail, sn)
                db.session.commit()
        cycling_tasks[user_id][sn]['retry_count'] = 1
        logger.info(f"[循环OTA] {sn} 升级请求失败(第1次)，将由后台线程重试")

    final_state = cycling_tasks[user_id][sn]['state']
    # 循环立即完成或失败时触发AI分析
    if final_state in ('done', 'failed'):
        trigger_cycle_ai_analysis(user_id, sn, current_app._get_current_object())
    else:
        # 启动后台线程驱动循环
        threading.Thread(target=_cycle_worker, args=(user_id, sn), daemon=True).start()
        logger.info(f"[循环OTA] {sn} 后台线程已启动")
    return jsonify({
        'success': final_state != 'failed',
        'message': f"循环OTA已启动: 共{cycle_count}轮" if final_state == 'running' else ('循环已完成' if final_state == 'done' else 'OTA请求失败'),
        'record_id': first_rid
    })

@ota_bp.route('/cycle-status/<string:sn>', methods=['GET'])
@login_required
def get_cycle_status(sn):
    user_id = get_current_user_id()
    task = cycling_tasks.get(user_id, {}).get(sn)
    if not task:
        return jsonify({'active': False, 'message': '没有进行中的循环OTA任务'})

    # 统计成功/失败
    success_count = 0
    fail_count = 0
    for rid in task.get('records', []):
        rec = OtaRecord.query.get(rid)
        if rec:
            if rec.result and '成功' in rec.result:
                success_count += 1
            elif rec.result and ('失败' in rec.result or '超时' in rec.result or 'OTA请求失败' in rec.result):
                fail_count += 1

    return jsonify({
        'active': True,
        'state': task['state'],
        'total_cycles': task['total_cycles'],
        'current_cycle': task['current_cycle'],
        'current_direction': task['current_direction'],
        'upgrade_version': task['upgrade_version'],
        'downgrade_version': task['downgrade_version'],
        'records': task['records'],
        'success_count': success_count,
        'fail_count': fail_count,
        'started_at': task['started_at']
    })

@ota_bp.route('/stop-cycle', methods=['POST'])
@login_required
def stop_ota_cycle():
    data = request.get_json()
    sn = data.get('sn')
    if not sn:
        return jsonify({'error': '缺少sn参数'}), 400

    user_id = get_current_user_id()
    with cycle_lock:
        user_tasks = cycling_tasks.get(user_id, {})
        task = user_tasks.get(sn)
        if task:
            task['state'] = 'stopping'
            task['_pending'] = False
            return jsonify({'success': True, 'message': '循环已停止，当前OTA完成后不再继续'})

    return jsonify({'success': False, 'message': '没有进行中的循环任务'})

# ===== 进度查询（支持循环自动切换） =====

@ota_bp.route('/progress/<string:sn>', methods=['GET'])
@login_required
def get_progress(sn):
    user_id = get_current_user_id()
    env_id = request.args.get('env_id', type=int)
    # 循环OTA中优先使用任务保存的env_id
    task = cycling_tasks.get(user_id, {}).get(sn)
    if task and task.get('env_id'):
        env_id = task['env_id']
    # 设备已关联环境时优先使用设备环境
    env_id = resolve_env_id(sn, env_id, user_id)
    client = get_ota_client(env_id, user_id)
    progress = client.get_progress(sn)

    record = OtaRecord.query.filter_by(device_sn=sn, user_id=user_id).order_by(OtaRecord.id.desc()).first()
    is_finished = False
    is_timeout = False
    # 当没有数据库记录时，仍根据OTA API状态判断是否完成
    if not record:
        state = progress.get('upgrade_state', '')
        upgrade_pct = progress.get('upgrade_percent', 0)
        SUCCESS_STATES = ('success', 'burn_done', 'done', 'finish', 'finished')
        FAIL_STATES = ('burn_fail', 'down_fail', 'fail', 'failed', 'error', 'timeout')
        state_is_success = state in SUCCESS_STATES and not (state == 'burn_done' and upgrade_pct < 100)
        state_is_fail = state in FAIL_STATES
        if state_is_success or state_is_fail:
            is_finished = True
            # 创建记录保存这次OTA结果
            record = OtaRecord(
                user_id=user_id,
                device_sn=sn,
                source_version=progress.get('current_version', ''),
                target_version=progress.get('target_version', ''),
                result='OTA升级成功' if state_is_success else 'OTA升级失败',
                start_time=datetime.now(),
                end_time=datetime.now(),
                upgrade_percent=upgrade_pct,
                download_percent=progress.get('download_percent', 0),
                fail_reason=f"upgradeState={state}, upgradeErrno={progress.get('upgrade_errno', 0)}" if state_is_fail else None
            )
            db.session.add(record)
            db.session.commit()
            logger.info(f"[OTA] {sn} 无数据库记录但OTA已完成(state={state})，自动创建记录 id={record.id}")

    elif record:
        record.upgrade_percent = progress['upgrade_percent']
        record.download_percent = progress['download_percent']
        src_ver = progress.get('current_version', '')
        if src_ver and not record.source_version:
            record.source_version = src_ver
        state = progress.get('upgrade_state', '')
        upgrade_pct = progress.get('upgrade_percent', 0)
        SUCCESS_STATES = ('success', 'burn_done', 'done', 'finish', 'finished')
        FAIL_STATES = ('burn_fail', 'down_fail', 'fail', 'failed', 'error', 'timeout')

        state_is_success = False
        state_is_fail = False
        if state in SUCCESS_STATES:
            if state == 'burn_done' and upgrade_pct < 100:
                pass
            else:
                state_is_success = True
        elif state in FAIL_STATES:
            state_is_fail = True

        # 循环OTA中：后台线程负责更新记录和续轮，progress接口只读取状态
        is_cycling_now = cycling_tasks.get(user_id, {}).get(sn, {}).get('state') == 'running'

        if is_cycling_now:
            # 循环OTA模式：不在此处更新记录结果（后台线程负责）
            pass
        else:
            # 单次OTA模式：直接更新记录
            if state_is_success:
                record.result = 'OTA升级成功'
            elif state_is_fail:
                record.result = 'OTA升级失败'
                record.fail_reason = f"upgradeState={state}, upgradeErrno={progress.get('upgrade_errno', 0)}"

            # 超时检测
            setting = Setting.query.filter_by(user_id=user_id).first()
            ota_timeout = setting.ota_timeout if setting else 3600
            if not state_is_success and not state_is_fail:
                if record.start_time and not record.end_time:
                    elapsed = (datetime.now() - record.start_time).total_seconds()
                    if elapsed > ota_timeout:
                        is_timeout = True
                        record.result = 'OTA升级超时'
                        record.fail_reason = f"超过{ota_timeout}秒未完成，当前状态: {state or '未知'}"

            is_finished = state_is_success or state_is_fail or is_timeout
            if is_finished and not record.end_time:
                record.end_time = datetime.now()
                if record.start_time:
                    record.duration = round((record.end_time - record.start_time).total_seconds(), 2)
            if is_finished and not record.log_paths:
                save_logs_for_record(record, sn)
            if (state_is_fail or is_timeout) and not record.ai_analysis:
                trigger_ai_analysis(record)

        # 循环OTA模式：根据记录当前结果判断is_finished
        if is_cycling_now:
            is_finished = record.result != 'OTA升级中' if record else False
        else:
            is_finished = state_is_success or state_is_fail or is_timeout

        db.session.commit()

    return jsonify({
        'sn': sn,
        'upgrade_percent': progress['upgrade_percent'],
        'download_percent': progress['download_percent'],
        'upgrade_state': progress.get('upgrade_state', ''),
        'upgrade_errno': progress.get('upgrade_errno', 0),
        'current_version': progress.get('current_version', ''),
        'target_version': progress.get('target_version', ''),
        'upgrade_time': progress.get('upgrade_time', ''),
        'device_name': progress.get('device_name', ''),
        'record_id': record.id if record else None,
        'is_finished': is_finished,
        'is_timeout': is_timeout,
        'ai_analysis': record.ai_analysis if record else None,
        'token_expired': progress.get('token_expired', False)
    })


# ===== 设备OTA状态检查（供前端设备选择时调用） =====

@ota_bp.route('/check-status/<string:sn>', methods=['GET'])
@login_required
def check_ota_status(sn):
    """检查指定设备是否有正在进行的OTA（循环或单次），供前端设备选择时调用"""
    user_id = get_current_user_id()

    # 1. 检查循环OTA
    task = cycling_tasks.get(user_id, {}).get(sn)
    if task and task.get('state') == 'running':
        return jsonify({
            'active': True,
            'mode': 'cycle',
            'cycle_info': {
                'current_cycle': task.get('current_cycle', 1),
                'total_cycles': task.get('total_cycles', 1),
                'current_direction': task.get('current_direction', 'upgrade'),
                'upgrade_version': task.get('upgrade_version', ''),
                'downgrade_version': task.get('downgrade_version', ''),
                'env_id': task.get('env_id')
            }
        })

    # 2. 检查单次OTA：查询进度，is_finished=False 说明正在运行
    env_id = request.args.get('env_id', type=int)
    env_id = resolve_env_id(sn, env_id, user_id)
    client = get_ota_client(env_id, user_id)
    progress = client.get_progress(sn)

    if progress.get('token_expired'):
        return jsonify({
            'active': False,
            'mode': None,
            'token_expired': True
        })

    state = progress.get('upgrade_state', '')
    upgrade_pct = progress.get('upgrade_percent', 0)
    SUCCESS_STATES = ('success', 'burn_done', 'done', 'finish', 'finished')
    FAIL_STATES = ('burn_fail', 'down_fail', 'fail', 'failed', 'error', 'timeout')
    state_is_success = state in SUCCESS_STATES and not (state == 'burn_done' and upgrade_pct < 100)
    state_is_fail = state in FAIL_STATES
    is_finished = state_is_success or state_is_fail

    # 查询最新记录，判断是否正在升级中
    record = OtaRecord.query.filter_by(device_sn=sn, user_id=user_id).order_by(OtaRecord.id.desc()).first()
    record_in_progress = bool(record and record.result == 'OTA升级中')
    # state 非空说明 OTA 服务确实返回了该设备的升级状态
    has_ota_state = bool(state)

    # OTA正在进行的判断：必须存在“确有其事且未完成”的信号，满足其一：
    #   1) 服务端返回了该设备的升级状态（state 非空）且尚未完成；
    #   2) 数据库最新记录标记为“OTA升级中”（覆盖刚发起、服务端尚未登记的短暂窗口）。
    # 若 state 为空（服务端没有该设备的升级记录，即设备空闲），不能因为 is_finished 默认为
    # False 就判定为正在升级，否则一进入页面就会出现“进度条自动跑”的假象。
    if not is_finished and (has_ota_state or record_in_progress):
        return jsonify({
            'active': True,
            'mode': 'single',
            'progress_info': {
                'upgrade_percent': progress.get('upgrade_percent', 0),
                'download_percent': progress.get('download_percent', 0),
                'upgrade_state': state,
                'current_version': progress.get('current_version', ''),
                'target_version': progress.get('target_version', ''),
                'env_id': env_id
            }
        })

    # 3. 没有正在进行的OTA
    return jsonify({
        'active': False,
        'mode': None
    })
