"""Shared exception types for agent role adapters."""


class AgentOutputError(ValueError):
    """A model response was not usable at the typed product boundary."""


class AgentAborted(Exception):
    """The owning Run was cancelled; raised inside a tool to unwind the model session."""
