# v2.0.3

## Release Date

2026-04-14

## Summary

v2.0.3 is a patch release that fixes a `Status.DoesNotExist` error thrown by the Intent Deployment job on Nautobot instances that were not initialised using the development seed script. All Intent lifecycle statuses are now created automatically by a data migration during `post_upgrade`. No breaking changes.

## Fixed

- **Intent lifecycle statuses now seeded by migration** — a new data migration (`0015_seed_intent_lifecycle_statuses`) ensures the eight lifecycle statuses (`Draft`, `Validated`, `Deploying`, `Deployed`, `Failed`, `Rolled Back`, `Deprecated`, `Retired`) exist and are associated with the `Intent` content type on any Nautobot instance. Previously these were only created by the development `seed_data.py` script, causing any fresh production or staging install to fail immediately with a `Status.DoesNotExist` exception when the first job ran.

  The migration is idempotent — instances that already have these statuses (created via `seed_data.py`) are unaffected.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.3
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! note "Database migration included"
    v2.0.3 includes one data migration (`0015_seed_intent_lifecycle_statuses`). Running `post_upgrade` will apply it automatically. No table schema changes are made — only status records are inserted.
