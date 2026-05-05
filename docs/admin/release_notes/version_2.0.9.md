# v2.0.9

## Release Date

2026-05-01

## Summary

v2.0.9 is a bug-fix release that resolves a compatibility issue with Nautobot 3.1.1. The VNI Pools list view crashed with an `AttributeError` when `DynamicFilterForm` was instantiated without a `filterset` attribute — a validation that was tightened in Nautobot 3.1.1.

## Fixed

- **VNI Pools list view crash on Nautobot 3.1.1** — browsing to `/plugins/intent-networking/vni-pools/` raised `AttributeError: 'DynamicFilterForm' object requires 'filterset' attribute`. The `VxlanVniPoolUIViewSet` was missing `filterset_class` and `filterset_form_class` attributes, which `NautobotUIViewSet` requires to construct the dynamic filter panel in list views. Fixed by adding `VxlanVniPoolFilterSet` (in `filters.py`) and `VxlanVniPoolFilterForm` (in `forms.py`) and wiring them into the viewset.

## Upgrade

No database migrations are included in this release.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.9
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**Full changelog:** [`v2.0.8...v2.0.9`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.8...v2.0.9)
