"""Реестр адаптеров: все подклассы Source из модулей этого пакета подхватываются автоматически."""

import importlib
import inspect
import pkgutil

from .base import Source


def discover() -> list[Source]:
    found: dict[str, Source] = {}
    for module_info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if module_info.name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (issubclass(cls, Source) and cls.__module__ == module.__name__
                    and cls.id and cls.enabled):
                if cls.id in found:
                    raise ValueError(f"Повторяющийся id источника: {cls.id}")
                found[cls.id] = cls()
    return list(found.values())
