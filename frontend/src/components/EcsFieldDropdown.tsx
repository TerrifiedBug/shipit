import { useState, useRef, useEffect, useMemo } from 'react';

interface EcsFieldOption {
  value: string;
  type: string;
}

interface EcsFieldDropdownProps {
  value: string;
  options: EcsFieldOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

// Group ECS fields by their top-level category
function groupByCategory(options: EcsFieldOption[]): Map<string, EcsFieldOption[]> {
  const groups = new Map<string, EcsFieldOption[]>();

  for (const opt of options) {
    const category = opt.value.includes('.')
      ? opt.value.split('.')[0]
      : 'other';

    if (!groups.has(category)) {
      groups.set(category, []);
    }
    groups.get(category)!.push(opt);
  }

  // Sort categories alphabetically, but put common ones first
  const priorityOrder = ['source', 'destination', 'host', 'user', 'event', 'network', 'http', 'url', 'file', 'process', 'log'];
  const sortedGroups = new Map<string, EcsFieldOption[]>();

  // Add priority categories first
  for (const cat of priorityOrder) {
    if (groups.has(cat)) {
      sortedGroups.set(cat, groups.get(cat)!);
      groups.delete(cat);
    }
  }

  // Add remaining categories alphabetically
  const remaining = Array.from(groups.keys()).sort();
  for (const cat of remaining) {
    sortedGroups.set(cat, groups.get(cat)!);
  }

  return sortedGroups;
}

export function EcsFieldDropdown({
  value,
  options,
  onChange,
  disabled = false,
  placeholder = "Select or type ECS field..."
}: EcsFieldDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setSearch('');
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Filter options based on search
  const filteredOptions = useMemo(() => {
    if (!search.trim()) return options;
    const searchLower = search.toLowerCase();
    return options.filter(opt =>
      opt.value.toLowerCase().includes(searchLower) ||
      opt.type.toLowerCase().includes(searchLower)
    );
  }, [options, search]);

  // Group filtered options
  const groupedOptions = useMemo(() => {
    return groupByCategory(filteredOptions);
  }, [filteredOptions]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setSearch(newValue);
    onChange(newValue);
    if (!isOpen) setIsOpen(true);
  };

  const handleSelect = (fieldValue: string) => {
    onChange(fieldValue);
    setSearch('');
    setIsOpen(false);
  };

  const handleInputFocus = () => {
    if (!disabled) {
      setIsOpen(true);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsOpen(false);
      setSearch('');
    } else if (e.key === 'Enter' && filteredOptions.length === 1) {
      handleSelect(filteredOptions[0].value);
      e.preventDefault();
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={isOpen ? search || value : value}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          className="block w-full px-2 py-1 pr-8 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 dark:disabled:bg-gray-600"
        />
        <button
          type="button"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled}
          className="absolute inset-y-0 right-0 flex items-center px-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-50"
        >
          <svg className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {isOpen && !disabled && (
        <div
          ref={listRef}
          className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-lg max-h-60 overflow-auto"
        >
          {filteredOptions.length === 0 ? (
            <div className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
              No matching fields
            </div>
          ) : (
            Array.from(groupedOptions.entries()).map(([category, categoryOptions]) => (
              <div key={category}>
                <div className="px-3 py-1 text-xs font-semibold text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-700 sticky top-0">
                  {category}.*
                </div>
                {categoryOptions.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => handleSelect(opt.value)}
                    className={`w-full px-3 py-1.5 text-left text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/30 flex justify-between items-center ${
                      opt.value === value ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-900 dark:text-indigo-100' : 'text-gray-900 dark:text-white'
                    }`}
                  >
                    <span className="truncate">{opt.value}</span>
                    <span className="ml-2 text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
                      {opt.type}
                    </span>
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
