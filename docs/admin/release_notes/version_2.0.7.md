# v2.0.7

## Release Date

2026-04-17

## Summary

v2.0.7 is a bug-fix and hardening release. It resolves four production-impacting defects in the NUTS verification engine and related subsystems, and introduces `save_config` support for persisting the running configuration to startup configuration after a successful deployment push.

## Added

- **`save_config` deployment flag** — intents can now set `deployment.save_config: true` to run `write memory` (or the platform-equivalent) on each device immediately after a successful configuration push. Defaults to `false` to preserve existing behaviour for ephemeral environments (cEOS / containerlab). Supported in both `all_at_once` and staged (`rolling` / `canary`) strategies.

    ```yaml
    deployment:
      controller: nornir
      strategy: rolling
      save_config: true   # persists running-config to startup-config after push
    ```

- **`TestNapalmRunningConfigContains` NUTS test class** — a custom first-party NUTS test class packaged inside the plugin at `intent_networking.nuts_tests.running_config`. It connects to a device via NAPALM, retrieves the running configuration, and asserts that one or more text snippets are present in the output. The class is automatically registered into the NUTS test-class index at run time — no `test_module` override is needed in the intent YAML. This enables content-aware running-config verification that is not possible with the built-in `TestNapalmConfig` class.

    ```yaml
    verification:
      level: nuts
      tests:
        - test_class: TestNapalmRunningConfigContains
          label: "Verify NTP servers in running config"
          expected:
            - config_snippet: "ntp server 10.0.0.1"
            - config_snippet: "ntp server 10.0.0.2"
    ```

## Fixed

- **NUTS `--nornir-config` flag never passed to pytest** — `NutsVerifier` was writing a `conftest.py` that attempted to set `config.option.nuts_config` (a nonexistent attribute on the pytest config object), so NUTS never received the path to the Nornir inventory and silently fell back to its own inventory discovery. Fixed by passing `--nornir-config=<path>` directly to `pytest.main()`, which is the documented NUTS CLI flag. Without this fix, all NUTS test bundles ran against an empty inventory and produced no results.

- **NUTS Netmiko platform key incorrect** — the per-host Nornir inventory constructed by `NutsVerifier` was using `data.netmiko_device_type` as the connection-option key for Netmiko. This key is not part of the Nornir inventory spec. Fixed to `connection_options.netmiko.platform`, consistent with the [nornir-netmiko](https://github.com/nornir-automation/nornir_netmiko) documentation. Without this fix, all Netmiko-based NUTS test classes (`TestNetmikoCdpNeighbors`, `TestNetmikoOspfNeighbors`, `TestNetmikoIperf`) silently failed to connect.

- **`VerificationResult` detail view raised `AttributeError` (HTTP 500)** — navigating to `/plugins/intent-networking/verifications/<uuid>/` raised `AttributeError: 'VerificationResult' object has no attribute 'natural_key_field_lookups'` because Nautobot's `BaseModel.natural_key_field_lookups` property could not determine a unique natural key for `VerificationResult` (which has no unique business-key fields — each row is a timestamped event). Fixed by adding `natural_key_field_names = ["pk"]` to `VerificationResult`.

- **cEOS topology live collection always used environment-variable credentials** — `topology_api.py` contained a private `_get_device_credential` stub that read only the `DEVICE_USERNAME` and `DEVICE_PASSWORD` environment variables, entirely bypassing the SecretsGroup lookup chain in `secrets.py`. Fixed by removing the stub and calling `get_credentials_for_device(device)` directly, consistent with the credential resolution used by the deployment pipeline.

## Upgrade

No database migrations are included in this release.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.7
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! warning "Action required if you use `TestNapalmConfig` with `config_snippet`"
    The built-in NUTS `TestNapalmConfig` class supports only one field: `startup_equals_running_config: true|false`. It does **not** support a `config_snippet` field — NUTS silently ignores unknown fields, so tests using this pattern were never actually executed.

    Replace `test_class: TestNapalmConfig` with `test_class: TestNapalmRunningConfigContains` to perform content-based assertions against the running configuration:

    ```yaml
    # Before (invalid — config_snippet silently ignored by NUTS)
    - test_class: TestNapalmConfig
      label: "Verify NTP"
      expected:
        - config_snippet: "ntp server 10.0.0.1"

    # After (correct)
    - test_class: TestNapalmRunningConfigContains
      label: "Verify NTP"
      expected:
        - config_snippet: "ntp server 10.0.0.1"
    ```

!!! tip "Optional — production devices"
    Add `save_config: true` under `deployment:` in any intent that targets physical hardware to ensure the running configuration is persisted to startup configuration after each push. Leave `save_config` unset (or `false`) for ephemeral lab targets such as cEOS containers.

**Full changelog:** [`v2.0.6...v2.0.7`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.6...v2.0.7)
