"""FilterSet definitions for the intent_networking app."""

import django_filters
from nautobot.apps.filters import NautobotFilterSet
from nautobot.extras.models import GitRepository, Status
from nautobot.tenancy.models import Tenant

from intent_networking.models import Intent, IntentTypeChoices, RouteDistinguisherPool, RouteTargetPool


class IntentFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """FilterSet for the Intent model."""

    q = django_filters.CharFilter(method="search", label="Search")
    tenant = django_filters.ModelMultipleChoiceFilter(queryset=Tenant.objects.all(), label="Tenant")
    intent_type = django_filters.MultipleChoiceFilter(choices=IntentTypeChoices.choices, label="Type")
    status = django_filters.ModelMultipleChoiceFilter(queryset=Status.objects.all(), label="Status")
    git_repository = django_filters.ModelMultipleChoiceFilter(
        queryset=GitRepository.objects.all(),
        label="Git Repository",
    )

    class Meta:
        """Meta options for IntentFilterSet."""

        model = Intent
        fields = "__all__"

    def search(self, queryset, _name, value):
        """Filter intents by intent_id substring."""
        return queryset.filter(intent_id__icontains=value)


class RouteDistinguisherPoolFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """FilterSet for the RouteDistinguisherPool model."""

    q = django_filters.CharFilter(method="search", label="Search")

    class Meta:
        """Meta options for RouteDistinguisherPoolFilterSet."""

        model = RouteDistinguisherPool
        fields = "__all__"

    def search(self, queryset, _name, value):
        """Filter RD pools by name substring."""
        return queryset.filter(name__icontains=value)


class RouteTargetPoolFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """FilterSet for the RouteTargetPool model."""

    q = django_filters.CharFilter(method="search", label="Search")

    class Meta:
        """Meta options for RouteTargetPoolFilterSet."""

        model = RouteTargetPool
        fields = "__all__"

    def search(self, queryset, _name, value):
        """Filter RT pools by name substring."""
        return queryset.filter(name__icontains=value)
