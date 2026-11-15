"""Shared loopback HTTP boundary types without runtime behavior."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, TypeAlias, TypedDict

if TYPE_CHECKING:
    from .server import Handler

JsonObject: TypeAlias = dict[str, object]
DomainPost: TypeAlias = Callable[["Handler", list[str]], None]
Webhook: TypeAlias = Callable[[str], None]
DesktopProof: TypeAlias = Callable[[str], str]


class AppVersionRow(TypedDict):
    version: int


class WorkerHealthHook(Protocol):
    worker_health: Callable[[], dict[str, object]]
