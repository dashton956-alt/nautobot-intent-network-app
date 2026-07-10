# v2.0.14 Release Notes

## Release Date

2026-07-10

## Summary

v2.0.14 is a **bug-fix release** addressing two user-facing issues: the
full-screen topology viewer covering Nautobot's navigation (a side effect of
the v2.0.13 z-index fix), and a crash when opening the VNI Pools add/edit form
on newer Nautobot releases.

There are no new database migrations and no behaviour changes to the intent
pipeline.

## Bug Fixes

### Topology viewer no longer covers Nautobot's navigation

The v2.0.13 fix stopped the viewer being clipped *under* the navbar — but did
so by sitting *on top of* Nautobot's chrome, hiding the navbar/sidebar and
leaving no way off the page except the browser back button.

- The viewer now fits **around** whatever chrome the theme renders (top navbar
  and/or left sidebar): it measures where Nautobot placed the content block in
  normal layout flow and uses those offsets as its insets.
- It **re-fits live** when the sidebar expands or collapses (`ResizeObserver`
  on the content block, with a `transitionend` fallback for animated chrome),
  redrawing the graph canvas to the new area.
- The viewer's z-index sits below Nautobot's chrome again, so navigation
  dropdown menus open over it.
- A new **← Exit** toolbar link returns to the Intent dashboard as a guaranteed
  escape hatch.

### VNI Pools add/edit form crash

Opening `/plugins/intent-networking/vni-pools/add/` raised:

```text
AttributeError: 'VxlanVniPool' object has no attribute 'get_relationships'
```

`VxlanVniPool` is a plain `BaseModel` (no relationship/custom-field/note
support), but its form extended `NautobotModelForm`, whose relationship mixin
calls `instance.get_relationships()` unconditionally on newer Nautobot
releases. The form is now a plain `BootstrapMixin` `ModelForm`, keeping the
searchable tenant selector via an explicit `DynamicModelChoiceField`.
Regression tests cover the add-view instantiation path.

## Quality

- `invoke unittest`: 598 passing (11 browser-only skips).
- `invoke pylint`: 10.00/10; ruff, djlint, yamllint, markdownlint clean.
- Render smoke test: green across all six platform template sets.

## Upgrade

No database migrations.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.14
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**Full changelog:** [`v2.0.13...v2.0.14`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.13...v2.0.14)
