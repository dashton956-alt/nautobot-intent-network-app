"""Django API urlpatterns declaration for intent_networking app."""

from django.urls import path
from nautobot.apps.api import OrderedDefaultRouter

from intent_networking.api import views
from intent_networking.metrics import PrometheusMetricsView
from intent_networking.topology_api import (
    DeviceLiveDataView,
    IntentHighlightView,
    TopologyFiltersView,
    TopologyGraphView,
)

router = OrderedDefaultRouter()
router.register("intents", views.IntentViewSet)
router.register("resolution-plans", views.ResolutionPlanViewSet)
router.register("verification-results", views.VerificationResultViewSet)

app_name = "intent_networking-api"

urlpatterns = router.urls + [
    # Prometheus metrics (#7)
    path("metrics/", PrometheusMetricsView.as_view(), name="metrics"),
    # Topology viewer API
    path("topology/", TopologyGraphView.as_view(), name="topology-graph"),
    path("topology/filters/", TopologyFiltersView.as_view(), name="topology-filters"),
    path("topology/device/<str:device_name>/live/", DeviceLiveDataView.as_view(), name="topology-device-live"),
    path("topology/intent/<str:intent_id>/highlight/", IntentHighlightView.as_view(), name="topology-intent-highlight"),
]
