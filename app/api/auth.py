from flask import Blueprint, request, session, jsonify, render_template
from app import db
from app.models.models import User
from app.utils.decorators import login_required, get_current_user

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'error': '用户名或密码错误'}), 401

    session['user_id'] = user.id
    session['username'] = user.username

    return jsonify({
        'message': '登录成功',
        'user': user.to_dict()
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': '已注销'})


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    display_name = data.get('display_name', '').strip()

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码至少6个字符'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': '用户名已存在'}), 400

    user = User(username=username, display_name=display_name or username, is_admin=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    session['username'] = user.username

    return jsonify({
        'message': '注册成功',
        'user': user.to_dict()
    }), 201


@auth_bp.route('/current', methods=['GET'])
def current():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'logged_in': False}), 401
    user = User.query.get(uid)
    if not user:
        session.clear()
        return jsonify({'logged_in': False}), 401
    return jsonify({
        'logged_in': True,
        'user': user.to_dict()
    })
