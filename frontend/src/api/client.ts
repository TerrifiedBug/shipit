const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface FieldInfo {
  name: string;
  type: string;
}

export interface UploadResponse {
  upload_id: string;
  filename: string;
  file_size: number;
  file_format: 'json_array' | 'ndjson' | 'csv';
  preview: Record<string, unknown>[];
  fields: FieldInfo[];
}

export interface PreviewResponse {
  upload_id: string;
  filename: string;
  file_format: 'json_array' | 'ndjson' | 'csv';
  preview: Record<string, unknown>[];
  fields: FieldInfo[];
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/api/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

export async function getPreview(uploadId: string): Promise<PreviewResponse> {
  const response = await fetch(`${API_BASE}/api/upload/${uploadId}/preview`);

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
  file_format: 'json_array' | 'ndjson' | 'csv';
  index_name: string | null;
  timestamp_field: string | null;
  field_mappings: Record<string, string> | null;
  excluded_fields: string[] | null;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  total_records: number | null;
  success_count: number | null;
  failure_count: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  error_message: string | null;
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

  const response = await fetch(`${API_BASE}/api/history?${params}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch history');
  }

  return response.json();
}

export function getFailuresDownloadUrl(uploadId: string): string {
  return `${API_BASE}/api/upload/${uploadId}/failures`;
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
  const eventSource = new EventSource(`${API_BASE}/api/upload/${uploadId}/status`);

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

export async function cancelIngest(uploadId: string, deleteIndex: boolean): Promise<void> {
  const response = await fetch(`${API_BASE}/api/upload/${uploadId}/cancel?delete_index=${deleteIndex}`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to cancel ingestion');
  }
}
