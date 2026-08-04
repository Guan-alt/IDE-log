"""门锁OTA监控测试平台 - 主入口"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    print("=" * 50)
    print("  门锁OTA监控测试平台")
    print("  访问地址: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
