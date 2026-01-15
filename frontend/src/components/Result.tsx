import { IngestResponse } from '../api/client';

interface ResultProps {
  result: IngestResponse;
  onNewUpload: () => void;
}

export function Result({ result, onNewUpload }: ResultProps) {
  const successRate = result.processed > 0
    ? ((result.success / result.processed) * 100).toFixed(1)
    : '0';

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <div className="text-center">
          {result.failed === 0 ? (
            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 dark:bg-green-900">
              <svg className="h-6 w-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          ) : (
            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-yellow-100 dark:bg-yellow-900">
              <svg className="h-6 w-6 text-yellow-600 dark:text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
          )}

          <h3 className="mt-4 text-lg font-medium text-gray-900 dark:text-white">
            {result.failed === 0 ? 'Ingestion Complete' : 'Ingestion Complete with Errors'}
          </h3>

          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            Index: <span className="font-medium text-gray-900 dark:text-white">{result.index_name}</span>
          </p>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-4">
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 text-center">
            <p className="text-2xl font-bold text-gray-900 dark:text-white">{result.processed.toLocaleString()}</p>
            <p className="text-sm text-gray-500 dark:text-gray-400">Processed</p>
          </div>
          <div className="bg-green-50 dark:bg-green-900/30 rounded-lg p-4 text-center">
            <p className="text-2xl font-bold text-green-600 dark:text-green-400">{result.success.toLocaleString()}</p>
            <p className="text-sm text-gray-500 dark:text-gray-400">Successful</p>
          </div>
          <div className={`rounded-lg p-4 text-center ${result.failed > 0 ? 'bg-red-50 dark:bg-red-900/30' : 'bg-gray-50 dark:bg-gray-700'}`}>
            <p className={`text-2xl font-bold ${result.failed > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-400 dark:text-gray-500'}`}>
              {result.failed.toLocaleString()}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">Failed</p>
          </div>
        </div>

        <div className="mt-4 text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Success rate: <span className="font-medium">{successRate}%</span>
          </p>
        </div>
      </div>

      <div className="flex justify-center">
        <button
          onClick={onNewUpload}
          className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700"
        >
          Upload Another File
        </button>
      </div>
    </div>
  );
}
