import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from unicex.hyperliquid import UniClient


# Смещение для индексации спот-активов в exchange-эндпоинте Hyperliquid.
# Документация: asset = 10000 + universe_index для спота.
_SPOT_ASSET_OFFSET = 10000

# Множитель цены для агрессивной лимитки, имитирующей market buy.
# Гарантирует мгновенное исполнение по верхней стороне стакана.
_MARKET_BUY_PRICE_MULTIPLIER = 1.05

# Алиасы привычных тикеров для спот-рынка Hyperliquid.
# Список выверен по реальному ответу /info type=spotMeta:
# BTC/ETH/SOL на споте Hyperliquid представлены обёрнутыми версиями
# (UBTC, UETH, USOL — мостовые U-токены), а голые BTC/ETH/SOL — это перпетуалы.
# Нативные токены платформы (HYPE, PUMP, TRUMP и пр.) торгуются под своими
# именами и алиасов не требуют.
_SPOT_TICKER_ALIASES: dict[str, str] = {
    "BTC": "UBTC",
    "ETH": "UETH",
    "SOL": "USOL",
}


@dataclass(frozen=True)
class SpotAsset:
    """Метаданные спот-актива, нужные для размещения ордера."""

    coin: str            # человеческое имя, например "BTC"
    asset_int: int       # числовой ID для поля "a" в action ордера
    pair_name: str       # имя пары в universe, например "@142"
    sz_decimals: int     # точность размера ордера


@dataclass(frozen=True)
class OrderResult:
    """Результат попытки разместить ордер."""

    success: bool
    price: float
    qty: float
    raw_response: Any
    error: str | None = None


def _resolve_spot_asset(spot_meta: dict, coin: str) -> SpotAsset:
    """Находит спот-актив по тикеру через метаданные Hyperliquid.

    Поддерживает алиасы: BTC → UBTC, ETH → UETH и т.п. — на споте Hyperliquid
    торгуются "обёрнутые" версии этих монет, а не базовые тикеры.

    Args:
        spot_meta: ответ /info type=spotMeta
        coin: тикер монеты, например "BTC" или сразу "UBTC"

    Returns:
        SpotAsset со всеми параметрами для размещения ордера.
        Поле coin содержит реальный спот-тикер (UBTC), а не введённый алиас.

    Raises:
        ValueError: если токен или его spot-пара (с USDC) не найдены.
    """
    # Резолвим алиас: если пользователь написал BTC — ищем UBTC
    requested = coin.upper()
    resolved = _SPOT_TICKER_ALIASES.get(requested, requested)

    token = next((t for t in spot_meta["tokens"] if t["name"].upper() == resolved), None)
    if token is None:
        raise ValueError(f"Token {resolved} not found in Hyperliquid spot universe")

    token_idx = token["index"]
    sz_decimals = int(token["szDecimals"])

    # На споте торгуются пары токен/USDC, USDC имеет index=0.
    # Ищем пару, у которой первый токен — наш, второй — USDC (index 0).
    # ВАЖНО: asset_int считаем по полю pair["index"], а НЕ по позиции в массиве —
    # эти значения могут расходиться (массив бывает с пропусками или отсортирован),
    # а имя пары (@142) всегда соответствует именно pair["index"].
    for pair in spot_meta["universe"]:
        tokens_pair = pair.get("tokens", [])
        if len(tokens_pair) >= 2 and tokens_pair[0] == token_idx and tokens_pair[1] == 0:
            return SpotAsset(
                coin=resolved,
                asset_int=_SPOT_ASSET_OFFSET + int(pair["index"]),
                pair_name=pair["name"],
                sz_decimals=sz_decimals,
            )

    raise ValueError(f"Spot pair {resolved}/USDC not found in Hyperliquid universe")


def _round_price(px: float, sz_decimals: int) -> float:
    """Округляет цену по правилам Hyperliquid: 5 значащих цифр и максимум (8 - szDecimals) знаков после запятой."""
    if px == 0:
        return 0.0
    sig5 = round(px, -int(math.floor(math.log10(abs(px)))) + 4)
    max_dec = 8 - sz_decimals
    return round(sig5, max_dec)


