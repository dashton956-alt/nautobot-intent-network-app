"""UI URL routing for the intent_networking plugin."""

from django.urls import path
from nautobot.core.views.routers import NautobotUIViewSetRouter

from intent_networking import views
from intent_networking.topology_view import TopologyViewerView

router = NautobotUIViewSetRouter()
router.register("intents", views.IntentUIViewSet)

urlpatterns = router.urls + [
    # ── Dashboard ─────────────────────────────────────────────────────────
    path("", views.DashboardView.as_view(), name="dashboard"),
    # ── Topology Viewer ───────────────────────────────────────────────────
    path("topology/", TopologyViewerView.as_view(), name="topology_viewer"),
    # ── Resolution Plans (read-only UI) ───────────────────────────────────
    path("resolution-plans/", views.ResolutionPlanListView.as_view(), name="resolutionplan_list"),
    path("resolution-plans/<uuid:pk>/", views.ResolutionPlanDetailView.as_view(), name="resolutionplan"),
    # ── Verification Results (read-only UI) ───────────────────────────────
    path("verifications/", views.VerificationResultListView.as_view(), name="verificationresult_list"),
    path("verifications/<uuid:pk>/", views.VerificationResultDetailView.as_view(), name="verificationresult"),
    # ── Audit Trail (#4) ─────────────────────────────────────────────────
    path("audit-trail/", views.AuditTrailListView.as_view(), name="intentauditentry_list"),
    path("audit-trail/<uuid:pk>/", views.AuditTrailDetailView.as_view(), name="intentauditentry"),
    # ── Config Preview (#1) ──────────────────────────────────────────────
    path("config-preview/<str:intent_id>/", views.ConfigPreviewView.as_view(), name="config_preview"),
]
