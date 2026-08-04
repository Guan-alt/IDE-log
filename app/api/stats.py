from flask import Blueprint, request, jsonify
from app.models.models import OtaRecord
from app.utils.decorators import login_required, get_current_user_id
from sqlalchemy import func, or_, case
from datetime import datetime, timedelta

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')

# 成功/失败判定表达式
SUCCESS_COND = OtaRecord.result.like('%成功%')
FAIL_COND = or_(OtaRecord.result.like('%失败%'),
                OtaRecord.result.like('%超时%'),
                OtaRecord.result.like('%请求失败%'))


def _compute_stats(query):
    """计算给定 query 的总数/成功/失败/成功率/平均耗时"""
    total = query.count()
    success = query.filter(SUCCESS_COND).count()
    fail = query.filter(FAIL_COND).count()
    avg_duration = query.filter(SUCCESS_COND).with_entities(
        func.avg(OtaRecord.duration)).scalar() or 0
    success_rate = success / total * 100 if total > 0 else 0
    return total, success, fail, success_rate, avg_duration


@stats_bp.route('', methods=['GET'])
@login_required
def get_stats():
    sn = request.args.get('sn')
    task_id = request.args.get('task_id', type=int)
    user_id = get_current_user_id()

    query = OtaRecord.query.filter(OtaRecord.user_id == user_id)
    if sn:
        query = query.filter_by(device_sn=sn)
    if task_id:
        query = query.filter_by(task_id=task_id)

    total = query.count()
    success = query.filter(OtaRecord.result == 'OTA升级成功').count()
    fail = total - success

    success_records = query.filter(OtaRecord.result == 'OTA升级成功')
    avg_duration = success_records.with_entities(func.avg(OtaRecord.duration)).scalar() or 0

    return jsonify({
        'total_tests': total,
        'success_count': success,
        'fail_count': fail,
        'success_rate': f'{success / total * 100:.2f}%' if total > 0 else '0.00%',
        'avg_duration': f'{avg_duration:.2f}s' if avg_duration else '0.00s'
    })


@stats_bp.route('/overview', methods=['GET'])
@login_required
def get_overview():
    """总次数/成功/失败/成功率/平均耗时 + 前一天环比"""
    sn = request.args.get('sn')
    task_id = request.args.get('task_id', type=int)
    user_id = get_current_user_id()

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now
    yesterday_start = today_start - timedelta(days=1)
    yesterday_end = today_start - timedelta(seconds=1)

    base_query = OtaRecord.query.filter(OtaRecord.user_id == user_id)
    if sn:
        base_query = base_query.filter_by(device_sn=sn)
    if task_id:
        base_query = base_query.filter_by(task_id=task_id)

    # 全部记录统计
    total, success, fail, success_rate, avg_duration = _compute_stats(base_query)

    # 今天 0:00 ~ 现在
    today_query = base_query.filter(
        OtaRecord.start_time >= today_start,
        OtaRecord.start_time <= today_end)
    t_total, t_success, t_fail, t_success_rate, t_avg = _compute_stats(today_query)

    # 前一天 0:00 ~ 23:59:59
    yesterday_query = base_query.filter(
        OtaRecord.start_time >= yesterday_start,
        OtaRecord.start_time <= yesterday_end)
    y_total, y_success, y_fail, y_success_rate, y_avg = _compute_stats(yesterday_query)

    def change(today_val, yesterday_val):
        value = round(today_val - yesterday_val, 2)
        if yesterday_val != 0:
            pct = round((today_val - yesterday_val) / yesterday_val * 100, 2)
        else:
            pct = 0
        return {'value': value, 'pct': pct}

    return jsonify({
        'total_tests': total,
        'success_count': success,
        'fail_count': fail,
        'success_rate': round(success_rate, 2),
        'avg_duration': round(avg_duration, 2),
        'changes': {
            'total_tests': change(t_total, y_total),
            'success_count': change(t_success, y_success),
            'fail_count': change(t_fail, y_fail),
            'success_rate': change(t_success_rate, y_success_rate),
            'avg_duration': change(t_avg, y_avg),
        }
    })


