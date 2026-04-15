v2.0.4 is a patch release that adds a full UI for managing VXLAN VNI Pools directly in Nautobot. No database migrations are required and there are no breaking changes.

## Added

- **VXLAN VNI Pool management UI** — a new **VNI Pools** entry appears in the Intent Engine nav menu with list, create, edit, and delete views. Pools created here are immediately available for use by `evpn_vxlan_fabric`, `l2vni`, and `l3vni` intents. Previously pools could only be created via the Django shell, REST API, or the development seed script.
- **`VxlanVniPoolSerializer`** — REST API serializer added, exposing VNI pools at `/api/plugins/intent-networking/vxlan-vni-pools/` with full read/write support.

## Upgrade

```
pip install --upgrade nautobot-app-intent-networking==2.0.4
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

> No database migrations — `post_upgrade` completes immediately with no schema changes.

**Full changelog:** [`v2.0.3...v2.0.4`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.3...v2.0.4)
