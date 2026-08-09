"""日志系统：控制台 + 滚动文件双落点，级别 INFO。

用法：`logger = get_logger("battle")` → 记录到 `app.battle` logger，控制台与
data/logs/app.log 双写。在 main.py 的 lifespan 里调用 setup_logging() 初始化一次。
"""

import logging
import os
from logging.handlers import RotatingFileHandler

_LOGGER_PREFIX = "app"
_LOG_FILE = "data/logs/app.log"
_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def setup_logging() -> None:
    """初始化根日志配置（幂等）：控制台 StreamHandler + 滚动文件 RotatingFileHandler。"""
    global _initialized
    if _initialized:
        return
    _initialized = True
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)
    os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
    file_h = RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_h.setFormatter(fmt)
    root.addHandler(file_h)


def get_logger(name: str) -> logging.Logger:
    """取带 `app.` 前缀的命名 logger。"""
    return logging.getLogger(f"{_LOGGER_PREFIX}.{name}")
