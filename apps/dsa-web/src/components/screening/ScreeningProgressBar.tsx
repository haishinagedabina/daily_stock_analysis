import type React from 'react';
import { cn } from '../../utils/cn';
import { SCREENING_STAGES, STAGE_LABELS, getStageIndex, type ScreeningRunStatus } from '../../types/screening';

interface ScreeningProgressBarProps {
  status: ScreeningRunStatus;
}

export const ScreeningProgressBar: React.FC<ScreeningProgressBarProps> = ({ status }) => {
  const currentIdx = getStageIndex(status);
  const isFailed = status === 'failed';
  const total = SCREENING_STAGES.length;
  const pct = isFailed ? 100 : Math.round(((currentIdx + 1) / total) * 100);

  return (
    <div data-testid="screening-progress-bar">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className={cn('font-medium', isFailed ? 'text-danger' : 'text-cyan')}>
          {STAGE_LABELS[status] || status}
        </span>
        <span className="text-secondary-text">{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-elevated">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-700 ease-out',
            isFailed ? 'bg-danger' : 'bg-gradient-to-r from-cyan to-purple',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-2 flex justify-between">
        {SCREENING_STAGES.map((stage, i) => (
          <span
            key={stage}
            className={cn(
              'text-[10px]',
              i <= currentIdx ? (isFailed ? 'text-danger' : 'text-cyan') : 'text-secondary-text/40',
            )}
          >
            {STAGE_LABELS[stage]}
          </span>
        ))}
      </div>
    </div>
  );
};
