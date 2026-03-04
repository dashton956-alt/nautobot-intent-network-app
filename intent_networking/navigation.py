"""Menu items for the Intent Networking plugin."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

items = (
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

menu_items = (
    NavMenuTab(
        name="Apps",
        groups=(NavMenuGroup(name="Intent Networking", items=tuple(items)),),
    ),
)
