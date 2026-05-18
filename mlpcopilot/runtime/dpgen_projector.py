"""Deprecated compatibility wrapper for the DP-GEN adapter plugin.

New code should import from ``mlpcopilot.plugins.dpgen_adapter`` directly.
The runtime package keeps this wrapper only for older callers.
"""

from __future__ import annotations

from mlpcopilot.plugins.dpgen_adapter.projector import project_dpgen_run

__all__ = ["project_dpgen_run"]
