# v1.1.8

## Release Date

2026-03-23

## Fixed

- **Nornir inventory plugin registration** — `NautobotORMInventory` is now explicitly registered with nornir's `InventoryPluginRegister` before each `InitNornir` call. The `nautobot-plugin-nornir` package registers the inventory under the name `"nautobot-inventory"`, not `"NautobotORMInventory"` — all three call sites (`jobs.py` `_push()`, `basic.py` `_collect_device_state()`, `basic.py` `_measure_latency()`) now use the correct registered name.
- **`nautobot_plugin_nornir` added to PLUGINS** — the plugin must be listed in `PLUGINS` in `nautobot_config.py` so its nornir inventory and credential classes are available at runtime. Added to development config with `CredentialsNautobotSecrets` as the default credential backend.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==1.1.8
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! important
    Ensure your `nautobot_config.py` includes `"nautobot_plugin_nornir"` in the `PLUGINS` list **before** `"intent_networking"`, and configure the credential backend in `PLUGINS_CONFIG`:

    ```python
    PLUGINS = ["nautobot_plugin_nornir", "intent_networking"]

    PLUGINS_CONFIG = {
        "nautobot_plugin_nornir": {
            "use_config_context": {"secrets": False, "connection_options": True},
            "nornir_settings": {
                "credentials": "nautobot_plugin_nornir.plugins.credentials.nautobot_secrets.CredentialsNautobotSecrets",
            },
        },
        "intent_networking": {
            # ... your existing config ...
        },
    }
    ```
