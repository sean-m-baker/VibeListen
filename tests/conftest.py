"""Pytest configuration — shared fixtures for all tests."""
import pytest


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """Reset rate limiter storage before each test to prevent cross-test bleed."""
    import backend.main as main
    main.limiter._limiter.storage.reset()
