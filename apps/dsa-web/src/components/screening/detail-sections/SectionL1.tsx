import type React from 'react';
import { Shield } from 'lucide-react';
import { Card, Badge } from '../../common';
import type { ScreeningCandidateDetail } from '../../../types/screening';
import { LabeledBadge, MARKET_REGIME_LABELS, MARKET_REGIME_COLORS } from './shared';

export const SectionL1: React.FC<{ candidate: ScreeningCandidateDetail }> = ({ candidate }) => {
  if (!candidate.marketRegime) return null;
  return (
    <Card variant="default" padding="sm" className="border-cyan/20 bg-cyan/3">
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-cyan">
        <Shield className="h-3.5 w-3.5" /> L1 大盘环境
      </h4>
      <div className="flex items-center gap-2">
        <LabeledBadge value={candidate.marketRegime} labelMap={MARKET_REGIME_LABELS} colorMap={MARKET_REGIME_COLORS} />
        {candidate.riskLevel && (
          <Badge variant={candidate.riskLevel === 'low' ? 'success' : candidate.riskLevel === 'high' ? 'danger' : 'warning'} size="sm">
            风险: {candidate.riskLevel === 'low' ? '低' : candidate.riskLevel === 'high' ? '高' : '中'}
          </Badge>
        )}
      </div>
      {candidate.marketMessage && (
        <p className="mt-2 text-xs leading-relaxed text-secondary-text">{candidate.marketMessage}</p>
      )}
    </Card>
  );
};
