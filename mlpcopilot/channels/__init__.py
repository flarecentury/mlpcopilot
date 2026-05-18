"""Chat channels module with plugin architecture."""

from mlpcopilot.channels.base import BaseChannel
from mlpcopilot.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
