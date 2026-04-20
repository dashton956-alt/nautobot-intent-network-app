"""REST API endpoints that power the topology viewer.

Endpoints (all registered in api/urls.py):

  GET /api/plugins/intent-networking/topology/
      Full topology graph — nodes (devices) + edges (cables).
      Each node carries intent deployment colour, status, and VRF list.
      Filter by ?tenant=<name> or ?site=<name>.

  GET /api/plugins/intent-networking/topology/device/<name>/live/
      Live ARP table, routing table, interface states, and deployed intents
      for a single device. Collected via Nornir on-demand. Results cached
      in Django's cache for 60 seconds to prevent hammering devices.

  GET /api/plugins/intent-networking/topology/intent/<intent_id>/highlight/
      Returns the set of device names and edge pairs that belong to a
      specific intent, so the UI can highlight the intent path.
"""

import logging
import os

from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from nautobot.dcim.models import Cable, Device, Location
from nautobot.tenancy.models import Tenant
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Intent, ResolutionPlan
from .secrets import get_credentials_for_device

logger = logging.getLogger(__name__)

# How long to cache live device data (seconds).
# Keeps the UI snappy — engineers hovering rapidly don't flood devices.
LIVE_CACHE_TTL = 60


# ─────────────────────────────────────────────────────────────────────────────
# Topology graph data
# ─────────────────────────────────────────────────────────────────────────────


