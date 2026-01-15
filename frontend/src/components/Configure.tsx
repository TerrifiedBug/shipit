import { useState } from 'react';
import {
  cancelIngest,
  FieldInfo,
  IngestResponse,
  ProgressEvent,
  startIngest,
  subscribeToProgress,
  UploadResponse,
} from '../api/client';
import { useToast } from '../contexts/ToastContext';

interface ConfigureProps {
  data: UploadResponse;
  onBack: () => void;
  onComplete: (result: IngestResponse) => void;
  onReset: () => void;
}

const INDEX_PREFIX = 'shipit-';

// Keywords that suggest a field is a timestamp
const TIMESTAMP_KEYWORDS = ['time', 'date', 'created', 'updated', 'timestamp', 'at', 'when', 'ts'];

// Patterns that look like timestamps
const TIMESTAMP_PATTERNS = [
  /^\d{4}-\d{2}-\d{2}/, // ISO date start
  /^\d{2}\/\w{3}\/\d{4}/, // Nginx/Apache CLF
  /^\d{10,13}$/, // Epoch seconds or milliseconds
  /T\d{2}:\d{2}/, // ISO datetime
];

function looksLikeTimestamp(value: unknown): boolean {
  if (value === null || value === undefined) return false;

  // Check if it's an epoch number
  if (typeof value === 'number' && value > 1000000000) return true;

  const str = String(value);
  return TIMESTAMP_PATTERNS.some(pattern => pattern.test(str));
}

function isLikelyTimestampField(fieldName: string, sampleValues: unknown[]): boolean {
  // Check field name
  const nameLower = fieldName.toLowerCase();
  if (TIMESTAMP_KEYWORDS.some(keyword => nameLower.includes(keyword))) {
    return true;
  }

  // Check sample values - if any look like timestamps
  return sampleValues.some(looksLikeTimestamp);
}

interface FieldMapping {
  originalName: string;
  mappedName: string;
  excluded: boolean;
}

interface ProgressState {
  processed: number;
  total: number;
  success: number;
  failed: number;
  records_per_second: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number;
}

