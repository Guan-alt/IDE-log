from flask import Blueprint, request, jsonify, session
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
    """保存当前运行中的串口/JLink日志到文件，并更新record.log_paths"""
    from app.api.serial import serial_manager, jlink_loggers
    log_dir = os.path.join('logs', 'ota_logs', f"record_{record.id}")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    saved_paths = []
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    for cid, s_logger in serial_manager.loggers.items():
        if s_logger.is_running:
            try:
                filepath = s_logger.save_to_file(log_dir)
                saved_paths.append(filepath)
            except Exception as e:
                logger.error(f"保存串口日志失败: {e}")

    user_id = record.user_id
    user_jlink_loggers = jlink_loggers.get(user_id, {})
    for cid, j_logger in user_jlink_loggers.items():
        if j_logger.is_running:
            try:
                filepath = j_logger.save_to_file(log_dir)
                saved_paths.append(filepath)
            except Exception as e:
                logger.error(f"保存JLink日志失败: {e}")

    if saved_paths:
        record.log_paths = json.dumps(saved_paths, ensure_ascii=False)
        logger.info(f"记录 {record.id} 已保存 {len(saved_paths)} 个日志文件")

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


def trigger_cycle_ai_analysis(user_id, sn):
    """循环OTA结束后，触发AI分析所有失败的leg记录（异步，避免阻塞主流程）"""
    task = cycling_tasks.get(user_id, {}).get(sn)
    if not task:
        return

    def _analyze():
        try:
            from app import create_app
            app = create_app()
            with app.app_context():
                for rid in task.get('records', []):
                    rec = OtaRecord.query.get(rid)
                    if rec and rec.result and ('失败' in rec.result or 'OTA请求失败' in rec.result):
                        if not rec.ai_analysis:
                            trigger_ai_analysis(rec)
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
    success, message = client.ota_start(sn, target_version)

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
    return jsonify({'success': True, 'versions': versions})

# ===== 循环OTA接口 =====

def _start_ota_leg(sn, target_version, tag='', env_id=None, user_id=None, task_id=None):
    """发起单次OTA，返回(record_id, success)。
    当设备已是最新版本时，视为跳过（ok=True），记录为'已是目标版本'"""
    if user_id is None:
        user_id = get_current_user_id()
    client = get_ota_client(env_id, user_id)
    success, message = client.ota_start(sn, target_version)

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

def _verify_ota_success_by_version(sn, target_version, env_id, user_id, max_retries=6, interval=5):
    """通过查询设备当前版本是否到达目标版本来确认OTA是否真正成功。
    每隔 interval 秒查一次，最多查 max_retries 次。"""
    client = get_ota_client(env_id, user_id)
    for i in range(max_retries):
        time.sleep(interval)
        try:
            current_ver = client.get_version(sn)
            logger.info(f"[循环OTA] {sn} 版本确认第{i+1}/{max_retries}次: 当前={current_ver} 目标={target_version}")
            if current_ver and target_version and current_ver.strip() == target_version.strip():
                return True
        except Exception as e:
            logger.warning(f"[循环OTA] {sn} 版本确认第{i+1}次查询异常: {e}")
    return False

def _wait_ota_terminal(sn, env_id, user_id, record_id, timeout=3600):
    """轮询OTA网关，等待终态（成功/失败/超时）。
    返回 (state_is_success, state_is_fail, is_timeout, state_str)"""
    client = get_ota_client(env_id, user_id)
    SUCCESS_STATES = ('success', 'burn_done', 'done', 'finish', 'finished')
    FAIL_STATES = ('burn_fail', 'down_fail', 'fail', 'failed', 'error', 'timeout')
    start_time = datetime.now()
    
    while True:
        time.sleep(3)
        
        # 检查是否用户已停止
        with cycle_lock:
            user_tasks = cycling_tasks.get(user_id, {})
            task = user_tasks.get(sn)
            if not task or task['state'] in ('stopping', 'stopped'):
                return False, False, False, 'stopped'
        
        try:
            progress = client.get_progress(sn)
        except Exception as e:
            logger.warning(f"[循环OTA] {sn} 轮询进度异常: {e}")
            continue
        
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
        
        # 保存日志
        if state_is_success or state_is_fail or is_timeout:
            try:
                rec = OtaRecord.query.get(record_id)
                if rec and not rec.log_paths:
                    save_logs_for_record(rec, sn)
            except Exception:
                pass

