from flask import Blueprint, request, jsonify, session
from app import db
from app.models.models import Device, OtaRecord, Setting
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
            return OtaClient(env.ota_url, env.token, 10)
    # 2. 回退到该用户第一个环境
    first_env = OtaEnvironment.query.filter_by(user_id=user_id).order_by(OtaEnvironment.sort_order.asc()).first()
    if first_env:
        return OtaClient(first_env.ota_url, first_env.token, 10)
    # 3. 最终回退到 Setting
    setting = Setting.query.filter_by(user_id=user_id).first()
    if setting:
        return OtaClient(setting.ota_url, setting.token, 10)
    return OtaClient('https://test-lkadmin-lockin-management.lockin.com', '', 10)

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
    task_id = data.get('task_id')  # 关联的测试任务ID，可为空
    if not sn or not target_version:
        return jsonify({'error': '缺少sn或target_version参数'}), 400

    user_id = get_current_user_id()
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
    client = get_ota_client()
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
        logger.info(f"[循环OTA] {sn} {tag} -> {target_version} record_id={record.id} success={success}")
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
        logger.info(f"[循环OTA] {sn} {tag} -> {target_version} record_id={record.id} success=False reason={message}")
        return record.id, False

def _continue_cycle_after_wait(user_id, sn):
    """OTA完成后，随机等待30~60秒再继续下一轮循环OTA（后台线程，不阻塞HTTP响应）"""
    wait_time = random.randint(30, 60)
    logger.info(f"[循环OTA] {sn} 本次OTA完成，等待{wait_time}秒后进行下一次OTA")
    time.sleep(wait_time)
    try:
        # 等待结束后检查是否用户已停止循环
        with cycle_lock:
            user_tasks = cycling_tasks.get(user_id, {})
            task = user_tasks.get(sn)
            if task and task['state'] == 'stopping':
                task['state'] = 'stopped'
                logger.info(f"[循环OTA] {sn} 等待期间用户已停止循环，终止续轮")
                trigger_cycle_ai_analysis(user_id, sn)
                return
        from app import create_app
        app = create_app()
        with app.app_context():
            _continue_cycle(user_id, sn)
    except Exception as e:
        logger.error(f"[循环OTA] {sn} 后台续轮异常: {e}", exc_info=True)
        with cycle_lock:
            user_tasks = cycling_tasks.get(user_id, {})
            task = user_tasks.get(sn)
            if task:
                task['_pending'] = False


def _continue_cycle(user_id, sn):
    """检查并继续循环OTA：当前OTA完成后自动触发下一轮。
    如果下一leg返回"已是目标版本"，则跳过并继续推进，直到找到真正的OTA或循环结束。"""
    with cycle_lock:
        user_tasks = cycling_tasks.get(user_id, {})
        task = user_tasks.get(sn)
        if not task or task['state'] != 'running':
            return

        task['_pending'] = False
        env_id = task.get('env_id')
        task_id = task.get('task_id')

        # 循环推进，跳过"已是目标版本"的leg
        while task['state'] == 'running':
            if task['current_direction'] == 'upgrade':
                # 升级完成，开始降级
                task['current_direction'] = 'downgrade'
                target = task['downgrade_version']
                rid, ok = _start_ota_leg(sn, target, f"降级 第{task['current_cycle']}轮", env_id, user_id, task_id)
                if ok:
                    if rid is not None:
                        task['records'].append(rid)
                        break  # 真正的OTA已发起，等待进度轮询
                    # rid为None表示已是目标版本，继续循环推进
                else:
                    task['state'] = 'failed'
                    task['fail_reason'] = f"降级请求失败 (第{task['current_cycle']}轮)"
                    break
            elif task['current_direction'] == 'downgrade':
                # 降级完成，检查是否还有下一轮
                if task['current_cycle'] < task['total_cycles']:
                    task['current_cycle'] += 1
                    task['current_direction'] = 'upgrade'
                    target = task['upgrade_version']
                    rid, ok = _start_ota_leg(sn, target, f"升级 第{task['current_cycle']}轮", env_id, user_id, task_id)
                    if ok:
                        if rid is not None:
                            task['records'].append(rid)
                            break  # 真正的OTA已发起
                        # 已是目标版本，继续循环推进
                    else:
                        task['state'] = 'failed'
                        task['fail_reason'] = f"升级请求失败 (第{task['current_cycle']}轮)"
                        break
                else:
                    # 全部完成
                    task['state'] = 'done'
                    logger.info(f"[循环OTA] {sn} 全部完成")
                    trigger_cycle_ai_analysis(user_id, sn)
                    break

