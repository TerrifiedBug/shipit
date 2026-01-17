import { useCallback, useState } from 'react';
import { uploadFilesWithProgress, UploadResponse } from '../api/client';
import { useToast } from '../contexts/ToastContext';

interface UploadProps {
  onUploadComplete: (data: UploadResponse) => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Upload({ onUploadComplete }: UploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const { addToast } = useToast();

  const handleFiles = useCallback(async (files: File[]) => {
    setError(null);
    setSelectedFiles(files);
    setIsUploading(true);
    setUploadProgress(0);

    try {
      const result = await uploadFilesWithProgress(files, (percent) => {
        setUploadProgress(percent);
      });
      onUploadComplete(result);
      addToast(files.length > 1 ? 'Files uploaded successfully' : 'File uploaded successfully', 'success');
      setSelectedFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  }, [onUploadComplete, addToast]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      handleFiles(files);
    }
  }, [handleFiles]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFiles(Array.from(files));
    }
    // Reset the input so the same files can be selected again
    e.target.value = '';
  }, [handleFiles]);

  return (
    <div className="px-4 py-6 sm:px-0">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-4 border-dashed rounded-lg h-96 flex items-center justify-center transition-colors ${
          isDragging
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900'
            : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500'
        } ${isUploading ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <div className="text-center">
          {isUploading ? (
            <div className="w-full max-w-md px-4">
              <svg
                className="mx-auto h-12 w-12 text-indigo-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
              <p className="mt-4 text-lg font-medium text-gray-700 dark:text-gray-200">
                Uploading {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''}...
              </p>
              {/* Progress bar */}
              <div className="mt-4 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 overflow-hidden">
                <div
                  className="bg-indigo-500 h-full rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="mt-2 text-2xl font-semibold text-indigo-600 dark:text-indigo-400">
                {uploadProgress}%
              </p>
              {selectedFiles.length > 0 && (
                <ul className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                  {selectedFiles.map((file, i) => (
                    <li key={i}>{file.name} ({formatFileSize(file.size)})</li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <>
              <svg
                className="mx-auto h-12 w-12 text-gray-400"
                stroke="currentColor"
                fill="none"
                viewBox="0 0 48 48"
                aria-hidden="true"
              >
                <path
                  d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <div className="mt-4">
                <p className="text-lg text-gray-600 dark:text-gray-300">
                  Drag and drop your file here, or{' '}
                  <label className="text-indigo-600 dark:text-indigo-400 cursor-pointer hover:text-indigo-500 dark:hover:text-indigo-300">
                    browse
                    <input
                      type="file"
                      className="hidden"
                      accept=".json,.csv,.tsv,.ltsv,.log,.txt,.ndjson,.jsonl"
                      multiple
                      onChange={handleFileInput}
                    />
                  </label>
                </p>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  Supports JSON, NDJSON, CSV, TSV, LTSV, and Syslog formats
                </p>
              </div>
            </>
          )}
          {error && (
            <p className="mt-4 text-sm text-red-600">{error}</p>
          )}
        </div>
      </div>
    </div>
  );
}
