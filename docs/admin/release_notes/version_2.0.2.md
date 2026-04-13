# v2.0.2

## Release Date

2026-04-13

## Summary

v2.0.2 is a patch release that introduces an `expected` shorthand for NUTS verification test bundles. Intent authors no longer need to repeat identical checks for every device in scope — a single `expected` list is automatically expanded to all devices resolved by the intent scope at verification time. No database migrations are required and there are no breaking changes.

## Added

- **`expected` shorthand in NUTS test bundles** — a new top-level `expected` key can be used on any verification test entry as an alternative to `test_data`. When `expected` is defined (without `test_data`), the verifier automatically expands the checks to every device in the resolution plan's `affected_devices`, eliminating per-host repetition in intent YAML files.

  **Before (repeated per device):**

  ```yaml
  verification:
    tests:
      - test_class: TestNapalmConfig
        test_data:
          - host: sw01
            expected:
              - config_snippet: "ntp server 10.0.0.1"
          - host: sw02
            expected:
              - config_snippet: "ntp server 10.0.0.1"
  ```

  **After (defined once, runs on all scoped devices):**

  ```yaml
  verification:
    tests:
      - test_class: TestNapalmConfig
        expected:
          - config_snippet: "ntp server 10.0.0.1"
  ```

- **Explicit precedence warning** — when both `expected` and `test_data` are defined on the same test entry, `test_data` takes precedence and a `WARNING` is logged to make the ambiguity visible rather than silently discarding `expected`.

- **Deterministic bundle generation** — device names are now sorted alphabetically when expanding `expected`, ensuring consistent test bundle YAML output across runs regardless of queryset ordering.

## Fixed

- Resolved all unresolved git merge conflicts in intent YAML files across `mgmt/`, `l2/`, `l3/`, `cloud/`, `dc/`, `ipsec-wan/`, `connectivity/`, `qos/`, `reachability/`, `security/`, `mpls/`, and `wireless/` intent directories.

- Updated `schemas/intent.schema.yml` — `test_data` is now `required: false` (was `required: true`) and the new `expected` key is added to the test entry schema, so intents using the shorthand pass schema validation.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.2
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! note "No database migrations"
    v2.0.2 contains only application logic and schema definition changes. No database migrations are included — `post_upgrade` will complete immediately with no schema changes.

!!! note "Backwards compatible"
    Existing intent YAML files using `test_data` continue to work unchanged. The `expected` shorthand is purely additive.
