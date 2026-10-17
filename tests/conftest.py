import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Любая попытка открыть сетевое соединение в тестах это ошибка."""
    def guard(*args, **kwargs):
        raise RuntimeError("Тесты не должны ходить в сеть")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
