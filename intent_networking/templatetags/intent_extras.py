"""Custom template tags & filters for Intent Networking templates."""

import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


# ── Arithmetic ────────────────────────────────────────────────────────────

@register.filter
def percentage_of(value, total):
    """Return value/total as an integer percentage. Usage: {{ 3|percentage_of:10 }}."""
    try:
        return int(int(value) / int(total) * 100) if int(total) else 0
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def subtract(value, arg):
    """Subtract arg from value. Usage: {{ 10|subtract:3 }}."""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value


# ── NUTS test-class → human-friendly name lookup ─────────────────────────

_NUTS_CLASS_LABELS = {
    "TestNapalmInterfaces": "Interface State",
    "TestNapalmBgpNeighbors": "BGP Neighbors",
    "TestNapalmLldpNeighbors": "LLDP Neighbors",
    "TestNetmikoOspfNeighbors": "OSPF Neighbors",
    "TestNetmikoCdpNeighbors": "CDP Neighbors",
    "TestNetmikoLldpNeighbors": "LLDP Neighbors",
    "TestNapalmNtp": "NTP Servers",
    "TestNapalmUsers": "User Accounts",
    "TestNapalmPing": "Ping Reachability",
    "TestNapalmTraceroute": "Traceroute",
}


@register.filter
def nuts_test_label(raw_check):
    """Parse NUTS node-id into a short human label.

    Input:  "test_bundle.yaml::TestNapalmInterfaces - Loopback0 up::test_is_enabled[lab-spine-01_]"
    Output: "Interface State · is_enabled"
    """
    parts = str(raw_check).split("::")
    if len(parts) < 2:
        return raw_check

    # Class part: "TestNapalmInterfaces - Loopback0 up"
    class_part = parts[1].strip()
    class_name = class_part.split(" - ")[0].split()[0] if " - " in class_part else class_part.split()[0]
    label = _NUTS_CLASS_LABELS.get(class_name, class_name)

    # Test function: "test_is_enabled[...]" → "is_enabled"
    if len(parts) >= 3:
        test_func = parts[2].strip()
        func_name = re.sub(r"^test_", "", test_func.split("[")[0])
        return f"{label} · {func_name}"

    return label


@register.filter
def nuts_device(raw_check):
    """Extract device hostname from NUTS node-id bracket params.

    Input:  "...::test_is_enabled[lab-spine-01_]"
    Output: "lab-spine-01"
    """
    match = re.search(r"\[([^\]]+)\]", str(raw_check))
    if match:
        # Params like "lab-spine-01_" or "host=lab-spine-01 name=Mgmt0"
        params = match.group(1)
        if "=" not in params:
            # Simple device name with trailing underscore
            return params.rstrip("_").strip()
        # key=value style
        for token in params.split():
            if token.startswith("host="):
                return token.split("=", 1)[1].rstrip(",")
        # fallback: first token
        return params.split()[0].split("=")[-1].rstrip(",_")
    return ""


@register.filter
def nuts_context(raw_check):
    """Extract the descriptive context from the NUTS test class part.

    Input:  "test_bundle.yaml::TestNapalmInterfaces - Loopback0 up::test_is_up[...]"
    Output: "Loopback0 up"
    """
    parts = str(raw_check).split("::")
    if len(parts) >= 2:
        class_part = parts[1].strip()
        if " - " in class_part:
            return class_part.split(" - ", 1)[1].strip()
    return ""


@register.filter
def nuts_error_summary(detail_str):
    """Extract a clean one-line error from NUTS detail string.

    Strips outcome=/duration= prefixes. Finds the key assertion error.
    Input:  "outcome=failed; /usr/local/.../napalm_interfaces.py:37: in test_is_enabled\\n    assert ...\\nE   KeyError: 'Loopback0'"
    Output: "KeyError: 'Loopback0'"
    """
    detail = str(detail_str)
    if not detail or detail == "—":
        return ""

    # Don't show errors for passed/skipped outcomes
    outcome_match = re.search(r"outcome=(\w+)", detail)
    if outcome_match and outcome_match.group(1) in ("passed", "skipped"):
        return ""

    # Look for E   <error> lines (pytest assertion output)
    e_match = re.search(r"E\s{2,}(\S.+?)(?:\n|$)", detail)
    if e_match:
        return e_match.group(1).strip()

    # Look for AssertionError / KeyError / etc patterns
    err_match = re.search(r"((?:Key|Value|Assertion|Type|Attribute|Index)Error:\s*.+?)(?:;|\n|$)", detail)
    if err_match:
        return err_match.group(1).strip()

    # Strip outcome=xxx; duration=xxx; prefix and return the rest
    cleaned = re.sub(r"outcome=\w+;\s*", "", detail)
    cleaned = re.sub(r"duration=[\d.]+s;\s*", "", cleaned)
    cleaned = cleaned.strip()

    # If it's still long, take the last meaningful line
    if len(cleaned) > 120:
        lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip() and not ln.strip().startswith("/")]
        if lines:
            return lines[-1][:120]

    return cleaned[:120] if cleaned else ""


@register.filter
def nuts_outcome(detail_str):
    """Extract just the outcome value from detail. Returns 'passed', 'failed', 'skipped', etc."""
    match = re.search(r"outcome=(\w+)", str(detail_str))
    return match.group(1) if match else ""
