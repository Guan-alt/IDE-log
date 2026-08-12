"""
模拟 JLink 连接失败的测试脚本，验证重试机制是否按预期工作。

测试场景：
1. JLinkRTTLogger 进程启动后立即输出 "ERROR: Could not connect to target." 然后退出
   → 验证：自动重试 3 次，3 次都失败后 is_running = False
2. 在重试等待期间手动调用 stop()
   → 验证：is_running 立即变为 False，不继续重试
3. 第一次失败、第二次成功（模拟连接恢复）
   → 验证：重试后 is_running 保持 True，_retry_count 记录正确
4. 正常 RTT 日志中包含 ERROR 字样但不是连接错误，不应触发重试

运行方式：
    python tests/test_jlink_retry.py
"""

import os
import sys
import time
import logging
from unittest.mock import patch
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

from app.services.jlink_logger import JLinkLogger


class FakeProcess:
    """模拟 JLinkRTTLogger 进程"""

    def __init__(self, stdout_lines=None, keep_running=False):
        """
        Args:
            stdout_lines: stdout 输出的行列表
            keep_running: True=进程保持运行不退出；False=输出后立即退出
        """
        self._stdout = StringIO(''.join(stdout_lines or []))
        self._stdin = StringIO()
        self._keep_running = keep_running
        self._poll_result = None if keep_running else 0
        self._returncode = None if keep_running else 0
        self._terminated = False

    @property
    def stdout(self):
        return self._stdout

    @property
    def stdin(self):
        return self._stdin

    def poll(self):
        return self._poll_result

    @property
    def returncode(self):
        return self._returncode

    def terminate(self):
        self._terminated = True
        self._poll_result = -1
        self._returncode = -1

    def kill(self):
        self._terminated = True
        self._poll_result = -1
        self._returncode = -1

    def wait(self, timeout=None):
        return self._returncode or 0


def test_retry_exhausted():
    """测试1：连接持续失败，验证重试3次后 is_running 变为 False"""
    print('\n' + '=' * 60)
    print('测试1：连接持续失败，重试3次后停止')
    print('=' * 60)

    jl = JLinkLogger(name='TestJLink', device_sn='59400009', jlink_serial='59400009')
    jl._MAX_RETRIES = 3
    jl._RETRY_DELAY = 1  # 1秒间隔加速测试

    call_count = [0]

    def fake_popen(*args, **kwargs):
        call_count[0] += 1
        print(f'  [Mock] 第 {call_count[0]} 次启动（模拟连接失败后退出）')
        return FakeProcess(stdout_lines=[
            'SEGGER J-Link RTT Logger V7.86c\n',
            'ERROR: Could not connect to target.\n',
        ], keep_running=False)

    # 整个测试逻辑都在 patch 上下文内，防止后台线程逃逸到真实进程
    with patch('app.services.jlink_logger.subprocess.Popen', side_effect=fake_popen):
        result = jl.start()
        print(f'  start() 返回: {result}')
        print(f'  is_running: {jl.is_running}')

        # 等待重试全部完成（3次 × 1秒间隔 + 进程启动时间 ≈ 最多15秒）
        for i in range(20):
            if not jl.is_running:
                break
            time.sleep(1)

        print(f'\n  最终状态:')
        print(f'    is_running: {jl.is_running}')
        print(f'    _retry_count: {jl._retry_count}')
        print(f'    进程启动次数: {call_count[0]}')

        success = True
        if jl.is_running:
            print('  [FAIL] is_running 应为 False')
            success = False
        if jl._retry_count != 3:
            print(f'  [FAIL] _retry_count 应为 3，实际 {jl._retry_count}')
            success = False
        if call_count[0] != 4:  # 初始1次 + 3次重试
            print(f'  [FAIL] 进程应启动 4 次（1+3重试），实际 {call_count[0]}')
            success = False
        if success:
            print('  [PASS] 重试3次后正确停止')

        try:
            jl.stop()
        except:
            pass
    return success


def test_stop_during_retry():
    """测试2：重试等待期间手动 stop()，验证立即中断"""
    print('\n' + '=' * 60)
    print('测试2：重试等待期间手动 stop()')
    print('=' * 60)

    jl = JLinkLogger(name='TestJLink', device_sn='59400009', jlink_serial='59400009')
    jl._MAX_RETRIES = 3
    jl._RETRY_DELAY = 10  # 10秒间隔，留足时间手动停止

    call_count = [0]

    def fake_popen(*args, **kwargs):
        call_count[0] += 1
        print(f'  [Mock] 第 {call_count[0]} 次启动（模拟连接失败后退出）')
        return FakeProcess(stdout_lines=[
            'ERROR: Could not connect to target.\n',
        ], keep_running=False)

    with patch('app.services.jlink_logger.subprocess.Popen', side_effect=fake_popen):
        result = jl.start()
        print(f'  start() 返回: {result}')

        # 等待进入重试等待
        time.sleep(2)
        print(f'  2秒后 is_running: {jl.is_running}, _retry_count: {jl._retry_count}')

        print('  手动调用 stop()...')
        stop_start = time.time()
        jl.stop()
        stop_duration = time.time() - stop_start
        print(f'  stop() 耗时: {stop_duration:.2f}秒')
        print(f'  stop 后 is_running: {jl.is_running}')

        success = True
        if jl.is_running:
            print('  [FAIL] stop 后 is_running 应为 False')
            success = False
        if stop_duration > 5:
            print(f'  [FAIL] stop() 应快速返回（<5秒），实际 {stop_duration:.2f}秒')
            success = False
        if success:
            print('  [PASS] stop() 正确中断重试等待')
    return success


