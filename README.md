# Hyperliquid DCA Bot

Минималистичный DCA-бот для **спот-рынка Hyperliquid**. Один запуск = одна покупка,
расписание задаётся системным **crontab**.

## Quickstart

```bash
git clone https://github.com/LoveBloodAndDiamonds/hyperliquid-dca-bot.git
cd hyperliquid-dca-bot
uv sync
cp .env.dist .env       # вписать PRIVATE_KEY, опционально Telegram
nano .env
```

Разовая покупка:

```bash
uv run -m app --coin=BTC --amount=0.001    # купить 0.001 BTC
uv run -m app --coin=ETH --notional=25     # купить ETH на $25
```

Расписание через `crontab -e`:

```cron
0 * * * *   cd /root/hyperliquid-dca-bot && /usr/local/bin/uv run -m app --coin=BTC --amount=0.001 >> logs/cron.log 2>&1
0 */4 * * * cd /root/hyperliquid-dca-bot && /usr/local/bin/uv run -m app --coin=ETH --notional=25  >> logs/cron.log 2>&1
```

Путь до `uv` — абсолютный (`which uv`), `cd` в директорию проекта обязателен (там лежит `.env`).

## Как это работает

- Размер — ровно один из флагов: `--amount` (в монетах) или `--notional` (в USDC).
- BTC/ETH/SOL автоматически резолвятся в UBTC/UETH/USOL (на споте Hyperliquid торгуются обёрнутые версии).
- Покупка — агрессивная GTC-лимитка с ценой +5% от рыночной (у Hyperliquid нет отдельного "market"-типа).
- Telegram-уведомления включаются, если в `.env` заданы `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`.
- Уровни логов настраиваются через `LOG_LEVEL_STDOUT` / `LOG_LEVEL_FILE` (по умолчанию `INFO`).

## Структура

```
app/
├── __main__.py     # точка входа (uv run -m app)
├── config.py       # парсинг .env и CLI
├── hyperliquid.py  # резолв монеты + размещение ордера
├── telegram.py     # уведомления (best-effort)
└── logger.py       # loguru
```

Логи пишутся в `app.log` (ротация 10 МБ, хранение 7 файлов) и в stdout (попадает в `logs/cron.log` из crontab).
