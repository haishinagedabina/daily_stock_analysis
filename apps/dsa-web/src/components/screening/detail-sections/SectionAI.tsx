import type React from 'react';
import { Brain } from 'lucide-react';
import { Card } from '../../common';
import type { ScreeningCandidateDetail } from '../../../types/screening';
import { LabeledBadge, TRADE_STAGE_LABELS, TRADE_STAGE_COLORS } from './shared';

function renderBoolLabel(value?: boolean): string {
  if (value == null) return '--';
  return value ? '通过' : '不通过';
}

export const SectionAI: React.FC<{ candidate: ScreeningCandidateDetail }> = ({ candidate }) => {
  const aiTradeStage = candidate.aiTradeStage ?? candidate.aiReview?.aiTradeStage;
  const aiConfidence = candidate.aiConfidence ?? candidate.aiReview?.aiConfidence;
  const aiReasoning = candidate.aiReasoning ?? candidate.aiReview?.aiReasoning;
  const aiOperationAdvice = candidate.aiOperationAdvice ?? candidate.aiReview?.aiOperationAdvice;
  const aiSummary = candidate.aiSummary ?? candidate.aiReview?.aiSummary;
  const aiEnvironmentOk = candidate.aiEnvironmentOk ?? candidate.aiReview?.aiEnvironmentOk;
  const aiThemeAlignment = candidate.aiThemeAlignment ?? candidate.aiReview?.aiThemeAlignment;
  const aiEntryQuality = candidate.aiEntryQuality ?? candidate.aiReview?.aiEntryQuality;
  const stageConflict = candidate.stageConflict ?? candidate.aiReview?.stageConflict;
  const resultSource = candidate.resultSource ?? candidate.aiReview?.resultSource;
  const fallbackReason = candidate.fallbackReason ?? candidate.aiReview?.fallbackReason;
  const downgradeReasons = candidate.downgradeReasons ?? candidate.aiReview?.downgradeReasons;
  const hasAiReview = aiTradeStage != null;
  const hasAiSummary = aiSummary != null;
  const hasStructuredAudit =
    stageConflict != null ||
    aiEnvironmentOk != null ||
    aiThemeAlignment != null ||
    aiEntryQuality != null ||
    resultSource != null;

  if (!hasAiReview && !hasAiSummary && !hasStructuredAudit) return null;

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
              <LabeledBadge value={aiTradeStage} labelMap={TRADE_STAGE_LABELS} colorMap={TRADE_STAGE_COLORS} />
              {aiConfidence != null && (
                <span className="text-xs text-secondary-text">
                  ({(aiConfidence * 100).toFixed(0)}%)
                </span>
              )}
            </div>
            {aiReasoning && (
              <p className="text-xs leading-relaxed text-secondary-text">
                {aiReasoning}
              </p>
            )}
          </div>
        )}

        {aiOperationAdvice && (
          <div className="rounded-lg border border-cyan/20 bg-cyan/5 px-3 py-2 text-xs text-cyan">
            {aiOperationAdvice}
          </div>
        )}

        {aiSummary && (
          <p className="text-xs leading-relaxed text-secondary-text">
            {aiSummary}
          </p>
        )}

        {resultSource && (
          <div className="rounded-lg border border-border/20 bg-background/40 px-3 py-2 text-xs text-secondary-text">
            <div>来源: {resultSource}</div>
            {fallbackReason && <div className="mt-1">回退原因: {fallbackReason}</div>}
            {downgradeReasons && downgradeReasons.length > 0 && (
              <div className="mt-1">降级原因: {downgradeReasons.join(', ')}</div>
            )}
          </div>
        )}

        {hasStructuredAudit && (
          <div className="grid grid-cols-1 gap-2 border-t border-border/20 pt-2 text-xs text-secondary-text sm:grid-cols-2">
            <div className="rounded-lg border border-border/20 bg-background/40 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-tertiary-text">环境审计</div>
              <div className="mt-1 text-foreground">{renderBoolLabel(aiEnvironmentOk)}</div>
            </div>
            <div className="rounded-lg border border-border/20 bg-background/40 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-tertiary-text">题材一致性</div>
              <div className="mt-1 text-foreground">{renderBoolLabel(aiThemeAlignment)}</div>
            </div>
            <div className="rounded-lg border border-border/20 bg-background/40 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-tertiary-text">入场质量</div>
              <div className="mt-1 text-foreground">{aiEntryQuality ?? '--'}</div>
            </div>
            <div className="rounded-lg border border-border/20 bg-background/40 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-tertiary-text">阶段冲突</div>
              <div className="mt-1 text-foreground">{renderBoolLabel(stageConflict)}</div>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};
