"""Запуск: python -m collector [run|export] [--only id1,id2]"""

import argparse
import logging
import sys

from . import runner


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m collector", description="Эко-сборщик открытых данных")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "export"],
                        help="run - собрать данные (по умолчанию), export - только CSV и таблица источников")
    parser.add_argument("--only", help="через запятую id источников, например mnr,zakupki")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.command == "export":
        runner.export()
        return 0
    only = set(args.only.split(",")) if args.only else None
    record = runner.run(only=only)
    t = record["totals"]
    print(f"Готово за {record['duration_s']} с: статус {record['status']}, получено {t['fetched']}, "
          f"новых {t['new']}, дублей {t['duplicates']}, ошибок {t['errors']}")
    return 1 if record["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
