# ShipIt ![alt text](image.png)

Self-service file ingestion tool for OpenSearch. Upload JSON or CSV files, configure field mappings, and bulk ingest into OpenSearch indices.

## Features

- Drag-and-drop file upload (JSON array, NDJSON, CSV)
- Auto-detection of file format and field types
- Field mapping and renaming
- Timestamp field parsing with automatic UTC conversion
- Real-time ingestion progress via SSE
- Upload history with status tracking
- Dark mode support

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

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENSEARCH_HOST` | Yes | - | OpenSearch URL (must include https://) |
| `OPENSEARCH_USER` | Yes | - | OpenSearch username |
| `OPENSEARCH_PASSWORD` | Yes | - | OpenSearch password |
| `INDEX_PREFIX` | No | `shipit-` | Prefix for all created indices |
| `MAX_FILE_SIZE_MB` | No | `500` | Maximum upload file size in MB |
| `DATA_DIR` | No | `/data` | Directory for uploads and database |

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

## Roadmap

Planned features for future releases:

### Authentication
- OIDC/SAML SSO, or local users
- User identity in upload history for audit trails

### Custom Parsers - Regex/Grok
- Ingest unstructured log files (plain text)
- Define regex with named capture groups or select grok patterns
- New "Parser" step between Upload and Preview

### Field Type Coercion
- CSV columns are always strings; convert to numbers, booleans, dates
- Per-field type dropdown in Configure step
- Custom date format specification

### Additional File Parsers
- **Syslog**: RFC 3164 and RFC 5424 syslog message formats
- **TSV**: Tab-separated values
- **LTSV**: Labeled Tab-separated Values (common in web server logs)

### Multi-File Upload
- Ingest multiple related files into the same index
- Accept multiple files in upload step, concatenate during ingestion

### API Access
- Programmatic uploads from scripts or CI/CD pipelines
- REST API with token-based auth
