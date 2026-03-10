# Extending the App

This guide explains how to extend the Intent Networking app with custom intent types, controller adapters, Jinja templates, and OPA policies.

## Adding a New Intent Type

Intent types are defined in the `IntentTypeChoices` enum in `models.py`. To add a new type:

1. Add the choice to `IntentTypeChoices`:

```python
class IntentTypeChoices(models.TextChoices):
    # ... existing types ...
    MY_CUSTOM_TYPE = "my_custom_type", "My Custom Type"
```

2. Add resolution logic in `resolver.py`. The resolver maps each intent type to a set of vendor-neutral network primitives:

```python
def resolve_intent(intent):
    """Resolve an intent into deployment primitives."""
    if intent.intent_type == "my_custom_type":
        return resolve_my_custom_type(intent)
    # ... existing handlers ...
```

3. Create a migration to add the new choice value:

```shell
nautobot-server makemigrations intent_networking
```

## Custom Controller Adapters

Controller adapters translate vendor-neutral primitives into device-specific configurations. They live in `controller_adapters.py`.

To add a new adapter:

1. Create a function that returns the device configuration for each primitive type:

```python
def my_vendor_adapter(primitives, device):
    """Generate configuration for MyVendor devices."""
    config_lines = []
    for primitive in primitives:
        if primitive["type"] == "vrf":
            config_lines.append(f"vrf {primitive['name']}")
            config_lines.append(f"  rd {primitive['rd']}")
    return "\n".join(config_lines)
```

2. Register the adapter in the `get_adapter()` function, keyed by the device platform slug.

## Custom Jinja Templates

The app uses Jinja2 templates in `jinja_templates/` for configuration rendering. To add templates for a new platform:

1. Create a directory under `jinja_templates/` named after the platform slug (e.g. `jinja_templates/cisco_ios/`)
2. Add template files named after the primitive type (e.g. `vrf.j2`, `bgp_neighbor.j2`)

```jinja2
{# jinja_templates/cisco_ios/vrf.j2 #}
vrf definition {{ vrf_name }}
 rd {{ rd }}
 !
 address-family ipv4
  route-target export {{ rt_export }}
  route-target import {{ rt_import }}
 exit-address-family
```

## Custom OPA Policies

OPA policies are written in Rego and loaded into your OPA server. The app sends the full intent data as input.

Example: enforce that all security intents must have a change ticket:

```rego
package intent

deny["Security intents require a change ticket"] {
    input.intent_type == "security"
    input.change_ticket == ""
}
```

## Custom Resource Pools

If you need a new type of resource pool (beyond VNI, Tunnel ID, Loopback, and Wireless VLAN):

1. Add a `Pool` model and an `Allocation` model in `models.py` following the existing pool pattern
2. Add allocation logic in `allocations.py` using `select_for_update()` for atomicity
3. Register the models in `admin.py`, `tables.py`, `views.py`, and `api/serializers.py`
4. Create a migration

## Contributing Extensions

Extensions and contributions are welcome. Please open an issue first to discuss the approach before submitting a PR. See the [Contributing Guide](contributing.md) for development setup and code standards.
