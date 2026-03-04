"""Django view that renders the topology viewer HTML page."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class TopologyViewerView(LoginRequiredMixin, TemplateView):
    """Serve the full-screen topology viewer.

    All data is loaded client-side via the topology API endpoints.
    """

    template_name = "intent_networking/topology_viewer.html"

    def get_context_data(self, **kwargs):
        """Inject page title into the template context."""
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Intent Topology Viewer"
        return ctx
