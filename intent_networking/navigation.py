"""Menu items for the Intent Networking plugin."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

items = (
    NavMenuItem(
        link="plugins:intent_networking:dashboard",
        name="📊 Dashboard",
        permissions=["intent_networking.view_intent"],
    ),
    NavMenuItem(
        link="plugins:intent_networking:topology_viewer",
        name="🌐 Topology",
        permissions=["intent_networking.view_intent"],
    ),
    NavMenuItem(
        link="plugins:intent_networking:intent_list",
        name="Intents",
        permissions=["intent_networking.view_intent"],
        buttons=(
            NavMenuAddButton(
                link="plugins:intent_networking:intent_add",
                permissions=["intent_networking.add_intent"],
            ),
        ),
    ),
    NavMenuItem(
        link="plugins:intent_networking:resolutionplan_list",
        name="Resolution Plans",
        permissions=["intent_networking.view_resolutionplan"],
    ),
    NavMenuItem(
        link="plugins:intent_networking:verificationresult_list",
        name="Verifications",
        permissions=["intent_networking.view_verificationresult"],
    ),
    NavMenuItem(
        link="plugins:intent_networking:auditentry_list",
        name="🔍 Audit Trail",
        permissions=["intent_networking.view_intentauditentry"],
    ),
)

ipam_items = (
    NavMenuItem(
        link="ipam:vrf_list",
        name="VRFs",
        permissions=["ipam.view_vrf"],
    ),
    NavMenuItem(
        link="ipam:routetarget_list",
        name="Route Targets",
        permissions=["ipam.view_routetarget"],
    ),
    NavMenuItem(
        link="ipam:namespace_list",
        name="Namespaces",
        permissions=["ipam.view_namespace"],
    ),
)

menu_items = (
    NavMenuTab(
        name="Intent Engine",
        weight=450,  # Between Circuits (400) and VPN (450) – prominent position
        icon="route",
        groups=(
            NavMenuGroup(name="Intent Networking", weight=100, items=tuple(items)),
            NavMenuGroup(name="IPAM Resources", weight=200, items=tuple(ipam_items)),
        ),
    ),
)
