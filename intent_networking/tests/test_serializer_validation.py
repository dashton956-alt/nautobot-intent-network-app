"""Unit tests for intent_networking.api.serializers module.

Tests INTENT_REQUIRED_FIELDS completeness, validate_intent_data_for_type(),
and the IntentSerializer cross-field validation.
"""

from django.test import SimpleTestCase

from intent_networking.api.serializers import (
    INTENT_REQUIRED_FIELDS,
    validate_intent_data_for_type,
)
from intent_networking.models import IntentTypeChoices

# ─────────────────────────────────────────────────────────────────────────────
# INTENT_REQUIRED_FIELDS completeness
# ─────────────────────────────────────────────────────────────────────────────


class IntentRequiredFieldsTest(SimpleTestCase):
    """Test INTENT_REQUIRED_FIELDS dict matches IntentTypeChoices."""

    def test_all_intent_types_have_required_fields_entry(self):
        """Every IntentTypeChoices value must have a key in INTENT_REQUIRED_FIELDS."""
        missing = []
        for choice_value, _label in IntentTypeChoices.choices:
            if choice_value not in INTENT_REQUIRED_FIELDS:
                missing.append(choice_value)
        self.assertEqual(missing, [], f"Missing INTENT_REQUIRED_FIELDS entries: {missing}")

    def test_no_extra_entries(self):
        """INTENT_REQUIRED_FIELDS should not have keys outside IntentTypeChoices."""
        valid_types = {v for v, _l in IntentTypeChoices.choices}
        extra = set(INTENT_REQUIRED_FIELDS.keys()) - valid_types
        self.assertEqual(extra, set(), f"Extra keys in INTENT_REQUIRED_FIELDS: {extra}")

    def test_all_values_are_lists(self):
        """Every value in INTENT_REQUIRED_FIELDS must be a list."""
        for key, value in INTENT_REQUIRED_FIELDS.items():
            self.assertIsInstance(value, list, f"INTENT_REQUIRED_FIELDS['{key}'] is not a list")

    def test_list_items_are_strings(self):
        """Required field names must be strings."""
        for key, fields in INTENT_REQUIRED_FIELDS.items():
            for field in fields:
                self.assertIsInstance(field, str, f"INTENT_REQUIRED_FIELDS['{key}'] contains non-string: {field}")


# ─────────────────────────────────────────────────────────────────────────────
# validate_intent_data_for_type
# ─────────────────────────────────────────────────────────────────────────────


class ValidateIntentDataTest(SimpleTestCase):
    """Test validate_intent_data_for_type() function."""

    def test_valid_connectivity(self):
        """Connectivity with 'source' passes validation."""
        errors = validate_intent_data_for_type("connectivity", {"source": "Gi0/1"})
        self.assertEqual(errors, [])

    def test_missing_required_field(self):
        """Missing 'source' for connectivity returns error."""
        errors = validate_intent_data_for_type("connectivity", {})
        self.assertEqual(len(errors), 1)
        self.assertIn("source", errors[0])

    def test_unknown_intent_type(self):
        """Unknown intent type returns error."""
        errors = validate_intent_data_for_type("completely_unknown", {})
        self.assertEqual(len(errors), 1)
        self.assertIn("Unknown intent type", errors[0])

    def test_security_no_required_fields(self):
        """Security has no required fields — always passes."""
        errors = validate_intent_data_for_type("security", {})
        self.assertEqual(errors, [])

    def test_reachability_requires_type(self):
        """Reachability needs 'reachability_type'."""
        errors = validate_intent_data_for_type("reachability", {})
        self.assertGreater(len(errors), 0)
        errors_ok = validate_intent_data_for_type("reachability", {"reachability_type": "static"})
        self.assertEqual(errors_ok, [])

    def test_ospf_requires_interfaces(self):
        """OSPF needs 'interfaces'."""
        errors = validate_intent_data_for_type("ospf", {})
        self.assertGreater(len(errors), 0)
        errors_ok = validate_intent_data_for_type("ospf", {"interfaces": ["Gi0/1"]})
        self.assertEqual(errors_ok, [])

    def test_bgp_ebgp_requires_multiple_fields(self):
        """BGP eBGP needs local_asn, neighbor_ip, neighbor_asn."""
        errors = validate_intent_data_for_type("bgp_ebgp", {})
        self.assertEqual(len(errors), 3)

    def test_bgp_ebgp_all_present(self):
        """BGP eBGP with all fields passes."""
        data = {"local_asn": 65000, "neighbor_ip": "10.0.0.1", "neighbor_asn": 65001}
        errors = validate_intent_data_for_type("bgp_ebgp", data)
        self.assertEqual(errors, [])

    def test_mpls_l3vpn_requires_source(self):
        """MPLS L3VPN needs 'source'."""
        errors = validate_intent_data_for_type("mpls_l3vpn", {})
        self.assertGreater(len(errors), 0)

    def test_acl_requires_acl_name(self):
        """ACL needs 'acl_name'."""
        errors = validate_intent_data_for_type("acl", {})
        self.assertGreater(len(errors), 0)
        errors_ok = validate_intent_data_for_type("acl", {"acl_name": "DENY-ALL"})
        self.assertEqual(errors_ok, [])

    def test_cloud_vpc_peer_requires_vpcs(self):
        """Cloud VPC peer needs requester_vpc and accepter_vpc."""
        errors = validate_intent_data_for_type("cloud_vpc_peer", {})
        self.assertEqual(len(errors), 2)

    def test_wireless_ssid_requires_ssid_name(self):
        """Wireless SSID needs 'ssid_name'."""
        errors = validate_intent_data_for_type("wireless_ssid", {})
        self.assertGreater(len(errors), 0)

    def test_mgmt_ntp_requires_servers(self):
        """NTP management needs 'servers'."""
        errors = validate_intent_data_for_type("mgmt_ntp", {})
        self.assertGreater(len(errors), 0)

    def test_static_route_requires_routes(self):
        """Static route needs 'routes'."""
        errors = validate_intent_data_for_type("static_route", {})
        self.assertGreater(len(errors), 0)

    def test_fhrp_requires_three_fields(self):
        """FHRP needs group_id, virtual_ip, interface."""
        errors = validate_intent_data_for_type("fhrp", {})
        self.assertEqual(len(errors), 3)

    def test_service_lb_vip_requires_two_fields(self):
        """Service LB VIP needs vip_address and pool_members."""
        errors = validate_intent_data_for_type("service_lb_vip", {})
        self.assertEqual(len(errors), 2)

    def test_every_type_validates_without_crash(self):
        """Calling validate with empty data for every type should not crash."""
        for intent_type, _label in IntentTypeChoices.choices:
            # Should not raise
            result = validate_intent_data_for_type(intent_type, {})
            self.assertIsInstance(result, list)
