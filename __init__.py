"""Native Hermes plugin entrypoint."""

from .workgraph.hermes_adapter import register

__all__ = ["register"]
