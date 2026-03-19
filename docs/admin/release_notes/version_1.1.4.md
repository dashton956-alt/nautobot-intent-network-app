# v1.1.4

## Fixed

- **Migration `atomic = False` for PostgreSQL** — Migrations `0010` (verification level fields) and `0013` (controller fields) now set `atomic = False` to prevent PostgreSQL "pending trigger events" errors when `AddField` and `AlterField` run in the same transaction.
- **Python 3.13 build failure** — Pinned Python to `>=3.10,<3.13` because pyATS/Genie do not yet publish wheels for Python 3.13+. The `genie` package installation previously failed during Docker builds on Python 3.13.
- **drf-spectacular warnings** — Added return type hints to `SerializerMethodField` getters (W001) and `@extend_schema` decorators to topology API views (W002).
- **CI pylint `E1120` errors** — Added `pylint: disable=no-value-for-parameter` to `dnacentersdk` method calls in the Catalyst Center adapter rollback path.

## Added

- **Catalyst Center adapter** — New `CatalystCenterAdapter` for deploying, verifying, and rolling back intents via Cisco Catalyst Center (DNA Center) REST API. Includes `controller_type`, `controller_site`, and `controller_org` fields on the Intent model.
- **Intent Dependency Graph** — Intents can now declare dependencies on other intents via a `dependencies` ManyToManyField. Deployment is blocked until all upstream intents are in `Deployed` status.
- **Updated seed data and examples** — All seed intents, test fixtures, and Network-as-Code YAML examples now include the new controller, deployment strategy, and verification fields.

## Upgrade

```shell
pip install --upgrade nautobot-app-intent-networking==1.1.4
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**Catalyst Center support (optional):**

```shell
pip install nautobot-app-intent-networking[catalyst]
```

## Python Version Note

This release pins Python to **3.10–3.12**. If you require pyATS extended verification, use Python 3.12 or below. This constraint will be lifted once Cisco publishes pyATS/Genie wheels for Python 3.13.
