import json
import os
import logging
import requests

logger = logging.getLogger(__name__)

# 分析用的系统提示词
SYSTEM_PROMPT = """你是一位固件OTA升级分析专家。用户会提供门锁设备OTA升级失败时的日志（可能来自串口或JLink RTT）。
请分析日志内容，找出OTA升级失败的根本原因。

请按以下格式输出分析报告：

## 失败原因总结
[简要说明失败的根本原因，1-2句话]

## 各日志源关键日志片段
[列出每个日志源中与失败相关的关键日志行，标注日志来源名称和类型（串口/JLink）]

## 建议解决方案
[给出2-3条具体的修复建议]

注意：
- 如果日志中没有明显的错误信息，请说明"日志中未发现明确错误信息"
- 日志可能包含乱码或不可读字符，请忽略
- 关注关键词：error, fail, timeout, abort, exception, reset, crash, disconnect, retry
"""

BATCH_REPORT_PROMPT = """你是一位固件OTA升级测试分析专家。用户会提供多条OTA测试记录的汇总数据。
请基于这些数据生成一份综合测试报告，评估整体OTA质量。

请按以下格式输出测试报告：

## 一、测试概览
[测试记录总数、成功数、失败数、成功率、总耗时等统计数据]

## 二、版本升级路径分析
[列出涉及的来源版本→目标版本路径，每条路径的成功/失败次数]

## 三、失败原因汇总
[如果有失败记录，归纳失败原因类型，统计各类失败出现的次数，列出典型失败案例]

## 四、版本兼容性评估
[评估各版本间的升级兼容性，标注存在风险的版本路径]

## 五、设备表现分析
[如果有多个设备的数据，对比各设备的OTA成功率，标注表现异常的设备]

## 六、改进建议
[给出3-5条针对性的改进建议，包括但不限于固件修复、测试策略优化、版本发布建议等]

注意：
- 数据中可能包含已有的单条AI分析结果，请参考但不逐条复述
- 用统计和归纳的方式呈现，避免逐条罗列
- 如数据不足以支撑某个章节，注明"数据不足，暂无法评估"
"""

