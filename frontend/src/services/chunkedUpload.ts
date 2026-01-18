// frontend/src/services/chunkedUpload.ts

const PARALLEL_CHUNKS = 3;

interface ChunkedUploadResult {
  upload_id: string;
  chunk_size: number;
  total_chunks: number;
}

interface UploadStatus {
  completed_chunks: number[];
  total_chunks: number;
}

export async function initChunkedUpload(
  filename: string,
  fileSize: number
): Promise<ChunkedUploadResult> {
  const formData = new FormData();
  formData.append('filename', filename);
  formData.append('file_size', fileSize.toString());

  const response = await fetch('/api/upload/chunked/init', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to initialize upload');
  }

  return response.json();
}

export async function getUploadStatus(uploadId: string): Promise<UploadStatus> {
  const response = await fetch(`/api/upload/chunked/${uploadId}/status`);
  if (!response.ok) {
    throw new Error('Failed to get upload status');
  }
  return response.json();
}

async function uploadChunk(
  file: File,
  uploadId: string,
  chunkIndex: number,
  chunkSize: number
): Promise<void> {
  const start = chunkIndex * chunkSize;
  const end = Math.min(start + chunkSize, file.size);
  const chunk = file.slice(start, end);

  const response = await fetch(
    `/api/upload/chunked/${uploadId}/chunk/${chunkIndex}`,
    {
      method: 'POST',
      body: chunk,
      headers: {
        'Content-Type': 'application/octet-stream',
      },
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to upload chunk ${chunkIndex}`);
  }
}

async function uploadChunksParallel(
  file: File,
  uploadId: string,
  pendingChunks: number[],
  chunkSize: number,
  parallelism: number,
  onProgress: (completed: number, total: number) => void
): Promise<void> {
  let completed = 0;
  const total = pendingChunks.length;

  // Process chunks in batches
  for (let i = 0; i < pendingChunks.length; i += parallelism) {
    const batch = pendingChunks.slice(i, i + parallelism);

    await Promise.all(
      batch.map(async (chunkIndex) => {
        await uploadChunk(file, uploadId, chunkIndex, chunkSize);
        completed++;
        onProgress(completed, total);
      })
    );
  }
}

export async function uploadLargeFile(
  file: File,
  onProgress: (percent: number) => void
): Promise<string> {
  // Initialize upload
  const { upload_id, chunk_size, total_chunks } = await initChunkedUpload(
    file.name,
    file.size
  );

  // Check for resume - get current status
  const status = await getUploadStatus(upload_id);
  const completedSet = new Set(status.completed_chunks);
  const pending = Array.from({ length: total_chunks }, (_, i) => i)
    .filter((i) => !completedSet.has(i));

  // Upload remaining chunks
  await uploadChunksParallel(
    file,
    upload_id,
    pending,
    chunk_size,
    PARALLEL_CHUNKS,
    (completed, _total) => {
      const existingProgress = status.completed_chunks.length;
      const overallProgress = (existingProgress + completed) / total_chunks;
      onProgress(Math.round(overallProgress * 100));
    }
  );

  // Complete upload
  const completeResponse = await fetch(
    `/api/upload/chunked/${upload_id}/complete`,
    { method: 'POST' }
  );

  if (!completeResponse.ok) {
    throw new Error('Failed to complete upload');
  }

  return upload_id;
}

// Threshold for using chunked upload (100MB)
export const CHUNKED_UPLOAD_THRESHOLD = 100 * 1024 * 1024;
