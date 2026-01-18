const API_BASE = import.meta.env.VITE_API_URL || '';

// Auth types and functions
export interface User {
  id: string;
  email: string;
  name: string;
  is_admin: number;
  auth_type: 'local' | 'oidc';
  password_change_required?: boolean;
}

export async function getCurrentUser(): Promise<User | null> {
  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      credentials: 'include',
    });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

export async function login(email: string, password: string): Promise<User> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Login failed');
  }
  const data = await response.json();
  return {
    ...data.user,
    password_change_required: data.password_change_required,
  };
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/auth/change-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to change password');
  }
}

export interface AuthConfig {
  oidc_enabled: boolean;
  local_enabled: boolean;
}

export async function getAuthConfig(): Promise<AuthConfig> {
  const response = await fetch(`${API_BASE}/api/auth/config`, {
    credentials: 'include',
  });
  if (!response.ok) {
    return { oidc_enabled: false, local_enabled: true };
  }
  return response.json();
}

export function getOidcLoginUrl(): string {
  return `${API_BASE}/api/auth/oidc/login`;
}

export async function setup(email: string, password: string, name: string): Promise<User> {
  const response = await fetch(`${API_BASE}/api/auth/setup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email, password, name }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Setup failed');
  }
  return response.json();
}

// API Keys types and functions
export interface ApiKey {
  id: string;
  name: string;
  expires_at: string;
  created_at: string;
  last_used: string | null;
  allowed_ips: string | null;
}

export interface CreateKeyResponse extends ApiKey {
  key: string;
}

export async function listApiKeys(): Promise<ApiKey[]> {
  const response = await fetch(`${API_BASE}/api/keys`, {
    credentials: 'include',
  });
  if (!response.ok) throw new Error('Failed to list API keys');
  return response.json();
}

export async function createApiKey(
  name: string,
  expiresInDays: number,
  allowedIps?: string
): Promise<CreateKeyResponse> {
  const response = await fetch(`${API_BASE}/api/keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      name,
      expires_in_days: expiresInDays,
      allowed_ips: allowedIps || null,
    }),
  });
  if (!response.ok) throw new Error('Failed to create API key');
  return response.json();
}

export async function deleteApiKey(keyId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/keys/${keyId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) throw new Error('Failed to delete API key');
}

// Upload types and functions
export interface FieldInfo {
  name: string;
  type: string;
}

// Supported file formats for parsing
export type FileFormat = 'json_array' | 'ndjson' | 'csv' | 'tsv' | 'ltsv' | 'syslog' | 'logfmt' | 'raw' | 'custom';

export interface UploadResponse {
  upload_id: string;
  filename: string;
  filenames: string[];
  file_size: number;
  file_format: FileFormat;
  preview: Record<string, unknown>[];
  fields: FieldInfo[];
  raw_preview: string[];  // Raw lines for pattern testing
}

export interface PreviewResponse {
  upload_id: string;
  filename: string;
  file_format: FileFormat;
  preview: Record<string, unknown>[];
  fields: FieldInfo[];
}

export async function uploadFiles(files: File[]): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));

  const response = await fetch(`${API_BASE}/api/upload`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

export function uploadFilesWithProgress(
  files: File[],
  onProgress: (percent: number) => void
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));

    const xhr = new XMLHttpRequest();

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        onProgress(percent);
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText);
          resolve(response);
        } catch {
          reject(new Error('Invalid response from server'));
        }
      } else {
        try {
          const error = JSON.parse(xhr.responseText);
          reject(new Error(error.detail || 'Upload failed'));
        } catch {
          reject(new Error('Upload failed'));
        }
      }
    };

    xhr.onerror = () => {
      reject(new Error('Network error during upload'));
    };

    xhr.open('POST', `${API_BASE}/api/upload`);
    xhr.withCredentials = true;
    xhr.send(formData);
  });
}

