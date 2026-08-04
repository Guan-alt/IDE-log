from flask import Blueprint, request, jsonify
from app import db
from app.models.models import OtaRecord
from app.services.ai_analyzer import get_ai_analyzer
from app.utils.decorators import login_required, get_current_user_id
import logging

logger = logging.getLogger(__name__)
ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')


@ai_bp.route('/analyze/<int:record_id>', methods=['POST'])
@login_required
def analyze_record(record_id):
    """手动触发AI分析某条OTA失败记录"""
    record = OtaRecord.query.filter_by(id=record_id, user_id=get_current_user_id()).first()
    if not record:
        return jsonify({'error': '记录不存在或无权访问'}), 404

    analyzer = get_ai_analyzer()
    result = analyzer.analyze_record(record)

    # 更新记录
    record.ai_analysis = result
    db.session.commit()

    logger.info(f"记录 {record_id} AI分析完成")
    return jsonify({
        'record_id': record_id,
        'ai_analysis': result
    })


@ai_bp.route('/report/<int:record_id>', methods=['GET'])
@login_required
def get_report(record_id):
    """查看AI分析报告"""
    record = OtaRecord.query.filter_by(id=record_id, user_id=get_current_user_id()).first()
    if not record:
        return jsonify({'error': '记录不存在或无权访问'}), 404

    if not record.ai_analysis:
        return jsonify({
            'record_id': record_id,
            'ai_analysis': None,
            'message': '该记录暂无AI分析报告，请先点击"重新分析"'
        })

    return jsonify({
        'record_id': record_id,
        'device_sn': record.device_sn,
        'result': record.result,
        'fail_reason': record.fail_reason,
        'ai_analysis': record.ai_analysis,
        'log_paths': record.log_paths
    })


@ai_bp.route('/batch-report', methods=['POST'])
@login_required
def batch_report():
    """批量生成AI综合测试报告"""
    data = request.get_json()
    record_ids = data.get('record_ids', []) if data else []
    user_id = get_current_user_id()

    if not record_ids or not isinstance(record_ids, list):
        return jsonify({'error': '缺少record_ids参数或参数为空'}), 400

    records = OtaRecord.query.filter(
        OtaRecord.id.in_(record_ids),
        OtaRecord.user_id == user_id
    ).all()

    if not records:
        return jsonify({'error': '未找到对应的测试记录'}), 404

    logger.info(f"批量AI测试报告：共 {len(records)} 条记录 (ids={record_ids})")

    analyzer = get_ai_analyzer()
    report = analyzer.analyze_batch(records)

    return jsonify({
        'report': report,
        'record_count': len(records)
    })
