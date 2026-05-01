"""FilterSet definitions for the intent_networking app."""

import django_filters
from nautobot.apps.filters import NautobotFilterSet
from nautobot.extras.models import GitRepository, Status
from nautobot.tenancy.models import Tenant

from intent_networking.models import (
    Intent,
    IntentAuditEntry,
    IntentTypeChoices,
    VxlanVniPool,
)


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
    deployment_strategy = django_filters.MultipleChoiceFilter(
        choices=[
            ("all_at_once", "All at once"),
            ("canary", "Canary"),
            ("rolling", "Rolling"),
        ],
        label="Deployment Strategy",
    )

    class Meta:
        """Meta options for IntentFilterSet."""

        model = Intent
        fields = "__all__"

    def search(self, queryset, _name, value):
        """Filter intents by intent_id substring."""
        return queryset.filter(intent_id__icontains=value)


class IntentAuditEntryFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """FilterSet for the IntentAuditEntry model."""

    q = django_filters.CharFilter(method="search", label="Search")
    action = django_filters.MultipleChoiceFilter(
        choices=IntentAuditEntry.ACTION_CHOICES,
        label="Action",
    )
    actor = django_filters.CharFilter(lookup_expr="icontains", label="Actor")

    class Meta:
        """Meta options for IntentAuditEntryFilterSet."""

        model = IntentAuditEntry
        fields = ["action", "actor"]

    def search(self, queryset, _name, value):
        """Filter audit entries by intent_id or actor substring."""
        return queryset.filter(intent__intent_id__icontains=value) | queryset.filter(actor__icontains=value)


class VxlanVniPoolFilterSet(NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """FilterSet for the VxlanVniPool model."""

    q = django_filters.CharFilter(method="search", label="Search")
    tenant = django_filters.ModelMultipleChoiceFilter(queryset=Tenant.objects.all(), label="Tenant")

    class Meta:
        """Meta options for VxlanVniPoolFilterSet."""

        model = VxlanVniPool
        fields = ["name", "tenant"]

    def search(self, queryset, _name, value):
        """Filter VNI pools by name substring."""
        return queryset.filter(name__icontains=value)
