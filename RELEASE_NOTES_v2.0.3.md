v2.0.3 is a patch release that fixes a `Status.DoesNotExist` error on fresh Nautobot installs. No breaking changes.

## Fixed

- **Intent lifecycle statuses now seeded by migration** — a new data migration (`0015_seed_intent_lifecycle_statuses`) ensures all eight lifecycle statuses (`Draft`, `Validated`, `Deploying`, `Deployed`, `Failed`, `Rolled Back`, `Deprecated`, `Retired`) are created automatically on any Nautobot instance. Previously a fresh production or staging install would fail immediately with `Status.DoesNotExist` when the first Intent Deployment job ran.

## Upgrade

```
pip install --upgrade nautobot-app-intent-networking==2.0.3
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

> One data migration included — `post_upgrade` applies it automatically. No table schema changes.

**Full changelog:** [`v2.0.2...v2.0.3`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.2...v2.0.3)
