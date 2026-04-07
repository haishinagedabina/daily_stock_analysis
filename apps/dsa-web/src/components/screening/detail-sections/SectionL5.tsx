import type React from 'react';
import { TrendingUp } from 'lucide-react';
import { Card } from '../../common';
import type { ScreeningCandidateDetail } from '../../../types/screening';
import {
  TRADE_STAGE_LABELS,
  TRADE_STAGE_COLORS,
} from '../../../types/screening';
import { LabeledBadge, InfoRow } from './shared';

export const SectionL5: React.FC<{ candidate: ScreeningCandidateDetail }> = ({ candidate }) => {
  if (!candidate.tradeStage) return null;

  const tradePlan = candidate.tradePlan;
  const isExecutable = candidate.tradeStage === 'probe_entry' || candidate.tradeStage === 'add_on_strength';

  return (
    <Card variant="default" padding="sm" className="border-green-500/20 bg-green-500/3">
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-green-400">
        <TrendingUp className="h-3.5 w-3.5" /> L5 交易阶段
      </h4>
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <LabeledBadge value={candidate.tradeStage} labelMap={TRADE_STAGE_LABELS} colorMap={TRADE_STAGE_COLORS} />
        </div>

        {isExecutable && tradePlan && (
          <div className="space-y-1.5 rounded-lg border border-green-500/20 bg-green-500/5 px-3 py-2 text-xs">
            {tradePlan.initialPosition && (
              <InfoRow label="初始仓位">{tradePlan.initialPosition}</InfoRow>
            )}
            {tradePlan.stopLossRule && (
              <InfoRow label="止损规则">
                <span className="text-danger">{tradePlan.stopLossRule}</span>
              </InfoRow>
            )}
            {tradePlan.addRule && (
              <InfoRow label="加仓规则">{tradePlan.addRule}</InfoRow>
            )}
            {tradePlan.takeProfitPlan && (
              <InfoRow label="止盈计划">{tradePlan.takeProfitPlan}</InfoRow>
            )}
            {tradePlan.invalidationRule && (
              <InfoRow label="失效条件">
                <span className="text-warning">{tradePlan.invalidationRule}</span>
              </InfoRow>
            )}
            {tradePlan.holdingExpectation && (
              <InfoRow label="持仓期望">{tradePlan.holdingExpectation}</InfoRow>
            )}
          </div>
        )}
      </div>
    </Card>
  );
};
