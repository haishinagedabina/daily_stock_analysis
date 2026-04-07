import type React from 'react';
import { MarketEnvironmentCard } from './MarketEnvironmentCard';
import { SectorHeatPanel } from './SectorHeatPanel';
import { ScreeningSummaryCard } from './ScreeningSummaryCard';
import type { DecisionContext, ScreeningCandidate } from '../../types/screening';

interface DecisionContextSectionProps {
  context?: DecisionContext;
  candidates: ScreeningCandidate[];
}

export const DecisionContextSection: React.FC<DecisionContextSectionProps> = ({
  context,
  candidates,
}) => {
  if (!context && candidates.length === 0) return null;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3" data-testid="decision-context-section">
      <MarketEnvironmentCard environment={context?.marketEnvironment} />
      <SectorHeatPanel
        sectors={context?.sectorHeatResults ?? []}
        hotCount={context?.hotThemeCount ?? 0}
        warmCount={context?.warmThemeCount ?? 0}
      />
      <ScreeningSummaryCard candidates={candidates} />
    </div>
  );
};
