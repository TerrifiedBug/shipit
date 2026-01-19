import { useState, useEffect, useCallback } from 'react';

interface HealthResponse {
  status: string;
  opensearch: {
    connected: boolean;
    cluster_name: string | null;
    version: string | null;
  };
}

export function OpenSearchStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [checking, setChecking] = useState(true);
  const [showDetails, setShowDetails] = useState(false);

  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch('/api/health');
      if (response.ok) {
        const data = await response.json();
        setHealth(data);
      } else {
        setHealth(null);
      }
    } catch {
      setHealth(null);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();

    // Re-check every 30 seconds
    const interval = setInterval(checkHealth, 30000);

    // Re-check when tab becomes visible
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        checkHealth();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [checkHealth]);

  const connected = health?.opensearch?.connected ?? false;

  return (
    <div className="relative">
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="flex items-center gap-2 px-2 py-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-sm"
        title={connected ? 'OpenSearch connected' : 'OpenSearch disconnected'}
      >
        <span className={`w-2 h-2 rounded-full ${
          checking ? 'bg-yellow-500' :
          connected ? 'bg-green-500' : 'bg-red-500'
        }`} />
        <span className="text-gray-600 dark:text-gray-300">OpenSearch</span>
      </button>

      {showDetails && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setShowDetails(false)} />
          <div className="absolute right-0 top-full mt-1 w-64 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3 z-20">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Status:</span>
                <span className={connected ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                  {connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
              {connected && health?.opensearch && (
                <>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Cluster:</span>
                    <span className="text-gray-900 dark:text-white">{health.opensearch.cluster_name || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Version:</span>
                    <span className="text-gray-900 dark:text-white">{health.opensearch.version || 'N/A'}</span>
                  </div>
                </>
              )}
              <button
                onClick={() => { setChecking(true); checkHealth(); }}
                className="w-full mt-2 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 text-xs"
              >
                Refresh
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
