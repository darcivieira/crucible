from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from typing import Any

from crucible.modules.optimizer.domain.assertions import AssertionContext, AssertionResult

PluginAssertionHandler = Callable[
    [str, str, dict[str, Any], AssertionContext],
    Awaitable[AssertionResult] | AssertionResult,
]


class PluginRegistry:
    def __init__(self):
        self.assertions: dict[str, PluginAssertionHandler] = {}
        self.importers: dict[str, Callable[[str], Any]] = {}

    def register_assertion(self, name: str, handler: PluginAssertionHandler) -> None:
        self.assertions[name] = handler

    def register_importer(self, name: str, handler: Callable[[str], Any]) -> None:
        self.importers[name] = handler


_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    return _registry


def load_plugins(module_names: list[str]) -> PluginRegistry:
    registry = get_plugin_registry()
    for module_name in module_names:
        module = importlib.import_module(module_name)
        register = getattr(module, "register", None)
        if callable(register):
            register(registry)
    return registry
