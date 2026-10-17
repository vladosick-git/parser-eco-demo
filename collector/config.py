"""Общие настройки сборщика."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
AUDIT_PATH = ROOT / "docs" / "AUDIT.md"
# Публичный корневой сертификат Минцифры: им подписаны сертификаты части госсайтов.
# Добавляется к стандартному набору certifi, проверка TLS не отключается.
EXTRA_CA = Path(__file__).resolve().parent / "certs" / "russian_trusted_root_ca.pem"

USER_AGENT = "EcoCollectorDemo/0.1 (+https://github.com/vladosick-git/parser-eco-demo; portfolio demo, open data only)"
MIN_DELAY_S = 2.0          # минимальная пауза между запросами к одному домену
MAX_CRAWL_DELAY_S = 90.0   # потолок для Crawl-delay из robots.txt
TIMEOUT_S = 60.0
RETRY_PAUSE_S = 15.0       # пауза перед единственным повтором при сетевом сбое

SUMMARY_MAX = 300          # длина краткого описания
NEWS_MAX_AGE_DAYS = 180    # старые записи из лент не забираем
RUNS_KEEP = 200            # сколько запусков хранить в журнале
