"""Вежливый HTTP-клиент: robots.txt, пауза между запросами к домену, условные запросы, проверка TLS."""

import re
import ssl
import time
from urllib.parse import urlsplit

import certifi
import httpx

from . import config


class RobotsDisallowed(Exception):
    """robots.txt запрещает этот адрес."""


class RobotsRules:
    """Разбор robots.txt по правилам Google: групповые User-agent, `*` и `$` в путях,
    побеждает самое длинное совпадение, при равенстве Allow."""

    def __init__(self, text: str, agent: str):
        self.rules: list[tuple[bool, str]] = []
        self.crawl_delay: float | None = None
        groups = self._parse_groups(text)
        token = agent.split("/")[0].lower()
        chosen = next((g for g in groups if any(a != "*" and a in token for a in g["agents"])), None)
        chosen = chosen or next((g for g in groups if "*" in g["agents"]), None)
        if chosen:
            self.rules = chosen["rules"]
            self.crawl_delay = chosen["delay"]

    @staticmethod
    def _parse_groups(text: str) -> list[dict]:
        groups: list[dict] = []
        current = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent:
                    current = {"agents": [], "rules": [], "delay": None}
                    groups.append(current)
                current["agents"].append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue
            if key in ("allow", "disallow") and value:
                current["rules"].append((key == "allow", value))
            elif key == "crawl-delay":
                try:
                    current["delay"] = float(value)
                except ValueError:
                    pass
        return groups

    @staticmethod
    def _to_regex(pattern: str) -> re.Pattern:
        anchored = pattern.endswith("$")
        body = re.escape(pattern.rstrip("$")).replace(r"\*", ".*")
        return re.compile(body + ("$" if anchored else ""))

    def allowed(self, path: str) -> bool:
        best_len, best_allow = -1, True
        for allow, pattern in self.rules:
            if self._to_regex(pattern).match(path):
                if len(pattern) > best_len or (len(pattern) == best_len and allow):
                    best_len, best_allow = len(pattern), allow
        return best_allow


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.load_verify_locations(str(config.EXTRA_CA))
    return ctx


class PoliteClient:
    """Один запрос за раз, пауза по каждому домену, уважение robots.txt и Crawl-delay.

    http_cache: словарь {url: {"etag": ..., "last_modified": ...}}, сохраняется между запусками.
    """

    def __init__(self, http_cache: dict | None = None, *, transport=None, sleep=time.sleep,
                 clock=time.monotonic, min_delay: float = config.MIN_DELAY_S):
        self.http_cache = http_cache if http_cache is not None else {}
        self._sleep, self._clock, self._min_delay = sleep, clock, min_delay
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotsRules] = {}
        self._client = httpx.Client(
            headers={"User-Agent": config.USER_AGENT, "Accept-Language": "ru"},
            timeout=config.TIMEOUT_S,
            follow_redirects=True,
            verify=ssl_context() if transport is None else True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _delay_for(self, host: str) -> float:
        rules = self._robots.get(host)
        crawl = rules.crawl_delay if rules and rules.crawl_delay else 0
        return max(self._min_delay, min(crawl, config.MAX_CRAWL_DELAY_S))

    def _wait(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self._delay_for(host) - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def _send(self, url: str, headers: dict | None = None) -> httpx.Response:
        """Один повтор при сетевом сбое (таймаут, обрыв): госсайты иногда не отвечают с первого раза."""
        host = urlsplit(url).netloc
        for attempt in range(2):
            self._wait(host)
            try:
                return self._client.get(url, headers=headers)
            except httpx.TransportError:
                if attempt == 1:
                    raise
                self._sleep(config.RETRY_PAUSE_S)
        raise AssertionError("unreachable")

    def _rules(self, scheme: str, host: str) -> RobotsRules:
        if host not in self._robots:
            resp = self._send(f"{scheme}://{host}/robots.txt")
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError("robots.txt недоступен", request=resp.request, response=resp)
            # 4xx означает, что правил нет и сбор не ограничен
            text = resp.text if resp.status_code == 200 else ""
            self._robots[host] = RobotsRules(text, config.USER_AGENT)
        return self._robots[host]

    def get(self, url: str, *, conditional: bool = True) -> httpx.Response | None:
        """GET с проверкой robots.txt. Возвращает None, если сервер ответил 304 Not Modified."""
        parts = urlsplit(url)
        rules = self._rules(parts.scheme, parts.netloc)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        if not rules.allowed(path or "/"):
            raise RobotsDisallowed(url)

        headers = {}
        cached = self.http_cache.get(url, {}) if conditional else {}
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]

        resp = self._send(url, headers)
        if resp.status_code == 304:
            return None
        resp.raise_for_status()
        if conditional:
            entry = {k: v for k, v in (("etag", resp.headers.get("etag")),
                                       ("last_modified", resp.headers.get("last-modified"))) if v}
            if entry:
                self.http_cache[url] = entry
            else:
                self.http_cache.pop(url, None)
        return resp
