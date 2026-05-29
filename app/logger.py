import os
import sys
from pathlib import Path

from loguru import logger

# Директория для логов: сюда пишет и сам бот (app.log), и crontab (cron.log).
# Создаём заранее, иначе loguru при первом запуске упадёт на отсутствующем пути.
_LOG_DIR = Path("logs")

# Допустимые уровни loguru. Если в .env указано что-то другое — падаем явно,
# чтобы не молча ловить логи "в никуда".
_VALID_LEVELS = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}


def _read_level(env_name: str, default: str) -> str:
    """Читает уровень логирования из переменной окружения с валидацией."""
    raw = (os.getenv(env_name) or default).upper().strip()
    if raw not in _VALID_LEVELS:
        raise SystemExit(
            f"Invalid {env_name}={raw!r}. Allowed: {', '.join(sorted(_VALID_LEVELS))}"
        )
    return raw


def setup_logger() -> None:
    """Настраивает loguru: stdout + ротация файла app.log.

    Уровни читаются из .env:
        LOG_LEVEL_STDOUT — по умолчанию INFO
        LOG_LEVEL_FILE   — по умолчанию INFO
    """
    _LOG_DIR.mkdir(exist_ok=True)

    logger.remove()
    fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    logger.add(sys.stdout, format=fmt, level=_read_level("LOG_LEVEL_STDOUT", "INFO"))
    logger.add(
        _LOG_DIR / "app.log",
        format=fmt,
        level=_read_level("LOG_LEVEL_FILE", "INFO"),
        rotation="10 MB",
        retention=7,
    )
