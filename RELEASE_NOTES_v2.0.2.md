v2.0.2 is a patch release that adds an `expected` shorthand to NUTS verification bundles and fixes merge conflicts across all shipped intent YAML files. No database migrations are required and there are no breaking changes.

## Added

- **`expected` shorthand in NUTS verification** — test bundles now accept a top-level `expected` key instead of repeating `test_data` entries per host. When `expected` is present, checks are automatically expanded to every device resolved by the intent's scope. `test_data` continues to work unchanged and takes precedence if both keys are present.

  Before:
  ```yaml
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

  After:
  ```yaml
  tests:
    - test_class: TestNapalmConfig
      expected:
        - config_snippet: "ntp server 10.0.0.1"
  ```

## Fixed

- **Intent YAML merge conflicts** — resolved unresolved merge markers in all intent files across `mgmt/`, `l2/`, `l3/`, `cloud/`, `dc/`, `ipsec-wan/`, `connectivity/`, `qos/`, `reachability/`, `security/`, `mpls/`, and `wireless/` directories.
- **Intent schema** — `schemas/intent.schema.yml` updated: `test_data` is now optional and `expected` is recognised as a valid key, so intents using the new shorthand pass schema validation without errors.

## Upgrade

```
pip install --upgrade nautobot-app-intent-networking==2.0.2
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

No database migrations — `post_upgrade` completes immediately with no schema changes.
