# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-01-18

### Added
- Chunked upload for files up to 5GB with resume support
- GeoIP enrichment for IP fields using MaxMind GeoLite2
- ECS (Elastic Common Schema) field mapping suggestions
- Field transformations: lowercase, uppercase, trim, regex_extract, regex_replace, truncate, base64_decode, url_decode, hash_sha256, mask_email, mask_ip, default, parse_json, parse_kv
- Format validation with suggested alternatives when mismatch detected
- Trusted proxy configuration for X-Forwarded-For
- Nested JSON flattening - automatically converts nested objects to dot-notation (e.g., `log.level`)
- Bulk grok pattern import - import pattern files from GitHub (Cisco ASA, etc.) via paste or file upload
- OpenSearch connectivity status indicator in header with cluster info popover
- LOG_LEVEL configuration for diagnostic output (debug, info, warning, error)

### Changed
- Large file uploads now use chunked upload automatically (>100MB)
- ECS mapping now uses official Elastic schema with 200+ fields
- ECS auto-mapping removes ambiguous fields (e.g., `remote_ip` no longer auto-maps)

### Fixed
- SQL injection vulnerability in dynamic column updates
- Default session secret now fails in production environment
- Timing attack in authentication (constant-time comparison)
- GeoIP checkbox now detects IP fields by value validation, not field name patterns

### Security
- Added column allowlists for database updates
- Added SHIPIT_ENV production check for session secret
- Added TRUSTED_PROXIES config for reverse proxy setups

## [0.2.1] - 2025-01-18

### Added
- Logfmt format parser (`key=value key2="quoted value"`)
- Raw format parser (each line becomes `raw_message` field)
- Grok pattern support with 50+ built-in patterns
- Custom pattern management - save and reuse parsing patterns
- Pattern-based parsing in Preview step with live highlighting
- Grok autocomplete in pattern editor
- Multiline pattern matching for multi-line log entries
- Change Password option in user menu dropdown

### Changed
- Session invalidation on password change (logs out other sessions)

### Fixed
- Account lockout counter not decrementing after timeout
- Upload cancellation handling
- Custom pattern preview display
- NDJSON format detection for .log files
- Patterns API routing with user email

### Security
- ReDoS protection with regex timeout (5 second limit)
- CodeQL vulnerability fixes
- Static error messages to prevent information exposure

## [0.2.0] - 2025-01-10

### Added
- SSL certificate verification for OpenSearch connections
- Per-user upload rate limiting (configurable, default 10/min)
- Comprehensive audit logging for security events
- Session hardening with HTTP-only secure cookies
- Account protection with login rate limiting and lockout
- Session invalidation on password change
- API upload tracking in history with method and key name
- Upload method display (UI/API) in history
- API key IP allowlisting with CIDR support
- API key expiration warnings in UI
- Upload progress indicator for large files
- Automatic index retention/TTL (configurable days)
- Field type coercion (string, integer, float, boolean)

### Changed
- Improved field type inference from sample data

### Fixed
- Audit log schema migration from older versions

## [0.1.8] - 2025-01-05

### Added
- Security & Guardrails section in README
- Update available check functionality

### Changed
- Improved README with motivation and tech stack sections
- Added disclaimer about intended use case

## [0.1.7] - 2025-01-04

### Added
- CI path filters to only build on app code changes
- Dev tag for main branch pushes

### Fixed
- Dev compose .env file configuration

## [0.1.6] - 2025-01-03

### Added
- Version display in UI
- Auto-release on version bump
- Auto-tag latest on version bump

### Fixed
- Docker cache busting on version change

## [0.1.5] - 2025-01-02

### Added
- Single-shot upload API endpoint (`/api/v1/upload`)
- Filename enrichment option (add source filename to records)
- Logo in header and login page
- UI polish improvements (phase 6)

### Fixed
- Use data_dir for temp files in API upload

## [0.1.4] - 2025-01-01

### Added
- Strict index mode (only write to ShipIt-created indices)
- Index protection validation in upload flow
- Soft delete users with re-registration support
- Block login for deactivated users

### Fixed
- Path validation security in tests

## [0.1.3] - 2024-12-28

### Added
- TSV parser (tab-separated values)
- LTSV parser (labeled tab-separated values)
- Syslog parser (RFC 3164 and RFC 5424)
- Multi-file upload support
- Streaming ingestion for large files
- BULK_BATCH_SIZE configuration
- Index existence check in history
- Clean up pending uploads on browser tab close

### Fixed
- LTSV format detection in .log files
- Multiple spaces as delimiter in TSV/LTSV
- Delete pending uploads when user abandons flow

### Security
- Path traversal vulnerability in file upload
- Validate upload_id as UUID
- Validate file paths within allowed directory

## [0.1.2] - 2024-12-20

### Fixed
- SSE live progress not working with multiple workers

### Changed
- Simplified compose.yaml configuration
- Use env_file for all configuration

## [0.1.1] - 2024-12-15

### Added
- User management UI for admins
- OIDC SSO with auto-provisioning
- API keys for programmatic access
- Bearer token authentication
- Delete index functionality
- Expandable rows in History
- Download failed records from Result page
- Auth middleware for protected endpoints

### Changed
- Hide password reset for OIDC users

## [0.1.0] - 2024-12-01

### Added
- Initial release
- Drag-and-drop file upload
- JSON and NDJSON format support
- CSV format support with auto-delimiter detection
- Field mapping (rename, exclude)
- Timestamp parsing with UTC conversion
- Real-time ingestion progress via SSE
- Upload history with user attribution
- Dark mode support
- Docker deployment with nginx reverse proxy

[Unreleased]: https://github.com/TerrifiedBug/shipit/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/TerrifiedBug/shipit/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/TerrifiedBug/shipit/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/TerrifiedBug/shipit/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/TerrifiedBug/shipit/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/TerrifiedBug/shipit/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/TerrifiedBug/shipit/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/TerrifiedBug/shipit/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/TerrifiedBug/shipit/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/TerrifiedBug/shipit/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/TerrifiedBug/shipit/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/TerrifiedBug/shipit/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/TerrifiedBug/shipit/releases/tag/v0.1.0
