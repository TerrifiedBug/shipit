import React, { useRef, useEffect } from 'react';

const GROUP_COLORS = [
  'bg-blue-200 dark:bg-blue-800',
  'bg-green-200 dark:bg-green-800',
  'bg-yellow-200 dark:bg-yellow-700',
  'bg-purple-200 dark:bg-purple-800',
  'bg-pink-200 dark:bg-pink-800',
  'bg-orange-200 dark:bg-orange-800',
  'bg-cyan-200 dark:bg-cyan-800',
  'bg-red-200 dark:bg-red-800',
];

export interface Highlight {
  start: number;
  end: number;
  colorIndex: number;
}

interface HighlightedInputProps {
  value: string;
  onChange: (value: string) => void;
  highlights: Highlight[];
  placeholder?: string;
  className?: string;
  rows?: number;
}

export function HighlightedInput({
  value,
  onChange,
  highlights,
  placeholder,
  className = '',
  rows = 2,
}: HighlightedInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  // Sync scroll between textarea and backdrop
  useEffect(() => {
    const textarea = textareaRef.current;
    const backdrop = backdropRef.current;
    if (!textarea || !backdrop) return;

    const handleScroll = () => {
      backdrop.scrollTop = textarea.scrollTop;
      backdrop.scrollLeft = textarea.scrollLeft;
    };

    textarea.addEventListener('scroll', handleScroll);
    return () => textarea.removeEventListener('scroll', handleScroll);
  }, []);

  // Build highlighted text segments
  const renderHighlightedText = () => {
    if (!value || highlights.length === 0) {
      return <span className="whitespace-pre-wrap">{value || ' '}</span>;
    }

    // Sort highlights by start position
    const sortedHighlights = [...highlights].sort((a, b) => a.start - b.start);

    const segments: React.ReactNode[] = [];
    let lastEnd = 0;

    sortedHighlights.forEach((highlight, idx) => {
      // Add text before this highlight
      if (highlight.start > lastEnd) {
        segments.push(
          <span key={`text-${idx}`} className="whitespace-pre-wrap">
            {value.slice(lastEnd, highlight.start)}
          </span>
        );
      }

      // Add highlighted segment
      const colorClass = GROUP_COLORS[highlight.colorIndex % GROUP_COLORS.length];
      segments.push(
        <mark
          key={`highlight-${idx}`}
          className={`${colorClass} rounded px-0.5 whitespace-pre-wrap`}
        >
          {value.slice(highlight.start, highlight.end)}
        </mark>
      );

      lastEnd = highlight.end;
    });

    // Add remaining text
    if (lastEnd < value.length) {
      segments.push(
        <span key="text-end" className="whitespace-pre-wrap">
          {value.slice(lastEnd)}
        </span>
      );
    }

    return segments;
  };

  return (
    <div className="relative">
      {/* Backdrop with highlights */}
      <div
        ref={backdropRef}
        className={`absolute inset-0 pointer-events-none overflow-hidden font-mono text-sm p-3 ${className}`}
        style={{ color: 'transparent' }}
        aria-hidden="true"
      >
        {renderHighlightedText()}
      </div>

      {/* Actual textarea */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className={`relative bg-transparent font-mono text-sm p-3 w-full border border-gray-300 dark:border-gray-600 rounded-md text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none ${className}`}
        style={{ caretColor: 'auto' }}
      />
    </div>
  );
}

export { GROUP_COLORS };
