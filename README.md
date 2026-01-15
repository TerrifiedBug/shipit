# <img src="docs/logo.png" width="32" height="32" alt="ShipIt"> ShipIt

Self-service file ingestion tool for OpenSearch. Designed for ad-hoc data uploads during investigations, troubleshooting, and analysis - quickly get JSON, CSV, TSV, LTSV, or syslog data into OpenSearch without writing ingestion pipelines.

## Features

- **Authentication**: Local users, OIDC SSO, and API keys for automation
- **User Management**: Admin UI for creating/editing/deleting users
- **OIDC SSO**: Enterprise single sign-on with auto-provisioning and group-based roles
- **Drag-and-drop upload**: JSON, NDJSON, CSV, TSV, LTSV, and syslog formats
- **Multi-file upload**: Combine multiple files of the same format into a single index
- **Auto-detection**: File format and field type inference
- **Field mapping**: Rename, exclude, and configure fields before ingestion
- **Timestamp parsing**: Automatic UTC conversion for various formats
- **Real-time progress**: Live ingestion status via Server-Sent Events
- **Upload history**: Track all uploads with user attribution and audit trail
- **Index management**: Delete indices directly from History
- **Dark mode**: Full dark theme support

## Screenshots

| Upload | Preview |
|--------|---------|
| ![Upload](docs/screenshots/upload.png) | ![Preview](docs/screenshots/preview.png) |

| Configure | Live Progress |
|-----------|----------|
| ![Configure](docs/screenshots/configure.png) | ![Progress](docs/screenshots/progress1.png) |

| Progress Complete |
|----------------------|
| ![Progress](docs/screenshots/progress2.png) |

## Quick Start (Development)

1. Clone the repository
2. Copy `.env.example` to `backend/.env` and configure:

```bash
OPENSEARCH_HOST=https://your-opensearch:9200
OPENSEARCH_USER=your-user
OPENSEARCH_PASSWORD=your-password
```

3. Start the development environment:

```bash
docker compose -f compose.dev.yaml up
```

4. Open http://localhost:8080

## Production Deployment

Build and run the production image:

```bash
docker build -t shipit .
docker run -p 80:80 --env-file .env shipit
```

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `OPENSEARCH_HOST` | OpenSearch URL (must include `https://`) |
| `OPENSEARCH_USER` | OpenSearch username |
| `OPENSEARCH_PASSWORD` | OpenSearch password |
| `SESSION_SECRET` | Secret key for signing session cookies (change in production!) |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEX_PREFIX` | `shipit-` | Prefix for all created indices |
| `MAX_FILE_SIZE_MB` | `500` | Maximum upload file size in MB |
| `DATA_DIR` | `/data` | Directory for uploads and database |
| `SESSION_DURATION_HOURS` | `8` | How long user sessions remain valid |
| `APP_URL` | - | Public URL for CORS and OIDC callbacks (e.g., `https://shipit.example.com`) |
| `FAILURE_FILE_RETENTION_HOURS` | `24` | How long to keep failed record files |
| `BULK_BATCH_SIZE` | `1000` | Number of records per bulk insert to OpenSearch |

### OIDC SSO (Optional)

| Variable | Description |
|----------|-------------|
| `OIDC_ENABLED` | Set to `true` to enable OIDC SSO |
| `OIDC_ISSUER_URL` | OIDC provider issuer URL (e.g., `https://idp.example.com`) |
| `OIDC_CLIENT_ID` | OIDC client ID |
| `OIDC_CLIENT_SECRET` | OIDC client secret |
| `OIDC_ALLOWED_DOMAIN` | Optional: restrict to email domain (e.g., `example.com`) |
| `OIDC_ADMIN_GROUP` | Optional: group name that grants admin role (e.g., `shipit-admins`) |

## Required OpenSearch Permissions

The OpenSearch user needs these permissions:

- `cluster_monitor` - Required for health check endpoint
- `crud` on `shipit-*` indices - Read/write documents
- `create_index` on `shipit-*` indices - Create new indices
- `delete_index` on `shipit-*` indices - Required for "Delete Index" option when cancelling ingestion (optional)

Example OpenSearch security role:

```json
{
  "cluster_permissions": ["cluster_monitor"],
  "index_permissions": [{
    "index_patterns": ["shipit-*"],
    "allowed_actions": ["crud", "create_index", "delete_index"]
  }]
}
```

## Supported File Formats

