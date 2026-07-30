"""
终端颜色工具

使用 ANSI 转义码实现不同颜色输出。
Windows 10+ 原生支持，无需额外依赖。
"""

import sys
import os

# ---- ANSI 颜色常量 ----
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"
RED = "\033[31m"
BLUE = "\033[34m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _enable_windows_ansi():
    """启用 Windows 10+ 控制台的 ANSI 支持。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(-11)
        # 获取当前控制台模式
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


_enable_windows_ansi()


def cprint(text: str, color: str = RESET, end: str = "\n"):
    """带颜色的打印。"""
    sys.stdout.write(f"{color}{text}{RESET}{end}")
    sys.stdout.flush()


def cwrite(text: str, color: str = RESET):
    """带颜色的写入（不换行，立即刷新）。"""
    sys.stdout.write(f"{color}{text}{RESET}")
    sys.stdout.flush()
