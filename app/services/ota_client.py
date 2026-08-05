import requests
import logging
import time

logger = logging.getLogger(__name__)

class OtaClient:
    """OTA API客户端，封装门锁OTA相关接口"""

    def __init__(self, ota_url, token, timeout=10, region='cn'):
        self.ota_url = ota_url
        self.token = token
        self.timeout = timeout
        self.region = region or 'cn'  # cn=国内 os=国外（查询设备版本方式不同）
        self.headers = {"x-access-token": token}

    def get_version(self, sn):
        """查询设备当前固件版本"""
        info = self.get_device_info(sn)
        return info.get('version', '') if info else ''

    def get_device_info(self, sn):
        """查询设备完整信息（版本号+在线状态），按环境区域选择查询方式"""
        if self.region == 'os':
            return self._get_device_info_overseas(sn)
        return self._get_device_info_cn(sn)

    def _get_device_info_cn(self, sn):
        """国内平台：通过 /device/infoBySN 查询设备信息"""
        try:
            response = requests.get(
                f"{self.ota_url}/device/infoBySN?sn={sn}",
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            result_list = data.get("result", [])
            info = {'version': '', 'online': False}
            if isinstance(result_list, list):
                for item in result_list:
                    pid = item.get("pid", "")
                    value = item.get("value", "")
                    if pid == "ota_ver":
                        info['version'] = value
                    elif pid in ('online', 'status', 'state', 'net_state', 'device_status', 'online_state'):
                        info['online'] = self._is_online_value(value)
            return info
        except Exception as e:
            logger.error(f"获取设备信息失败: {e}")
            return {'version': '', 'online': False}

    def _get_device_info_overseas(self, sn):
        """国外平台：通过 /device/state/page 查询设备版本（pidList=ota_ver）"""
        try:
            response = requests.post(
                f"{self.ota_url}/device/state/page",
                headers=self.headers,
                json={
                    "pageIndex": 0,
                    "pageSize": 20,
                    "sn": sn,
                    "pidList": ["ota_ver"],
                    "terms": []
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            result = data.get("result", {})
            if isinstance(result, dict):
                items = result.get("data", []) or result.get("list", []) or result.get("rows", [])
            elif isinstance(result, list):
                items = result
            else:
                items = []
            info = {'version': '', 'online': False}
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        pid = item.get("pid", "")
                        value = item.get("value", "")
                        if pid == "ota_ver":
                            info['version'] = str(value or '')
                        elif pid in ('online', 'status', 'state', 'net_state', 'device_status', 'online_state'):
                            info['online'] = self._is_online_value(value)
                    else:
                        # 纯值列表（请求只带 pidList=ota_ver 时，可能直接返回版本值）
                        if not info['version'] and item is not None:
                            info['version'] = str(item)
            return info
        except Exception as e:
            logger.error(f"获取设备信息失败(国外): {e}")
            return {'version': '', 'online': False}

    @staticmethod
    def _is_online_value(value):
        """判断在线状态字段值是否为'在线'（兼容数字/布尔/字符串）"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value == 1
        return str(value).strip().lower() in (
            'true', '1', 'online', 'on', 'yes', 'up', 'connected', '在线', '正常'
        )
    
    def ota_start(self, sn, target_ver):
        """发起OTA升级请求"""
        try:
            response = requests.post(
                f"{self.ota_url}/ota/version/forceUpgrade",
                headers=self.headers,
                json={"sn": sn, "version": target_ver},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") == 200:
                return True, "OTA升级请求成功"
            else:
                return False, data.get('message', '未知错误')
        except requests.exceptions.HTTPError as e:
            # 尝试提取响应体中的错误信息
            try:
                error_msg = e.response.json().get('message', str(e))
            except Exception:
                error_msg = str(e)
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def get_available_versions(self, sn, limit=100):
        """获取设备可用的所有OTA版本列表"""
        try:
            response = requests.get(
                f"{self.ota_url}/ota/version/latest",
                params={"sn": sn, "limit": limit},
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") == 200:
                result = data.get("result", [])
                versions = []
                if isinstance(result, list):
                    for item in result:
                        ver = item.get("version", "")
                        if ver:
                            versions.append({
                                "version": ver,
                                "description": item.get("description", ""),
                                "force": item.get("force", 0),
                                "url": item.get("url", ""),
                                "size": item.get("size", 0)
                            })
                return versions
            return []
        except Exception as e:
            logger.error(f"获取可用版本列表失败: {e}")
            return []
    
    def get_progress(self, sn):
        """查询OTA升级进度，返回完整信息字典"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.ota_url}/ota/record/page",
                    headers=self.headers,
                    json={"pageIndex": 0, "pageSize": 1, "sn": sn, "terms": []},
                    timeout=(5, 10)
                )
                response.raise_for_status()
                data = response.json()
                if data.get("status") == 200:
                    result = data.get("result", {})
                    if result:
                        data_list = result.get("data", [])
                        if data_list and isinstance(data_list, list) and len(data_list) > 0:
                            item = data_list[0]
                            return {
                                'upgrade_percent': item.get("upgradePercent", 0),
                                'download_percent': item.get("downloadPercent", 0),
                                'upgrade_state': item.get("upgradeState", ""),
                                'upgrade_errno': item.get("upgradeErrno", 0),
                                'current_version': item.get("version", ""),
                                'target_version': item.get("upgradeVersion", ""),
                                'upgrade_time': item.get("upgradeTime", ""),
                                'device_name': item.get("deviceName", "")
                            }
                return {
                    'upgrade_percent': 0,
                    'download_percent': 0,
                    'upgrade_state': '',
                    'upgrade_errno': 0,
                    'current_version': '',
                    'target_version': '',
                    'upgrade_time': '',
                    'device_name': ''
                }
            except requests.exceptions.Timeout:
                logger.warning(f"获取OTA进度超时 (尝试 {attempt + 1}/{max_retries})")
                time.sleep(2)
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"获取OTA进度失败，正在重试... ({e})")
                    time.sleep(2)
                else:
                    logger.error(f"获取OTA进度最终失败: {e}")
        return {
            'upgrade_percent': 0,
            'download_percent': 0,
            'upgrade_state': '',
            'upgrade_errno': 0,
            'current_version': '',
            'target_version': '',
            'upgrade_time': '',
            'device_name': ''
        }