class TopologyGraphView(APIView):
    """Returns nodes and edges for the vis.js Network graph.

    Node shape encodes device role:
      router   → dot (circle)
      switch   → square
      firewall → triangle
      server   → diamond
      unknown  → ellipse

    Node colour encodes intent status:
      green  (#4ade80) — all intents deployed and verified
      amber  (#fbbf24) — intents present but some unverified or deploying
      red    (#f87171) — one or more intents in failed/rolled_back state
      blue   (#38bdf8) — device has no intents
      grey   (#64748b) — device in maintenance
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request):
        """Return nodes and edges for the topology vis.js graph."""
        tenant_slug = request.query_params.get("tenant")
        site_slug = request.query_params.get("site")

        # ── Filter devices ────────────────────────────────────────────────
        qs = Device.objects.select_related(
            "location", "tenant", "platform", "role", "status", "primary_ip4"
        ).prefetch_related("tags", "interfaces")

        if tenant_slug:
            qs = qs.filter(tenant__name=tenant_slug)
        if site_slug:
            qs = qs.filter(location__name=site_slug)

        devices = list(qs)
        device_ids = {d.pk for d in devices}

        # ── Build intent index — device_name → list of intent summaries ───
        intent_index = _build_intent_index(devices)

        # ── Build nodes ───────────────────────────────────────────────────
        nodes = []
        for device in devices:
            colour = _device_colour(device, intent_index)
            shape = _device_shape(device)
            mgmt_ip = str(device.primary_ip4.address.ip) if device.primary_ip4 else None
            intents = intent_index.get(device.name, [])

            nodes.append(
                {
                    "id": device.name,
                    "label": device.name,
                    "title": device.name,  # tooltip placeholder — real data loaded on hover
                    "group": device.location.name if device.location else "unknown",
                    "shape": shape,
                    "color": {
                        "background": colour,
                        "border": _darken(colour),
                        "highlight": {
                            "background": "#ffffff",
                            "border": colour,
                        },
                    },
                    "font": {
                        "color": "#e2e8f0",
                        "size": 13,
                    },
                    "meta": {
                        "nautobot_id": str(device.pk),
                        "site": device.location.name if device.location else None,
                        "site_slug": device.location.name if device.location else None,
                        "tenant": device.tenant.name if device.tenant else None,
                        "tenant_slug": device.tenant.name if device.tenant else None,
                        "platform": device.platform.name if device.platform else None,
                        "role": device.role.name if device.role else None,
                        "status": device.status.name if device.status else None,
                        "mgmt_ip": mgmt_ip,
                        "in_maintenance": device.status.name.lower() == "maintenance" if device.status else False,
                        "intent_count": len(intents),
                        "intents": intents,
                    },
                }
            )

        # ── Build edges from Nautobot cables ──────────────────────────────
        edges = []
        seen_cables = set()

        # In Nautobot 3.x termination_a/b are GenericForeignKeys, so we
        # filter via the denormalised _termination_a/b_device FKs instead.
        cables = Cable.objects.filter(
            _termination_a_device__in=devices,
            _termination_b_device__in=devices,
        ).select_related(
            "_termination_a_device",
            "_termination_b_device",
            "status",
        )

        for cable in cables:
            if cable.pk in seen_cables:
                continue
            seen_cables.add(cable.pk)

            try:
                dev_a = cable._termination_a_device  # pylint: disable=protected-access
                dev_b = cable._termination_b_device  # pylint: disable=protected-access
                if not dev_a or not dev_b:
                    continue
                if dev_a.pk not in device_ids or dev_b.pk not in device_ids:
                    continue
            except AttributeError:
                continue

            # Check if any intent uses both these devices
            shared_intents = _shared_intents(dev_a.name, dev_b.name, intent_index)

            edge_colour = "#1e2d45"  # default dark — no intent
            edge_width = 1
            if shared_intents:
                edge_colour = "#38bdf8"  # blue — intent path
                edge_width = 2

            # Resolve interface names when the GFK targets resolve
            iface_a_name = ""
            iface_b_name = ""
            try:
                if cable.termination_a:
                    iface_a_name = cable.termination_a.name
                if cable.termination_b:
                    iface_b_name = cable.termination_b.name
            except Exception:  # noqa: BLE001, S110
                pass

            edges.append(
                {
                    "id": str(cable.pk),
                    "from": dev_a.name,
                    "to": dev_b.name,
                    "label": f"{iface_a_name} ↔ {iface_b_name}" if iface_a_name else "",
                    "color": {
                        "color": edge_colour,
                        "highlight": "#ffffff",
                        "hover": "#94d4f0",
                    },
                    "width": edge_width,
                    "smooth": {"type": "curvedCW", "roundness": 0.1},
                    "meta": {
                        "cable_id": str(cable.pk),
                        "cable_type": cable.type or "unknown",
                        "iface_a": iface_a_name,
                        "iface_b": iface_b_name,
                        "shared_intents": shared_intents,
                    },
                }
            )

        # ── Synthesise edges from shared intents ─────────────────────────
        # When devices share a resolution plan we draw a logical edge even
        # if no physical cable exists.  This makes the topology useful in
        # lab/demo environments that have no cable records.
        seen_intent_pairs = set()
        for plan in (
            ResolutionPlan.objects.filter(affected_devices__in=devices)
            .prefetch_related("affected_devices")
            .select_related("intent", "intent__status")
            .distinct()
        ):
            plan_devices = [d for d in plan.affected_devices.all() if d.pk in device_ids]
            for i, d_a in enumerate(plan_devices):
                for d_b in plan_devices[i + 1 :]:
                    pair_key = tuple(sorted([d_a.name, d_b.name]))
                    if pair_key in seen_intent_pairs:
                        continue
                    seen_intent_pairs.add(pair_key)
                    edge_id = f"intent-{d_a.name}-{d_b.name}"
                    if any(e["id"] == edge_id for e in edges):
                        continue
                    # skip if a physical cable edge already connects these two
                    if any(
                        (e["from"] == d_a.name and e["to"] == d_b.name)
                        or (e["from"] == d_b.name and e["to"] == d_a.name)
                        for e in edges
                    ):
                        continue
                    s_intents = _shared_intents(d_a.name, d_b.name, intent_index)
                    edges.append(
                        {
                            "id": edge_id,
                            "from": d_a.name,
                            "to": d_b.name,
                            "label": "",
                            "dashes": True,
                            "color": {
                                "color": "#38bdf8",
                                "highlight": "#ffffff",
                                "hover": "#94d4f0",
                            },
                            "width": 1.5,
                            "smooth": {"type": "curvedCW", "roundness": 0.1},
                            "meta": {
                                "cable_id": None,
                                "cable_type": "logical",
                                "iface_a": "",
                                "iface_b": "",
                                "shared_intents": s_intents,
                            },
                        }
                    )

        # ── Dependency edges ───────────────────────────────────────────────
        # Draw a dashed orange edge between intents that have a depends_on
        # relationship, linking the first affected device of each intent.
        dep_edges = _build_dependency_edges(device_ids)
        edges.extend(dep_edges)

        # ── Site grouping for vis.js clustering ───────────────────────────
        sites = {}
        for device in devices:
            if device.location:
                if device.location.name not in sites:
                    sites[device.location.name] = {
                        "name": device.location.name,
                        "count": 0,
                    }
                sites[device.location.name]["count"] += 1

        return Response(
            {
                "nodes": nodes,
                "edges": edges,
                "sites": list(sites.values()),
                "device_count": len(nodes),
                "edge_count": len(edges),
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Live device data (hover panel)
# ─────────────────────────────────────────────────────────────────────────────


class DeviceLiveDataView(APIView):
    """Return live device data for the hover panel.

    Tries Nornir first. Falls back to Nautobot-cached data if device is
    unreachable. Results cached for LIVE_CACHE_TTL seconds.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request, device_name):
        """Return live ARP, routing, interface and intent data for a single device."""
        cache_key = f"intent_topo_live_{device_name}"
        cached = cache.get(cache_key)
        if cached:
            return Response({**cached, "from_cache": True})

        try:
            device = (
                Device.objects.select_related("platform", "location", "tenant", "primary_ip4")
                .prefetch_related("interfaces__ip_addresses", "tags")
                .get(name=device_name)
            )
        except Device.DoesNotExist:
            return Response({"error": f"Device '{device_name}' not found"}, status=status.HTTP_404_NOT_FOUND)

        # ── Deployed intents ──────────────────────────────────────────────
        deployed_intents = _get_device_intents(device)

        # ── Nautobot interface inventory (always available) ───────────────
        interfaces = _get_interface_inventory(device)

        # ── Live data via Nornir ──────────────────────────────────────────
        live = _collect_live_data(device)

        result = {
            "device_name": device.name,
            "platform": device.platform.name if device.platform else "unknown",
            "site": device.location.name if device.location else None,
            "mgmt_ip": str(device.primary_ip4.address.ip) if device.primary_ip4 else None,
            "nautobot_url": f"/dcim/devices/{device.pk}/",
            "deployed_intents": deployed_intents,
            "interfaces": interfaces,
            "arp_table": live.get("arp_table", []),
            "routing_table": live.get("routing_table", []),
            "vrfs": live.get("vrfs", []),
            "bgp_neighbors": live.get("bgp_neighbors", []),
            "collection_error": live.get("error"),
            "from_cache": False,
        }

        cache.set(cache_key, result, LIVE_CACHE_TTL)
        return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
