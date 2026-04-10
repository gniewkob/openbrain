from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .memory_reads import (
    get_hidden_test_data_counts,
    get_memory_domain_status_counts,
    get_memory_status_counts,
)
from .telemetry import set_gauge_metric


def build_memory_gauges(
    status_counts: dict[str, int],
    domain_status_counts: dict[str, dict[str, int]],
    hidden_test_data_counts: dict[str, int] | None = None,
) -> dict[str, float]:
    """Build gauge payload from canonical memory status counts."""
    active_total = int(status_counts.get("active", 0))

    build_active = int(domain_status_counts.get("build", {}).get("active", 0))
    corporate_active = int(domain_status_counts.get("corporate", {}).get("active", 0))
    personal_active = int(domain_status_counts.get("personal", {}).get("active", 0))

    gauges = {
        "active_memories_total": float(active_total),
        "active_memories_build_total": float(build_active),
        "active_memories_corporate_total": float(corporate_active),
        "active_memories_personal_total": float(personal_active),
    }
    if hidden_test_data_counts:
        gauges.update(
            {
                "hidden_test_data_total": float(
                    hidden_test_data_counts.get("hidden_test_data_total", 0)
                ),
                "hidden_test_data_active_total": float(
                    hidden_test_data_counts.get("hidden_test_data_active_total", 0)
                ),
                "hidden_test_data_build_total": float(
                    hidden_test_data_counts.get("hidden_test_data_build_total", 0)
                ),
                "hidden_test_data_corporate_total": float(
                    hidden_test_data_counts.get(
                        "hidden_test_data_corporate_total", 0
                    )
                ),
                "hidden_test_data_personal_total": float(
                    hidden_test_data_counts.get("hidden_test_data_personal_total", 0)
                ),
            }
        )
    return gauges


async def refresh_memory_gauges(session: AsyncSession) -> dict[str, float]:
    """Refresh active memory gauges from database state."""
    status_counts = await get_memory_status_counts(session)
    domain_status_counts = await get_memory_domain_status_counts(session)
    hidden_test_data_counts = await get_hidden_test_data_counts(session)
    gauges = build_memory_gauges(
        status_counts, domain_status_counts, hidden_test_data_counts
    )
    for name, value in gauges.items():
        set_gauge_metric(name, value)
    return gauges
