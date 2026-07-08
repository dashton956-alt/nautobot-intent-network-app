"""End-to-end render smoke-test for the example intent corpus.

For every example intent: run the real resolver (stubbing only the DB / device /
allocation layer) and render each resulting primitive through every platform
template that exists, under StrictUndefined. This guarantees the
example -> resolver -> template field contract holds and cannot silently drift.

Primitive types routed to controller/cloud adapters (no Jinja template) are
skipped, as are resolvers that require live DB state the stub can't provide.
"""

import glob
from pathlib import Path
from unittest import mock

import yaml
from django.test import TestCase
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from intent_networking import resolver as R

REPO = Path(__file__).resolve().parent.parent.parent
INTENTS = REPO / "network_as_code_example" / "intents"
TPL = REPO / "intent_networking" / "jinja_templates"
# Platforms held to the StrictUndefined render contract. arista/eos is the
# reference lab platform and cisco/ios-xe the default; the remaining vendor
# template sets are enforced to the same contract.
PLATFORMS = ["arista/eos", "cisco/ios-xe", "cisco/ios-xr", "cisco/nxos", "juniper/junos", "aruba/aos-cx"]

# Primitive types handled by controller/cloud adapters (not Jinja-rendered).
ADAPTER_PRIMITIVES = {
    "wireless_ssid",
    "wireless_vlan_map",
    "wireless_dot1x",
    "wireless_guest",
    "wireless_rf",
    "wireless_qos",
    "wireless_band_steer",
    "wireless_roam",
    "wireless_segment",
    "wireless_mesh",
    "wireless_flexconnect",
    "sdwan_overlay",
    "sdwan_app_policy",
    "sdwan_qos",
    "sdwan_dia",
    "cloud_sdwan",
    "cloud_vpc_peer",
    "cloud_transit_gw",
    "cloud_direct_connect",
    "cloud_vpn_gw",
    "cloud_security_group",
    "cloud_nat",
    "cloud_route_table",
    "hybrid_dns",
    "fw_rule",
}
# Intent types whose resolver needs live DB beyond the stub layer.
SKIP_TYPES = {"dc_mlag"}


def _stub_device(name="render-leaf-01"):
    d = mock.MagicMock()
    d.name = name
    d.platform.name = "arista-eos"
    d.platform.network_driver = "arista_eos"
    d.interfaces.all.return_value = []
    d.tags.all.return_value = []
    d.role.name = "leaf-switch"
    return d


def _intent_obj(data):
    i = mock.MagicMock()
    i.intent_data = data
    i.intent_type = data.get("type")
    i.intent_id = data.get("id", "render-intent")
    i.version = data.get("version", 1)
    i.tenant.name = data.get("tenant", "acme-corp")
    return i


def _template_map():
    import re

    src = (REPO / "intent_networking" / "jobs.py").read_text()
    m = re.search(r"primitive_template_map\s*=\s*\{(.*?)\n    \}", src, re.S)
    return dict(re.findall(r'"([a-z0-9_]+)"\s*:\s*"([a-z0-9_]+\.j2)"', m.group(1)))


class IntentRenderSmokeTest(TestCase):
    """Resolve + render every example intent across all platforms."""

    def test_corpus_resolves_and_renders(self):
        tmap = _template_map()
        envs = {
            p: Environment(
                loader=FileSystemLoader(str(TPL / p)),
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            for p in PLATFORMS
        }
        files = sorted(glob.glob(str(INTENTS / "**" / "*.y*ml"), recursive=True))
        failures = []
        # Return two devices so multi-device intents (e.g. mlag, which requires a
        # peer pair) produce primitives instead of raising on a single-device scope.
        two = [_stub_device("render-leaf-01"), _stub_device("render-leaf-02")]
        patches = {
            "_get_scope_devices": mock.Mock(side_effect=lambda intent, scope_key="scope": list(two)),
            "get_devices_for_group": mock.Mock(side_effect=lambda *a, **k: list(two)),
            "_devices_by_ip": mock.Mock(side_effect=lambda *a, **k: list(two)),
            "_fabric_member_names": mock.Mock(side_effect=lambda *a, **k: ["render-leaf-01"]),
            "allocate_vxlan_vni": mock.Mock(return_value=10100),
            "allocate_tunnel_id": mock.Mock(return_value=100),
            "allocate_loopback_ip": mock.Mock(return_value="10.0.0.1"),
            "allocate_route_distinguisher": mock.Mock(return_value="65000:1"),
            "allocate_route_target": mock.Mock(return_value=("65000:1", "65000:1")),
        }
        with mock.patch.multiple(R, **patches):
            for f in files:
                if "/examples/" in f:
                    continue
                rel = f.split("/intents/")[1]
                with open(f, encoding="utf-8") as fh:
                    docs = [d for d in yaml.safe_load_all(fh) if d]
                if len(docs) != 1:
                    continue
                d = docs[0]
                d = d.get("intent", d) if isinstance(d, dict) else d
                if not isinstance(d, dict) or not d.get("type") or d["type"] in SKIP_TYPES:
                    continue
                try:
                    plan = R.resolve_intent(_intent_obj(d))
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"RESOLVE {rel} ({d['type']}): {type(exc).__name__}: {exc}")
                    continue
                for prim in plan.get("primitives", []):
                    ptype = prim.get("primitive_type")
                    if ptype in ADAPTER_PRIMITIVES:
                        continue
                    tname = tmap.get(ptype)
                    if not tname:
                        failures.append(f"NOTMPL  {rel}: primitive '{ptype}' has no template mapping")
                        continue
                    for plat in PLATFORMS:
                        if not (TPL / plat / tname).exists():
                            continue  # not every platform implements every primitive
                        try:
                            envs[plat].get_template(tname).render(**prim)
                        except Exception as exc:  # noqa: BLE001
                            failures.append(f"RENDER  {rel} [{plat}/{tname}]: {type(exc).__name__}: {exc}")

        self.assertEqual(failures, [], "\n" + "\n".join(failures) + f"\n\n{len(failures)} render/resolve failures")
