# v2.0.4

## Release Date

2026-04-14

## Summary

v2.0.4 is a patch release that adds a full UI for managing VXLAN VNI Pools directly in Nautobot. Previously pools could only be created via the Django shell, the REST API, or the development seed script. No database migrations are required and there are no breaking changes.

## Added

- **VXLAN VNI Pool management UI** — a new **VNI Pools** entry appears in the Intent Engine nav menu with list, create, edit, and delete views. Pools created here are immediately available for use by `evpn_vxlan_fabric`, `l2vni`, and `l3vni` intents.
- **`VxlanVniPoolSerializer`** — REST API serializer added so VNI pools are accessible via `/api/plugins/intent-networking/vxlan-vni-pools/` with full read/write support.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.4
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! note "No database migrations"
    v2.0.4 contains only UI and API changes. No database migrations are included — `post_upgrade` will complete immediately with no schema changes.
