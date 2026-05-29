from html import escape

import aiohttp
from loguru import logger

# Базовый URL Telegram Bot API
_API_BASE = "https://api.telegram.org"

# Ссылка на страницу торговли спот-парой на Hyperliquid
_TRADE_URL_TEMPLATE = "https://app.hyperliquid.xyz/trade/{coin}"


def _trade_url(coin: str) -> str:
    """Возвращает ссылку на страницу спот-торговли монетой."""
    return _TRADE_URL_TEMPLATE.format(coin=coin.upper())


def build_success_message(coin: str, qty: float, price: float) -> str:
    """Форматирует HTML-сообщение об успешной покупке.

    Args:
        coin: тикер монеты.
        qty: купленное количество монет.
        price: рыночная цена на момент покупки (USDC).
    """
    coin_safe = escape(coin)
    notional = qty * price
    return (
        f"✅ <b>DCA buy executed</b>\n"
        f"<b>Coin:</b> {coin_safe}\n"
        f"<b>Amount:</b> {qty} {coin_safe}\n"
        f"<b>Price:</b> ${price:,.4f}\n"
        f"<b>Notional:</b> ~${notional:,.2f}\n"
        f'<a href="{_trade_url(coin)}">Open on Hyperliquid →</a>'
    )


def build_error_message(coin: str, size_desc: str, error: str) -> str:
    """Форматирует HTML-сообщение об ошибке покупки.

    Args:
        coin: тикер монеты.
        size_desc: человекочитаемое описание размера заказа (например "0.001 BTC" или "$10").
        error: текст ошибки.
    """
    coin_safe = escape(coin)
    size_safe = escape(size_desc)
    error_safe = escape(error)
    return (
        f"❌ <b>DCA buy failed</b>\n"
        f"<b>Coin:</b> {coin_safe}\n"
        f"<b>Size:</b> {size_safe}\n"
        f"<b>Error:</b> <code>{error_safe}</code>\n"
        f'<a href="{_trade_url(coin)}">Open on Hyperliquid →</a>'
    )


async def send_notification(token: str, chat_id: str, text: str) -> None:
    """Отправляет HTML-сообщение в Telegram. Ошибки только логируем — не падаем.

    Args:
        token: токен бота из @BotFather.
        chat_id: ID чата (может быть числом или @username).
        text: тело сообщения в HTML.
    """
    url = f"{_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"Telegram API returned {resp.status}: {body}")
    except Exception as e:
        # Уведомление — best-effort, не должно ломать основной flow покупки
        logger.warning(f"Failed to send Telegram notification: {e}")
