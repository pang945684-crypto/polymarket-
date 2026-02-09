import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Any

import requests


CONFIG_PATH = Path(__file__).with_name("config.json")
STATE_PATH = Path(__file__).with_name("state.json")

POLYMARKET_TRADES_URL = "https://data-api.polymarket.com/trades"
TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"


@dataclass
class Config:
    polymarket_leader_address: str
    telegram_bot_token: str
    telegram_chat_id: int
    poll_interval_seconds: int = 15
    taker_only: bool = False
    min_trade_size: float = 0.0
    my_bankroll_usdc: float = 0.0
    copy_percent_of_bankroll: float = 0.0
    fixed_copy_usdc: float = 0.0


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"未找到配置文件 {CONFIG_PATH}. 请先复制 config.example.json 为 config.json 并填写参数。"
        )

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    required_keys = [
        "polymarket_leader_address",
        "telegram_bot_token",
        "telegram_chat_id",
    ]
    for key in required_keys:
        if key not in raw or not raw[key]:
            raise ValueError(f"配置文件缺少或为空: {key}")

    return Config(
        polymarket_leader_address=raw["polymarket_leader_address"],
        telegram_bot_token=raw["telegram_bot_token"],
        telegram_chat_id=int(raw["telegram_chat_id"]),
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 15)),
        taker_only=bool(raw.get("taker_only", False)),
        min_trade_size=float(raw.get("min_trade_size", 0.0)),
        my_bankroll_usdc=float(raw.get("my_bankroll_usdc", 0.0)),
        copy_percent_of_bankroll=float(raw.get("copy_percent_of_bankroll", 0.0)),
        fixed_copy_usdc=float(raw.get("fixed_copy_usdc", 0.0)),
    )


def load_state() -> Set[str]:
    """
    简单的状态文件, 只记录最近已经通知过的 transactionHash 集合,
    防止重复推送。
    """
    if not STATE_PATH.exists():
        return set()

    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        hashes = data.get("seen_transaction_hashes", [])
        return set(hashes)
    except Exception as e:
        logging.warning("读取 state.json 失败, 将重新开始记录. 错误: %s", e)
        return set()


def save_state(seen_hashes: Set[str]) -> None:
    # 只保存最近 500 条, 防止文件无限长
    hashes: List[str] = list(seen_hashes)[-500:]
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump({"seen_transaction_hashes": hashes}, f, ensure_ascii=False, indent=2)


def fetch_trades(config: Config, limit: int = 100) -> List[Dict[str, Any]]:
    params = {
        "user": config.polymarket_leader_address,
        "limit": min(limit, 100),
        "takerOnly": "true" if config.taker_only else "false",
    }

    resp = requests.get(POLYMARKET_TRADES_URL, params=params, timeout=10)
    resp.raise_for_status()
    trades = resp.json()

    if not isinstance(trades, list):
        logging.warning("Polymarket 返回格式异常: %s", trades)
        return []

    # 确保按时间从旧到新排序, 方便顺序推送
    trades.sort(key=lambda t: t.get("timestamp", 0))
    return trades


