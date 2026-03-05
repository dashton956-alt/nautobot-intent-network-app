"""Atomic resource allocation for Route Distinguishers and Route Targets.

Uses select_for_update() to lock the pool row at the database level,
preventing two concurrent resolution jobs from allocating the same value.

All allocation functions must be called inside a transaction.atomic() block.
The Jobs that call these already wrap their work in a transaction.
"""

import logging

from django.conf import settings
from django.db import transaction

from intent_networking.models import (
    Intent,
    RouteDistinguisher,
    RouteDistinguisherPool,
    RouteTarget,
    RouteTargetPool,
)

logger = logging.getLogger(__name__)


def _get_plugin_config(key: str):
    """Retrieve a value from the intent_networking plugin config."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key)


def allocate_route_distinguisher(device, vrf_name: str, intent: Intent) -> str:
    """Claim the next available RD from the configured pool for this device+VRF.

    If an RD is already allocated for this device+VRF combination, return the
    existing one (idempotent). This handles re-resolution of the same intent
    version without leaking RD values.

    Args:
        device:   Nautobot Device ORM object
        vrf_name: VRF name string e.g. "ACMECORP-PCI"
        intent:   Intent ORM object (used for pool lookup and FK)

    Returns:
        RD string e.g. "65000:7823"

    Raises:
        ValueError: if pool is exhausted or not found
    """
    # Check for existing allocation first (idempotency)
    existing = RouteDistinguisher.objects.filter(device=device, vrf_name=vrf_name).first()

    if existing:
        logger.info("Reusing existing RD %s for %s/%s", existing.value, device.name, vrf_name)
        return existing.value

    # Get pool name from plugin config
    pool_name = _get_plugin_config("rd_pool_name")

    with transaction.atomic():
        # Lock the pool row to prevent concurrent allocation
        try:
            pool = RouteDistinguisherPool.objects.select_for_update().get(name=pool_name)
        except RouteDistinguisherPool.DoesNotExist as exc:
            raise ValueError(
                f"RD pool '{pool_name}' not found. "
                f"Create it in Nautobot admin under "
                f"Intent Engine \u2192 Route Distinguisher Pools."
            ) from exc

        # Find all currently used values in this pool
        used = set(RouteDistinguisher.objects.filter(pool=pool).values_list("value", flat=True))

        # Find first available value in range
        for i in range(pool.range_start, pool.range_end + 1):
            candidate = f"{pool.asn}:{i}"
            if candidate not in used:
                rd = RouteDistinguisher.objects.create(
                    pool=pool,
                    value=candidate,
                    device=device,
                    vrf_name=vrf_name,
                    intent=intent,
                )
                logger.info(
                    "Allocated RD %s for %s/%s (intent: %s)",
                    candidate,
                    device.name,
                    vrf_name,
                    intent.intent_id,
                )
                return rd.value

        # Pool exhausted
        raise ValueError(
            f"RD pool '{pool_name}' exhausted. "
            f"Range {pool.asn}:{pool.range_start}-{pool.range_end} "
            f"is fully allocated ({len(used)} allocations). "
            f"Expand the pool range or create a new pool."
        )


def allocate_route_target(intent: Intent) -> tuple[str, str]:
    """Claim the next available RT from the configured pool for this intent.

    Route targets are intent-level (not per-device), so one RT serves all
    devices implementing the same intent. Export and import use the same
    value for simple VPN topologies.

    Returns:
        Tuple of (rt_export, rt_import) strings e.g. ("65000:100", "65000:100")
    """
    # Check for existing allocation
    existing = RouteTarget.objects.filter(intent=intent).first()
    if existing:
        logger.info("Reusing existing RT %s for %s", existing.value, intent.intent_id)
        return existing.value, existing.value

    pool_name = _get_plugin_config("rt_pool_name")

    with transaction.atomic():
        try:
            pool = RouteTargetPool.objects.select_for_update().get(name=pool_name)
        except RouteTargetPool.DoesNotExist as exc:
            raise ValueError(
                f"RT pool '{pool_name}' not found. "
                f"Create it in Nautobot admin under "
                f"Intent Engine \u2192 Route Target Pools."
            ) from exc

        used = set(RouteTarget.objects.filter(pool=pool).values_list("value", flat=True))

        for i in range(pool.range_start, pool.range_end + 1):
            candidate = f"{pool.asn}:{i}"
            if candidate not in used:
                rt = RouteTarget.objects.create(
                    pool=pool,
                    value=candidate,
                    intent=intent,
                )
                logger.info("Allocated RT %s for intent %s", candidate, intent.intent_id)
                return rt.value, rt.value

        raise ValueError(
            f"RT pool '{pool_name}' exhausted. Range {pool.asn}:{pool.range_start}-{pool.range_end} is fully allocated."
        )


def release_allocations(intent: Intent) -> dict:
    """Release all RD and RT allocations for an intent.

    Called when an intent is deprecated or when a rollback cleans up.

    Returns:
        Dict with counts of released resources.
    """
    rds_released = RouteDistinguisher.objects.filter(intent=intent).count()
    RouteDistinguisher.objects.filter(intent=intent).delete()

    rts_released = RouteTarget.objects.filter(intent=intent).count()
    RouteTarget.objects.filter(intent=intent).delete()

    logger.info(
        "Released allocations for %s: %s RDs, %s RTs",
        intent.intent_id,
        rds_released,
        rts_released,
    )

    return {"rds_released": rds_released, "rts_released": rts_released}
