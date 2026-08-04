from flask import Blueprint, request, jsonify
from app import db
from app.models.models import OtaRecord
from app.utils.decorators import login_required, get_current_user_id
import math

records_bp = Blueprint('records', __name__, url_prefix='/api/records')

@records_bp.route('', methods=['GET'])
@login_required
def get_records():
    sn = request.args.get('sn')
    result = request.args.get('result')
    task_id = request.args.get('task_id', type=int)
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 15, type=int)

    query = OtaRecord.query.filter(OtaRecord.user_id == get_current_user_id())
    if sn:
        query = query.filter_by(device_sn=sn)
    if task_id:
        query = query.filter_by(task_id=task_id)
    if result:
        if result == 'success':
            query = query.filter(OtaRecord.result.contains('成功'))
        elif result == 'fail':
            query = query.filter(
                (OtaRecord.result.contains('失败')) |
                (OtaRecord.result.contains('超时')) |
                (OtaRecord.result == 'OTA请求失败')
            )

    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))

    records = query.order_by(OtaRecord.id.desc()) \
        .offset((page - 1) * page_size) \
        .limit(page_size) \
        .all()

    return jsonify({
        'records': [r.to_dict() for r in records],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages
    })

@records_bp.route('/<int:record_id>', methods=['GET'])
@login_required
def get_record(record_id):
    record = OtaRecord.query.filter_by(id=record_id, user_id=get_current_user_id()).first()
    if not record:
        return jsonify({'error': '记录不存在或无权访问'}), 404
    return jsonify(record.to_dict())

@records_bp.route('/<int:record_id>', methods=['DELETE'])
@login_required
def delete_record(record_id):
    record = OtaRecord.query.filter_by(id=record_id, user_id=get_current_user_id()).first()
    if not record:
        return jsonify({'error': '记录不存在或无权操作'}), 404
    db.session.delete(record)
    db.session.commit()
    return jsonify({'message': '删除成功'})

@records_bp.route('', methods=['DELETE'])
@login_required
def clear_records():
    OtaRecord.query.filter(OtaRecord.user_id == get_current_user_id()).delete()
    db.session.commit()
    return jsonify({'message': '已清空所有记录'})
