"""Tests for the agent backend registry, using an in-memory fake backend."""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from socra_server.agent_registry import BackendRegistry, UnknownSelection
from socra_server.domain.agent import (
    AgentEvent,
    AgentSelection,
    BackendStatus,
    ModelOption,
    ReplyDone,
)
from socra_server.ports import AgentBackend, PermissionDecider


class FakeConversation:
    async def send(self, text: str) -> AsyncIterator[AgentEvent]:
        yield ReplyDone(text=f"echo: {text}")

    async def interrupt(self) -> None:
        pass

    async def close(self) -> None:
        pass


class FakeBackend:
    def __init__(
        self,
        backend_id: str = "fake",
        models: list[str] | None = None,
        status: BackendStatus | Exception | None = None,
    ) -> None:
        self.id = backend_id
        self.label = backend_id.title()
        self.supports_modes = backend_id == "alpha"
        self._models = models if models is not None else ["small", "large"]
        self._status = status or BackendStatus("ready")

    def models(self) -> list[ModelOption]:
        return [ModelOption(id=m, label=m.title()) for m in self._models]

    async def check(self) -> BackendStatus:
        if isinstance(self._status, Exception):
            raise self._status
        return self._status

    async def open(
        self, model: str, cwd: Path, decide_permission: PermissionDecider
    ) -> FakeConversation:
        return FakeConversation()


def test_fake_backend_satisfies_port():
    assert isinstance(FakeBackend(), AgentBackend)


async def test_describe_lists_backends_with_models_and_status():
    registry = BackendRegistry([
        FakeBackend("alpha", ["a1", "a2"]),
        FakeBackend("beta", ["b1"], BackendStatus("not_configured", "Missing login")),
    ])

    infos = await registry.describe()

    assert [i.id for i in infos] == ["alpha", "beta"]
    assert [m.id for m in infos[0].models] == ["a1", "a2"]
    assert infos[0].status == BackendStatus("ready")
    assert infos[1].status == BackendStatus("not_configured", "Missing login")
    assert [i.supports_modes for i in infos] == [True, False]


async def test_describe_reports_failing_check_as_unreachable_without_hiding_others():
    registry = BackendRegistry([
        FakeBackend("broken", status=RuntimeError("CLI not found")),
        FakeBackend("ok"),
    ])

    infos = await registry.describe()

    assert infos[0].status.state == "unreachable"
    assert "CLI not found" in infos[0].status.message
    assert infos[1].status.ready


def test_resolve_returns_backend_for_known_selection():
    beta = FakeBackend("beta", ["b1"])
    registry = BackendRegistry([FakeBackend("alpha"), beta])

    assert registry.resolve(AgentSelection("beta", "b1")) is beta


@pytest.mark.parametrize(
    "selection",
    [AgentSelection("missing", "small"), AgentSelection("fake", "missing")],
)
def test_resolve_rejects_unknown_backend_or_model(selection):
    registry = BackendRegistry([FakeBackend()])

    with pytest.raises(UnknownSelection):
        registry.resolve(selection)


def test_duplicate_backend_ids_are_rejected():
    with pytest.raises(ValueError):
        BackendRegistry([FakeBackend("same"), FakeBackend("same")])


def test_default_selection_is_first_backend_first_model():
    registry = BackendRegistry([FakeBackend("alpha", ["a1", "a2"]), FakeBackend("beta")])

    assert registry.default_selection() == AgentSelection("alpha", "a1")
    assert BackendRegistry([]).default_selection() is None