export function Configure({ data, onBack, onComplete, onReset }: ConfigureProps) {
  const { addToast } = useToast();
  const [indexName, setIndexName] = useState('');
  const [timestampField, setTimestampField] = useState<string | null>(null);
  const [fieldMappings, setFieldMappings] = useState<FieldMapping[]>(
    data.fields.map((f) => ({
      originalName: f.name,
      mappedName: f.name,
      excluded: false,
    }))
  );
  const [isIngesting, setIsIngesting] = useState(false);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const handleFieldNameChange = (index: number, newName: string) => {
    setFieldMappings((prev) =>
      prev.map((f, i) => (i === index ? { ...f, mappedName: newName } : f))
    );
  };

  const handleExcludeToggle = (index: number) => {
    setFieldMappings((prev) =>
      prev.map((f, i) => (i === index ? { ...f, excluded: !f.excluded } : f))
    );
  };

  const handleIngest = async () => {
    if (!indexName.trim()) {
      setError('Index name is required');
      return;
    }

    // Validate index name
    if (indexName !== indexName.toLowerCase()) {
      setError('Index name must be lowercase');
      return;
    }

    const invalidChars = ['\\', '/', '*', '?', '"', '<', '>', '|', ' ', ',', '#', ':'];
    for (const char of invalidChars) {
      if (indexName.includes(char)) {
        setError(`Index name cannot contain '${char}'`);
        return;
      }
    }

    setError(null);
    setIsIngesting(true);
    setProgress(null);

    try {
      // Build field mappings (only include changed names)
      const mappings: Record<string, string> = {};
      const excluded: string[] = [];

      for (const field of fieldMappings) {
        if (field.excluded) {
          excluded.push(field.originalName);
        } else if (field.mappedName !== field.originalName) {
          mappings[field.originalName] = field.mappedName;
        }
      }

      // Start ingestion (returns immediately)
      const startResult = await startIngest(data.upload_id, {
        index_name: indexName,
        timestamp_field: timestampField,
        field_mappings: mappings,
        excluded_fields: excluded,
      });

      // Subscribe to progress updates via SSE
      const unsubscribe = subscribeToProgress(
        data.upload_id,
        // onProgress
        (progressData: ProgressEvent) => {
          setProgress(progressData);
        },
        // onComplete
        (finalData: ProgressEvent) => {
          setProgress(finalData);
          setIsIngesting(false);
          addToast(`Ingestion complete: ${finalData.success} records indexed`, 'success');
          onComplete({
            upload_id: data.upload_id,
            index_name: startResult.index_name,
            processed: finalData.processed,
            success: finalData.success,
            failed: finalData.failed,
          });
        },
        // onError
        (errorMsg: string) => {
          setError(errorMsg);
          setIsIngesting(false);
          addToast(errorMsg, 'error');
        }
      );

      // Store unsubscribe function for cleanup (not used currently but good practice)
      return () => unsubscribe();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ingestion failed');
      setIsIngesting(false);
    }
  };

  const handleCancel = async (deleteIndex: boolean) => {
    try {
      await cancelIngest(data.upload_id, deleteIndex);
      addToast('Ingestion cancelled', 'info');
      onReset();
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Failed to cancel', 'error');
    }
  };

  const activeFields = fieldMappings.filter((f) => !f.excluded);

  // Filter to only fields that look like timestamps
  const timestampCandidates = activeFields.filter((field) => {
    const sampleValues = data.preview.map((row) => row[field.originalName]);
    return isLikelyTimestampField(field.originalName, sampleValues);
  });

  const formatTime = (seconds: number): string => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  const progressPercent = progress
    ? Math.round((progress.processed / progress.total) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {/* Progress Panel (shown during ingestion) */}
      {isIngesting && progress && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Ingestion Progress</h3>

          {/* Progress Bar */}
          <div className="mb-4">
            <div className="flex justify-between text-sm text-gray-600 dark:text-gray-300 mb-1">
              <span>{progress.processed.toLocaleString()} / {progress.total.toLocaleString()} records</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4">
              <div
                className="bg-indigo-600 h-4 rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <div className="text-2xl font-bold text-green-600">
                {progress.success.toLocaleString()}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Success</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <div className="text-2xl font-bold text-red-600">
                {progress.failed.toLocaleString()}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Failed</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <div className="text-2xl font-bold text-indigo-600">
                {progress.records_per_second.toLocaleString()}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Records/sec</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <div className="text-2xl font-bold text-gray-700 dark:text-gray-200">
                {formatTime(progress.elapsed_seconds)}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">Elapsed</div>
            </div>
          </div>

          {progress.estimated_remaining_seconds > 0 && (
            <div className="mt-4 text-center text-sm text-gray-500 dark:text-gray-400">
              Estimated time remaining: {formatTime(progress.estimated_remaining_seconds)}
            </div>
          )}

          <div className="mt-4 flex justify-center">
            <button
              onClick={() => setShowCancelDialog(true)}
              className="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 border border-red-300 dark:border-red-600 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Index Configuration */}
      <div className={`bg-white dark:bg-gray-800 shadow rounded-lg p-6 ${isIngesting ? 'opacity-50 pointer-events-none' : ''}`}>
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Index Configuration</h3>

        <div className="space-y-4">
          {/* Index Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
              Index Name
            </label>
            <div className="flex">
              <span className="inline-flex items-center px-3 rounded-l-md border border-r-0 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-sm">
                {INDEX_PREFIX}
              </span>
              <input
                type="text"
                value={indexName}
                onChange={(e) => setIndexName(e.target.value.toLowerCase())}
                placeholder="my-index-name"
                className="flex-1 min-w-0 block w-full px-3 py-2 rounded-none rounded-r-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-indigo-500 focus:border-indigo-500"
                disabled={isIngesting}
              />
            </div>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Full index name will be: {INDEX_PREFIX}{indexName || '<name>'}
            </p>
          </div>

          {/* Timestamp Field */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
              Timestamp Field
            </label>
            <select
              value={timestampField || ''}
              onChange={(e) => setTimestampField(e.target.value || null)}
              className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md focus:ring-indigo-500 focus:border-indigo-500"
              disabled={isIngesting}
            >
              <option value="">None</option>
              {timestampCandidates.map((field) => (
                <option key={field.originalName} value={field.originalName}>
                  {field.mappedName}
                </option>
              ))}
            </select>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {timestampCandidates.length > 0
                ? 'Selected field will be parsed and mapped to @timestamp'
                : 'No timestamp-like fields detected'}
            </p>
          </div>
        </div>
      </div>

      {/* Field Mapping */}
      <div className={`bg-white dark:bg-gray-800 shadow rounded-lg p-6 ${isIngesting ? 'opacity-50 pointer-events-none' : ''}`}>
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
          Field Mapping ({activeFields.length} of {fieldMappings.length} fields)
        </h3>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Original Field
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Target Field
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Exclude
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {fieldMappings.map((field, index) => {
                const fieldInfo = data.fields.find(
                  (f) => f.name === field.originalName
                ) as FieldInfo;
                return (
                  <tr
                    key={field.originalName}
                    className={field.excluded ? 'bg-gray-50 dark:bg-gray-700 opacity-50' : ''}
                  >
                    <td className="px-4 py-2 text-sm font-medium text-gray-900 dark:text-white">
                      {field.originalName}
                    </td>
                    <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                      <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs">
                        {fieldInfo?.type || 'string'}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <input
                        type="text"
                        value={field.mappedName}
                        onChange={(e) => handleFieldNameChange(index, e.target.value)}
                        disabled={field.excluded || isIngesting}
                        className="block w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 dark:disabled:bg-gray-600"
                      />
                    </td>
                    <td className="px-4 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={field.excluded}
                        onChange={() => handleExcludeToggle(index)}
                        disabled={isIngesting}
                        className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 dark:border-gray-600 rounded"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-4">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between">
        <button
          onClick={onBack}
          disabled={isIngesting}
          className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
        >
          Back to Preview
        </button>
        <button
          onClick={handleIngest}
          disabled={isIngesting || !indexName.trim()}
          className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
        >
          {isIngesting ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Ingesting...
            </>
          ) : (
            'Start Ingestion'
          )}
        </button>
      </div>

      {/* Cancel Confirmation Dialog */}
      {showCancelDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
              Cancel Ingestion?
            </h3>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              Are you sure you want to cancel the current ingestion?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowCancelDialog(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Continue Ingesting
              </button>
              <button
                onClick={() => {
                  setShowCancelDialog(false);
                  if (progress && progress.success > 0) {
                    setShowDeleteDialog(true);
                  } else {
                    handleCancel(false);
                  }
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
              >
                Cancel Ingestion
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Index Dialog */}
      {showDeleteDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
              Delete Indexed Records?
            </h3>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              {progress?.success.toLocaleString()} records have already been indexed. Would you like to keep or delete them?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDeleteDialog(false);
                  handleCancel(false);
                }}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Keep Records
              </button>
              <button
                onClick={() => {
                  setShowDeleteDialog(false);
                  handleCancel(true);
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
              >
                Delete Index
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
