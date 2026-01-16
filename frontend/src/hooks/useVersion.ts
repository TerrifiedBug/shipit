import { useState, useEffect } from 'react';

const GITHUB_TAGS_URL = 'https://api.github.com/repos/TerrifiedBug/shipit/tags';
const CACHE_DURATION = 60 * 60 * 1000; // 1 hour

interface VersionCache {
  latestVersion: string | null;
  timestamp: number;
}

let cache: VersionCache | null = null;

function isUpdateAvailable(current: string, latest: string | null): boolean {
  if (!latest) return false;

  const normalize = (v: string): [number, number, number] => {
    const parts = v.replace(/^v/, '').split('.').map(Number);
    return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0];
  };

  const [cMaj, cMin, cPatch] = normalize(current);
  const [lMaj, lMin, lPatch] = normalize(latest);

  if (lMaj > cMaj) return true;
  if (lMaj < cMaj) return false;
  if (lMin > cMin) return true;
  if (lMin < cMin) return false;
  return lPatch > cPatch;
}

async function fetchLatestVersion(): Promise<string | null> {
  // Check cache first
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return cache.latestVersion;
  }

  try {
    const response = await fetch(GITHUB_TAGS_URL, {
      headers: { Accept: 'application/vnd.github+json' },
    });

    if (!response.ok) return null;

    const tags = (await response.json()) as Array<{ name: string }>;
    if (tags.length === 0) return null;

    const latestVersion = tags[0].name.replace(/^v/, '');
    cache = { latestVersion, timestamp: Date.now() };
    return latestVersion;
  } catch {
    return null;
  }
}

export function useVersion() {
  const currentVersion = import.meta.env.VITE_APP_VERSION ?? 'unknown';
  const [latestVersion, setLatestVersion] = useState<string | null>(null);

  useEffect(() => {
    fetchLatestVersion().then(setLatestVersion);
  }, []);

  const updateAvailable = isUpdateAvailable(currentVersion, latestVersion);

  return {
    currentVersion,
    latestVersion,
    updateAvailable,
    releaseUrl: latestVersion
      ? `https://github.com/TerrifiedBug/shipit/releases/tag/v${latestVersion}`
      : null,
  };
}
