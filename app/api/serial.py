from flask import Blueprint, request, jsonify
from app import db
from app.models.models import LogConfig, Setting
from app.services.serial_manager import SerialManager, serial_manager
from app.services.jlink_logger import JLinkLogger
from app.utils.decorators import login_required, get_current_user_id
import subprocess
import os
import logging

logger = logging.getLogger(__name__)
serial_bp = Blueprint('serial', __name__, url_prefix='/api/serial')

# JLink采集器实例管理 - 嵌套字典: {user_id: {config_id: jlink_logger}}
jlink_loggers = {}

# 常见芯片型号列表
COMMON_CHIPS = [
    'NRF52840_xxAA',
    'NRF52832_xxAA',
    'NRF52833_xxAA',
    'NRF51822_xxAA',
    'NRF51822_xxAC',
    'STM32F103C8',
    'STM32F103CB',
    'STM32F103RB',
    'STM32F103ZE',
    'STM32F407VG',
    'STM32F407VE',
    'STM32F411CE',
    'STM32L071CB',
    'STM32L432KC',
    'ESP32',
    'ESP32S2',
    'ESP32S3',
    'ESP32C3',
    'HC32F460',
    'HT32F52344',
]


@serial_bp.route('/ports', methods=['GET'])
@login_required
def list_ports():
    """列出可用串口"""
    try:
        import serial.tools.list_ports
        ports = [{'port': p.device, 'description': p.description} for p in serial.tools.list_ports.comports()]
        return jsonify(ports)
    except Exception as e:
        logger.error(f"列出串口失败: {e}")
        return jsonify([])


