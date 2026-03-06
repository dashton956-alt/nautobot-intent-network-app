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
)

pool_items = (
    NavMenuItem(
        link="plugins:intent_networking:routedistinguisherpool_list",
        name="RD Pools",
        permissions=["intent_networking.view_routedistinguisherpool"],
        buttons=(
            NavMenuAddButton(
                link="plugins:intent_networking:routedistinguisherpool_add",
                permissions=["intent_networking.add_routedistinguisherpool"],
            ),
        ),
    ),
    NavMenuItem(
        link="plugins:intent_networking:routetargetpool_list",
        name="RT Pools",
        permissions=["intent_networking.view_routetargetpool"],
        buttons=(
            NavMenuAddButton(
                link="plugins:intent_networking:routetargetpool_add",
                permissions=["intent_networking.add_routetargetpool"],
            ),
        ),
    ),
)

menu_items = (
    NavMenuTab(
        name="Apps",
        groups=(
            NavMenuGroup(name="Intent Networking", items=tuple(items)),
            NavMenuGroup(name="Resource Pools", items=tuple(pool_items)),
        ),
    ),
)
