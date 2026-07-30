"""
ACT智能体自主委托支付Demo — 一键启动脚本

依次启动四个服务，初始化数据，运行买方智能体。
"""

import asyncio
import os
import sys
import time
import socket
import subprocess
import uvicorn
import multiprocessing

# 确保项目根在 path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 加载 .env
from dotenv import load_dotenv
load_dotenv()


def run_delegation_service():
    """启动委托授权服务 (8000)。"""
    import asyncio as _a
    from delegation_service import app, run_demo_init
    _a.run(run_demo_init())
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


def run_seller_service():
    """启动卖方智能体 (8001)。"""
    import asyncio as _a
    from seller import app, run_demo_init
    _a.run(run_demo_init())
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")


def run_psp_service():
    """启动支付服务方 (8002)。"""
    import asyncio as _a
    from demo_psp import app, run_demo_init
    _a.run(run_demo_init())
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="warning")


def run_trust_service():
    """启动信任服务方 (8003)。"""
    import asyncio as _a
    from trust_service import app, run_demo_init
    _a.run(run_demo_init())
    uvicorn.run(app, host="127.0.0.1", port=8003, log_level="warning")


def run_web_gui():
    """启动 Web GUI 服务 (8080)。"""
    from web_gui import app
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="warning")


SERVICE_PORTS = [8000, 8001, 8002, 8003, 8080]


def _check_and_clean_ports():
    """检查端口可用性，尝试清理上次运行残留的僵尸进程。"""
    needs_clean = False
    for port in SERVICE_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                needs_clean = True
                print(f"  [检测] 端口 {port} 已被占用")

    if not needs_clean:
        return

    print("\n  检测到端口占用，尝试清理残留进程...")
    try:
        result = subprocess.run(
            'netstat -ano | findstr ":8000 :8001 :8002 :8003 :8080"',
            shell=True, capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split("\n")
        pids_to_kill: set[str] = set()
        for line in lines:
            if not line.strip():
                continue
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in line:
                pids_to_kill.add(parts[-1])

        for pid in pids_to_kill:
            print(f"  [清理] 终止 PID {pid} ...")
            subprocess.run(
                f"taskkill /F /PID {pid}",
                shell=True, capture_output=True, text=True, timeout=5
            )

        # 等待端口释放
        time.sleep(1.5)
    except Exception as e:
        print(f"  [警告] 端口清理失败: {e}")

    # 二次验证
    still_blocked = []
    for port in SERVICE_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                still_blocked.append(port)
    if still_blocked:
        raise RuntimeError(
            f"端口 {still_blocked} 仍被占用，无法启动。"
            f"请手动终止占用进程后重试。"
        )


def start_services():
    """并行启动四个服务。"""
    print("=" * 60)
    print("  ACT 智能体自主委托支付 Demo — 启动中")
    print("=" * 60)

    # 端口预检查与清理
    _check_and_clean_ports()

    services = [
        ("委托授权服务", 8000, run_delegation_service),
        ("卖方智能体", 8001, run_seller_service),
        ("支付服务方", 8002, run_psp_service),
        ("信任服务方", 8003, run_trust_service),
        ("Web GUI", 8080, run_web_gui),
    ]

    processes = []
    for name, port, target in services:
        p = multiprocessing.Process(target=target, name=name)
        p.daemon = True
        p.start()
        processes.append(p)
        print(f"  [启动] {name} → http://127.0.0.1:{port}")

    # 等待服务就绪
    print("\n  等待服务就绪...")
    time.sleep(3)
    _wait_for_services(services, processes)

    print("\n  全部服务已就绪!")
    return processes


def _wait_for_services(services: list, processes: list, timeout: int = 20):
    """轮询检查服务健康，检测子进程崩溃。"""
    import requests
    deadline = time.time() + timeout
    failed_services: list[str] = []
    while time.time() < deadline:
        failed_services.clear()
        # 检查是否有子进程已崩溃
        for p in processes:
            if not p.is_alive():
                raise RuntimeError(
                    f"[{p.name}] 子进程意外退出 (exitcode={p.exitcode})，"
                    f"请检查对应服务的错误日志后重试"
                )

        # 检查各服务健康状态
        all_ok = True
        for name, port, _ in services:
            try:
                r = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
                if r.status_code != 200:
                    all_ok = False
                    failed_services.append(f"{name}({port}): HTTP {r.status_code}")
            except Exception as e:
                all_ok = False
                failed_services.append(f"{name}({port}): {type(e).__name__}")

        if all_ok:
            return

        time.sleep(0.5)

    # 超时 → 报错终止
    raise RuntimeError(
        f"服务启动超时 ({timeout}s)，以下服务未就绪:\n  " +
        "\n  ".join(failed_services) +
        "\n请检查日志后重试"
    )


async def run_chat_agent():
    """运行对话式购买智能体。"""
    from buyer.conversation_agent import ConversationAgent
    agent = ConversationAgent()
    await agent.run_loop()


async def run_test_agent():
    """自动测试对话式智能体。"""
    from buyer.conversation_agent import ConversationAgent
    agent = ConversationAgent()
    await agent.initialize()

    tests = [
        ("闲聊", "Hello"),
        ("发现服务", "Show me what data services are available for purchase"),
        ("购买", "Buy all three services for me, budget 1.00 CNY"),
        ("汇总", "Show me the summary"),
    ]
    for label, msg in tests:
        print("\n" + "=" * 50)
        print(f"TEST: {label}")
        print("=" * 50)
        resp = await agent.chat(msg)
        # 安全打印（避免 GBK 编码问题）
        try:
            print(f"\nAssistant: {resp[:300]}")
        except UnicodeEncodeError:
            print(f"\nAssistant: {resp[:300].encode('gbk', errors='replace').decode('gbk')}")
    print("\nAll tests done!")


def main():
    import sys

    mode_test = "--test" in sys.argv
    mode_web = "--web" in sys.argv or (not mode_test)  # 默认启用 Web GUI
    mode_cli = "--cli" in sys.argv

    if mode_cli:
        mode_web = False

    print("=" * 60)
    print("  ACT Agentic Commerce Trust Protocol Demo")
    print("  智能体自主委托支付 — 教学演示")
    print("=" * 60)
    if mode_web:
        print("  Web GUI: http://127.0.0.1:8080")
    print()

    # 1. 启动服务
    processes = start_services()

    try:
        if mode_test:
            # 自动测试模式
            print("\n" + "=" * 60)
            print("  对话式智能体 — 自动测试模式")
            print("=" * 60 + "\n")
            asyncio.run(run_test_agent())
        elif mode_cli:
            # 命令行交互模式
            print("\n" + "=" * 60)
            print("  启动对话式购买智能体 (CLI)")
            print("=" * 60 + "\n")
            asyncio.run(run_chat_agent())
        else:
            # Web GUI 模式 — 保持运行
            print("\n  Web GUI 已启动，访问 http://127.0.0.1:8080")
            print("  按 Ctrl+C 停止所有服务...")
            # 保持主进程存活
            try:
                import signal
                signal_event = asyncio.Event()

                async def _wait():
                    await signal_event.wait()

                asyncio.run(_wait())
            except KeyboardInterrupt:
                pass

    except Exception as e:
        print(f"\n[错误] {e}")
    finally:
        print("\n  正在停止所有服务...")
        try:
            for p in processes:
                if p.is_alive():
                    p.terminate()
                    p.join(timeout=3)
        except KeyboardInterrupt:
            pass
        print("  已停止。")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
