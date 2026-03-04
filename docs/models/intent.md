# Intent

An **Intent** is the central record for a declarative network policy defined in the network-as-code Git repository.

Each `Intent` corresponds to one YAML file in the repo. It is created or updated when the CI pipeline calls the sync-from-git API on a pull request, and updated at every lifecycle stage thereafter.

## Fields

| Field | Type | Description |
|---|---|---|
| `intent_id` | string | Unique identifier — matches the `id` field in the YAML file, e.g. `fin-pci-connectivity-001` |
| `version` | integer | Version number, incremented each time the YAML changes |
| `intent_type` | choice | `connectivity`, `security`, or `reachability` |
| `tenant` | FK → Tenant | Business owner of the intent |
| `status` | StatusField | Current lifecycle status: `Draft → Validated → Deploying → Deployed → Failed → Rolled Back → Deprecated` |
| `intent_data` | JSON | Full parsed YAML stored as JSON — the single source of truth |
| `change_ticket` | string | Change management ticket reference, e.g. `CHG0012345` |
| `approved_by` | string | GitHub username of the PR approver |
| `git_commit_sha` | string | Commit SHA that triggered the most recent deployment |
| `git_branch` | string | Source branch |
| `git_pr_number` | integer | Pull request number |
| `deployed_at` | datetime | When the intent was last successfully deployed |
| `last_verified_at` | datetime | When the intent was last verified |

## Relationships

- `resolution_plans` — one or more `ResolutionPlan` records produced each time the intent is resolved
- `verifications` — one or more `VerificationResult` records produced after each deployment
