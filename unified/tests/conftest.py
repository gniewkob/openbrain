import os
import pytest
import importlib
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True, scope="session")
def global_setup():
    """Session-wide setup to ensure clean environment."""
    # Force disable public mode for all tests by default
    with patch.dict(os.environ, {"PUBLIC_MODE": "false", "PUBLIC_BASE_URL": ""}):
        # Reload modules that define constants based on environment
        import src.auth
        import src.security.policy
        importlib.reload(src.auth)
        importlib.reload(src.security.policy)
        
        # Global mock for Obsidian CLI to prevent hangs
        # We patch the underlying _run method to avoid real subprocess calls
        from unittest.mock import AsyncMock
        with patch("src.common.obsidian_adapter.ObsidianCliAdapter._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ""
            yield

@pytest.fixture(autouse=True)
def disable_public_mode(monkeypatch):
    """Globally disable public mode for all tests unless explicitly enabled."""
    monkeypatch.setenv("PUBLIC_MODE", "false")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    
    from src import config
    config.get_config.cache_clear()
    
    # Also patch the constants in case they were already imported
    with patch("src.auth.PUBLIC_EXPOSURE", False), \
         patch("src.auth.PUBLIC_MODE", False), \
         patch("src.security.policy.PUBLIC_MODE", False):
        yield
