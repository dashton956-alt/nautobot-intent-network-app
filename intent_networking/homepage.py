"""Homepage layout for the Intent Networking app.

Registers panels that appear on Nautobot's main homepage, giving operators
quick visibility into intent counts, resource pools and recent activity
without navigating into the plugin.
"""

from nautobot.apps.ui import HomePageGroup, HomePageItem, HomePagePanel

from intent_networking import models


def _get_intent_summary(request):
    """Return summary stats for the custom homepage panel."""
    from django.db.models import Count  # noqa: PLC0415

    qs = models.Intent.objects.restrict(request.user, "view")
    status_counts = {
        row["status__name"].lower(): row["count"]
        for row in qs.values("status__name").annotate(count=Count("id"))
        if row["status__name"]
    }

    total_verifications = models.VerificationResult.objects.count()
    passed = models.VerificationResult.objects.filter(passed=True).count()

    return {
        "total_intents": qs.count(),
        "deployed": status_counts.get("deployed", 0),
        "failed": status_counts.get("failed", 0),
        "pending": (qs.filter(approved_by="").exclude(status__name__in=["Deprecated", "Draft"]).count()),
        "verification_pct": int(passed / total_verifications * 100) if total_verifications else 0,
    }


def _get_recent_intents(request):
    """Return the 5 most recently updated intents for the homepage panel."""
    return (
        models.Intent.objects.restrict(request.user, "view")
        .select_related("tenant", "status")
        .order_by("-last_updated")[:5]
    )


layout = (
    HomePagePanel(
        name="Intent Engine",
        weight=150,
        custom_template="intent_engine_homepage.html",
        custom_data={
            "summary": _get_intent_summary,
            "recent_intents": _get_recent_intents,
        },
        permissions=["intent_networking.view_intent"],
    ),
    HomePagePanel(
        name="Intent Resources",
        weight=160,
        items=(
            HomePageItem(
                name="Intents",
                link="plugins:intent_networking:intent_list",
                model=models.Intent,
                description="Network intents expressed as YAML",
                permissions=["intent_networking.view_intent"],
                weight=100,
            ),
            HomePageItem(
                name="Resolution Plans",
                link="plugins:intent_networking:resolutionplan_list",
                model=models.ResolutionPlan,
                permissions=["intent_networking.view_resolutionplan"],
                weight=200,
            ),
            HomePageItem(
                name="Verifications",
                link="plugins:intent_networking:verificationresult_list",
                model=models.VerificationResult,
                permissions=["intent_networking.view_verificationresult"],
                weight=300,
            ),
            HomePageGroup(
                name="IPAM Resources",
                weight=400,
                items=(
                    HomePageItem(
                        name="VRFs",
                        link="ipam:vrf_list",
                        description="Nautobot VRFs with auto-allocated RDs",
                        permissions=["ipam.view_vrf"],
                        weight=100,
                    ),
                    HomePageItem(
                        name="Route Targets",
                        link="ipam:routetarget_list",
                        description="Nautobot Route Targets",
                        permissions=["ipam.view_routetarget"],
                        weight=200,
                    ),
                    HomePageItem(
                        name="Namespaces",
                        link="ipam:namespace_list",
                        description="Nautobot Namespaces",
                        permissions=["ipam.view_namespace"],
                        weight=300,
                    ),
                ),
            ),
        ),
    ),
)
