import type React from 'react';
import { Layers } from 'lucide-react';
import { Card } from '../../common';
import type { ScreeningCandidateDetail } from '../../../types/screening';
import { POOL_LEVEL_LABELS } from './shared';

const POOL_ICONS: Record<string, string> = {
  leader_pool: '\u{1f3c6}',
  focus_list: '\u{1f3af}',
  watchlist: '\u{1f4cb}',
};

export const SectionL3: React.FC<{ candidate: ScreeningCandidateDetail }> = ({ candidate }) => {
  if (!candidate.candidatePoolLevel) return null;
  const poolLabel = POOL_LEVEL_LABELS[candidate.candidatePoolLevel] ?? candidate.candidatePoolLevel;
  const poolIcon = POOL_ICONS[candidate.candidatePoolLevel] ?? '';
  return (
    <Card variant="default" padding="sm" className="border-emerald-500/20 bg-emerald-500/3">
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
        <Layers className="h-3.5 w-3.5" /> L3 候选池
      </h4>
      <div className="flex items-center gap-2 text-xs">
        <span>{poolIcon}</span>
        <span className="font-medium text-foreground">{poolLabel}</span>
      </div>
    </Card>
  );
};