export async function getPreview(uploadId: string): Promise<PreviewResponse> {
  const response = await fetch(`${API_BASE}/api/upload/${uploadId}/preview`, {
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch preview');
  }

  return response.json();
}

export interface IngestRequest {
  index_name: string;
  timestamp_field?: string | null;
  field_mappings: Record<string, string>;
  excluded_fields: string[];
  field_types?: Record<string, string>;
  include_filename?: boolean;
  filename_field?: string;
}

export interface IngestResponse {
  upload_id: string;
  index_name: string;
  processed: number;
  success: number;
  failed: number;
}

export async function startIngest(
  uploadId: string,
  request: IngestRequest
): Promise<IngestResponse> {
  const response = await fetch(`${API_BASE}/api/upload/${uploadId}/ingest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Ingestion failed');
  }

  return response.json();
}

export interface UploadRecord {
  id: string;
  filename: string;
  file_size: number;
  file_format: FileFormat;
  index_name: string | null;
  timestamp_field: string | null;
  field_mappings: Record<string, string> | null;
  excluded_fields: string[] | null;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  total_records: number | null;
  success_count: number | null;
  failure_count: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  error_message: string | null;
  index_deleted: number;
  index_exists: boolean | null;
  user_name: string | null;
  user_email: string | null;
  upload_method: 'web' | 'api';
  api_key_name: string | null;
}

export interface HistoryResponse {
  uploads: UploadRecord[];
  limit: number;
  offset: number;
}

export async function getHistory(
  limit = 50,
  offset = 0,
  status?: string
): Promise<HistoryResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (status) {
    params.append('status', status);
  }

  const response = await fetch(`${API_BASE}/api/history?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch history');
  }

  return response.json();
}

export function getFailuresDownloadUrl(uploadId: string): string {
  return `${API_BASE}/api/upload/${uploadId}/failures`;
}

export function downloadFailures(uploadId: string): void {
  window.open(`${API_BASE}/api/upload/${uploadId}/failures`, '_blank');
}

export interface ProgressEvent {
  processed: number;
  total: number;
  success: number;
  failed: number;
  records_per_second: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number;
}

export function subscribeToProgress(
  uploadId: string,
  onProgress: (data: ProgressEvent) => void,
  onComplete: (data: ProgressEvent) => void,
  onError: (error: string) => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/api/upload/${uploadId}/status`, {
    withCredentials: true,
  });

  eventSource.addEventListener('progress', (event) => {
    onProgress(JSON.parse(event.data));
  });

  eventSource.addEventListener('complete', (event) => {
    onComplete(JSON.parse(event.data));
    eventSource.close();
  });

  eventSource.addEventListener('error', (event) => {
    if (event instanceof MessageEvent) {
      onError(JSON.parse(event.data).error);
    } else {
      onError('Connection lost');
    }
    eventSource.close();
  });

  return () => eventSource.close();
}

export interface CancelResult {
  status: string;
  upload_id: string;
  index_deleted: boolean | null;
}

export async function cancelIngest(uploadId: string, deleteIndex: boolean): Promise<CancelResult> {
  const response = await fetch(`${API_BASE}/api/upload/${uploadId}/cancel?delete_index=${deleteIndex}`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to cancel ingestion');
  }
  return response.json();
}

export async function deleteIndex(indexName: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/indexes/${indexName}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete index');
  }
}

export async function deletePendingUpload(uploadId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/upload/${uploadId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  // Silently ignore errors - upload may have already been processed
  if (!response.ok) {
    console.warn('Failed to delete pending upload:', uploadId);
  }
}

// Admin user management types and functions
export interface AdminUser {
  id: string;
  email: string;
  name: string | null;
  is_admin: boolean;
  is_active: boolean;
  auth_type: string;
  created_at: string;
  last_login: string | null;
}

export interface CreateUserRequest {
  email: string;
  name: string;
  password: string;
  is_admin: boolean;
}

export interface UpdateUserRequest {
  name?: string;
  is_admin?: boolean;
  new_password?: string;
}

export async function listUsers(): Promise<AdminUser[]> {
  const response = await fetch(`${API_BASE}/api/admin/users`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to list users');
  }
  const data = await response.json();
  return data.users;
}

export async function createUser(request: CreateUserRequest): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/api/admin/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create user');
  }
  return response.json();
}

export async function updateUser(userId: string, request: UpdateUserRequest): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/api/admin/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update user');
  }
  return response.json();
}

export async function deleteUser(userId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/admin/users/${userId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete user');
  }
}

export async function deactivateUser(userId: string): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/api/admin/users/${userId}/deactivate`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to deactivate user');
  }
  return response.json();
}

export async function activateUser(userId: string): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/api/admin/users/${userId}/activate`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to activate user');
  }
  return response.json();
}

// Audit log types and functions
export interface AuditLogEntry {
  id: string;
  event_type: string;
  actor_id: string | null;
  actor_name: string | null;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  logs: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AuditLogParams {
  page?: number;
  page_size?: number;
  event_type?: string;
  actor_id?: string;
  target_type?: string;
}

export async function getAuditLogs(params: AuditLogParams = {}): Promise<AuditLogListResponse> {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.append('page', params.page.toString());
  if (params.page_size) searchParams.append('page_size', params.page_size.toString());
  if (params.event_type) searchParams.append('event_type', params.event_type);
  if (params.actor_id) searchParams.append('actor_id', params.actor_id);
  if (params.target_type) searchParams.append('target_type', params.target_type);

  const response = await fetch(`${API_BASE}/api/audit/logs?${searchParams}`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch audit logs');
  }
  return response.json();
}

export async function getAuditEventTypes(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/api/audit/event-types`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch event types');
  }
  const data = await response.json();
  return data.event_types;
}

// App settings
export interface AppSettings {
  index_retention_days: number;
}

