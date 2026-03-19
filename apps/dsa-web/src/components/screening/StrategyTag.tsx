import type React from 'react';
import { cn } from '../../utils/cn';
import { CATEGORY_LABELS, CATEGORY_COLORS } from '../../types/screening';

interface StrategyTagProps {
  name: string;
  category: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

export const StrategyTag: React.FC<StrategyTagProps> = ({
  name,
  category,
  active = false,
  disabled = false,
  onClick,
}) => {
  const label = CATEGORY_LABELS[category] || category;
  const color = CATEGORY_COLORS[category] || 'bg-gray-500/20 text-gray-400 border-gray-500/30';

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      data-testid={`strategy-tag-${name}`}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
        active ? color : 'border-border/40 bg-elevated/30 text-secondary-text',
        active && 'ring-1 ring-current/20',
        disabled && 'cursor-not-allowed opacity-40',
        !disabled && !active && 'cursor-pointer hover:border-border/70 hover:text-foreground',
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', active ? 'bg-current' : 'bg-secondary-text/40')} />
      {name}
      <span className="text-[10px] opacity-70">({label})</span>
    </button>
  );
};
