from flask import Blueprint, request, jsonify
from app import db
from app.models.models import OtaEnvironment
from app.utils.decorators import login_required, get_current_user_id
from datetime import datetime

ota_envs_bp = Blueprint('ota_envs', __name__, url_prefix='/api/ota-envs')


@ota_envs_bp.route('', methods=['GET'])
@login_required
def list_envs():
    user_id = get_current_user_id()
    envs = OtaEnvironment.query.filter_by(user_id=user_id).order_by(OtaEnvironment.sort_order.asc(), OtaEnvironment.id.asc()).all()
    return jsonify({'envs': [e.to_dict() for e in envs]})


@ota_envs_bp.route('', methods=['POST'])
@login_required
def create_env():
    user_id = get_current_user_id()
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    ota_url = (data.get('ota_url') or '').strip()
    token = (data.get('token') or '').strip()
    sort_order = int(data.get('sort_order') or 0)
    if not name:
        return jsonify({'error': '环境名称不能为空'}), 400
    if not ota_url:
        return jsonify({'error': 'OTA URL 不能为空'}), 400
    # 区域校验（cn=国内 os=国外）
    region = (data.get('region') or 'cn').strip().lower()
    if region not in ('cn', 'os'):
        return jsonify({'error': '区域只能为 cn（国内）或 os（国外）'}), 400
    # 同用户下 name 唯一
    if OtaEnvironment.query.filter_by(user_id=user_id, name=name).first():
        return jsonify({'error': '环境名称已存在'}), 400
    env = OtaEnvironment(user_id=user_id, name=name, ota_url=ota_url, token=token, region=region, sort_order=sort_order)
    db.session.add(env)
    db.session.commit()
    return jsonify({'success': True, 'env': env.to_dict()})


@ota_envs_bp.route('/<int:env_id>', methods=['PUT'])
@login_required
def update_env(env_id):
    user_id = get_current_user_id()
    env = OtaEnvironment.query.filter_by(id=env_id, user_id=user_id).first()
    if not env:
        return jsonify({'error': '环境不存在或无权操作'}), 404
    data = request.get_json() or {}
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return jsonify({'error': '环境名称不能为空'}), 400
        # 唯一性校验，排除自身
        existing = OtaEnvironment.query.filter_by(user_id=user_id, name=name).first()
        if existing and existing.id != env.id:
            return jsonify({'error': '环境名称已存在'}), 400
        env.name = name
    if 'ota_url' in data:
        ota_url = (data['ota_url'] or '').strip()
        if not ota_url:
            return jsonify({'error': 'OTA URL 不能为空'}), 400
        env.ota_url = ota_url
    if 'token' in data:
        env.token = (data['token'] or '').strip()
    if 'region' in data:
        region = (data['region'] or 'cn').strip().lower()
        if region not in ('cn', 'os'):
            return jsonify({'error': '区域只能为 cn（国内）或 os（国外）'}), 400
        env.region = region
    if 'sort_order' in data:
        env.sort_order = int(data['sort_order'] or 0)
    env.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'success': True, 'env': env.to_dict()})


@ota_envs_bp.route('/<int:env_id>', methods=['DELETE'])
@login_required
def delete_env(env_id):
    user_id = get_current_user_id()
    env = OtaEnvironment.query.filter_by(id=env_id, user_id=user_id).first()
    if not env:
        return jsonify({'error': '环境不存在或无权操作'}), 404
    db.session.delete(env)
    db.session.commit()
    return jsonify({'success': True, 'message': '环境已删除'})