def format_trade_message(trade: Dict[str, Any], config: Config) -> str:
    side = trade.get("side", "?")
    size = trade.get("size", 0)
    price = trade.get("price", 0)
    title = trade.get("title", "")
    outcome = trade.get("outcome", "")
    event_slug = trade.get("eventSlug", "")
    tx_hash = trade.get("transactionHash", "")

    side_zh = "买入" if side.upper() == "BUY" else "卖出" if side.upper() == "SELL" else side
    market_url = f"https://polymarket.com/event/{event_slug}" if event_slug else ""
    tx_url = f"https://polygonscan.com/tx/{tx_hash}" if tx_hash else "N/A"

    # 计算该地址本单的名义金额
    try:
        trade_value_usdc = float(size) * float(price)
    except Exception:
        trade_value_usdc = 0.0

    # 给出建议投入金额（优先使用每单固定金额，其次按资金池百分比）
    bankroll = float(getattr(config, "my_bankroll_usdc", 0.0) or 0.0)
    copy_pct = float(getattr(config, "copy_percent_of_bankroll", 0.0) or 0.0)
    fixed_copy = float(getattr(config, "fixed_copy_usdc", 0.0) or 0.0)

    suggestion_line = ""
    if fixed_copy > 0:
        suggestion_line = f"\n建议: 每单固定跟单 {fixed_copy:.2f} USDC"
    elif bankroll > 0 and copy_pct > 0:
        suggested_usdc = bankroll * copy_pct
        suggestion_line = (
            f"\n建议: 若你的资金池为 {bankroll:.2f} USDC, "
            f"本单按 {copy_pct * 100:.1f}% 跟单, 约 {suggested_usdc:.2f} USDC"
        )

    text = (
        f"📈 Polymarket 跟单信号\n"
        f"方向: {side_zh}\n"
        f"市场: {title}\n"
        f"结果: {outcome}\n"
        f"数量: {size}\n"
        f"价格: {price}\n"
        f"该地址本单名义金额: {trade_value_usdc:.2f} USDC"
        f"{suggestion_line}\n"
        f"市场链接: {market_url or 'N/A'}\n"
        f"交易哈希: {tx_url}"
    )
    return text


def send_telegram_message(config: Config, text: str, market_url: str | None = None) -> None:
    url = TELEGRAM_SEND_MESSAGE_URL.format(token=config.telegram_bot_token)
    payload: Dict[str, Any] = {
        "chat_id": config.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    # 如果有市场链接，则同时附带一个可点击的跟单按钮
    if market_url:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {
                        "text": "🔗 打开市场跟单",
                        "url": market_url,
                    }
                ]
            ]
        }

    resp = requests.post(url, json=payload, timeout=10)
    if not resp.ok:
        logging.error("发送 Telegram 消息失败: %s - %s", resp.status_code, resp.text)
        resp.raise_for_status()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    config = load_config()
    logging.info("已加载配置, 监控地址: %s", config.polymarket_leader_address)

    seen_hashes = load_state()
    if not seen_hashes:
        # 首次运行: 把现有成交记录到 state 中, 但不推送历史
        logging.info("首次运行, 初始化历史成交记录, 不推送历史单。")
        try:
            trades = fetch_trades(config, limit=200)
            for t in trades:
                tx_hash = t.get("transactionHash")
                if tx_hash:
                    seen_hashes.add(tx_hash)
            save_state(seen_hashes)
        except Exception as e:
            logging.error("初始化历史成交失败: %s", e)

    logging.info("开始轮询 Polymarket 成交, 每 %d 秒检查一次。", config.poll_interval_seconds)

    while True:
        try:
            trades = fetch_trades(config, limit=100)

            new_trades: List[Dict[str, Any]] = []
            for t in trades:
                tx_hash = t.get("transactionHash")
                if not tx_hash:
                    continue
                if tx_hash in seen_hashes:
                    continue
                size = float(t.get("size", 0))
                if size < config.min_trade_size:
                    continue
                new_trades.append(t)

            if new_trades:
                logging.info("发现 %d 笔新成交, 正在推送 Telegram...", len(new_trades))

            for t in new_trades:
                msg = format_trade_message(t, config)
                event_slug = t.get("eventSlug", "")
                market_url = (
                    f"https://polymarket.com/event/{event_slug}" if event_slug else None
                )
                try:
                    send_telegram_message(config, msg, market_url)
                    tx_hash = t.get("transactionHash")
                    if tx_hash:
                        seen_hashes.add(tx_hash)
                except Exception as e:
                    logging.error("推送单笔成交失败: %s", e)

            if new_trades:
                save_state(seen_hashes)

        except Exception as e:
            logging.error("轮询过程出错: %s", e)

        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    main()

