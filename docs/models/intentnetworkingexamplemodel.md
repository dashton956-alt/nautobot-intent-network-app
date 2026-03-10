# Resource Pool Models

The app provides four resource pool types for network resources that are not natively modelled in Nautobot's IPAM. Each pool defines a numeric range, and allocations are drawn atomically using `select_for_update()` to prevent duplicates under concurrent access.

!!! note
    Route Distinguishers and Route Targets are now managed through Nautobot's native `ipam.VRF` and `ipam.RouteTarget` models. See [IPAM Integration](#ipam-integration) below.

---

## VxlanVniPool

A pool of VXLAN Network Identifiers (VNIs) available for allocation.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique pool name (e.g. `"dc1-vni-pool"`) |
| `range_start` | integer | First VNI in the pool (e.g. `10000`) |
| `range_end` | integer | Last VNI in the pool (e.g. `19999`) |
| `description` | string | Optional description |

### VniAllocation

An individual VNI allocation from a `VxlanVniPool`.

| Field | Type | Description |
|-------|------|-------------|
| `pool` | FK → VxlanVniPool | Parent pool |
| `vni` | integer | Allocated VNI value |
| `intent` | FK → Intent | Intent that requested the allocation |
| `tenant` | FK → Tenant | Owning tenant |
| `allocated_at` | datetime | When the allocation was made |

---

## TunnelIdPool

A pool of tunnel interface IDs (e.g. for GRE, IPsec, DMVPN tunnels).

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique pool name (e.g. `"wan-tunnel-ids"`) |
| `range_start` | integer | First tunnel ID (e.g. `100`) |
| `range_end` | integer | Last tunnel ID (e.g. `999`) |
| `description` | string | Optional description |

### TunnelIdAllocation

An individual tunnel ID allocation from a `TunnelIdPool`.

| Field | Type | Description |
|-------|------|-------------|
| `pool` | FK → TunnelIdPool | Parent pool |
| `tunnel_id` | integer | Allocated tunnel ID |
| `intent` | FK → Intent | Intent that requested the allocation |
| `device` | FK → Device | Target device |
| `allocated_at` | datetime | When the allocation was made |

---

## ManagedLoopbackPool

A pool of /32 loopback IP addresses.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique pool name (e.g. `"loopback-pool"`) |
| `network` | string | CIDR network (e.g. `"10.255.0.0/24"`) |
| `description` | string | Optional description |

### ManagedLoopback

An individual loopback IP allocation from a `ManagedLoopbackPool`.

| Field | Type | Description |
|-------|------|-------------|
| `pool` | FK → ManagedLoopbackPool | Parent pool |
| `ip_address` | string | Allocated /32 IP address |
| `intent` | FK → Intent | Intent that requested the allocation |
| `device` | FK → Device | Target device |
| `allocated_at` | datetime | When the allocation was made |

---

## WirelessVlanPool

A pool of VLAN IDs reserved for wireless SSID provisioning.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique pool name (e.g. `"wireless-vlans"`) |
| `range_start` | integer | First VLAN ID (e.g. `3000`) |
| `range_end` | integer | Last VLAN ID (e.g. `3999`) |
| `description` | string | Optional description |

### WirelessVlanAllocation

An individual VLAN ID allocation from a `WirelessVlanPool`.

| Field | Type | Description |
|-------|------|-------------|
| `pool` | FK → WirelessVlanPool | Parent pool |
| `vlan_id` | integer | Allocated VLAN ID |
| `intent` | FK → Intent | Intent that requested the allocation |
| `site` | string | Site / location name |
| `allocated_at` | datetime | When the allocation was made |

---

## IPAM Integration

Route Distinguisher and Route Target allocation uses Nautobot's native IPAM models:

| Nautobot Model | How the App Uses It |
|----------------|-------------------|
| `ipam.Namespace` | Scoping boundary for VRF uniqueness (configured via `vrf_namespace` setting) |
| `ipam.VRF` | Each intent-created VRF stores its RD in the native `rd` field. The `description` field tracks the owning intent ID. |
| `ipam.RouteTarget` | Import/export RT values are created as native `RouteTarget` objects and associated with VRFs via the standard `import_targets` / `export_targets` M2M relationships. |

RD and RT values are auto-generated in `<ASN>:<counter>` format using the `default_bgp_asn` setting.