@serial_bp.route('/jlinks', methods=['GET'])
@login_required
def list_jlinks():
    """自动扫描电脑连接的JLink调试器，返回序列号列表"""
    import re
    import tempfile

    # 尝试多个可能的JLink.exe路径
    jlink_candidates = [
        'JLink.exe',
        r'C:\Program Files\SEGGER\JLink\JLink.exe',
        r'C:\Program Files (x86)\SEGGER\JLink\JLink.exe',
    ]

    jlink_exe = None
    for path in jlink_candidates:
        try:
            result = subprocess.run(
                [path, '--version'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0 or 'SEGGER' in (result.stdout + result.stderr):
                jlink_exe = path
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if not jlink_exe:
        logger.warning("JLink.exe 未找到")
        return jsonify({'error': 'JLink.exe 未找到，请确认已安装JLink软件'}), 404

    # 创建临时脚本文件，通过 -CommanderScript 执行 emu 和 ShowEmuList 命令
    script_content = 'emu\nShowEmuList\nexit\n'
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jlink', delete=False, encoding='utf-8') as f:
            f.write(script_content)
            tmp_path = f.name

        result = subprocess.run(
            [jlink_exe, '-CommanderScript', tmp_path],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        output = result.stdout + result.stderr

        # 解析输出中的所有序列号
        # emu 命令输出格式: "No.0: USBAddr=0, SN=59400009"
        # ShowEmuList 输出格式: "Serial number: 59400009"
        jlinks = []

        # 匹配 emu 命令输出: SN=xxxxxx（列出所有连接的JLink）
        emu_matches = re.findall(r'SN=(\d+)', output)
        # 匹配 Serial number: xxxxxx 格式（ShowEmuList输出）
        serial_matches = re.findall(r'[Ss]erial\s*number:\s*(\d+)', output)

        # 合并并去重
        all_sns = list(dict.fromkeys(emu_matches + serial_matches))

        for sn in all_sns:
            jlinks.append({'serial': sn, 'label': f'J-Link (S/N: {sn})'})

        if not jlinks:
            return jsonify([])

        return jsonify(jlinks)

    except FileNotFoundError:
        logger.warning("JLink.exe 未找到")
        return jsonify({'error': 'JLink.exe 未找到，请确认已安装JLink软件或配置PATH'}), 404
    except subprocess.TimeoutExpired:
        logger.error("扫描JLink超时")
        return jsonify({'error': '扫描超时，请重试'}), 500
    except Exception as e:
        logger.error(f"扫描JLink失败: {e}")
        return jsonify({'error': f'扫描失败: {str(e)}'}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@serial_bp.route('/chips', methods=['GET'])
@login_required
def list_chips():
    """返回常见芯片型号列表"""
    return jsonify(COMMON_CHIPS)


@serial_bp.route('/detect_chip/<string:serial>', methods=['GET'])
@login_required
def detect_chip(serial):
    """选择JLink序列号后，自动检测连接的芯片型号"""
    import re
    import tempfile

    # 查找JLink.exe
    jlink_candidates = [
        'JLink.exe',
        r'C:\Program Files\SEGGER\JLink\JLink.exe',
        r'C:\Program Files (x86)\SEGGER\JLink\JLink.exe',
    ]
    jlink_exe = None
    for path in jlink_candidates:
        try:
            result = subprocess.run(
                [path, '--version'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0 or 'SEGGER' in (result.stdout + result.stderr):
                jlink_exe = path
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if not jlink_exe:
        return jsonify({'error': 'JLink.exe 未找到'}), 404

    # 创建脚本：选择指定JLink，SWD连接，读取默认芯片型号
    # connect命令会弹出交互提示，其中包含<Default>设备名
    # 由于connect等待交互输入，脚本结束后JLink会自动退出
    script_content = f'si SWD\nspeed 4000\nconnect\nq\n'
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jlink', delete=False, encoding='utf-8') as f:
            f.write(script_content)
            tmp_path = f.name

        # 使用 subprocess.run，给足超时时间让脚本处理完成
        # JLink在脚本处理完成后会自动退出（connect等待输入但脚本已结束）
        result = subprocess.run(
            [jlink_exe, '-selectemubysn', serial, '-CommanderScript', tmp_path],
            capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        output = result.stdout + result.stderr

        # 解析检测到的芯片型号
        detected_chip = None

        # 优先匹配 connect 命令的默认设备提示: "<Default>: NRF52840_XXAA"
        default_match = re.search(r'<Default>:\s*(\S+)', output)
        if default_match:
            detected_chip = default_match.group(1)

        # 匹配 "Device: xxx selected" 或 "Device xxx selected"
        if not detected_chip:
            device_match = re.search(r'Device[:\s]+"?(\w+)"?\s*selected', output, re.IGNORECASE)
            if device_match:
                detected_chip = device_match.group(1)

        # 匹配 "Cortex-Mx identified"，映射到常见芯片
        if not detected_chip:
            cortex_match = re.search(r'Cortex-(M\d+\+?)\s+identified', output, re.IGNORECASE)
            if cortex_match:
                core = cortex_match.group(1)
                if core == 'M4':
                    detected_chip = 'NRF52840_xxAA'
                elif core == 'M3':
                    detected_chip = 'STM32F103C8'
                elif core in ('M0', 'M0+'):
                    detected_chip = 'NRF52832_xxAA'

        if detected_chip:
            # 验证检测到的芯片是否在常见列表中
            matched = None
            for chip in COMMON_CHIPS:
                if chip.lower() == detected_chip.lower():
                    matched = chip
                    break
            if not matched:
                # 尝试模糊匹配
                for chip in COMMON_CHIPS:
                    if detected_chip.lower() in chip.lower() or chip.lower() in detected_chip.lower():
                        matched = chip
                        break
            return jsonify({
                'success': True,
                'chip': matched or detected_chip,
                'raw_output': output[-500:]
            })
        else:
            return jsonify({
                'success': False,
                'error': '未能自动检测到芯片型号',
                'raw_output': output[-500:]
            })

    except subprocess.TimeoutExpired:
        return jsonify({'error': '检测超时，请确认JLink已连接目标芯片'}), 500
    except Exception as e:
        logger.error(f"检测芯片型号失败: {e}")
        return jsonify({'error': f'检测失败: {str(e)}'}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ===== 日志配置管理（串口+JLink统一管理）=====

@serial_bp.route('/configs', methods=['GET'])
@login_required
def get_configs():
    """获取所有日志采集配置"""
    user_id = get_current_user_id()
    log_type = request.args.get('type')
    query = LogConfig.query.filter_by(user_id=user_id)
    if log_type:
        query = query.filter_by(log_type=log_type)
    configs = query.all()
    return jsonify([c.to_dict() for c in configs])


@serial_bp.route('/configs', methods=['POST'])
@login_required
def add_config():
    """添加日志采集配置（支持串口和JLink）"""
    user_id = get_current_user_id()
    data = request.get_json()
    log_type = data.get('log_type', 'serial')

    config = LogConfig(
        user_id=user_id,
        log_type=log_type,
        name=data.get('name', ''),
        device_sn=data.get('device_sn', ''),
        enabled=data.get('enabled', False)
    )

    if log_type == 'serial':
        config.port = data.get('port', '')
        config.baudrate = data.get('baudrate', 115200)
    elif log_type == 'jlink':
        config.jlink_path = data.get('jlink_path', '')
        config.jlink_serial = data.get('jlink_serial', '')
        config.rtt_channel = data.get('rtt_channel', 0)
        config.target_device = data.get('target_device', 'NRF52840_xxAA')
        config.interface = data.get('interface', 'SWD')
        config.speed = data.get('speed', 4000)

    db.session.add(config)
    db.session.commit()
    return jsonify(config.to_dict()), 201


@serial_bp.route('/configs/<int:config_id>', methods=['PUT'])
@login_required
def update_config(config_id):
    """更新日志采集配置"""
    user_id = get_current_user_id()
    config = LogConfig.query.filter_by(id=config_id, user_id=user_id).first()
    if not config:
        return jsonify({'error': '配置不存在或无权操作'}), 404
    data = request.get_json()

    for field in ['name', 'device_sn', 'enabled', 'port', 'baudrate',
                  'jlink_path', 'jlink_serial', 'rtt_channel',
                  'target_device', 'interface', 'speed']:
        if field in data:
            setattr(config, field, data[field])

    db.session.commit()
    return jsonify(config.to_dict())


@serial_bp.route('/configs/<int:config_id>', methods=['DELETE'])
@login_required
def delete_config(config_id):
    """删除日志采集配置"""
    user_id = get_current_user_id()
    config = LogConfig.query.filter_by(id=config_id, user_id=user_id).first()
    if not config:
        return jsonify({'error': '配置不存在或无权操作'}), 404

    if config.log_type == 'serial':
        serial_manager.remove_logger(config_id)
    elif config.log_type == 'jlink':
        user_jlink_loggers = jlink_loggers.get(user_id, {})
        if config_id in user_jlink_loggers:
            user_jlink_loggers[config_id].stop()
            del user_jlink_loggers[config_id]

    db.session.delete(config)
    db.session.commit()
    return jsonify({'message': '删除成功'})


# ===== 采集控制 =====

@serial_bp.route('/start', methods=['POST'])
@login_required
def start_collection():
    """启动日志采集（可指定config_ids列表，不指定则启动所有已启用的）"""
    user_id = get_current_user_id()
    data = request.get_json() or {}
    config_ids = data.get('config_ids', [])

    if config_ids:
        configs = LogConfig.query.filter(
            LogConfig.id.in_(config_ids),
            LogConfig.user_id == user_id
        ).all()
    else:
        configs = LogConfig.query.filter_by(enabled=True, user_id=user_id).all()

    if not configs:
        return jsonify({'error': '没有可启动的采集配置'}), 400

    user_jlink_loggers = jlink_loggers.setdefault(user_id, {})
    results = []
    for config in configs:
        if config.log_type == 'serial':
            serial_manager.add_logger(
                config.id, config.port, config.baudrate,
                config.name, config.device_sn
            )
            success = serial_manager.start_one(config.id)
            results.append({
                'config_id': config.id, 'type': 'serial',
                'port': config.port, 'name': config.name, 'success': success
            })
        elif config.log_type == 'jlink':
            # 若该配置已有采集器实例，先停止旧的，防止进程堆积占用JLink
            old_logger = user_jlink_loggers.get(config.id)
            if old_logger is not None:
                try:
                    old_logger.stop()
                except Exception:
                    pass
            jlink_logger = JLinkLogger(
                name=config.name,
                device_sn=config.device_sn,
                jlink_path=config.jlink_path or '',
                jlink_serial=config.jlink_serial or '',
                rtt_channel=config.rtt_channel,
                target_device=config.target_device or 'NRF52840_xxAA',
                interface=config.interface or 'SWD',
                speed=config.speed or 4000
            )
            success = jlink_logger.start()
            user_jlink_loggers[config.id] = jlink_logger
            results.append({
                'config_id': config.id, 'type': 'jlink',
                'name': config.name, 'serial': config.jlink_serial,
                'success': success
            })

    success_count = sum(1 for r in results if r['success'])
    return jsonify({
        'message': f'已启动 {success_count}/{len(results)} 个采集器',
        'results': results
    })


@serial_bp.route('/stop', methods=['POST'])
@login_required
def stop_collection():
    """停止日志采集（可指定config_ids列表，不指定则停止所有）"""
    user_id = get_current_user_id()
    data = request.get_json() or {}
    config_ids = data.get('config_ids', [])

    user_jlink_loggers = jlink_loggers.get(user_id, {})
    if config_ids:
        for cid in config_ids:
            cid_int = int(cid)
            serial_manager.remove_logger(cid_int)
            if cid_int in user_jlink_loggers:
                user_jlink_loggers[cid_int].stop()
                del user_jlink_loggers[cid_int]
        return jsonify({'message': f'已停止 {len(config_ids)} 个采集器'})
    else:
        serial_manager.stop_all()
        for config_id, jlink_logger in user_jlink_loggers.items():
            jlink_logger.stop()
        user_jlink_loggers.clear()
        return jsonify({'message': '已停止所有日志采集'})


@serial_bp.route('/status', methods=['GET'])
@login_required
def get_status():
    """获取所有采集器的运行状态"""
    user_id = get_current_user_id()
    user_jlink_loggers = jlink_loggers.get(user_id, {})
    status = {
        'serial': serial_manager.get_status(),
        'jlink': {}
    }
    for config_id, jlink_logger in user_jlink_loggers.items():
        status['jlink'][config_id] = {
            'name': jlink_logger.name,
            'device_sn': jlink_logger.device_sn,
            'is_running': jlink_logger.is_running
        }
    return jsonify(status)


@serial_bp.route('/logs/<int:config_id>', methods=['GET'])
@login_required
def get_logs(config_id):
    """获取指定采集器的实时日志"""
    user_id = get_current_user_id()
    config = LogConfig.query.filter_by(id=config_id, user_id=user_id).first()
    if not config:
        return jsonify({'error': '配置不存在或无权访问'}), 404

    user_jlink_loggers = jlink_loggers.get(user_id, {})
    if config.log_type == 'serial':
        logs = serial_manager.get_logs(config_id)
    elif config.log_type == 'jlink' and config_id in user_jlink_loggers:
        logs = user_jlink_loggers[config_id].get_logs()
    else:
        logs = ''

    return jsonify({
        'config_id': config_id,
        'log_type': config.log_type,
        'name': config.name,
        'logs': logs[-5000:] if len(logs) > 5000 else logs
    })


@serial_bp.route('/test/<int:config_id>', methods=['POST'])
@login_required
def test_collection(config_id):
    """测试日志采集：临时启动采集3秒，返回采集到的日志内容"""
    import time
    user_id = get_current_user_id()
    config = LogConfig.query.filter_by(id=config_id, user_id=user_id).first()
    if not config:
        return jsonify({'error': '配置不存在或无权操作'}), 404

    user_jlink_loggers = jlink_loggers.setdefault(user_id, {})
    if config.log_type == 'serial':
        serial_manager.add_logger(
            config.id, config.port, config.baudrate,
            config.name, config.device_sn
        )
        started = serial_manager.start_one(config.id)
        if not started:
            return jsonify({'success': False, 'error': '串口启动失败'})
        time.sleep(3)
        logs = serial_manager.get_logs(config.id) or ''
        serial_manager.remove_logger(config.id)
        return jsonify({
            'success': True,
            'message': '测试采集成功' if logs.strip() else '采集完成但未收到数据',
            'logs': logs[-2000:] if len(logs) > 2000 else logs,
            'has_data': bool(logs.strip())
        })

    elif config.log_type == 'jlink':
        jlink_logger = JLinkLogger(
            name=config.name,
            device_sn=config.device_sn,
            jlink_path=config.jlink_path or '',
            jlink_serial=config.jlink_serial or '',
            rtt_channel=config.rtt_channel,
            target_device=config.target_device or 'NRF52840_xxAA',
            interface=config.interface or 'SWD',
            speed=config.speed or 4000
        )
        started = jlink_logger.start()
        if not started:
            return jsonify({'success': False, 'error': 'JLink启动失败，请检查连接'})
        time.sleep(5)
        logs = jlink_logger.get_logs() or ''
        jlink_logger.stop()
        return jsonify({
            'success': True,
            'message': '测试采集成功' if logs.strip() else '采集完成但未收到数据',
            'logs': logs[-2000:] if len(logs) > 2000 else logs,
            'has_data': bool(logs.strip())
        })

    return jsonify({'success': False, 'error': '不支持的采集类型'})
