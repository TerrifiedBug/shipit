import { useState } from 'react';
import { Upload } from './components/Upload';
import { Preview } from './components/Preview';
import { Configure } from './components/Configure';
import { Result } from './components/Result';
import { History } from './components/History';
import { IngestResponse, UploadResponse } from './api/client';
import { useTheme } from './contexts/ThemeContext';

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

function App() {
  const [state, setState] = useState<AppState>('upload');
  const [uploadData, setUploadData] = useState<UploadResponse | null>(null);
  const [ingestResult, setIngestResult] = useState<IngestResponse | null>(null);
  const [showHistory, setShowHistory] = useState(false);

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
    setUploadData(null);
    setIngestResult(null);
    setState('upload');
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
      <header className="bg-white dark:bg-gray-800 shadow">
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">ShipIt</h1>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <button
                onClick={() => setShowHistory(true)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                History
              </button>
            </div>
          </div>
        </div>
      </header>

      {showHistory && <History onClose={() => setShowHistory(false)} />}
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
