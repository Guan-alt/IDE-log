"""门锁OTA监控测试平台 - 主入口"""
import logging
import os
from app import create_app

# 文件日志：捕获循环OTA后台线程的完整执行路径和异常
os.makedirs('logs', exist_ok=True)
_fh = logging.FileHandler('logs/ota_cycle.log', encoding='utf-8')
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logging.getLogger().addHandler(_fh)
logging.getLogger('app.api.ota').setLevel(logging.DEBUG)

app = create_app()

if __name__ == '__main__':
    print("=" * 50)
    print("  门锁OTA监控测试平台")
    print("  访问地址: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
