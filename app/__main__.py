import asyncio
import sys

from dotenv import load_dotenv
from loguru import logger

from .config import load_config
from .hyperliquid import buy_spot
from .logger import setup_logger
from .telegram import build_error_message, build_success_message, send_notification


async def _run() -> int:
    """Точка входа: одна покупка по параметрам CLI + опциональное уведомление в TG.

    Returns:
        Код возврата процесса (0 — успех, 1 — ошибка покупки).
    """
    # .env читаем явно здесь — нужно, чтобы LOG_LEVEL_* подхватились до setup_logger.
    # load_config() ниже сделает load_dotenv ещё раз, но это идемпотентно.
    load_dotenv()
    setup_logger()
    config = load_config()

    # Человекочитаемое описание размера для логов/уведомлений
    size_desc = (
        f"{config.amount} {config.coin}"
        if config.amount is not None
        else f"${config.notional}"
    )
    logger.info(f"DCA buy starting | coin={config.coin} | size={size_desc}")

    try:
        result = await buy_spot(
            private_key=config.private_key,
            coin=config.coin,
            amount=config.amount,
            notional=config.notional,
        )
    except Exception as e:
        logger.error(f"Unexpected error during buy: {e}")
        if config.telegram_enabled:
            await send_notification(
                config.telegram_token,  # type: ignore[arg-type]
                config.telegram_chat_id,  # type: ignore[arg-type]
                build_error_message(config.coin, size_desc, str(e)),
            )
        return 1

    if result.success:
        logger.info(
            f"Order placed | {config.coin} | qty={result.qty} | "
            f"price={result.price} | response={result.raw_response}"
        )
        if config.telegram_enabled:
            await send_notification(
                config.telegram_token,  # type: ignore[arg-type]
                config.telegram_chat_id,  # type: ignore[arg-type]
                build_success_message(config.coin, result.qty, result.price),
            )
        return 0
    else:
        logger.error(f"Order failed | {config.coin} | error={result.error}")
        if config.telegram_enabled:
            await send_notification(
                config.telegram_token,  # type: ignore[arg-type]
                config.telegram_chat_id,  # type: ignore[arg-type]
                build_error_message(config.coin, size_desc, result.error or "unknown"),
            )
        return 1


def main() -> None:
    """Синхронная обёртка для запуска через `python -m app`."""
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
