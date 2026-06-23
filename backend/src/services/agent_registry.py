"""Agent registry: pluggable role-to-factory mapping for multi-agent pipelines."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class AgentRegistry:
    """Register and create agents by pipeline role name."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Any]] = {}

    def register(self, role: str, factory: Callable[[], Any]) -> None:
        """Register a factory for a pipeline role."""
        self._factories[role] = factory

    def create(self, role: str) -> Any:
        """Instantiate the agent registered for a role."""
        factory = self._factories.get(role)
        if factory is None:
            raise KeyError(f"Unknown agent role: {role}")
        return factory()

    def roles(self) -> list[str]:
        """Return registered role names in stable order."""
        return sorted(self._factories)

    def has_role(self, role: str) -> bool:
        return role in self._factories