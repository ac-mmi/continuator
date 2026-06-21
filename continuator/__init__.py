"""Continuator — turn a long conversation into a continuation briefing for another AI."""

from continuator.runtime import bootstrap_engine_path

# Phase 2 platform modules import continuator_engine at CLI load time.
bootstrap_engine_path()

__version__ = "0.1.0"