def _cycle_worker(user_id, sn):
    """循环OTA后台线程：独立驱动整个循环流程。
    不依赖前端轮询progress接口，自己轮询网关、确认版本、更新记录、继续下一轮。"""
    logger.info(f"[循环OTA] {sn} 后台线程启动")
    
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
                        trigger_cycle_ai_analysis(user_id, sn)
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
                        
                        # 检查是否用户已停止
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if not task or task['state'] in ('stopping', 'stopped'):
                                task['state'] = 'stopped' if task else 'stopped'
                                logger.info(f"[循环OTA] {sn} 等待期间用户已停止")
                                trigger_cycle_ai_analysis(user_id, sn)
                                return
                        
                        # 2. 版本确认（无论网关报成功还是失败，都查版本）
                        target_ver = rec.target_version if rec else ''
                        version_confirmed = _verify_ota_success_by_version(sn, target_ver, env_id, user_id)
                        
                        # 3. 更新记录结果
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if not task or task['state'] in ('stopping', 'stopped'):
                                task['state'] = 'stopped' if task else 'stopped'
                                logger.info(f"[循环OTA] {sn} 版本确认后用户已停止")
                                trigger_cycle_ai_analysis(user_id, sn)
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
                            
                            with cycle_lock:
                                task = cycling_tasks.get(user_id, {}).get(sn)
                                if task:
                                    task['state'] = 'failed'
                                    task['fail_reason'] = f"第{current_cycle}轮 {current_direction} 版本确认失败"
                                task['current_record_id'] = None
                            trigger_cycle_ai_analysis(user_id, sn)
                            return
                        
                        # 4. 清除当前记录ID
                        with cycle_lock:
                            task = cycling_tasks.get(user_id, {}).get(sn)
                            if task:
                                task['current_record_id'] = None
                    
                    # 5. 随机等待30~60秒后继续下一轮
                    wait_time = random.randint(30, 60)
                    logger.info(f"[循环OTA] {sn} 等待{wait_time}秒后继续")
                    time.sleep(wait_time)
                    
                    # 等待期间检查用户是否已停止
                    with cycle_lock:
                        task = cycling_tasks.get(user_id, {}).get(sn)
                        if not task or task['state'] in ('stopping', 'stopped'):
                            task['state'] = 'stopped' if task else 'stopped'
                            logger.info(f"[循环OTA] {sn} 等待期间用户已停止")
                            trigger_cycle_ai_analysis(user_id, sn)
                            return
                
                # 6. 发起下一轮OTA
                with cycle_lock:
                    task = cycling_tasks.get(user_id, {}).get(sn)
                    if not task or task['state'] in ('stopping', 'stopped'):
                        task['state'] = 'stopped' if task else 'stopped'
                        return
                    
                    # 推进方向
                    if current_direction == 'upgrade':
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
                            trigger_cycle_ai_analysis(user_id, sn)
                            return
                
                # 发起下一轮OTA
                tag = f"{next_direction} 第{next_cycle}轮"
                logger.info(f"[循环OTA] {sn} 发起 {tag} -> {next_target}")
                rid, ok = _start_ota_leg(sn, next_target, tag, env_id, user_id, task_id)
                
                if ok and rid is not None:
                    with cycle_lock:
                        task = cycling_tasks.get(user_id, {}).get(sn)
                        if task:
                            task['records'].append(rid)
                            task['current_record_id'] = rid
                    logger.info(f"[循环OTA] {sn} {tag} 已发起 record_id={rid}")
                elif ok and rid is None:
                    # 已是目标版本，跳过，直接进入下一轮（循环继续）
                    logger.info(f"[循环OTA] {sn} {tag} 已是目标版本，跳过")
                    # 不设 current_record_id，循环继续
                    continue
                else:
                    # OTA请求失败
                    with cycle_lock:
                        task = cycling_tasks.get(user_id, {}).get(sn)
                        if task:
                            task['state'] = 'failed'
                            task['fail_reason'] = f"{next_direction}请求失败 (第{next_cycle}轮)"
                            task['current_record_id'] = None
                    trigger_cycle_ai_analysis(user_id, sn)
                    return
                    
    except Exception as e:
        logger.error(f"[循环OTA] {sn} 后台线程异常: {e}", exc_info=True)
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
            'current_record_id': None
        }

    # 发起第一轮升级；如果是"已是目标版本"则跳过并自动发起降级
    first_rid = None
    rid, ok = _start_ota_leg(sn, upgrade_version, f"升级 第1轮", env_id, user_id, task_id)
    if ok:
        if rid is not None:
            cycling_tasks[user_id][sn]['records'].append(rid)
            cycling_tasks[user_id][sn]['current_record_id'] = rid
            first_rid = rid
        else:
            # 已是最新版本，跳过升级，直接发起降级
            cycling_tasks[user_id][sn]['current_direction'] = 'downgrade'
            downgrade_rid, downgrade_ok = _start_ota_leg(sn, downgrade_version, f"降级 第1轮", env_id, user_id, task_id)
            if downgrade_ok:
                if downgrade_rid is not None:
                    cycling_tasks[user_id][sn]['records'].append(downgrade_rid)
                    cycling_tasks[user_id][sn]['current_record_id'] = downgrade_rid
                    first_rid = downgrade_rid
                else:
                    cycling_tasks[user_id][sn]['state'] = 'done'
            else:
                cycling_tasks[user_id][sn]['state'] = 'failed'
                cycling_tasks[user_id][sn]['fail_reason'] = f"降级请求失败 (第1轮)"
    else:
        cycling_tasks[user_id][sn]['state'] = 'failed'
        cycling_tasks[user_id][sn]['fail_reason'] = f"升级请求失败 (第1轮)"

    final_state = cycling_tasks[user_id][sn]['state']
    # 循环立即完成或失败时触发AI分析
    if final_state in ('done', 'failed'):
        trigger_cycle_ai_analysis(user_id, sn)
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
        'ai_analysis': record.ai_analysis if record else None
    })
