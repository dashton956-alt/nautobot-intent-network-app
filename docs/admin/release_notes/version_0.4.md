# v0.4 Release Notes

## v0.4.0 - 2026-03-09

### Added

- Expanded IntentTypeChoices to 129 intent types across 14 networking domains:
    - Layer 2 / Switching (14 types)
    - Layer 3 / Routing (16 types)
    - MPLS & Service Provider (10 types)
    - Data Centre / EVPN / VXLAN (9 types)
    - Security & Firewalling (14 types)
    - WAN & SD-WAN (9 types)
    - Wireless (11 types)
    - Cloud & Hybrid Cloud (10 types)
    - QoS (7 types)
    - Multicast (5 types)
    - Management & Operations (11 types)
    - Reachability expanded (4 types)
    - Service expanded (5 types)
- Full resolver implementation for all 129 intent types
- Controller adapters for non-Nornir deployment:
    - WirelessControllerAdapter (11 primitive types)
    - SdWanControllerAdapter (5 primitive types)
    - CloudAdapter (9 primitive types)
    - Adapter factory and primitive classifier
- Resource allocation pools and allocations:
    - VxlanVniPool / VniAllocation
    - TunnelIdPool / TunnelIdAllocation
    - ManagedLoopbackPool / ManagedLoopback
    - WirelessVlanPool / WirelessVlanAllocation
- Jinja2 templates for 5 platforms:
    - cisco/ios-xe, cisco/ios-xr, cisco/nxos, juniper/junos, aruba/aos-cx
- NX-OS specific templates for DC/EVPN/VXLAN intents
- REST API serializer validation for all 129 intent types
- Migration 0005 for all new models and updated intent_type choices

### Changed

- Updated primitive_template_map to 87+ entries covering all primitive types
- Updated platform_map to include cisco-nxos
- Improved pylint score to 10.00/10
