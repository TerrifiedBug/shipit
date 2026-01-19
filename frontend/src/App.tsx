import { useState, useEffect, useRef } from 'react';
import { Upload } from './components/Upload';
import { Preview } from './components/Preview';
import { Configure } from './components/Configure';
import { Result } from './components/Result';
import { History } from './components/History';
import { Login } from './components/Login';
import { ApiKeys } from './components/ApiKeys';
import { Users } from './components/Users';
import { Audit } from './components/Audit';
import { PatternLibrary } from './components/PatternLibrary';
import { PasswordChangeModal } from './components/PasswordChangeModal';
import { OpenSearchStatus } from './components/OpenSearchStatus';
import { CustomEcsMappings } from './components/CustomEcsMappings';
import { IngestResponse, UploadResponse, deletePendingUpload } from './api/client';
import { useTheme } from './contexts/ThemeContext';
import { useAuth } from './contexts/AuthContext';
import { useVersion } from './hooks/useVersion';

type AppState = 'upload' | 'preview' | 'configure' | 'result';

function ThemeToggle() {
  const { isDark, setTheme, theme } = useTheme();

  const cycleTheme = () => {
    if (theme === 'light') setTheme('dark');
    else if (theme === 'dark') setTheme('system');
    else setTheme('light');
  };

  return (
    <button
      onClick={cycleTheme}
      className="p-2 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
      title={`Theme: ${theme}`}
    >
      {theme === 'system' ? (
        <svg className="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      ) : isDark ? (
        <svg className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      ) : (
        <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      )}
    </button>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [showPasswordChange, setShowPasswordChange] = useState(false);

  if (!user) return null;

  return (
    <>
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
        >
          <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-medium">
            {user.name.charAt(0).toUpperCase()}
          </div>
          <span className="text-sm text-gray-700 dark:text-gray-200">{user.name}</span>
          <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {isOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
            <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-md shadow-lg border border-gray-200 dark:border-gray-700 z-20">
              <div className="py-1">
                <div className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  {user.email}
                </div>
                {/* Only show password change for local users, not OIDC */}
                {user.auth_type === 'local' && (
                  <button
                    onClick={() => {
                      setShowPasswordChange(true);
                      setIsOpen(false);
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    Change Password
                  </button>
                )}
                <button
                  onClick={() => {
                    logout();
                    setIsOpen(false);
                  }}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  Sign out
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {showPasswordChange && (
        <PasswordChangeModal
          onSuccess={() => setShowPasswordChange(false)}
          onCancel={() => setShowPasswordChange(false)}
        />
      )}
    </>
  );
}

function LoadingSpinner() {
  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 flex items-center justify-center">
      <svg
        className="animate-spin h-12 w-12 text-blue-600"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
    </div>
  );
}

function App() {
  const { user, loading, needsSetup, passwordChangeRequired, login, clearPasswordChangeRequired } = useAuth();
  const { currentVersion, updateAvailable, releaseUrl } = useVersion();
  const [state, setState] = useState<AppState>('upload');
  const [uploadData, setUploadData] = useState<UploadResponse | null>(null);
  const [ingestResult, setIngestResult] = useState<IngestResponse | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showApiKeys, setShowApiKeys] = useState(false);
  const [showUsers, setShowUsers] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [showPatterns, setShowPatterns] = useState(false);
  const [showCustomEcsMappings, setShowCustomEcsMappings] = useState(false);

  // Track pending upload for cleanup on tab close
  const pendingUploadRef = useRef<string | null>(null);

  // Update ref when uploadData changes (only track if not yet ingested)
  useEffect(() => {
    pendingUploadRef.current = uploadData && !ingestResult ? uploadData.upload_id : null;
  }, [uploadData, ingestResult]);

  // Clean up pending upload on tab/window close
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (pendingUploadRef.current) {
        // Use fetch with keepalive for reliable delivery on page unload
        // (sendBeacon doesn't include credentials for cross-origin requests)
        const url = `${import.meta.env.VITE_API_URL || ''}/api/upload/${pendingUploadRef.current}/abandon`;
        fetch(url, {
          method: 'POST',
          credentials: 'include',
          keepalive: true,
        });
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, []);

  // Show loading spinner while checking auth
  if (loading) {
    return <LoadingSpinner />;
  }

  // Show login if not authenticated
  if (!user) {
    return <Login isSetupMode={needsSetup} onLogin={login} />;
  }

  // Show password change modal if required
  if (passwordChangeRequired) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
        <PasswordChangeModal onSuccess={clearPasswordChangeRequired} required />
      </div>
    );
  }

  const handleUploadComplete = (data: UploadResponse) => {
    setUploadData(data);
    setState('preview');
  };

  const handleContinueToConfigure = () => {
    setState('configure');
  };

  const handleIngestComplete = (result: IngestResponse) => {
    setIngestResult(result);
    setState('result');
  };

  const handleReset = () => {
    // If abandoning before ingestion started, delete the pending upload
    if (uploadData && !ingestResult) {
      deletePendingUpload(uploadData.upload_id);
    }
    setUploadData(null);
    setIngestResult(null);
    setState('upload');
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
      <header className="bg-white dark:bg-gray-800 shadow">
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center">
            <button
              onClick={handleReset}
              className="flex items-center gap-3 hover:opacity-80 transition-opacity"
              title="Return to upload"
            >
              <span className="text-3xl" role="img" aria-label="ShipIt logo">🚀</span>
              <div className="flex items-baseline gap-2">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white">ShipIt</h1>
                <span className="text-xs text-gray-400 dark:text-gray-500">v{currentVersion}</span>
              </div>
            </button>
            {updateAvailable && releaseUrl && (
              <a
                href={releaseUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-500 hover:text-blue-600 hover:underline ml-2"
              >
                Update available
              </a>
            )}
            <div className="flex items-center gap-2">
              <OpenSearchStatus />
              <ThemeToggle />
              {user?.is_admin && (
                <>
                  <button
                    onClick={() => setShowAudit(true)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                  >
                    Audit
                  </button>
                  <button
                    onClick={() => setShowUsers(true)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                  >
                    Users
                  </button>
                </>
              )}
              {user?.role !== 'viewer' && (
                <button
                  onClick={() => setShowCustomEcsMappings(true)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  ECS Mappings
                </button>
              )}
              <button
                onClick={() => setShowPatterns(true)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Patterns
              </button>
              {user?.role !== 'viewer' && (
                <button
                  onClick={() => setShowApiKeys(true)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  API Keys
                </button>
              )}
              <button
                onClick={() => setShowHistory(true)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                History
              </button>
              <UserMenu />
            </div>
          </div>
        </div>
      </header>

      {showHistory && <History onClose={() => setShowHistory(false)} />}
      {showApiKeys && <ApiKeys onClose={() => setShowApiKeys(false)} />}
      {showUsers && <Users onClose={() => setShowUsers(false)} />}
      {showAudit && <Audit onClose={() => setShowAudit(false)} />}
      {showPatterns && <PatternLibrary onClose={() => setShowPatterns(false)} />}
      {showCustomEcsMappings && <CustomEcsMappings onClose={() => setShowCustomEcsMappings(false)} />}
      <main>
        <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
          {state === 'upload' && (
            <Upload onUploadComplete={handleUploadComplete} />
          )}
          {state === 'preview' && uploadData && (
            <Preview
              data={uploadData}
              onBack={handleReset}
              onContinue={handleContinueToConfigure}
              onDataUpdate={setUploadData}
            />
          )}
          {state === 'configure' && uploadData && (
            <Configure
              data={uploadData}
              onBack={() => setState('preview')}
              onComplete={handleIngestComplete}
              onReset={handleReset}
            />
          )}
          {state === 'result' && ingestResult && (
            <Result result={ingestResult} onNewUpload={handleReset} />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
