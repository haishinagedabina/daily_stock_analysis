import type React from 'react';
import { Brain } from 'lucide-react';
import { Card } from '../../common';
import type { ScreeningCandidateDetail } from '../../../types/screening';
import { LabeledBadge, TRADE_STAGE_LABELS, TRADE_STAGE_COLORS } from './shared';

export const SectionAI: React.FC<{ candidate: ScreeningCandidateDetail }> = ({ candidate }) => {
  const hasAiReview = candidate.aiTradeStage != null;
  const hasAiSummary = candidate.aiSummary != null;

  if (!hasAiReview && !hasAiSummary) return null;

  return (
    <Card variant="default" padding="sm" className="border-purple/20 bg-purple/3">
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-purple">
        <Brain className="h-3.5 w-3.5" /> AI 分析
      </h4>
      <div className="space-y-2">
        {hasAiReview && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-xs text-secondary-text">AI 阶段:</span>
              <LabeledBadge value={candidate.aiTradeStage} labelMap={TRADE_STAGE_LABELS} colorMap={TRADE_STAGE_COLORS} />
              {candidate.aiConfidence != null && (
                <span className="text-xs text-secondary-text">
                  ({(candidate.aiConfidence * 100).toFixed(0)}%)
                </span>
              )}
            </div>
            {candidate.aiReasoning && (
              <p className="text-xs leading-relaxed text-secondary-text">
                {candidate.aiReasoning}
              </p>
            )}
          </div>
        )}

        {candidate.aiOperationAdvice && (
          <div className="rounded-lg border border-cyan/20 bg-cyan/5 px-3 py-2 text-xs text-cyan">
            {candidate.aiOperationAdvice}
          </div>
        )}

        {candidate.aiSummary && (
          <p className="text-xs leading-relaxed text-secondary-text">
            {candidate.aiSummary}
          </p>
        )}
      </div>
    </Card>
  );
};