- **JSON Array**: `[{"field": "value"}, ...]`
- **NDJSON**: One JSON object per line
- **CSV**: Comma or semicolon delimited with header row
- **TSV**: Tab-separated values with header row
- **LTSV**: Labeled Tab-separated Values (`label:value\tlabel:value`)
- **Syslog**: RFC 3164 and RFC 5424 syslog message formats

## Timestamp Handling

When you select a timestamp field, ShipIt:

1. Parses various formats (ISO8601, nginx/Apache CLF, epoch seconds/milliseconds)
2. Converts to UTC
3. Creates an `@timestamp` field for OpenSearch index patterns

Supported formats:
- ISO8601: `2024-01-15T10:30:00Z`
- Nginx/Apache: `17/May/2015:08:05:02 +0000`
- Epoch seconds: `1705312200`
- Epoch milliseconds: `1705312200000`

## Authentication

### First-Time Setup

When no users exist, ShipIt prompts for initial admin registration. The first user is automatically an admin.

### Session Authentication

Users log in with email/password and receive a session cookie valid for `SESSION_DURATION_HOURS` (default 8 hours). Sessions are HTTP-only cookies for security.

### OIDC Single Sign-On

ShipIt supports OIDC SSO for enterprise deployments. When enabled:

1. Users see "Sign in with SSO" as the primary login option
2. Local login remains available as a fallback
3. New users are auto-provisioned on first login
4. Optional domain restriction limits which email domains can authenticate
5. Admin role can be assigned based on group membership from the IdP

**OIDC Setup:**

1. Register ShipIt as a client in your IdP
2. Set the callback URL to `{APP_URL}/api/auth/callback`
3. Configure the OIDC environment variables (see above)
4. Ensure the IdP returns `email`, `name`, and optionally `groups` claims

### User Management (Admin Only)

Admins can manage local users via the **Users** button in the header:

- **Create users**: Set email, name, initial password, and admin status
- **Edit users**: Update name, toggle admin, reset password
- **Delete users**: Soft-delete (preserves upload history)

Users created by admins must change their password on first login.

### API Keys

For programmatic access (scripts, CI/CD pipelines), users can create API keys:

1. Log in to ShipIt
2. Click **API Keys** in the header
3. Click **Create New Key**, set name and expiry
4. Copy the key (shown only once)

Use the API key in requests:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@data.json" \
  https://shipit.example.com/api/upload
```

API keys inherit the creating user's permissions and are tracked in audit logs.

## What's New in V2

### Authentication & Security
- Local user authentication with email/password
- OIDC SSO with auto-provisioning and group-based admin roles
- Admin UI for user management (create, edit, delete users)
- First-user setup flow (auto-prompts for registration when no users exist)
- Session-based auth with secure HTTP-only cookies
- API keys for programmatic access with configurable expiry
- Protected API endpoints with auth middleware
- Audit logging for security-relevant actions
- User attribution on uploads (who uploaded what)
- Password change enforcement for admin-created users

### History & Index Management
- Expandable history rows showing user, field mappings (if renamed), timestamps, errors
- Download failed records directly from Result page
- Delete index button in History with confirmation
- Visual indicator when index has been deleted
- APP_URL configuration for proxy/DNS deployments

## What's New in V3

### Index Existence Check
- Detects when indexes are deleted externally (outside ShipIt)
- History page shows "(missing)" indicator for externally-deleted indexes
- Distinguishes "deleted via ShipIt" from "deleted externally"

### Configurable Batch Size
- New `BULK_BATCH_SIZE` environment variable (default: 1000)
- Tune bulk insert performance for larger clusters

### Multi-File Upload
- Select multiple files to combine into a single index
- All files must be same format (JSON, CSV, TSV, etc.)
- Duplicate filename detection prevents overwrites

### Additional File Parsers
- **TSV**: Tab-separated values with header row
- **LTSV**: Labeled Tab-separated Values (`label:value` pairs)
- **Syslog**: RFC 3164 and RFC 5424 syslog message formats

## Roadmap (V4+)

### Elasticsearch Support
- Add compatibility with Elasticsearch clusters
- Auto-detect OpenSearch vs Elasticsearch from cluster info
- Use appropriate client library based on target

### Logfmt Parser
- Support for logfmt structured logs (`key=value key2="quoted value"`)
- Popular in Go ecosystem (Heroku, Prometheus, etc.)
- Auto-detect in `.log` files alongside LTSV and syslog

### Custom Parsers - Regex/Grok
- Ingest unstructured log files (plain text)
- Define regex with named capture groups or select grok patterns
- New "Parser" step between Upload and Preview

### Field Type Coercion
- CSV columns are always strings; convert to numbers, booleans, dates
- Per-field type dropdown in Configure step
- Custom date format specification