# Intent highlight — which nodes/edges belong to an intent
# ─────────────────────────────────────────────────────────────────────────────


class IntentHighlightView(APIView):
    """Return device names and edge IDs belonging to a specific intent.

    Used by the topology viewer to highlight an intent's path.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request, intent_id):
        """Return device names and edge IDs for the given intent."""
        try:
            intent = Intent.objects.get(intent_id=intent_id)
        except Intent.DoesNotExist:
            return Response({"error": f"Intent '{intent_id}' not found"}, status=status.HTTP_404_NOT_FOUND)

        plan = intent.latest_plan
        if not plan:
            return Response(
                {
                    "intent_id": intent_id,
                    "device_names": [],
                    "status": str(intent.status),
                }
            )

        device_names = list(plan.affected_devices.values_list("name", flat=True))

        # Find edges that connect any two devices in this intent
        highlighted_edges = []
        if len(device_names) >= 2:
            cables = Cable.objects.filter(
                _termination_a_device__name__in=device_names,
                _termination_b_device__name__in=device_names,
            ).values_list("pk", flat=True)
            highlighted_edges = [str(pk) for pk in cables]

            # Also include synthesised intent-edge IDs
            sorted_names = sorted(device_names)
            for i, a in enumerate(sorted_names):
                for b in sorted_names[i + 1 :]:
                    highlighted_edges.append(f"intent-{a}-{b}")

        return Response(
            {
                "intent_id": intent_id,
                "intent_type": intent.intent_type,
                "status": str(intent.status),
                "tenant": intent.tenant.name,
                "vrf_name": plan.vrf_name if plan else None,
                "device_names": device_names,
                "highlighted_edges": highlighted_edges,
                "deployed_at": intent.deployed_at,
                "last_verified_at": intent.last_verified_at,
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tenant/site list (for the filter dropdowns)
# ─────────────────────────────────────────────────────────────────────────────


class TopologyFiltersView(APIView):
    """Return tenant, site and intent lists for the topology filter dropdowns."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request):
        """Return tenants, sites and deployed intents for filter dropdowns."""
        tenants = list(Tenant.objects.values("name").order_by("name"))

        locations = list(Location.objects.values("name").order_by("name"))

        intents = list(
            Intent.objects.filter(status__name__iexact="Deployed")
            .values("intent_id", "intent_type", "tenant__name")
            .order_by("intent_id")
        )

        return Response(
            {
                "tenants": tenants,
                "sites": locations,
                "intents": intents,
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _build_dependency_edges(device_ids):
    """Build vis.js edges for intent dependency relationships.

    For each dependency pair, links the first affected device of the
    dependent intent to the first affected device of the dependency.
    Only includes devices that are in the current topology view.
    """
    edges = []
    seen = set()

    intents_with_deps = (
        Intent.objects.filter(
            dependencies__isnull=False,
        )
        .prefetch_related("dependencies", "resolution_plans__affected_devices")
        .distinct()
    )

    for intent in intents_with_deps:
        plan = intent.latest_plan
        if not plan:
            continue
        intent_device = plan.affected_devices.filter(pk__in=device_ids).first()
        if not intent_device:
            continue

        for dep in intent.dependencies.all():
            dep_plan = dep.latest_plan
            if not dep_plan:
                continue
            dep_device = dep_plan.affected_devices.filter(pk__in=device_ids).first()
            if not dep_device:
                continue

            pair_key = (intent.intent_id, dep.intent_id)
            if pair_key in seen:
                continue
            seen.add(pair_key)

            edges.append(
                {
                    "id": f"dep-{intent.intent_id}-{dep.intent_id}",
                    "from": dep_device.name,
                    "to": intent_device.name,
                    "label": "dependency",
                    "dashes": [5, 5],
                    "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}},
                    "color": {
                        "color": "#f59e0b",  # amber for dependency
                        "highlight": "#ffffff",
                        "hover": "#fbbf24",
                    },
                    "width": 1.5,
                    "smooth": {"type": "curvedCW", "roundness": 0.2},
                    "meta": {
                        "edge_type": "dependency",
                        "from_intent": dep.intent_id,
                        "to_intent": intent.intent_id,
                    },
                }
            )

    return edges


def _build_intent_index(devices):
    """Build a dict mapping device_name to a list of intent summary dicts."""
    device_names = [d.name for d in devices]
    index = {d.name: [] for d in devices}

    plans = (
        ResolutionPlan.objects.filter(affected_devices__name__in=device_names)
        .select_related("intent", "intent__tenant", "intent__status")
        .distinct()
    )

    for plan in plans:
        for device in plan.affected_devices.filter(name__in=device_names):
            index[device.name].append(
                {
                    "intent_id": plan.intent.intent_id,
                    "intent_type": plan.intent.intent_type,
                    "status": str(plan.intent.status),
                    "tenant": plan.intent.tenant.name,
                    "vrf_name": plan.vrf_name,
                    "version": plan.intent.version,
                    "deployed_at": plan.intent.deployed_at.isoformat() if plan.intent.deployed_at else None,
                }
            )

    return index


def _get_device_intents(device):
    """Full intent detail for the hover panel."""
    plans = ResolutionPlan.objects.filter(affected_devices=device).select_related(
        "intent", "intent__tenant", "intent__status"
    )

    result = []
    for plan in plans:
        intent = plan.intent
        latest_v = intent.verifications.order_by("-verified_at").first()
        result.append(
            {
                "intent_id": intent.intent_id,
                "intent_type": intent.intent_type,
                "status": str(intent.status),
                "tenant": intent.tenant.name,
                "vrf_name": plan.vrf_name,
                "version": intent.version,
                "change_ticket": intent.change_ticket,
                "deployed_at": intent.deployed_at.isoformat() if intent.deployed_at else None,
                "last_verified": intent.last_verified_at.isoformat() if intent.last_verified_at else None,
                "verified_ok": latest_v.passed if latest_v else None,
                "rd_allocated": plan.allocated_rds.get(device.name),
                "rt_export": plan.allocated_rts.get("export"),
            }
        )

    return result


def _get_interface_inventory(device):
    """Interface list from Nautobot — always available."""
    ifaces = []
    for iface in device.interfaces.prefetch_related("ip_addresses").all():
        ips = [str(ip.address) for ip in iface.ip_addresses.all()]

        # Connected peer info (cable endpoint)
        cable_peer = None
        if iface.cable:
            try:
                peer = iface.connected_endpoint
                if peer and hasattr(peer, "device"):
                    cable_peer = f"{peer.device.name} — {peer.name}"
            except Exception:  # noqa: BLE001, S110
                pass

        ifaces.append(
            {
                "name": iface.name,
                "enabled": iface.enabled,
                "type": iface.type,
                "ips": ips,
                "mtu": iface.mtu,
                "mac_address": str(iface.mac_address) if iface.mac_address else None,
                "description": iface.description or "",
                "status": str(iface.status) if iface.status else "Unknown",
                "mode": iface.mode or "",
                "mgmt_only": iface.mgmt_only,
                "speed": iface.speed,
                "duplex": iface.duplex or "",
                "vrf": str(iface.vrf) if iface.vrf else None,
                "lag": str(iface.lag) if iface.lag else None,
                "cable_peer": cable_peer,
            }
        )
    return ifaces


def _collect_live_data(device) -> dict:
    """Collect ARP table, routing table, VRFs, BGP neighbors from device via Nornir.

    Returns dict with collected data or an error message.
    """
    if not device.primary_ip4:
        return {"error": "No management IP set in Nautobot — cannot connect"}

    if device.status and device.status.name.lower() == "maintenance":
        return {"error": "Device is in maintenance mode — live collection skipped"}

    platform = device.platform.name if device.platform else ""
    supported = (
        "arista-eos",
        "cisco-ios-xe",
        "cisco-ios-xr",
        "cisco-nxos",
        "juniper-junos",
        "nokia-sros",
        "aruba-aos-cx",
    )
    if platform not in supported:
        return {"error": f"Unsupported platform '{platform}' for live collection"}

    try:
        import shutil
        import tempfile

        import yaml as _yaml
        from nornir import InitNornir
        from nornir_netmiko.tasks import netmiko_send_command

        username, password = get_credentials_for_device(device)

        tmpdir = tempfile.mkdtemp(prefix="topo-live-")
        try:
            hosts = {
                device.name: {
                    "hostname": str(device.primary_ip4.address.ip),
                    "platform": _nornir_platform(platform),
                    "port": 22,
                }
            }
            defaults = {"username": username, "password": password}

            host_file = os.path.join(tmpdir, "hosts.yaml")
            defaults_file = os.path.join(tmpdir, "defaults.yaml")
            with open(host_file, "w", encoding="utf-8") as f:
                _yaml.dump(hosts, f, default_flow_style=False)
            with open(defaults_file, "w", encoding="utf-8") as f:
                _yaml.dump(defaults, f, default_flow_style=False)

            nr = InitNornir(
                inventory={
                    "plugin": "SimpleInventory",
                    "options": {
                        "host_file": host_file,
                        "defaults_file": defaults_file,
                    },
                },
                runner={"plugin": "threaded", "options": {"num_workers": 1}},
                logging={"enabled": False},
            )

            commands = _platform_commands(platform)
            collected = {}

            for key, command in commands.items():
                result = nr.run(
                    task=netmiko_send_command,
                    command_string=command,
                    use_textfsm=True,
                    on_failed=True,
                )
                if result[device.name].failed:
                    collected[key] = []
                else:
                    raw = result[device.name].result
                    # If TextFSM has no template for this command it returns raw text
                    collected[key] = raw if isinstance(raw, list) else (raw if isinstance(raw, str) else [])

            return {
                "arp_table": _normalise_arp(collected.get("arp", []), platform),
                "routing_table": _normalise_routes(collected.get("routes", []), platform),
                "vrfs": _normalise_vrfs(collected.get("vrfs", []), platform),
                "bgp_neighbors": _normalise_bgp(collected.get("bgp", []), platform),
            }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    except Exception as exc:
        logger.warning("Live data collection failed for %s: %s", device.name, exc)
        return {"error": f"Collection failed: {str(exc)[:120]}"}


def _platform_commands(platform: str) -> dict:  # pylint: disable=too-many-return-statements
    """Return show commands per platform."""
    if platform == "arista-eos":
        return {
            "arp": "show arp",
            "routes": "show ip route",
            "vrfs": "show vrf",
            "bgp": "show ip bgp summary",
        }
    if platform == "cisco-nxos":
        return {
            "arp": "show ip arp",
            "routes": "show ip route",
            "vrfs": "show vrf",
            "bgp": "show bgp sessions",
        }
    if "ios" in platform:
        return {
            "arp": "show arp",
            "routes": "show ip route",
            "vrfs": "show vrf brief",
            "bgp": "show bgp summary",
        }
    if "junos" in platform:
        return {
            "arp": "show arp",
            "routes": "show route",
            "vrfs": "show routing-instances",
            "bgp": "show bgp summary",
        }
    if platform == "nokia-sros":
        return {
            "arp": "show router arp",
            "routes": "show router route-table",
            "vrfs": "show service id",
            "bgp": "show router bgp summary",
        }
    if "aos-cx" in platform:
        return {
            "arp": "show arp",
            "routes": "show ip route",
            "vrfs": "show vrf",
            "bgp": "show bgp summary",
        }
    return {}


def _nornir_platform(nautobot_platform: str) -> str:
    return {
        "arista-eos": "arista_eos",
        "cisco-ios-xe": "cisco_ios",
        "cisco-ios-xr": "cisco_xr",
        "cisco-nxos": "cisco_nxos",
        "juniper-junos": "juniper_junos",
        "nokia-sros": "nokia_sros",
        "aruba-aos-cx": "aruba_aoscx",
    }.get(nautobot_platform, "cisco_ios")


def _normalise_arp(rows, _platform) -> list:
    # If TextFSM had no template (e.g. arista_eos_show_arp.textfsm is absent),
    # Netmiko returns the raw command output as a string — parse it with a regex.
    if isinstance(rows, str):
        import re as _re

        out = []
        for line in rows.splitlines():
            m = _re.match(r"^\s*(\d+\.\d+\.\d+\.\d+)\s+(\S+)\s+([0-9a-fA-F:.]+)\s+(\S+)", line)
            if m:
                out.append(
                    {
                        "ip": m.group(1),
                        "age": m.group(2),
                        "mac": m.group(3),
                        "interface": m.group(4),
                        "type": "",
                    }
                )
        return out[:200]

    out = []
    for row in rows[:200]:  # cap at 200 rows for panel display
        if isinstance(row, dict):
            out.append(
                {
                    "ip": row.get("address") or row.get("ip") or row.get("ip_address", ""),
                    "mac": row.get("mac") or row.get("mac_address", ""),
                    "interface": row.get("interface") or row.get("intf", ""),
                    "age": row.get("age", ""),
                    "type": row.get("type", ""),
                }
            )
    return out


def _normalise_routes(rows, _platform) -> list:
    out = []
    for row in rows[:300]:
        if isinstance(row, dict):
            # next_hop and interface are List values in the EOS TextFSM template
            raw_nh = row.get("nexthop") or row.get("next_hop") or row.get("nexthop_ip", "")
            nexthop = ", ".join(raw_nh) if isinstance(raw_nh, list) else str(raw_nh or "")
            raw_if = row.get("interface") or row.get("outgoing_interface", "")
            interface = ", ".join(raw_if) if isinstance(raw_if, list) else str(raw_if or "")
            out.append(
                {
                    "network": row.get("network") or row.get("prefix", ""),
                    # Arista TextFSM template uses prefix_length; other platforms use mask
                    "mask": row.get("mask") or row.get("prefix_length", ""),
                    "nexthop": nexthop,
                    "protocol": row.get("protocol") or row.get("type", ""),
                    "interface": interface,
                    "metric": row.get("metric", ""),
                    "distance": row.get("distance", ""),
                    "vrf": row.get("vrf", "default"),
                }
            )
    return out


def _normalise_vrfs(rows, _platform) -> list:
    out = []
    for row in rows[:50]:
        if isinstance(row, dict):
            out.append(
                {
                    # Arista TextFSM template uses 'vrf'; others use 'name' / 'vrf_name'
                    "name": row.get("name") or row.get("vrf") or row.get("vrf_name", ""),
                    "rd": row.get("default_rd") or row.get("rd", ""),
                    "interfaces": row.get("interfaces", ""),
                }
            )
    return out


def _normalise_bgp(rows, _platform) -> list:
    out = []
    for row in rows[:100]:
        if isinstance(row, dict):
            out.append(
                {
                    # Arista template: bgp_neigh; others: bgp_neighbor / neighbor
                    "neighbor": row.get("bgp_neighbor") or row.get("bgp_neigh") or row.get("neighbor", ""),
                    # Arista template: neigh_as; others: neighbor_as / remote_as
                    "as": row.get("neighbor_as") or row.get("neigh_as") or row.get("remote_as", ""),
                    "state": row.get("state_pfxrcd") or row.get("state", ""),
                    "uptime": row.get("up_down") or row.get("uptime", ""),
                    "prefixes_rx": row.get("state_pfxrcd", ""),
                    "vrf": row.get("vrf", "default"),
                }
            )
    return out


def _device_colour(device, intent_index) -> str:
    if device.status and device.status.name.lower() == "maintenance":
        return "#64748b"

    intents = intent_index.get(device.name, [])
    if not intents:
        return "#38bdf8"  # blue — no intents

    statuses = {i["status"].lower().replace(" ", "_") for i in intents}
    if "failed" in statuses or "rolled_back" in statuses:
        return "#f87171"  # red
    if "deploying" in statuses or "validated" in statuses:
        return "#fbbf24"  # amber
    if statuses == {"deployed"}:
        return "#4ade80"  # green
    return "#fbbf24"  # amber — mixed


def _darken(hex_colour: str) -> str:
    """Return a slightly darker version of a hex colour for borders."""
    darkening = {
        "#4ade80": "#22c55e",
        "#fbbf24": "#f59e0b",
        "#f87171": "#ef4444",
        "#38bdf8": "#0ea5e9",
        "#64748b": "#475569",
    }
    return darkening.get(hex_colour, hex_colour)


def _device_shape(device) -> str:
    role = device.role.name.lower() if device.role else ""
    if "router" in role or "pe" in role or "ce" in role:
        return "dot"
    if "switch" in role or "leaf" in role or "spine" in role:
        return "square"
    if "firewall" in role or "fw" in role:
        return "triangle"
    if "server" in role:
        return "diamond"
    return "ellipse"


def _shared_intents(dev_a: str, dev_b: str, intent_index: dict) -> list:
    """Return intent_ids shared by both devices."""
    ids_a = {i["intent_id"] for i in intent_index.get(dev_a, [])}
    ids_b = {i["intent_id"] for i in intent_index.get(dev_b, [])}
    return list(ids_a & ids_b)
