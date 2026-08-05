from flask import Blueprint, jsonify
from app.utils.decorators import get_current_user

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/current', methods=['GET'])
def current():
    """认证状态接口（全局单用户模式，始终返回已登录状态）"""
    user = get_current_user()
    if not user:
        return jsonify({'logged_in': False}), 200
    return jsonify({
        'logged_in': True,
        'user': user.to_dict()
    })
