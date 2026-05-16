import pytest
from unittest.mock import AsyncMock, patch
from src.db import get_db_session

@pytest.mark.asyncio
async def test_get_db_session_yields_session():
    """Test that get_db_session yields the session from AsyncSessionLocal."""
    mock_session = AsyncMock()

    # Mock AsyncSessionLocal to return our mock_session when called
    # and ensure mock_session works as an async context manager
    with patch("src.db.AsyncSessionLocal") as mock_session_maker:
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        # get_db_session is an async generator
        generator = get_db_session()
        yielded_session = await anext(generator)

        assert yielded_session == mock_session
        mock_session_maker.assert_called_once()
        mock_session_maker.return_value.__aenter__.assert_called_once()

        # Complete the generator to trigger __aexit__
        try:
            await anext(generator)
        except StopAsyncIteration:
            pass

        mock_session_maker.return_value.__aexit__.assert_called_once()

@pytest.mark.asyncio
async def test_get_db_session_ensures_cleanup_on_error():
    """Test that get_db_session ensures the session is cleaned up even if an error occurs after yield."""
    mock_session = AsyncMock()

    with patch("src.db.AsyncSessionLocal") as mock_session_maker:
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        generator = get_db_session()
        yielded_session = await anext(generator)
        assert yielded_session == mock_session

        # Simulate an error being raised by the consumer of the generator
        with pytest.raises(RuntimeError, match="something went wrong"):
            await generator.athrow(RuntimeError("something went wrong"))

        # Verify __aexit__ was still called
        mock_session_maker.return_value.__aexit__.assert_called_once()
