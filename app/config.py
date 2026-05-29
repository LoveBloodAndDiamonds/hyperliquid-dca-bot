import argparse
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Полная конфигурация одного запуска бота.

    Объединяет секреты из .env и параметры покупки, переданные через CLI.
    Размер покупки задаётся ровно одним из: amount (в монетах) или notional (в USDC).
    """

    private_key: str
    coin: str
    amount: float | None
    notional: float | None
    telegram_token: str | None
    telegram_chat_id: str | None

    @property
    def telegram_enabled(self) -> bool:
        """Уведомления включены, если в .env заданы и токен, и chat_id."""
        return bool(self.telegram_token and self.telegram_chat_id)


def load_config() -> Config:
    """Загружает .env и парсит аргументы CLI.

    Returns:
        Config — собранная конфигурация запуска.

    Raises:
        SystemExit: если не задан PRIVATE_KEY или некорректные аргументы CLI.
    """
    load_dotenv()

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise SystemExit("PRIVATE_KEY is not set in .env")

    parser = argparse.ArgumentParser(
        prog="app",
        description="One-shot DCA buy on Hyperliquid spot (cron-driven)",
    )
    parser.add_argument(
        "--coin",
        required=True,
        help="Spot ticker, e.g. BTC, ETH, SOL (BTC/ETH/SOL автоматически → UBTC/UETH/USOL)",
    )

    # --amount и --notional взаимоисключающие, но один из них обязателен.
    size_group = parser.add_mutually_exclusive_group(required=True)
    size_group.add_argument(
        "--amount",
        type=float,
        default=None,
        help="Количество монет к покупке. Пример: 0.001 для 0.001 BTC",
    )
    size_group.add_argument(
        "--notional",
        type=float,
        default=None,
        help="Сумма покупки в USDC. Количество монет посчитается по текущей цене. Пример: 10 для $10",
    )

    args = parser.parse_args()

    # Валидация значения: положительное число
    value = args.amount if args.amount is not None else args.notional
    if value is None or value <= 0:
        raise SystemExit("--amount/--notional must be positive")

    return Config(
        private_key=private_key,
        coin=args.coin.upper().strip(),
        amount=args.amount,
        notional=args.notional,
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
    )