@ota_bp.route('/start-cycle', methods=['POST'])
@login_required
def start_ota_cycle():
    data = request.get_json()
    sn = data.get('sn')
    upgrade_version = data.get('upgrade_version')
    downgrade_version = data.get('downgrade_version')
    cycle_count = int(data.get('cycle_count', 1))
    env_id = data.get('env_id')
    task_id = data.get('task_id')  # 关联的测试任务ID，可为空

    if not sn or not upgrade_version or not downgrade_version:
        return jsonify({'error': '缺少sn、upgrade_version或downgrade_version参数'}), 400
    if cycle_count < 1:
        return jsonify({'error': '循环次数至少为1'}), 400

    user_id = get_current_user_id()

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
            '_pending': False,
            'env_id': env_id,
            'user_id': user_id,
            'task_id': task_id
        }

    # 发起第一轮升级；如果是"已是目标版本"则跳过并自动发起降级
    first_rid = None
    rid, ok = _start_ota_leg(sn, upgrade_version, f"升级 第1轮", env_id, user_id, task_id)
    if ok:
        if rid is not None:
            cycling_tasks[user_id][sn]['records'].append(rid)
            first_rid = rid
            # 正常发起OTA，等待进度轮询
        else:
            # 已是最新版本，跳过升级，直接发起降级
            cycling_tasks[user_id][sn]['current_direction'] = 'downgrade'
            downgrade_rid, downgrade_ok = _start_ota_leg(sn, downgrade_version, f"降级 第1轮", env_id, user_id, task_id)
            if downgrade_ok:
                if downgrade_rid is not None:
                    cycling_tasks[user_id][sn]['records'].append(downgrade_rid)
                    first_rid = downgrade_rid
                else:
                    # 降级也是目标版本，循环直接完成
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
        # 记录来源版本（OTA API返回的 current_version 是设备当前/原版本）
        src_ver = progress.get('current_version', '')
        if src_ver and not record.source_version:
            record.source_version = src_ver
        state = progress.get('upgrade_state', '')
        upgrade_pct = progress.get('upgrade_percent', 0)
        SUCCESS_STATES = ('success', 'burn_done', 'done', 'finish', 'finished')
        FAIL_STATES = ('burn_fail', 'down_fail', 'fail', 'failed', 'error', 'timeout')

        # 检查是否读到旧记录（API返回的upgradeTime早于本次OTA开始时间）
        is_stale = False
        upgrade_time_str = progress.get('upgrade_time', '')
        if upgrade_time_str and record.start_time:
            try:
                upgrade_time = datetime.strptime(upgrade_time_str, '%Y-%m-%d %H:%M:%S')
                if upgrade_time < record.start_time:
                    is_stale = True
                    logger.info(f"[OTA] {sn} 旧记录(upgradeTime={upgrade_time_str}<start={record.start_time})，忽略终态")
            except ValueError:
                pass

        # 循环OTA中：如果record刚创建且upgrade_time为空，可能是读到上一轮的旧状态
        # 此时不能判为成功，需等待upgrade_time更新为本次OTA的时间
        if not is_stale and record.result == 'OTA升级中':
            task = cycling_tasks.get(user_id, {}).get(sn)
            if task:
                # 循环OTA中，新记录刚创建但API还返回旧的成功状态
                if not upgrade_time_str:
                    is_stale = True
                    logger.info(f"[OTA] {sn} 循环OTA中record={record.id}刚创建但upgrade_time为空，疑为旧状态，忽略终态")
                elif record.start_time:
                    # upgrade_time有值，但如果距start_time不到3秒，也可能是旧数据缓存
                    elapsed_since_start = (datetime.now() - record.start_time).total_seconds()
                    if elapsed_since_start < 3:
                        is_stale = True
                        logger.info(f"[OTA] {sn} 循环OTA中record={record.id}创建仅{int(elapsed_since_start)}秒，疑为旧状态，忽略终态")

        # 判断成功/失败：burn_done需upgradePercent==100才算成功；旧记录忽略终态
        state_is_success = False
        state_is_fail = False
        if not is_stale:
            if state in SUCCESS_STATES:
                if state == 'burn_done' and upgrade_pct < 100:
                    pass  # 烧录完成但整体进度未满，继续等待
                else:
                    state_is_success = True
            elif state in FAIL_STATES:
                state_is_fail = True

        if state_is_success:
            record.result = 'OTA升级成功'
        elif state_is_fail:
            record.result = 'OTA升级失败'
            record.fail_reason = f"upgradeState={state}, upgradeErrno={progress.get('upgrade_errno', 0)}"

        logger.info(f"[OTA轮询] {sn} state={state} upgradePct={upgrade_pct} downloadPct={progress.get('download_percent',0)} stale={is_stale} success={state_is_success} fail={state_is_fail}")

        # OTA超时检测：状态非终态且超过配置超时时间
        setting = Setting.query.filter_by(user_id=user_id).first()
        ota_timeout = setting.ota_timeout if setting else 3600
        is_timeout = False
        if not state_is_success and not state_is_fail:
            if record.start_time and not record.end_time:
                elapsed = (datetime.now() - record.start_time).total_seconds()
                if elapsed > ota_timeout:
                    is_timeout = True
                    record.result = 'OTA升级超时'
                    record.fail_reason = f"超过{ota_timeout}秒未完成，当前状态: {state or '未知'}"
                    logger.info(f"[OTA超时] {sn} record_id={record.id} 已耗时{int(elapsed)}秒超过{ota_timeout}秒")

        is_finished = state_is_success or state_is_fail or is_timeout
        if is_finished and not record.end_time:
            record.end_time = datetime.now()
            if record.start_time:
                record.duration = round((record.end_time - record.start_time).total_seconds(), 2)
        if is_finished and not record.log_paths:
            save_logs_for_record(record, sn)

        # 循环OTA中不触发单条AI分析，等全部结束后统一处理
        is_cycling = cycling_tasks.get(user_id, {}).get(sn, {}).get('state') == 'running'
        if (state_is_fail or is_timeout) and not record.ai_analysis and not is_cycling:
            logger.info(f"OTA失败/超时，自动触发AI分析 (record_id={record.id})")
            trigger_ai_analysis(record)

        db.session.commit()

        # 循环OTA自动继续逻辑（随机等待30~60秒后再继续下一轮）
        if is_finished and state_is_success:
            task = cycling_tasks.get(user_id, {}).get(sn)
            if task and task['state'] == 'stopping':
                # 用户已停止循环，删除当前OTA记录，终止循环
                logger.info(f"[循环OTA] {sn} 用户已停止循环，删除当前OTA记录 id={record.id}")
                db.session.delete(record)
                db.session.commit()
                record = None  # 已删除，响应中返回record_id=None
                task['state'] = 'stopped'
                trigger_cycle_ai_analysis(user_id, sn)
            elif task and task['state'] == 'running' and not task.get('_pending'):
                task['_pending'] = True
                threading.Thread(target=_continue_cycle_after_wait, args=(user_id, sn), daemon=True).start()
        elif is_finished and (state_is_fail or is_timeout):
            task = cycling_tasks.get(user_id, {}).get(sn)
            if task and task['state'] == 'stopping':
                # 用户已停止循环，删除当前OTA记录，终止循环
                logger.info(f"[循环OTA] {sn} 用户已停止循环(失败/超时)，删除当前OTA记录 id={record.id}")
                db.session.delete(record)
                db.session.commit()
                record = None  # 已删除，响应中返回record_id=None
                task['state'] = 'stopped'
                trigger_cycle_ai_analysis(user_id, sn)
            elif task and task['state'] == 'running':
                task['state'] = 'failed'
                task['fail_reason'] = f"第{task['current_cycle']}轮 {task['current_direction']} 超时" if is_timeout else f"第{task['current_cycle']}轮 {task['current_direction']} 失败"
                logger.info(f"[循环OTA] {sn} 第{task['current_cycle']}轮 {task['current_direction']} {'超时' if is_timeout else '失败'}，循环中断")
                trigger_cycle_ai_analysis(user_id, sn)

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
