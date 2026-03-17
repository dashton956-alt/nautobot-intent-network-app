# v1.1.2

## Added

* Added `.intentignore` file support — users can place a `.intentignore` in the repo root or intent directory to exclude files from Git sync using fnmatch glob patterns.
* Added Approve/Reject buttons to the intent detail page UI. Added support for Nautobot native Approval Workflow (`on_workflow_approved`/`denied`/`canceled` callbacks). Updated `is_approved` to accept approval from either custom `IntentApproval` records or native `ApprovalWorkflow`.
* Added `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, and `mgmt_global_config` intent types for Management & Operations domain.
* Added "Retired" intent status. Retired intents remain in Git but are non-actionable — reconciliation skips them and only a transition back to Draft is allowed.
* Added `fw_rule` (Firewall Rule) intent type with stateful/stateless firewall policy support. Includes resolver, Jinja templates for all 6 vendor platforms (Cisco IOS-XE/IOS-XR/NX-OS, Juniper Junos, Aruba AOS-CX, Arista EOS), and `FirewallControllerAdapter` for centralized firewall appliances (Palo Alto Panorama, Fortinet FortiManager).