def test_recover_after_retry():
    """测试3：第一次失败，第二次成功，验证重试后恢复正常"""
    print('\n' + '=' * 60)
    print('测试3：第一次失败，第二次成功（模拟连接恢复）')
    print('=' * 60)

    jl = JLinkLogger(name='TestJLink', device_sn='59400009', jlink_serial='59400009')
    jl._MAX_RETRIES = 3
    jl._RETRY_DELAY = 1

    call_count = [0]

    def fake_popen(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            print(f'  [Mock] 第 1 次启动（模拟连接失败）')
            return FakeProcess(stdout_lines=[
                'ERROR: Could not connect to target.\n',
            ], keep_running=False)
        else:
            print(f'  [Mock] 第 {call_count[0]} 次启动（模拟连接成功，进程保持运行）')
            return FakeProcess(stdout_lines=[], keep_running=True)

    with patch('app.services.jlink_logger.subprocess.Popen', side_effect=fake_popen):
        result = jl.start()
        print(f'  start() 返回: {result}')
        print(f'  初始 is_running: {jl.is_running}')

        # 等待重试完成
        time.sleep(5)

        print(f'  5秒后 is_running: {jl.is_running}')
        print(f'  _retry_count: {jl._retry_count}')
        print(f'  进程启动次数: {call_count[0]}')

        success = True
        if not jl.is_running:
            print('  [FAIL] is_running 应为 True（重试成功后继续运行）')
            success = False
        if jl._retry_count != 1:
            print(f'  [FAIL] _retry_count 应为 1，实际 {jl._retry_count}')
            success = False
        if call_count[0] != 2:
            print(f'  [FAIL] 进程应启动 2 次（1失败+1成功），实际 {call_count[0]}')
            success = False
        if success:
            print('  [PASS] 第一次失败后重试成功，正确恢复运行')

        try:
            jl.stop()
        except:
            pass
    return success


def test_no_false_positive_on_normal_log():
    """测试4：正常 RTT 日志中包含 ERROR 字样但不是连接错误，不应触发重试"""
    print('\n' + '=' * 60)
    print('测试4：正常日志中含 ERROR 但非连接错误，不应误杀')
    print('=' * 60)

    jl = JLinkLogger(name='TestJLink', device_sn='59400009', jlink_serial='59400009')
    jl._MAX_RETRIES = 3
    jl._RETRY_DELAY = 1

    call_count = [0]

    def fake_popen(*args, **kwargs):
        call_count[0] += 1
        print(f'  [Mock] 第 {call_count[0]} 次启动（正常运行，日志含ERROR字样）')
        return FakeProcess(stdout_lines=[
            'SEGGER J-Link RTT Logger V7.86c\n',
            '[APP] ERROR: some application error (not connection)\n',
        ], keep_running=True)  # 进程保持运行

    with patch('app.services.jlink_logger.subprocess.Popen', side_effect=fake_popen):
        result = jl.start()
        print(f'  start() 返回: {result}')
        print(f'  is_running: {jl.is_running}')

        time.sleep(3)

        print(f'  3秒后 is_running: {jl.is_running}')
        print(f'  _retry_count: {jl._retry_count}')
        print(f'  进程启动次数: {call_count[0]}')

        success = True
        if not jl.is_running:
            print('  [FAIL] is_running 应为 True（正常日志不应触发重试/停止）')
            success = False
        if jl._retry_count != 0:
            print(f'  [FAIL] _retry_count 应为 0，实际 {jl._retry_count}')
            success = False
        if call_count[0] != 1:
            print(f'  [FAIL] 进程应只启动 1 次，实际 {call_count[0]}')
            success = False
        if success:
            print('  [PASS] 正常日志中的 ERROR 字样未误触发重试')

        try:
            jl.stop()
        except:
            pass
    return success


if __name__ == '__main__':
    results = []

    print('\n' + '#' * 60)
    print('# JLink 连接失败重试机制测试')
    print('#' * 60)

    results.append(('测试1: 重试耗尽后停止', test_retry_exhausted()))
    results.append(('测试2: 重试期间手动停止', test_stop_during_retry()))
    results.append(('测试3: 第一次失败第二次成功', test_recover_after_retry()))
    results.append(('测试4: 正常日志不误杀', test_no_false_positive_on_normal_log()))

    print('\n' + '#' * 60)
    print('# 测试结果汇总')
    print('#' * 60)
    for name, passed in results:
        status = 'PASS' if passed else 'FAIL'
        print(f'  [{status}] {name}')

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f'\n  {passed}/{total} 通过')

    if passed < total:
        sys.exit(1)
