from flask import Blueprint, request, jsonify
from app import db
from app.models.models import Device
from app.services.ota_client import OtaClient
from app.models.models import Setting
from app.utils.decorators import login_required, get_current_user_id
import logging

logger = logging.getLogger(__name__)
devices_bp = Blueprint('devices', __name__, url_prefix='/api/devices')

def get_ota_client(uid=None):
    if uid is None:
        uid = get_current_user_id()
    setting = Setting.query.filter_by(user_id=uid).first()
    if setting:
        return OtaClient(setting.ota_url, setting.token, 10)
    return OtaClient('https://test-lkadmin-lockin-management.lockin.com', '', 10)

@devices_bp.route('', methods=['GET'])
@login_required
def get_devices():
    uid = get_current_user_id()
    devices = Device.query.filter_by(user_id=uid).all()
    client = get_ota_client(uid)
    result = []
    for d in devices:
        # 每次请求时从OTA服务器刷新设备状态和版本
        info = client.get_device_info(d.sn)
        if info:
            d.current_version = info.get('version', '') or d.current_version
            d.status = '在线' if info.get('online') else '离线'
        else:
            d.status = '离线'
        result.append(d.to_dict())
    db.session.commit()
    return jsonify(result)

@devices_bp.route('', methods=['POST'])
@login_required
def add_device():
    data = request.get_json()
    if Device.query.filter_by(sn=data.get('sn')).first():
        return jsonify({'error': '设备SN已存在'}), 400
    device = Device(sn=data['sn'], name=data.get('name', ''))
    device.user_id = get_current_user_id()
    db.session.add(device)
    db.session.commit()
    return jsonify(device.to_dict()), 201

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
    client = get_ota_client()
    version = client.get_version(sn)
    if version:
        device = Device.query.filter_by(sn=sn, user_id=get_current_user_id()).first()
        if device:
            device.current_version = version
            db.session.commit()
        return jsonify({'sn': sn, 'version': version})
    return jsonify({'error': '获取版本失败'}), 400
