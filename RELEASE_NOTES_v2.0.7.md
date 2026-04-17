v2.0.7 is a bug-fix and hardening release that resolves four production-impacting defects introduced or discovered after v2.0.6 shipped, and adds one new deployment safety feature.

## Added

- **`save_config` deployment flag** — intents can now set `deployment.save_config: true` to run `write memory` (or the platform-equivalent) on each device immediately after a successful config push. Defaults to `false` to preserve existing behaviour for lab/cEOS environments. Supported in both `all_at_once` and staged (`rolling`/`canary`) strategies.

  ```yaml
  deployment:
    controller: nornir
    strategy: rolling
    save_config: true   # persists running-config to startup-config after push
  ```

- **`TestNapalmRunningConfigContains` NUTS test class** — custom first-party NUTS test class that connects to a device via NAPALM, retrieves the running configuration, and asserts that one or more text snippets are present. Registered automatically into the NUTS index at run time — no `test_module` override required. Enables content-aware config verification that was previously impossible with the built-in `TestNapalmConfig` class.

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

- **NUTS `--nornir-config` flag not passed** — `NutsVerifier` was writing a `conftest.py` that set `config.option.nuts_config` (a non-existent key), so NUTS never received the Nornir inventory path and fell back to its own discovery logic. Fixed by passing `--nornir-config=<path>` directly to `pytest.main()`, which is the documented NUTS CLI flag.

- **NUTS Netmiko platform key incorrect** — per-host inventory was using `data.netmiko_device_type` as the Nornir connection-option key, which is not a valid Nornir field. Fixed to `connection_options.netmiko.platform` per the Nornir/Netmiko inventory spec. Without this fix, all Netmiko-based NUTS test classes (CDP/OSPF/iPerf) silently failed to connect.

- **`VerificationResult` detail view 500 error** — navigating to `/plugins/intent-networking/verifications/<uuid>/` raised `AttributeError: 'VerificationResult' object has no attribute 'natural_key_field_lookups'` because Nautobot's `BaseModel` could not determine a natural key for the model. Fixed by adding `natural_key_field_names = ["pk"]` to `VerificationResult`.

- **cEOS live collection always used environment-variable credentials** — `topology_api.py` contained a dead `_get_device_credential` stub that read only `DEVICE_USERNAME` / `DEVICE_PASSWORD` env vars, bypassing the SecretsGroup lookup chain in `secrets.py` entirely. Fixed by removing the stub and calling `get_credentials_for_device(device)` directly, consistent with the deployment pipeline.

## Upgrade

No database migrations are included in this release.

```
pip install --upgrade nautobot-app-intent-networking==2.0.7
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

> **Action required if you use `TestNapalmConfig` with `config_snippet` in your intent YAMLs:** this field is not supported by the built-in NUTS `TestNapalmConfig` class — it only supports `startup_equals_running_config: true|false`. Replace `test_class: TestNapalmConfig` with `test_class: TestNapalmRunningConfigContains` to perform content-based running-config assertions. See the Added section above for the correct YAML syntax.

> **Optional — production Arista/Cisco deployments:** add `save_config: true` under `deployment:` in any intent that targets physical hardware to ensure the running config is persisted to startup config after each push.

**Full changelog:** [`v2.0.6...v2.0.7`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.6...v2.0.7)
