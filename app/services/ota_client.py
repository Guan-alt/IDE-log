import requests
import logging
import time

logger = logging.getLogger(__name__)

class OtaClient:
    """OTA API客户端，封装门锁OTA相关接口"""
    
    def __init__(self, ota_url, token, timeout=10):
        self.ota_url = ota_url
        self.token = token
        self.timeout = timeout
        self.headers = {"x-access-token": token}
    
    def get_version(self, sn):
        """查询设备当前固件版本"""
        info = self.get_device_info(sn)
        return info.get('version', '') if info else ''

    def get_device_info(self, sn):
        """查询设备完整信息（版本号+在线状态）"""
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
                    elif pid == "online" or pid == "status":
                        info['online'] = value in (True, 'true', '1', 1, 'online')
            return info
        except Exception as e:
            logger.error(f"获取设备信息失败: {e}")
            return {'version': '', 'online': False}
    
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
