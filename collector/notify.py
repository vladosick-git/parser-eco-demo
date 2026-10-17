"""Уведомление о сбоях в Telegram. Без секретов TELEGRAM_TOKEN и TELEGRAM_CHAT_ID шаг пропускается."""

import logging
import os

import httpx

log = logging.getLogger("collector")


def format_failure(record: dict) -> str:
    lines = [f"Эко-сборщик: ошибки в запуске {record['run_id']} ({record['status']})"]
    for r in record["sources"]:
        if r["status"] == "error":
            lines.append(f"- {r['source_name']}: {r['error']}")
    return "\n".join(lines)


def send_failure(record: dict) -> bool:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.info("Telegram не настроен, уведомление пропущено")
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": format_failure(record)[:4000]},
            timeout=20,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        # в лог не пишем URL целиком: в нём токен
        log.warning("Не удалось отправить уведомление в Telegram: %s", type(exc).__name__)
        return False
