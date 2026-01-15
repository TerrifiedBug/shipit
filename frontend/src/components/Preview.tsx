import { FieldInfo, UploadResponse } from '../api/client';

interface PreviewProps {
  data: UploadResponse;
  onBack: () => void;
  onContinue: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatFileFormat(format: string): string {
  switch (format) {
    case 'json_array':
      return 'JSON Array';
    case 'ndjson':
      return 'NDJSON';
    case 'csv':
      return 'CSV';
    default:
      return format;
  }
}

function getTypeColor(type: string): string {
  switch (type) {
    case 'integer':
    case 'float':
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
    case 'boolean':
      return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
    case 'object':
    case 'array':
      return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200';
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200';
  }
}

function FieldBadge({ field }: { field: FieldInfo }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-medium text-gray-900 dark:text-white">{field.name}</span>
      <span className={`px-2 py-0.5 text-xs rounded ${getTypeColor(field.type)}`}>
        {field.type}
      </span>
    </div>
  );
}

export function Preview({ data, onBack, onContinue }: PreviewProps) {
  const { filename, file_size, file_format, preview, fields } = data;

  return (
    <div className="space-y-6">
      {/* File info header */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{filename}</h2>
            <div className="mt-1 flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
              <span>{formatFileSize(file_size)}</span>
              <span className="px-2 py-0.5 bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200 rounded">
                {formatFileFormat(file_format)}
              </span>
              <span>{preview.length} records previewed</span>
            </div>
          </div>
          <button
            onClick={onBack}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            Upload Different File
          </button>
        </div>
      </div>

      {/* Detected fields */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">Detected Fields ({fields.length})</h3>
        <div className="flex flex-wrap gap-3">
          {fields.map((field) => (
            <FieldBadge key={field.name} field={field} />
          ))}
        </div>
      </div>

      {/* Data table */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                {fields.map((field) => (
                  <th
                    key={field.name}
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap"
                  >
                    {field.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {preview.map((row, rowIndex) => (
                <tr key={rowIndex} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  {fields.map((field) => (
                    <td
                      key={field.name}
                      className="px-4 py-2 text-sm text-gray-900 dark:text-white whitespace-nowrap max-w-xs truncate"
                      title={String(row[field.name] ?? '')}
                    >
                      {formatCellValue(row[field.name])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex justify-end">
        <button
          onClick={onContinue}
          className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700"
        >
          Continue to Configure
        </button>
      </div>
    </div>
  );
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}
