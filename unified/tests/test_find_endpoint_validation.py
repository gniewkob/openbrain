from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from src.schemas import MemoryFindRequest


class FindEndpointValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_v1_find_maps_filter_validation_error_to_422(self) -> None:
        from src.api.v1 import memory as mem_module

        req = MemoryFindRequest(query="policy", limit=5)
        session = AsyncMock()
        user = {"sub": "tester"}

        with (
            patch.object(
                mem_module,
                "find_memories_v1",
                new=AsyncMock(
                    side_effect=ValueError(
                        "filters.include_test_data must be bool when provided"
                    )
                ),
            ),
        ):
            from src.api.v1.memory import v1_find

            with self.assertRaises(HTTPException) as ctx:
                await v1_find(req=req, session=session, _user=user)

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("include_test_data must be bool", str(ctx.exception.detail))
