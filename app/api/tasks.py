from flask import Blueprint, request, jsonify
from app import db
from app.models.models import TestTask
from app.utils.decorators import login_required, get_current_user_id
from datetime import datetime

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')


@tasks_bp.route('', methods=['GET'])
@login_required
def get_tasks():
    """获取当前用户的测试任务列表（支持按状态过滤）"""
    user_id = get_current_user_id()
    status = request.args.get('status')

    query = TestTask.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)

    tasks = query.order_by(TestTask.id.desc()).all()
    return jsonify({'tasks': [t.to_dict() for t in tasks]})


@tasks_bp.route('', methods=['POST'])
@login_required
def create_task():
    """创建测试任务（名称+描述），状态为'进行中'"""
    user_id = get_current_user_id()
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()

    if not name:
        return jsonify({'error': '任务名称不能为空'}), 400

    task = TestTask(
        user_id=user_id,
        name=name,
        description=description,
        status='进行中',
        created_at=datetime.now()
    )
    db.session.add(task)
    db.session.commit()
    return jsonify({'success': True, 'task': task.to_dict()})


@tasks_bp.route('/<int:task_id>/end', methods=['POST'])
@login_required
def end_task(task_id):
    """结束测试任务，状态变为'已完成'"""
    user_id = get_current_user_id()
    task = TestTask.query.filter_by(id=task_id, user_id=user_id).first()
    if not task:
        return jsonify({'error': '任务不存在或无权操作'}), 404
    if task.status == '已完成':
        return jsonify({'success': True, 'task': task.to_dict(), 'message': '任务已是已完成状态'})

    task.status = '已完成'
    task.ended_at = datetime.now()
    db.session.commit()
    return jsonify({'success': True, 'task': task.to_dict()})


@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    """删除测试任务（仅当无关联OTA记录时允许）"""
    from app.models.models import OtaRecord
    from sqlalchemy import func

    user_id = get_current_user_id()
    task = TestTask.query.filter_by(id=task_id, user_id=user_id).first()
    if not task:
        return jsonify({'error': '任务不存在或无权操作'}), 404

    record_count = db.session.query(func.count(OtaRecord.id)).filter(
        OtaRecord.task_id == task_id
    ).scalar() or 0
    if record_count > 0:
        return jsonify({'error': '该任务已关联OTA记录，无法删除（请先删除关联记录或结束任务）'}), 400

    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True, 'message': '任务已删除'})
