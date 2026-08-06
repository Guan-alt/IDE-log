from flask import Blueprint, request, jsonify
from app import db
from app.models.models import OtaRecord, Setting
from app.services.ai_analyzer import AIAnalyzer, get_ai_analyzer
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


@ai_bp.route('/chat/<int:record_id>', methods=['POST'])
@login_required
def chat_with_ai(record_id):
    """基于OTA记录的日志和AI分析报告进行追问对话"""
    data = request.get_json() or {}
    question = (data.get('question') or '').strip()
    history = data.get('history', [])

    if not question:
        return jsonify({'error': '请输入问题'}), 400

    record = OtaRecord.query.filter_by(id=record_id, user_id=get_current_user_id()).first()
    if not record:
        return jsonify({'error': '记录不存在或无权访问'}), 404

    setting = Setting.query.filter_by(user_id=get_current_user_id()).first()
    if not setting or not setting.ai_api_key:
        return jsonify({'error': 'AI服务未配置，请先在设置页配置AI API Key'}), 400

    analyzer = AIAnalyzer(setting.ai_api_key, setting.ai_model, setting.ai_base_url)
    context = analyzer.build_chat_context(record)

    messages = [
        {"role": "system", "content":
            "你是一位固件OTA升级分析专家。用户正在就某次OTA升级的日志和AI分析报告进行追问。"
            "请基于以下上下文内容回答用户的问题。如果上下文中没有相关信息，请如实说明。\n\n" + context}
    ]
    # 添加对话历史（最多保留最近10轮）
    recent_history = history[-20:] if len(history) > 20 else history
    for h in recent_history:
        role = h.get('role', 'user')
        content = h.get('content', '')
        if role in ('user', 'assistant') and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    reply = analyzer.chat(messages)
    logger.info(f"记录 {record_id} AI对话完成，问题长度={len(question)}")
    return jsonify({'reply': reply})


@ai_bp.route('/test-connection', methods=['POST'])
@login_required
def test_connection():
    """测试AI服务连通性"""
    data = request.get_json() or {}
    api_key = data.get('api_key')
    model = data.get('model')
    base_url = data.get('base_url')

    # 缺失字段回退到当前用户已保存的配置
    setting = Setting.query.filter_by(user_id=get_current_user_id()).first()
    if setting:
        api_key = api_key or setting.ai_api_key or ''
        model = model or setting.ai_model or ''
        base_url = base_url or setting.ai_base_url or ''
    else:
        api_key = api_key or ''
        model = model or ''
        base_url = base_url or ''

    # 空值给默认
    if not base_url:
        base_url = 'https://api.deepseek.com'
    if not model:
        model = 'deepseek-chat'

    logger.info(f"AI连通性测试开始：base_url={base_url}, model={model}")
    analyzer = AIAnalyzer(api_key, model, base_url)
    result = analyzer.test_connection()
    logger.info(f"AI连通性测试完成：ok={result.get('ok')}, status={result.get('status')}, "
                f"latency_ms={result.get('latency_ms')}")
    return jsonify(result)


@ai_bp.route('/models', methods=['POST'])
@login_required
def list_models():
    """获取AI服务支持的模型列表"""
    data = request.get_json() or {}
    api_key = data.get('api_key')
    base_url = data.get('base_url')

    # 缺失字段回退到当前用户已保存的配置
    setting = Setting.query.filter_by(user_id=get_current_user_id()).first()
    if setting:
        api_key = api_key or setting.ai_api_key or ''
        base_url = base_url or setting.ai_base_url or ''
    else:
        api_key = api_key or ''
        base_url = base_url or ''

    # 空值给默认
    if not base_url:
        base_url = 'https://api.deepseek.com'

    logger.info(f"获取AI模型列表开始：base_url={base_url}")
    analyzer = AIAnalyzer(api_key, '', base_url)
    result = analyzer.list_models()
    logger.info(f"获取AI模型列表完成：ok={result.get('ok')}")
    return jsonify(result)
