# Uninstall the App from Nautobot

Here you will find any steps necessary to cleanly remove the App from your Nautobot environment.

## Database Cleanup

Prior to removing the app from the `nautobot_config.py`, run the following command to roll back any migration specific to this app.

```shell
nautobot-server migrate intent_networking zero
```

This will remove all Intent Networking database tables including intents, resolution plans, verification results, resource pools, and audit entries.

!!! warning
    Rolling back migrations will **permanently delete** all data stored by the app. Make sure to export any data you wish to retain before proceeding. Note that Nautobot native IPAM objects (VRFs, Route Targets, Namespaces) created by the app will **not** be removed — manage those through the standard IPAM interface if desired.

## Remove App Configuration

Remove the `"intent_networking"` entry from `PLUGINS` and `PLUGINS_CONFIG` in your `nautobot_config.py`.

## Uninstall the Package

```shell
pip uninstall nautobot-app-intent-networking
```

## Restart Services

```shell
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```
