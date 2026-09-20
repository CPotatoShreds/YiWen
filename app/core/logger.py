"""日志系统：控制台 + 滚动文件双落点，级别 INFO。

用法：`logger = get_logger("scenario")` → 记录到 `app.scenario` logger，控制台与
logs/app-<pid>.log 双写。在 main.py 的 lifespan 里调用 setup_logging() 初始化一次。

文件名带进程 PID：Windows 下 RotatingFileHandler 滚动要 rename 目标文件，任何其他
进程持有同一文件都会导致 PermissionError（滚动静默失效）。多实例/测试并行时每个
进程只写自己的文件，互不冲突；启动时清理超过一天的陈旧进程日志。

request_id：由 RequestIdMiddleware（app/core/middleware.py）写入 contextvar，
随 asyncio.create_task 自动透传到后台任务；日志过滤器把它注入每条记录。
LOG_JSON=true 时输出结构化 JSON（生产采集用），默认保持人类可读文本。
"""

import contextvars
import json
import logging
import os
import time
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from app.core.config import get_settings

_LOGGER_PREFIX = "app"
_LOG_DIR = "logs"
_LOG_FILE = os.path.join(_LOG_DIR, f"app-{os.getpid()}.log")
_STALE_LOG_SECONDS = 24 * 60 * 60  # 超过一天的进程日志视为陈旧，启动时清理
_FORMAT = "[%(asctime)s] [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def set_request_id(value: str) -> contextvars.Token:
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """结构化输出：时间戳统一 UTC ISO8601，供日志采集系统解析。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _purge_stale_logs() -> None:
    """删除超过一天的进程日志（含历史遗留的无 PID 版 app.log）。尽力而为，失败不阻塞启动。"""
    try:
        now = time.time()
        for name in os.listdir(_LOG_DIR):
            if not name.startswith("app"):
                continue
            if not (name.endswith(".log") or ".log." in name):
                continue
            path = os.path.join(_LOG_DIR, name)
            try:
                if now - os.path.getmtime(path) > _STALE_LOG_SECONDS:
                    os.remove(path)
            except OSError:
                pass  # 文件被其他进程持有（Windows）或已消失：留给下次启动
    except OSError:
        pass


def setup_logging() -> None:
    """初始化根日志配置（幂等）：控制台 StreamHandler + 滚动文件 RotatingFileHandler。"""
    global _initialized
    if _initialized:
        return
    _initialized = True
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    rid_filter = RequestIdFilter()
    if get_settings().LOG_JSON:
        fmt: logging.Formatter = JsonFormatter()
    else:
        fmt = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(rid_filter)
    root.addHandler(console)
    os.makedirs(_LOG_DIR, exist_ok=True)
    _purge_stale_logs()
    file_h = RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8", delay=True)
    file_h.setFormatter(fmt)
    file_h.addFilter(rid_filter)
    root.addHandler(file_h)


def get_logger(name: str) -> logging.Logger:
    """取带 `app.` 前缀的命名 logger。"""
    return logging.getLogger(f"{_LOGGER_PREFIX}.{name}")
