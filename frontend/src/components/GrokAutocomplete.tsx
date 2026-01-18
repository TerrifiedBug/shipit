import { useState, useEffect, useRef } from 'react';

interface GrokPattern {
  name: string;
  regex: string;
  description: string;
}

interface GrokAutocompleteProps {
  patterns: GrokPattern[];
  filter: string;
  position: { top: number; left: number };
  onSelect: (patternName: string) => void;
  onClose: () => void;
}

export function GrokAutocomplete({
  patterns,
  filter,
  position,
  onSelect,
  onClose,
}: GrokAutocompleteProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  // Filter patterns based on input
  const filteredPatterns = patterns.filter((p) =>
    p.name.toLowerCase().startsWith(filter.toLowerCase())
  ).slice(0, 10);

  // Reset selection when filter changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [filter]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) =>
            prev < filteredPatterns.length - 1 ? prev + 1 : prev
          );
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => (prev > 0 ? prev - 1 : prev));
          break;
        case 'Enter':
        case 'Tab':
          e.preventDefault();
          if (filteredPatterns[selectedIndex]) {
            onSelect(filteredPatterns[selectedIndex].name);
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [filteredPatterns, selectedIndex, onSelect, onClose]);

  // Scroll selected item into view
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const selected = list.children[selectedIndex] as HTMLElement;
    if (selected) {
      selected.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  if (filteredPatterns.length === 0) {
    return null;
  }

  return (
    <div
      className="absolute z-50 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-lg max-h-64 overflow-y-auto"
      style={{ top: position.top, left: position.left, minWidth: '300px' }}
    >
      <div ref={listRef}>
        {filteredPatterns.map((pattern, index) => (
          <div
            key={pattern.name}
            className={`px-3 py-2 cursor-pointer ${
              index === selectedIndex
                ? 'bg-blue-100 dark:bg-blue-900'
                : 'hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
            onClick={() => onSelect(pattern.name)}
            title={pattern.regex}
          >
            <div className="font-mono text-sm font-medium text-gray-900 dark:text-white">
              {pattern.name}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
              {pattern.description}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
