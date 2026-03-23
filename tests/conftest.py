"""Pytest configuration and shared fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture
def sample_date() -> str:
    return "2026-03-20"