class AIAnalyzer:
    """AI日志分析器（使用requests直接调用API，兼容OpenAI/DeepSeek格式）"""

    def __init__(self, api_key, model, base_url):
        self.api_key = api_key or ''
        self.model = model or 'deepseek-chat'
        self.base_url = (base_url or 'https://api.deepseek.com').rstrip('/')

    def analyze_logs(self, log_contents):
        """
        分析日志（串口或JLink）
        Args:
            log_contents: list of dict, 每个dict包含 'name'(日志源名称) 和 'content'(日志内容)
        Returns:
            str: AI分析报告文本
        """
        if not self.api_key:
            return "分析失败：AI API Key 未配置"

        # 构造用户消息
        user_message = "以下是OTA升级失败时采集的日志：\n\n"
        for log in log_contents:
            user_message += f"=== 日志源: {log.get('name', '未知')} ===\n"
            content = log.get('content', '')
            # 截断过长的日志，保留最后5000字符（通常错误在日志末尾）
            if len(content) > 5000:
                content = "...(日志过长，仅显示末尾部分)...\n" + content[-5000:]
            user_message += content + "\n\n"

        # 调用API（兼容OpenAI/DeepSeek的chat/completions接口）
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            result = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            if result:
                return result
            return f"分析失败：AI返回内容为空 - {response.text[:200]}"
        except requests.exceptions.Timeout:
            return "分析失败：AI接口调用超时（60秒）"
        except requests.exceptions.ConnectionError as e:
            return f"分析失败：无法连接AI服务 - {e}"
        except Exception as e:
            error_msg = f"分析失败：AI接口调用失败 - {e}"
            logger.error(error_msg)
            return error_msg

    def analyze_record(self, record):
        """
        分析OTA记录关联的日志文件（串口或JLink）
        Args:
            record: OtaRecord 实例
        Returns:
            str: AI分析报告
        """
        if not record.log_paths:
            return "分析失败：无关联的日志文件"

        # 解析日志文件路径列表
        try:
            log_paths = json.loads(record.log_paths)
        except (json.JSONDecodeError, TypeError):
            log_paths = [record.log_paths] if record.log_paths else []

        if not log_paths:
            return "分析失败：无关联的日志文件"

        # 读取所有日志文件
        log_contents = []
        for path in log_paths:
            if not isinstance(path, str):
                continue
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    # 从文件名提取日志源名称
                    basename = os.path.basename(path)
                    name = basename.replace('.log', '')
                    log_contents.append({'name': name, 'content': content})
                except Exception as e:
                    logger.error(f"读取日志文件 {path} 失败: {e}")
            else:
                logger.warning(f"日志文件不存在: {path}")

        if not log_contents:
            return "分析失败：所有关联的日志文件均不存在或为空"

        return self.analyze_logs(log_contents)

    def analyze_batch(self, records):
        """
        批量分析多条OTA记录，生成综合测试报告
        Args:
            records: list of OtaRecord 实例
        Returns:
            str: AI综合测试报告
        """
        if not self.api_key:
            return "分析失败：AI API Key 未配置"

        if not records:
            return "分析失败：没有可分析的记录"

        # 汇总每条记录的数据
        lines = []
        lines.append(f"共选中 {len(records)} 条OTA测试记录，以下是详细数据：\n")

        success_count = 0
        fail_count = 0
        total_duration = 0.0

        for i, rec in enumerate(records, 1):
            result = rec.result or '未知'
            if '成功' in result:
                success_count += 1
            else:
                fail_count += 1
            duration = rec.duration or 0
            total_duration += duration

            lines.append(f"--- 记录 {i} (ID={rec.id}) ---")
            lines.append(f"设备SN: {rec.device_sn or '未知'}")
            src = rec.source_version or '未知'
            tgt = rec.target_version or '未知'
            lines.append(f"版本路径: {src} → {tgt}")
            lines.append(f"结果: {result}")
            lines.append(f"耗时: {duration:.1f}秒")
            lines.append(f"开始时间: {rec.start_time.strftime('%Y-%m-%d %H:%M:%S') if rec.start_time else '未知'}")
            if rec.fail_reason:
                lines.append(f"失败原因: {rec.fail_reason}")
            if rec.ai_analysis:
                # 截断过长的单条AI分析，只保留摘要部分
                ai_text = rec.ai_analysis[:800]
                if len(rec.ai_analysis) > 800:
                    ai_text += '...(已截断)'
                lines.append(f"单条AI分析摘要: {ai_text}")
            lines.append('')

        # 统计摘要
        lines.append(f"\n=== 统计摘要 ===")
        lines.append(f"总记录数: {len(records)}")
        lines.append(f"成功: {success_count}, 失败: {fail_count}")
        success_rate = round(success_count / len(records) * 100, 1) if records else 0
        lines.append(f"成功率: {success_rate}%")
        lines.append(f"总耗时: {total_duration:.1f}秒, 平均耗时: {total_duration / len(records):.1f}秒")

        user_message = '\n'.join(lines)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": BATCH_REPORT_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3,
            "max_tokens": 3000
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            result = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            if result:
                return result
            return f"分析失败：AI返回内容为空 - {response.text[:200]}"
        except requests.exceptions.Timeout:
            return "分析失败：AI接口调用超时（120秒）"
        except requests.exceptions.ConnectionError as e:
            return f"分析失败：无法连接AI服务 - {e}"
        except Exception as e:
            error_msg = f"分析失败：AI接口调用失败 - {e}"
            logger.error(error_msg)
            return error_msg


def get_ai_analyzer():
    """从数据库获取配置创建AI分析器"""
    from app.models.models import Setting
    setting = Setting.query.first()
    if setting:
        return AIAnalyzer(setting.ai_api_key, setting.ai_model, setting.ai_base_url)
    return AIAnalyzer('', '', '')
