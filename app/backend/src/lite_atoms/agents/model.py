"""Model adapter factory and cooperative-abort plumbing shared by all agent roles."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Callable

from langchain_openai import ChatOpenAI

from lite_atoms.settings import settings


logger = logging.getLogger(__name__)


def _model(json_mode: bool = False) -> ChatOpenAI:
    """Build the sole configurable OpenAI-compatible model adapter.

    `json_mode` asks the provider for protocol-level JSON output; providers that do
    not support it fail loudly, and callers fall back to plain text extraction.
    A bounded request timeout keeps a reasoning model's long thinking from blocking
    a Run forever; the SDK retries transient failures before surfacing them.
    """
    kwargs: dict[str, Any] = {
        "model": settings.model_name,
        "api_key": settings.model_api_key,
        "base_url": settings.model_base_url,
        "temperature": 0,
        "request_timeout": 180,
        "max_retries": 2,
    }
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(**kwargs)


def _start_abort_watcher(
    model: ChatOpenAI, should_abort: Callable[[], bool], finished: threading.Event, name: str
) -> None:
    """Close the model's HTTP client once the owning Run is cancelled.

    The daemon thread polls the durable cancel flag; closing the client makes an
    in-flight request fail immediately instead of streaming to completion. Callers
    must set `finished` when the session ends so the watcher exits.
    """

    def _watch() -> None:
        while not finished.wait(1.0):
            if should_abort():
                try:
                    model.root_client.close()
                except Exception:
                    logger.debug("Model client already closed", exc_info=True)
                return

    threading.Thread(target=_watch, daemon=True, name=name).start()


@contextmanager
def agent_session(
    model_factory: Callable[[], ChatOpenAI] | None = None,
    should_abort: Callable[[], bool] | None = None,
    watcher_name: str = "agent-abort-watcher",
) -> Iterator[ChatOpenAI]:
    """Yield a model adapter with the cooperative-abort watcher armed for the session.

    Every agent role needs the same scaffolding — build the model, start the watcher
    that force-closes the HTTP client on cancellation, and guarantee the watcher is
    stopped on every exit path. Centralizing it here keeps cancellation semantics in
    exactly one place as new roles are added.

    `model_factory` defaults to the plain `_model()` adapter. Roles pass a factory
    (e.g. `lambda: _model(json_mode=True)`) rather than a prebuilt model so the
    adapter is constructed inside the session — this keeps test doubles patched onto
    the caller's module namespace working, and keeps model construction lazy.
    """
    factory = model_factory or _model
    model = factory()
    finished = threading.Event()
    if should_abort:
        _start_abort_watcher(model, should_abort, finished, name=watcher_name)
    try:
        yield model
    finally:
        finished.set()
