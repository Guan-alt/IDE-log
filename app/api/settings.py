from flask import Blueprint, request, jsonify
from app import db
from app.models.models import Setting
from app.utils.decorators import login_required, get_current_user_id

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

@settings_bp.route('', methods=['GET'])
@login_required
def get_settings():
    user_id = get_current_user_id()
    setting = Setting.query.filter_by(user_id=user_id).first()
    if not setting:
        # 自动创建一条默认设置
        setting = Setting(user_id=user_id)
        db.session.add(setting)
        db.session.commit()
    return jsonify(setting.to_dict())

@settings_bp.route('', methods=['POST'])
@login_required
def update_settings():
    user_id = get_current_user_id()
    data = request.get_json()
    setting = Setting.query.filter_by(user_id=user_id).first()
    if not setting:
        # 自动创建一条默认设置
        setting = Setting(user_id=user_id)
        db.session.add(setting)

    for field in ['ota_url', 'token', 'ota_url_online', 'token_online', 'ota_timeout', 'ai_api_key', 'ai_model', 'ai_base_url', 'serial_default_baudrate']:
        if field in data:
            setattr(setting, field, data[field])

    db.session.commit()
    return jsonify(setting.to_dict())
