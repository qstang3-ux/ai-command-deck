"""Harmless local terminal demonstration. No remote connections."""
import time

steps = [
    ('$ python --version', 'Python · 本机演示'),
    ('$ check application', '\x1b[32m✓ 应用状态正常\x1b[0m'),
    ('$ check model endpoint', '\x1b[36m✓ 模型接口验证通过（演示数据）\x1b[0m'),
    ('$ summarize', '执行完成。可切换历史回放，拖动时间轴查看每一步。'),
]
print('\x1b[2J\x1b[H\x1b[1;32mAI Command Deck · 本机功能演示\x1b[0m\n', flush=True)
for command, result in steps:
    print(command, flush=True)
    time.sleep(1)
    print(result + '\n', flush=True)
    time.sleep(1)
