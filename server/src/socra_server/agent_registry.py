"""Registry of agent backends: what the selector shows and what a selection means."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from socra_server.domain.agent import AgentSelection, BackendInfo, BackendStatus
from socra_server.ports import AgentBackend

logger = logging.getLogger(__name__)


class UnknownSelection(ValueError):
    """The selection names a backend or model this server does not offer."""


class BackendRegistry:
    def __init__(self, backends: Iterable[AgentBackend]) -> None:
        self._backends: dict[str, AgentBackend] = {}
        for backend in backends:
            if backend.id in self._backends:
                raise ValueError(f"Duplicate agent backend id: {backend.id!r}")
            self._backends[backend.id] = backend

    async def describe(self) -> list[BackendInfo]:
        """List every backend with its models and current status, in registration order."""
        statuses = await asyncio.gather(
            *(self._status(b) for b in self._backends.values())
        )
        return [
            BackendInfo(
                id=b.id, label=b.label, models=b.models(), status=status,
                supports_modes=b.supports_modes,
            )
            for b, status in zip(self._backends.values(), statuses)
        ]

    def resolve(self, selection: AgentSelection) -> AgentBackend:
        backend = self._backends.get(selection.backend)
        if backend is None:
            raise UnknownSelection(f"Unknown agent backend: {selection.backend!r}")
        if selection.model not in {m.id for m in backend.models()}:
            raise UnknownSelection(
                f"Unknown model {selection.model!r} for backend {selection.backend!r}"
            )
        return backend

    def default_selection(self) -> AgentSelection | None:
        for backend in self._backends.values():
            models = backend.models()
            if models:
                return AgentSelection(backend.id, models[0].id)
        return None

    @staticmethod
    async def _status(backend: AgentBackend) -> BackendStatus:
        # A failing check must not hide the other backends from the selector.
        try:
            return await backend.check()
        except Exception as exc:
            logger.warning("Agent backend %r check failed: %s", backend.id, exc)
            return BackendStatus("unreachable", str(exc))