export async function getAppSettings(): Promise<AppSettings> {
  const response = await fetch(`${API_BASE}/api/settings`, {
    credentials: 'include',
  });
  if (!response.ok) {
    return { index_retention_days: 0 };
  }
  return response.json();
}

// Reparse function for format override
export async function reparseUpload(
  uploadId: string,
  format: FileFormat | 'custom',
  patternId?: string,
  multilineStart?: string,
): Promise<{
  upload_id: string;
  file_format: string;
  pattern_id: string | null;
  preview: Record<string, unknown>[];
  fields: FieldInfo[];
  raw_preview: string[];
}> {
  const formData = new FormData();
  formData.append('format', format);
  if (patternId) {
    formData.append('pattern_id', patternId);
  }
  if (multilineStart) {
    formData.append('multiline_start', multilineStart);
  }

  const response = await fetch(`${API_BASE}/api/upload/${uploadId}/reparse`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    // Handle structured error with suggested_formats
    if (error.detail && typeof error.detail === 'object' && error.detail.suggested_formats) {
      const err = new Error(error.detail.error || 'Failed to reparse') as Error & {
        suggested_formats?: string[];
      };
      err.suggested_formats = error.detail.suggested_formats;
      throw err;
    }
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Failed to reparse');
  }

  return response.json();
}

// Pattern types and functions
export interface Pattern {
  id: string;
  name: string;
  type: 'regex' | 'grok';
  pattern: string;
  description: string | null;
  test_sample: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PatternCreate {
  name: string;
  type: 'regex' | 'grok';
  pattern: string;
  description?: string;
  test_sample?: string;
}

export interface PatternUpdate {
  name?: string;
  type?: 'regex' | 'grok';
  pattern?: string;
  description?: string;
  test_sample?: string;
}

export interface GrokPattern {
  id: string;
  name: string;
  regex: string;
  description: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  builtin: boolean;
}

export interface BuiltinGrokPattern {
  name: string;
  regex: string;
  description: string;
  builtin: true;
}

export interface GrokPatternCreate {
  name: string;
  regex: string;
  description?: string;
}

export interface GrokPatternUpdate {
  regex?: string;
  description?: string;
}

export interface PatternTestRequest {
  pattern: string;
  pattern_type: 'regex' | 'grok';
  test_text: string;
}

export interface PatternTestResponse {
  success: boolean;
  matches: Record<string, string> | null;
  error: string | null;
}

// Custom patterns CRUD
export async function listPatterns(): Promise<Pattern[]> {
  const response = await fetch(`${API_BASE}/api/patterns`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to list patterns');
  }
  return response.json();
}

export async function createPattern(data: PatternCreate): Promise<Pattern> {
  const response = await fetch(`${API_BASE}/api/patterns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create pattern');
  }
  return response.json();
}

export async function getPattern(patternId: string): Promise<Pattern> {
  const response = await fetch(`${API_BASE}/api/patterns/${patternId}`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Pattern not found');
  }
  return response.json();
}

export async function updatePattern(patternId: string, data: PatternUpdate): Promise<Pattern> {
  const response = await fetch(`${API_BASE}/api/patterns/${patternId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update pattern');
  }
  return response.json();
}

export async function deletePattern(patternId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/patterns/${patternId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete pattern');
  }
}

export async function testPattern(data: PatternTestRequest): Promise<PatternTestResponse> {
  const response = await fetch(`${API_BASE}/api/patterns/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to test pattern');
  }
  return response.json();
}

// Grok pattern components
export async function listBuiltinGrokPatterns(): Promise<BuiltinGrokPattern[]> {
  const response = await fetch(`${API_BASE}/api/patterns/grok/builtin`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to list built-in grok patterns');
  }
  return response.json();
}

export async function listGrokPatterns(): Promise<GrokPattern[]> {
  const response = await fetch(`${API_BASE}/api/patterns/grok`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to list grok patterns');
  }
  return response.json();
}

export async function createGrokPattern(data: GrokPatternCreate): Promise<GrokPattern> {
  const response = await fetch(`${API_BASE}/api/patterns/grok`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create grok pattern');
  }
  return response.json();
}

export async function updateGrokPattern(patternId: string, data: GrokPatternUpdate): Promise<GrokPattern> {
  const response = await fetch(`${API_BASE}/api/patterns/grok/${patternId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update grok pattern');
  }
  return response.json();
}

export async function deleteGrokPattern(patternId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/patterns/grok/${patternId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete grok pattern');
  }
}

// Grok pattern expansion
export interface GrokExpandResponse {
  expanded: string | null;
  groups: string[];
  valid: boolean;
  error?: string;
}

export async function expandGrokPattern(pattern: string): Promise<GrokExpandResponse> {
  const response = await fetch(
    `${API_BASE}/api/patterns/grok/expand?pattern=${encodeURIComponent(pattern)}`,
    {
      credentials: 'include',
    }
  );
  if (!response.ok) {
    throw new Error('Failed to expand grok pattern');
  }
  return response.json();
}
