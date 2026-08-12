import json
import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

# 项目根目录（ai_analyzer.py 位于 app/services/，上两级即项目根）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse_sse_content(text):
    """
    解析 SSE 流式响应文本，拼接所有 delta 的 content。

    部分网关（如私有部署）会强制以 text/event-stream 流式返回，
    格式为多行 "data: {json}"，结尾可能有 "data: [DONE]"。

    Returns:
        (is_sse, content): is_sse 表示文本是否为 SSE 格式；
                           content 为拼接出的完整文本内容
    """
    if not text or 'data:' not in text:
        return False, ''
    content_parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('data:'):
            continue
        payload = line[len('data:'):].strip()
        if not payload or payload == '[DONE]':
            continue
        try:
            obj = json.loads(payload)
        except ValueError:
            continue
        for ch in (obj.get('choices') or []):
            delta = ch.get('delta') or {}
            if delta.get('content'):
                content_parts.append(delta['content'])
    return True, ''.join(content_parts)

# 分析用的系统提示词
SYSTEM_PROMPT = """你是一位固件OTA升级分析专家。用户会提供门锁设备OTA升级失败时的日志（可能来自串口或JLink RTT）。
请分析日志内容，找出OTA升级失败的根本原因。

请严格按以下Markdown格式输出分析报告：

## 🔍 失败原因总结
简要说明失败的根本原因（1-2句话）

## 📋 关键日志片段
列出每个日志源中与失败相关的关键日志行，标注来源和类型

## 🔧 建议解决方案
给出2-3条具体的修复建议，每条用序号标注

注意：
- 如果日志中没有明显的错误信息，请说明"日志中未发现明确错误信息"
- 日志可能包含乱码或不可读字符，请忽略
- 关注关键词：error, fail, timeout, abort, exception, reset, crash, disconnect, retry
- 输出使用中文
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
            try:
                data = response.json()
                result = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            except ValueError:
                # 兼容强制流式（SSE）响应的网关
                is_sse, result = _parse_sse_content(response.content.decode('utf-8', errors='replace'))
                if not is_sse:
                    raise
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
        # 解析日志文件路径列表
        log_contents = []
        if record.log_paths:
            try:
                log_paths = json.loads(record.log_paths)
            except (json.JSONDecodeError, TypeError):
                log_paths = [record.log_paths] if record.log_paths else []
            log_contents = self._read_log_files(log_paths)

        # 如果没有日志文件，使用OTA记录信息作为上下文
        if not log_contents:
            logger.warning(f"记录 {record.id} 无可用日志文件，使用OTA记录信息分析")
            return self._analyze_record_info(record)

        return self.analyze_logs(log_contents)

    def _analyze_record_info(self, record):
        """无日志文件时，基于OTA记录信息生成AI分析"""
        info_parts = [f"OTA升级记录信息："]
        info_parts.append(f"设备SN: {record.device_sn or '未知'}")
        info_parts.append(f"源版本: {record.source_version or '未知'}")
        info_parts.append(f"目标版本: {record.target_version or '未知'}")
        info_parts.append(f"升级结果: {record.result or '未知'}")
        info_parts.append(f"升级进度: {record.upgrade_percent or 0}%")
        info_parts.append(f"下载进度: {record.download_percent or 0}%")
        info_parts.append(f"失败原因: {record.fail_reason or '无'}")
        info_parts.append(f"升级耗时: {record.duration or 0}秒")

        info_text = '\n'.join(info_parts)

        user_message = f"以下是OTA升级失败的记录信息（无采集日志）：\n\n{info_text}\n\n"
        user_message += "请根据以上信息分析可能的失败原因，并给出排查建议。"

        system_prompt = (
            "你是一位嵌入式OTA升级分析专家。请根据OTA升级记录信息分析失败原因。"
            "如果没有日志文件，请基于失败原因码和升级状态给出可能的原因分析和排查建议。"
            "请严格按以下Markdown格式输出：\n\n"
            "## 🔍 失败原因总结\n简要说明可能的失败原因\n\n"
            "## 🔧 建议解决方案\n给出2-3条具体修复建议\n\n"
            "回答使用中文，结构化输出。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        try:
            reply = self.chat(messages)
            logger.info(f"记录 {record.id} 基于记录信息分析完成")
            return reply
        except Exception as e:
            error_msg = f"分析失败：AI接口调用失败 - {e}"
            logger.error(error_msg)
            return error_msg

    def _read_log_files(self, log_paths):
        """读取日志文件列表，返回 [{'name': ..., 'content': ...}]"""
        log_contents = []
        for path in log_paths:
            if not isinstance(path, str):
                continue
            # 尝试路径解析：原始路径 → 项目根目录拼接（兼容历史相对路径记录）
            resolved = path
            if not os.path.exists(resolved) and not os.path.isabs(resolved):
                # 相对路径在当前CWD下找不到，尝试拼接到项目根目录
                alt = os.path.join(PROJECT_ROOT, path)
                if os.path.exists(alt):
                    resolved = alt
            if os.path.exists(resolved):
                try:
                    with open(resolved, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    basename = os.path.basename(resolved).replace('.log', '')
                    log_contents.append({'name': basename, 'content': content})
                except Exception as e:
                    logger.error(f"读取日志文件 {resolved} 失败: {e}")
            else:
                logger.warning(f"日志文件不存在: {path}")
        return log_contents

    def build_chat_context(self, record):
        """
        构建对话上下文：日志内容 + AI分析报告 + 记录基本信息
        """
        context = ""
        # 添加AI分析报告
        if record.ai_analysis:
            context += f"=== AI分析报告 ===\n{record.ai_analysis}\n\n"
        # 添加日志内容
        if record.log_paths:
            try:
                log_paths = json.loads(record.log_paths)
            except (json.JSONDecodeError, TypeError):
                log_paths = [record.log_paths] if record.log_paths else []
            log_contents = self._read_log_files(log_paths)
            for log in log_contents:
                content = log.get('content', '')
                if len(content) > 5000:
                    content = "...(日志过长，仅显示末尾部分)...\n" + content[-5000:]
                context += f"=== 日志源: {log.get('name', '未知')} ===\n{content}\n\n"
        # 添加记录基本信息
        context += f"=== 记录基本信息 ===\n"
        context += f"设备SN: {record.device_sn or '未知'}\n"
        context += f"升级结果: {record.result or '未知'}\n"
        context += f"来源版本: {record.source_version or '未知'}\n"
        context += f"目标版本: {record.target_version or '未知'}\n"
        context += f"升级进度: {record.upgrade_percent or 0}%\n"
        context += f"下载进度: {record.download_percent or 0}%\n"
        context += f"升级耗时: {record.duration or 0}秒\n"
        if record.fail_reason:
            context += f"失败原因: {record.fail_reason}\n"
        return context

    def chat(self, messages):
        """
        通用对话接口（支持多轮对话）
        Args:
            messages: list of {role, content}
        Returns:
            str: AI回复文本
        """
        if not self.api_key:
            return "AI API Key 未配置"

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2000
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            try:
                data = response.json()
                result = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            except ValueError:
                is_sse, result = _parse_sse_content(response.content.decode('utf-8', errors='replace'))
                if not is_sse:
                    raise
            if result:
                return result
            return "AI返回内容为空"
        except requests.exceptions.Timeout:
            return "对话失败：AI接口调用超时（60秒）"
        except requests.exceptions.ConnectionError as e:
            return f"对话失败：无法连接AI服务 - {e}"
        except Exception as e:
            logger.error(f"AI对话失败: {e}")
            return f"对话失败：{e}"

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
            try:
                data = response.json()
                result = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            except ValueError:
                # 兼容强制流式（SSE）响应的网关
                is_sse, result = _parse_sse_content(response.content.decode('utf-8', errors='replace'))
                if not is_sse:
                    raise
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

    def test_connection(self, api_key='', model='', base_url=''):
        """
        测试AI服务连通性（发送最小化请求）
        Args:
            api_key: API Key（空字符串则使用实例配置）
            model: 模型名（空字符串则使用实例配置）
            base_url: API地址（空字符串则使用实例配置）
        Returns:
            dict: {ok, status, latency_ms, message}
        """
        api_key = api_key or self.api_key
        model = model or self.model
        base_url = (base_url or self.base_url).rstrip('/')

        result = self._test_connection_once(api_key, model, base_url)

        # 常见问题：私有部署网关通常要求带 /v1 前缀。
        # 若当前地址测试失败且未以 /v1 结尾，自动尝试补 /v1 再测一次
        if not result.get('ok') and not base_url.endswith('/v1'):
            v1_url = base_url + '/v1'
            retry = self._test_connection_once(api_key, model, v1_url)
            if retry.get('ok'):
                retry['message'] = f'连接成功（需使用带 /v1 的地址：{v1_url}）'
                return retry
        return result

    def _test_connection_once(self, api_key, model, base_url):
        """单次连通性测试请求（不重试）"""
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5
        }

        start_time = time.time()
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            latency_ms = int((time.time() - start_time) * 1000)
            status = response.status_code

            if 200 <= status < 300:
                try:
                    data = response.json()
                except ValueError:
                    is_sse, _ = _parse_sse_content(response.content.decode('utf-8', errors='replace'))
                    if is_sse:
                        return {'ok': True, 'status': status, 'latency_ms': latency_ms,
                                'message': '连接成功（网关以流式SSE格式响应）'}
                    return {'ok': False, 'status': status, 'latency_ms': latency_ms,
                            'message': '响应不是有效JSON（可能地址错误，网关返回了网页或空内容）：' + response.text[:200]}
                if data.get('choices'):
                    return {'ok': True, 'status': status, 'latency_ms': latency_ms, 'message': '连接成功'}
                return {'ok': False, 'status': status, 'latency_ms': latency_ms,
                        'message': f'响应格式异常：{response.text[:200]}'}
            elif status in (401, 403):
                return {'ok': False, 'status': status, 'latency_ms': latency_ms,
                        'message': '鉴权失败：API Key 无效或无权限'}
            elif status == 404:
                return {'ok': False, 'status': status, 'latency_ms': latency_ms,
                        'message': '接口不存在：请检查 API 地址是否正确'}
            elif status == 400:
                return {'ok': False, 'status': status, 'latency_ms': latency_ms,
                        'message': '请求被拒绝（可能模型不存在）：' + response.text[:200]}
            else:
                return {'ok': False, 'status': status, 'latency_ms': latency_ms,
                        'message': f'调用失败（HTTP {status}）：' + response.text[:200]}
        except requests.exceptions.Timeout:
            latency_ms = int((time.time() - start_time) * 1000)
            return {'ok': False, 'status': 0, 'latency_ms': latency_ms, 'message': '连接超时（15秒）'}
        except requests.exceptions.ConnectionError:
            latency_ms = int((time.time() - start_time) * 1000)
            return {'ok': False, 'status': 0, 'latency_ms': latency_ms,
                    'message': '无法连接服务器，请检查 API 地址和网络'}
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"AI连通性测试失败: {e}")
            return {'ok': False, 'status': 0, 'latency_ms': latency_ms, 'message': f'调用失败：{e}'}

    def list_models(self, api_key='', base_url=''):
        """
        获取AI服务支持的模型列表（OpenAI兼容 /models 接口）
        Args:
            api_key: API Key（空字符串则使用实例配置）
            base_url: API地址（空字符串则使用实例配置）
        Returns:
            dict: {ok, models, message}
        """
        api_key = api_key or self.api_key
        base_url = (base_url or self.base_url).rstrip('/')

        url = f"{base_url}/models"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            status = response.status_code

            if status == 200:
                data = response.json()
                model_list = data.get('data', [])
                models = [{'id': m.get('id', ''), 'name': m.get('id', '')}
                          for m in model_list if m.get('id')]
                return {'ok': True, 'models': models,
                        'message': f'获取成功，共{len(models)}个模型'}
            elif status in (401, 403):
                return {'ok': False, 'message': '鉴权失败：API Key 无效或无权限'}
            elif status == 404:
                return {'ok': False, 'message': '该服务不支持模型列表接口，请手动输入模型名'}
            else:
                return {'ok': False, 'message': f'获取失败（HTTP {status}）：' + response.text[:200]}
        except requests.exceptions.Timeout:
            return {'ok': False, 'message': '请求超时（15秒）'}
        except requests.exceptions.ConnectionError:
            return {'ok': False, 'message': '无法连接服务器，请检查 API 地址和网络'}
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return {'ok': False, 'message': f'获取模型列表失败：{e}'}


def get_ai_analyzer():
    """从数据库获取配置创建AI分析器"""
    from app.models.models import Setting
    setting = Setting.query.first()
    if setting:
        return AIAnalyzer(setting.ai_api_key, setting.ai_model, setting.ai_base_url)
    return AIAnalyzer('', '', '')
