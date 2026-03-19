# Compatibility Matrix

The app follows semantic versioning. Patch releases (e.g. `0.4.1`) contain only bug-fixes; minor releases (e.g. `0.5.0`) may add features; major releases (e.g. `1.0.0`) may include breaking changes.

## Supported Versions

| Intent Networking Version | Nautobot Minimum | Nautobot Maximum | Python | Status |
|---------------------------|-----------------|-----------------|--------|--------|
| 1.1.4 | 3.0.0 | 3.x | 3.10–3.12 | Current |
| 1.1.x | 3.0.0 | 3.x | ≥ 3.10 | Supported |
| 1.0.x | 3.0.0 | 3.x | ≥ 3.10 | Supported |
| 0.5.x | 3.0.0 | 3.x | ≥ 3.10 | Deprecated |
| 0.4.x | 3.0.0 | 3.x | ≥ 3.10 | Deprecated |
| 0.3.x | 3.0.0 | 3.x | ≥ 3.10 | End of Life |
| 0.2.x | 3.0.0 | 3.x | ≥ 3.10 | End of Life |
| 0.1.x | 3.0.0 | 3.x | ≥ 3.10 | End of Life |

## Database Support

| Database | Supported |
|----------|-----------|
| PostgreSQL 14+ | ✅ Yes (recommended) |
| MySQL 8+ | ✅ Yes |

## Deprecation Policy

- Only the latest minor release receives bug-fix patches.
- Features deprecated in release N are removed no earlier than release N+2.
- Database migrations are always forward-compatible within a major version series.
