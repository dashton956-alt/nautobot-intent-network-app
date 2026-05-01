v2.0.9 is a bug-fix release that resolves a compatibility issue with Nautobot 3.1.1.

## What's Fixed

### VNI Pools list view crash on Nautobot 3.1.1

Browsing to `/plugins/intent-networking/vni-pools/` raised:

```
AttributeError: 'DynamicFilterForm' object requires `filterset` attribute
```

Nautobot 3.1.1 tightened validation inside `DynamicFilterForm.__init__` — the `NautobotUIViewSet` list view now requires `filterset_class` and `filterset_form_class` to be set on any viewset that renders a list page. The `VxlanVniPoolUIViewSet` was missing both.

**Fix:** Added `VxlanVniPoolFilterSet` and `VxlanVniPoolFilterForm`, and wired them into the viewset.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.9
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

No database migrations in this release.

**Full changelog:** [`v2.0.8...v2.0.9`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.8...v2.0.9)