@stats_bp.route('/trend', methods=['GET'])
@login_required
def get_trend():
    """按天聚合近N天的成功/失败次数"""
    sn = request.args.get('sn')
    task_id = request.args.get('task_id', type=int)
    days = request.args.get('days', 7, type=int)
    user_id = get_current_user_id()

    now = datetime.now()
    start_date = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0)

    query = OtaRecord.query.filter(
        OtaRecord.start_time >= start_date,
        OtaRecord.user_id == user_id)
    if sn:
        query = query.filter_by(device_sn=sn)
    if task_id:
        query = query.filter_by(task_id=task_id)

    date_expr = func.date(OtaRecord.start_time)
    success_expr = case((SUCCESS_COND, 1), else_=0)
    fail_expr = case((FAIL_COND, 1), else_=0)

    rows = query.with_entities(
        date_expr.label('date'),
        func.sum(success_expr).label('success'),
        func.sum(fail_expr).label('fail'),
    ).group_by(date_expr).order_by(date_expr).all()

    dates = [r.date for r in rows]
    success = [int(r.success or 0) for r in rows]
    fail = [int(r.fail or 0) for r in rows]

    return jsonify({
        'dates': dates,
        'success': success,
        'fail': fail
    })


@stats_bp.route('/fail-reasons', methods=['GET'])
@login_required
def get_fail_reasons():
    """按 fail_reason 分组统计"""
    sn = request.args.get('sn')
    task_id = request.args.get('task_id', type=int)
    user_id = get_current_user_id()

    query = OtaRecord.query.filter(
        OtaRecord.result != 'OTA升级成功',
        OtaRecord.fail_reason.isnot(None),
        OtaRecord.fail_reason != '',
        OtaRecord.user_id == user_id
    )
    if sn:
        query = query.filter_by(device_sn=sn)
    if task_id:
        query = query.filter_by(task_id=task_id)

    rows = query.with_entities(
        OtaRecord.fail_reason.label('reason'),
        func.count().label('count')
    ).group_by(OtaRecord.fail_reason).all()

    total = sum(r.count for r in rows)
    reasons = []
    for r in rows:
        pct = r.count / total * 100 if total > 0 else 0
        reasons.append({
            'reason': r.reason,
            'count': r.count,
            'pct': round(pct, 2)
        })

    return jsonify({
        'reasons': reasons,
        'total': total
    })


@stats_bp.route('/version-stats', methods=['GET'])
@login_required
def get_version_stats():
    """按 target_version 分组统计"""
    sn = request.args.get('sn')
    task_id = request.args.get('task_id', type=int)
    user_id = get_current_user_id()

    query = OtaRecord.query.filter(OtaRecord.user_id == user_id)
    if sn:
        query = query.filter_by(device_sn=sn)
    if task_id:
        query = query.filter_by(task_id=task_id)

    success_expr = case((SUCCESS_COND, 1), else_=0)
    fail_expr = case((FAIL_COND, 1), else_=0)

    rows = query.with_entities(
        OtaRecord.target_version.label('version'),
        func.sum(success_expr).label('success'),
        func.sum(fail_expr).label('fail'),
    ).group_by(OtaRecord.target_version).all()

    versions = []
    for r in rows:
        versions.append({
            'version': r.version,
            'success': int(r.success or 0),
            'fail': int(r.fail or 0)
        })

    return jsonify({'versions': versions})


@stats_bp.route('/device-ranking', methods=['GET'])
@login_required
def get_device_ranking():
    """按设备聚合排行"""
    sn = request.args.get('sn')
    task_id = request.args.get('task_id', type=int)
    user_id = get_current_user_id()

    query = OtaRecord.query.filter(OtaRecord.user_id == user_id)
    if sn:
        query = query.filter_by(device_sn=sn)
    if task_id:
        query = query.filter_by(task_id=task_id)

    success_expr = case((SUCCESS_COND, 1), else_=0)
    fail_expr = case((FAIL_COND, 1), else_=0)

    rows = query.with_entities(
        OtaRecord.device_sn.label('device_sn'),
        func.count().label('total'),
        func.sum(success_expr).label('success'),
        func.sum(fail_expr).label('fail'),
    ).group_by(OtaRecord.device_sn).order_by(func.count().desc()).all()

    devices = []
    for r in rows:
        total = r.total
        success = int(r.success or 0)
        fail = int(r.fail or 0)
        success_rate = success / total * 100 if total > 0 else 0
        devices.append({
            'device_sn': r.device_sn,
            'total': total,
            'success': success,
            'fail': fail,
            'success_rate': round(success_rate, 2)
        })

    return jsonify({'devices': devices})
