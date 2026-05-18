"""Message bus module for decoupled channel-agent communication."""

from mlpcopilot.bus.events import InboundMessage, OutboundMessage
from mlpcopilot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
