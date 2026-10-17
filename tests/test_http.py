import httpx
import pytest

from collector.http import PoliteClient, RobotsDisallowed, RobotsRules

ZAKUPKI_ROBOTS = """
User-agent: * # any agent
Disallow: /*auth*
Disallow: /epz/main/public/preview*
Crawl-delay: 60 # crawlers timeout 60
Allow: /*rss*
Disallow: /*.js
"""

SOLIDWASTE_ROBOTS = """
User-agent: Yandex
Disallow: /news/

User-agent: *
Disallow: /search/
Disallow: /user/
"""


def test_robots_wildcards_and_crawl_delay():
    rules = RobotsRules(ZAKUPKI_ROBOTS, "EcoCollectorDemo/0.1")
    assert rules.crawl_delay == 60
    assert rules.allowed("/epz/order/extendedsearch/rss.html?searchString=x")
    assert not rules.allowed("/epz/main/public/preview/1")
    assert not rules.allowed("/oauth/login")
    assert not rules.allowed("/static/app.js")


def test_robots_uses_star_group_not_other_bots():
    rules = RobotsRules(SOLIDWASTE_ROBOTS, "EcoCollectorDemo/0.1")
    assert rules.allowed("/news.html")
    assert rules.allowed("/news/view/1.html")
    assert not rules.allowed("/search/?q=1")


def test_robots_longest_match_and_allow_wins_tie():
    rules = RobotsRules("User-agent: *\nDisallow: /a\nAllow: /a/b\nDisallow: /x$\nAllow: /x$", "bot")
    assert not rules.allowed("/a/c")
    assert rules.allowed("/a/b/c")
    assert rules.allowed("/x")
    assert RobotsRules("", "bot").allowed("/anything")


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def time(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(round(s, 1))
        self.t += s


def make_client(handler, clock=None, cache=None):
    clock = clock or Clock()
    return PoliteClient(cache if cache is not None else {}, transport=httpx.MockTransport(handler),
                        sleep=clock.sleep, clock=clock.time), clock


def test_respects_robots_disallow():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        return httpx.Response(200, text="ok")

    client, _ = make_client(handler)
    assert client.get("https://site.ru/public").text == "ok"
    with pytest.raises(RobotsDisallowed):
        client.get("https://site.ru/private/page")


def test_waits_between_requests_to_same_domain_with_crawl_delay():
    def handler(request):
        if request.url.path == "/robots.txt":
            body = "User-agent: *\nCrawl-delay: 60\n" if request.url.host == "slow.ru" else ""
            return httpx.Response(200, text=body)
        return httpx.Response(200, text="ok")

    client, clock = make_client(handler)
    client.get("https://fast.ru/1")       # robots + страница: пауза 2 с
    client.get("https://fast.ru/2")       # ещё 2 с
    client.get("https://slow.ru/1")       # robots + страница: Crawl-delay 60
    client.get("https://slow.ru/2")
    assert clock.sleeps == [2.0, 2.0, 60.0, 60.0]


def test_conditional_requests_and_304():
    seen_headers = []

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        seen_headers.append(request.headers.get("if-none-match"))
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, text="feed", headers={"ETag": '"v1"', "Last-Modified": "Fri, 16 Oct 2026"})

    cache = {}
    client, _ = make_client(handler, cache=cache)
    assert client.get("https://feed.ru/rss").text == "feed"
    assert cache["https://feed.ru/rss"] == {"etag": '"v1"', "last_modified": "Fri, 16 Oct 2026"}
    assert client.get("https://feed.ru/rss") is None
    assert seen_headers == [None, '"v1"']


def test_http_error_raises():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(503)

    client, _ = make_client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://down.ru/rss")


def test_retries_once_on_network_error():
    attempts = {"n": 0}

    def flaky(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectTimeout("handshake timed out", request=request)
        return httpx.Response(200, text="ok")

    client, clock = make_client(flaky)
    assert client.get("https://gov.ru/rss").text == "ok"
    assert attempts["n"] == 2 and 15.0 in clock.sleeps

    def dead(request):
        raise httpx.ConnectTimeout("handshake timed out", request=request)

    client, _ = make_client(dead)
    with pytest.raises(httpx.ConnectTimeout):
        client.get("https://gov.ru/rss")
