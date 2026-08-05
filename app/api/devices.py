from flask import Blueprint, request, jsonify
from app import db
from app.models.models import Device, OtaEnvironment
from app.api.ota import get_ota_client
from app.services.ota_client import OtaClient
from app.utils.decorators import login_required, get_current_user_id
import logging

logger = logging.getLogger(__name__)
devices_bp = Blueprint('devices', __name__, url_prefix='/api/devices')


def detect_device_env(sn, user_id):
    """遍历所有已配置的OTA环境，找到能查到该设备信息的环境并返回其id（找不到返回None）"""
    envs = OtaEnvironment.query.filter_by(user_id=user_id).order_by(OtaEnvironment.sort_order.asc()).all()
    for env in envs:
        try:
            client = OtaClient(env.ota_url, env.token, timeout=3, region=env.region or 'cn')
            info = client.get_device_info(sn)
            # 能在该环境查到设备（返回了固件版本）即视为设备归属该环境
            if info and info.get('version'):
                logger.info(f"设备 {sn} 探测到环境: {env.name} (id={env.id})")
                return env.id
        except Exception as e:
            logger.warning(f"探测设备 {sn} 环境 {env.name} 失败: {e}")
    return None


def _env_name(env_id):
    """根据环境id返回环境名称（空则返回''）"""
    if not env_id:
        return ''
    env = OtaEnvironment.query.get(env_id)
    return env.name if env else ''


@devices_bp.route('', methods=['GET'])
@login_required
def get_devices():
    uid = get_current_user_id()
    devices = Device.query.filter_by(user_id=uid).all()
    # 设备默认环境（第一个环境），用于无关联环境的设备刷新版本
    default_client = get_ota_client(user_id=uid)
    result = []
    for d in devices:
        # 尚未关联环境的设备，自动探测归属环境
        if not d.env_id:
            detected = detect_device_env(d.sn, uid)
            if detected:
                d.env_id = detected
        # 使用设备关联的环境（若有）刷新设备版本，否则使用默认环境
        if d.env_id:
            env = OtaEnvironment.query.get(d.env_id)
            client = OtaClient(env.ota_url, env.token, 10, region=env.region or 'cn') if env else default_client
        else:
            client = default_client
        info = client.get_device_info(d.sn)
        if info:
            d.current_version = info.get('version', '') or d.current_version
        # 清理历史遗留的在线/离线状态值
        if d.status in ('在线', '离线'):
            d.status = 'idle'
        item = d.to_dict()
        item.pop('status', None)
        item['env_name'] = _env_name(d.env_id)
        result.append(item)
    db.session.commit()
    return jsonify(result)

@devices_bp.route('', methods=['POST'])
@login_required
def add_device():
    data = request.get_json()
    if Device.query.filter_by(sn=data.get('sn')).first():
        return jsonify({'error': '设备SN已存在'}), 400
    user_id = get_current_user_id()
    # 指定环境：校验环境存在；未指定：自动探测，找不到则拒绝添加
    env_id = data.get('env_id')
    if env_id:
        if not OtaEnvironment.query.filter_by(id=env_id, user_id=user_id).first():
            return jsonify({'error': '指定的OTA环境不存在'}), 400
    else:
        env_id = detect_device_env(data['sn'], user_id)
        if not env_id:
            return jsonify({'error': '未找到该设备所属的OTA环境，无法添加'}), 400
    device = Device(sn=data['sn'], name=data.get('name', ''), user_id=user_id, env_id=env_id)
    db.session.add(device)
    db.session.commit()
    item = device.to_dict()
    item['env_name'] = _env_name(device.env_id)
    return jsonify(item), 201

@devices_bp.route('/probe', methods=['POST'])
@login_required
def probe_device_env():
    """探测指定设备在指定OTA环境中是否存在（供前端添加设备时逐步显示进度）"""
    data = request.get_json()
    sn = data.get('sn')
    env_id = data.get('env_id')
    if not sn or not env_id:
        return jsonify({'error': '缺少sn或env_id参数'}), 400
    env = OtaEnvironment.query.filter_by(id=env_id, user_id=get_current_user_id()).first()
    if not env:
        return jsonify({'error': '环境不存在'}), 404
    client = OtaClient(env.ota_url, env.token, timeout=3, region=env.region or 'cn')
    info = client.get_device_info(sn)
    found = bool(info and info.get('version'))
    return jsonify({
        'env_id': env.id,
        'env_name': env.name,
        'found': found,
        'version': info.get('version', '') if found else ''
    })

@devices_bp.route('/<int:device_id>', methods=['DELETE'])
@login_required
def delete_device(device_id):
    device = Device.query.filter_by(id=device_id, user_id=get_current_user_id()).first()
    if not device:
        return jsonify({'error': '设备不存在或无权操作'}), 404
    db.session.delete(device)
    db.session.commit()
    return jsonify({'message': '删除成功'})

@devices_bp.route('/<string:sn>/version', methods=['GET'])
@login_required
def get_device_version(sn):
    user_id = get_current_user_id()
    device = Device.query.filter_by(sn=sn, user_id=user_id).first()
    # 优先使用设备关联的环境查询版本
    if device and device.env_id:
        env = OtaEnvironment.query.get(device.env_id)
        client = OtaClient(env.ota_url, env.token, 10, region=env.region or 'cn') if env else get_ota_client(user_id=user_id)
    else:
        client = get_ota_client(user_id=user_id)
    version = client.get_version(sn)
    if version:
        if device:
            device.current_version = version
            db.session.commit()
        return jsonify({'sn': sn, 'version': version})
    return jsonify({'error': '获取版本失败'}), 400