def _to_wire(value: float) -> str:
    """Преобразует число в строку без хвостовых нулей — формат, который ждёт Hyperliquid при подписи."""
    return format(Decimal(str(value)).normalize(), "f")


async def buy_spot(
    private_key: str,
    coin: str,
    amount: float | None = None,
    notional: float | None = None,
) -> OrderResult:
    """Выполняет одну покупку на споте Hyperliquid.

    Размер задаётся ровно одним из аргументов: amount (в монетах) или notional
    (в долларах — количество монет посчитается по текущей рыночной цене).

    Покупка реализована как агрессивная GTC-лимитка с ценой +5% от рыночной —
    Hyperliquid не поддерживает отдельный "market" тип, и это стандартный приём,
    рекомендованный их же Python SDK. На споте такая лимитка мгновенно исполняется.

    Args:
        private_key: приватный ключ кошелька.
        coin: тикер монеты (BTC, ETH, ...).
        amount: количество монет к покупке. Взаимоисключающий с notional.
        notional: сумма к покупке в USDC. Взаимоисключающий с amount.

    Returns:
        OrderResult с результатом исполнения.

    Raises:
        ValueError: если не передан ни amount, ни notional, или переданы оба.
    """
    if (amount is None) == (notional is None):
        raise ValueError("Specify exactly one of: amount, notional")

    client = await UniClient.create(private_key=private_key)
    inner = client._client  # низкоуровневый клиент с place_order

    try:
        # Получаем метаданные спот-рынка для резолва asset_id и szDecimals
        spot_meta = await inner.spot_metadata()
        asset = _resolve_spot_asset(spot_meta, coin)

        # Текущая цена нужна и для расчёта агрессивной лимитки, и
        # (опционально) для перевода долларовой суммы в количество монет.
        prices = await client.last_price(resolve_symbols=False)
        if asset.pair_name not in prices:
            fallback_qty = amount if amount is not None else 0.0
            return OrderResult(
                success=False, price=0.0, qty=fallback_qty, raw_response=None,
                error=f"Price not found for {coin} ({asset.pair_name})",
            )

        market_price = prices[asset.pair_name]

        # Количество монет: либо взято напрямую, либо посчитано из долларов.
        raw_qty = amount if amount is not None else notional / market_price  # type: ignore[operator]
        qty = round(raw_qty, asset.sz_decimals)

        if qty <= 0:
            return OrderResult(
                success=False, price=market_price, qty=qty, raw_response=None,
                error=f"Computed qty is 0 after rounding to {asset.sz_decimals} decimals",
            )

        limit_px = _round_price(market_price * _MARKET_BUY_PRICE_MULTIPLIER, asset.sz_decimals)

        result = await inner.place_order(
            asset=asset.asset_int,
            is_buy=True,
            size=_to_wire(qty),
            reduce_only=False,
            order_type="limit",
            order_body={"tif": "Gtc"},
            price=_to_wire(limit_px),
        )

        # Hyperliquid возвращает status="ok" на уровне ответа, но статусы ордеров
        # могут содержать "error" — проверяем оба уровня.
        ok = _is_order_successful(result)
        return OrderResult(
            success=ok,
            price=market_price,
            qty=qty,
            raw_response=result,
            error=None if ok else _extract_error(result),
        )
    finally:
        await inner._session.close()


def _is_order_successful(response: Any) -> bool:
    """Проверяет, что ответ exchange-эндпоинта означает успешное размещение/исполнение."""
    if not isinstance(response, dict):
        return False
    if response.get("status") != "ok":
        return False
    statuses = (
        response.get("response", {}).get("data", {}).get("statuses", [])
    )
    if not statuses:
        return False
    # Если хоть в одном статусе есть "error" — считаем неуспехом
    return all("error" not in s for s in statuses if isinstance(s, dict))


def _extract_error(response: Any) -> str:
    """Достаёт сообщение об ошибке из ответа exchange-эндпоинта."""
    if not isinstance(response, dict):
        return str(response)
    if response.get("status") != "ok":
        return str(response.get("response") or response)
    statuses = response.get("response", {}).get("data", {}).get("statuses", [])
    for s in statuses:
        if isinstance(s, dict) and "error" in s:
            return str(s["error"])
    return str(response)
