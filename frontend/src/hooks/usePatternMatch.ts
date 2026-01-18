import { useState, useEffect, useRef } from 'react';
import { useDebounce } from './useDebounce';
import { expandGrokPattern } from '../api/client';

export interface MatchGroup {
  name: string;
  value: string;
  start: number;
  end: number;
}

export interface MatchResult {
  fullMatch: { start: number; end: number };
  groups: MatchGroup[];
}

export interface PatternMatchState {
  result: MatchResult | null;
  error: string | null;
  loading: boolean;
}

function matchWithRegex(regexStr: string, text: string): MatchResult | null {
  try {
    // Convert Python named groups (?P<name>...) to JS (?<name>...)
    const jsRegex = regexStr.replace(/\(\?P<(\w+)>/g, '(?<$1>');
    const regex = new RegExp(jsRegex);
    const match = regex.exec(text);

    if (!match) return null;

    const groups: MatchGroup[] = [];
    if (match.groups) {
      for (const [name, value] of Object.entries(match.groups)) {
        if (value !== undefined) {
          // Find position of this group's value in the matched string
          const start = text.indexOf(value, match.index);
          groups.push({
            name,
            value,
            start,
            end: start + value.length,
          });
        }
      }
    }

    return {
      fullMatch: { start: match.index, end: match.index + match[0].length },
      groups,
    };
  } catch {
    return null;
  }
}

export function usePatternMatch(
  pattern: string,
  testSample: string,
  type: 'regex' | 'grok'
): PatternMatchState {
  const [state, setState] = useState<PatternMatchState>({
    result: null,
    error: null,
    loading: false,
  });

  const debouncedPattern = useDebounce(pattern, 300);
  const debouncedSample = useDebounce(testSample, 300);

  // Cache expanded grok patterns
  const grokCache = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    if (!debouncedPattern || !debouncedSample) {
      setState({ result: null, error: null, loading: false });
      return;
    }

    setState(prev => ({ ...prev, loading: true }));

    const doMatch = async () => {
      try {
        let regexStr: string;

        if (type === 'grok') {
          // Check cache first
          if (grokCache.current.has(debouncedPattern)) {
            regexStr = grokCache.current.get(debouncedPattern)!;
          } else {
            const expanded = await expandGrokPattern(debouncedPattern);
            if (!expanded.valid || !expanded.expanded) {
              setState({ result: null, error: expanded.error || 'Invalid grok pattern', loading: false });
              return;
            }
            regexStr = expanded.expanded;
            grokCache.current.set(debouncedPattern, regexStr);
          }
        } else {
          regexStr = debouncedPattern;
        }

        const result = matchWithRegex(regexStr, debouncedSample);
        if (result) {
          setState({ result, error: null, loading: false });
        } else {
          setState({ result: null, error: null, loading: false }); // No match, but not an error
        }
      } catch (err) {
        setState({
          result: null,
          error: err instanceof Error ? err.message : 'Match failed',
          loading: false
        });
      }
    };

    doMatch();
  }, [debouncedPattern, debouncedSample, type]);

  return state;
}
