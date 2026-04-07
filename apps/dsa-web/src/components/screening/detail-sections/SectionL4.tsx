import type React from 'react';
import { Target } from 'lucide-react';
import { Card } from '../../common';
import type {
  ScreeningCandidateDetail,
  ScreeningFactorSnapshot,
  ScreeningPhaseResults,
  ScreeningPhaseExplanation,
} from '../../../types/screening';
import {
  SETUP_TYPE_LABELS,
  ENTRY_MATURITY_LABELS,
} from '../../../types/screening';
import { extractTechnicalPatterns, TechnicalPatternCards } from '../TechnicalPatternCards';

const PHASE_DEFINITIONS = [
  { key: 'phase1_market_and_theme', label: '阶段1: 市场与题材' },
  { key: 'phase2_leader_screen', label: '阶段2: 龙头筛选' },
  { key: 'phase3_core_signal', label: '阶段3: 核心信号' },
  { key: 'phase4_entry_readiness', label: '阶段4: 入场准备' },
  { key: 'phase5_risk_controls', label: '阶段5: 风险控制' },
] as const satisfies ReadonlyArray<{
  key: keyof ScreeningPhaseResults;
  label: string;
}>;

const EMPTY_VALUE = '--';

function getPhaseDescription(label: string, isHit: boolean, snapshot: ScreeningFactorSnapshot): string {
  if (!isHit) return '未命中';
  if (label === '阶段1: 市场与题材') return '已确认热点题材匹配';
  if (label === '阶段2: 龙头筛选') return `龙头评分: ${snapshot.leader_score ?? EMPTY_VALUE}`;
  if (label === '阶段3: 核心信号') return snapshot.core_signal ?? '已命中强势信号';
  if (label === '阶段4: 入场准备') return snapshot.entry_reason ?? '已形成入场方案';
  return `止损: ${snapshot.risk_params?.stop_loss?.toFixed(2) ?? EMPTY_VALUE} | 仓位: ${snapshot.risk_params?.position_size ?? EMPTY_VALUE}`;
}

export const SectionL4: React.FC<{
  candidate: ScreeningCandidateDetail;
  factorSnapshot: ScreeningFactorSnapshot;
  technicalPatterns: ReturnType<typeof extractTechnicalPatterns>;
  phaseResults?: ScreeningPhaseResults;
  phaseExplanations?: ScreeningPhaseExplanation[];
}> = ({ candidate, factorSnapshot, technicalPatterns, phaseResults, phaseExplanations }) => {
  const hasSetup = candidate.setupType && candidate.setupType !== 'none';
  const hasPatterns = technicalPatterns.length > 0;
  const hasPhases = phaseResults != null;

  if (!hasSetup && !hasPatterns && !hasPhases) return null;

  return (
    <Card variant="default" padding="sm" className="border-orange/20 bg-orange/3">
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-orange">
        <Target className="h-3.5 w-3.5" /> L4 入场信号
      </h4>
      <div className="space-y-2">
        {hasSetup && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-secondary-text">买点:</span>
            <span className="inline-flex rounded border border-border/40 bg-elevated/40 px-1.5 py-0.5 text-[10px] font-medium text-foreground">
              {SETUP_TYPE_LABELS[candidate.setupType!] ?? candidate.setupType}
            </span>
            {candidate.entryMaturity && (
              <>
                <span className="text-xs text-secondary-text">成熟度:</span>
                <span className="text-xs font-medium text-foreground">
                  {ENTRY_MATURITY_LABELS[candidate.entryMaturity] ?? candidate.entryMaturity}
                </span>
              </>
            )}
          </div>
        )}

        {hasPhases && (
          <div className="space-y-1 text-xs">
            {PHASE_DEFINITIONS.map((phase) => {
              const backendExplanation = phaseExplanations?.find((item) => item.phase_key === phase.key);
              const isHit = backendExplanation?.hit ?? Boolean(phaseResults?.[phase.key]);
              return (
                <div key={phase.label} className="flex items-center justify-between gap-4">
                  <span className="text-secondary-text">{backendExplanation?.label ?? phase.label}</span>
                  <span className="text-right font-mono text-foreground">
                    {backendExplanation?.summary ?? getPhaseDescription(phase.label, isHit, factorSnapshot)}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {hasPatterns && (
          <div className="mt-1">
            <TechnicalPatternCards patterns={technicalPatterns} />
          </div>
        )}
      </div>
    </Card>
  );
};
