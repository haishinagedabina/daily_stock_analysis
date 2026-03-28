import type React from 'react';
import { Brain, BarChart3, FileText, Flame } from 'lucide-react';

import { Badge, Card, Drawer } from '../common';
import { useScreeningStore } from '../../stores/screeningStore';
import type {
  HotThemeNewsItem,
  ScreeningFactorSnapshot,
  ScreeningPhaseExplanation,
  ScreeningPhaseResults,
} from '../../types/screening';

function FactorRow({ label, value }: { label: string; value: unknown }) {
  const display = value == null ? '—' : typeof value === 'number' ? value.toFixed(2) : String(value);

  return (
    <div className="flex items-center justify-between border-b border-border/20 py-1.5 text-xs">
      <span className="text-secondary-text">{label}</span>
      <span className="font-mono text-foreground">{display}</span>
    </div>
  );
}

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

function getPhaseState(phaseResults: ScreeningPhaseResults | undefined, phaseKey: keyof ScreeningPhaseResults) {
  return Boolean(phaseResults?.[phaseKey]);
}

function getPhaseExplanation(
  phaseExplanations: ScreeningPhaseExplanation[] | undefined,
  phaseKey: keyof ScreeningPhaseResults,
): ScreeningPhaseExplanation | undefined {
  return phaseExplanations?.find((item) => item.phase_key === phaseKey);
}

function getPhaseDescription(label: string, isHit: boolean, snapshot: ScreeningFactorSnapshot): string {
  if (!isHit) {
    return '未命中';
  }
  if (label === '阶段1: 市场与题材') {
    return '已确认热点题材匹配';
  }
  if (label === '阶段2: 龙头筛选') {
    return `龙头评分: ${snapshot.leader_score ?? '—'}`;
  }
  if (label === '阶段3: 核心信号') {
    return snapshot.core_signal ?? '已命中强势信号';
  }
  if (label === '阶段4: 入场准备') {
    return snapshot.entry_reason ?? '已形成入场方案';
  }
  return `止损: ${snapshot.risk_params?.stop_loss?.toFixed(2) ?? '—'} | 仓位: ${snapshot.risk_params?.position_size ?? '—'}`;
}

export const CandidateDetailDrawer: React.FC = () => {
  const { selectedCandidate, clearSelectedCandidate } = useScreeningStore();
  const isOpen = selectedCandidate != null;
  const factorSnapshot = (selectedCandidate?.factorSnapshot ?? {}) as ScreeningFactorSnapshot;
  const phaseResults = factorSnapshot.phase_results;
  const phaseExplanations = Array.isArray(factorSnapshot.phase_explanations)
    ? (factorSnapshot.phase_explanations as ScreeningPhaseExplanation[])
    : undefined;
  const catalystNews = Array.isArray(factorSnapshot.theme_catalyst_news)
    ? (factorSnapshot.theme_catalyst_news as HotThemeNewsItem[])
    : [];

  return (
    <Drawer
      isOpen={isOpen}
      onClose={clearSelectedCandidate}
      title={selectedCandidate ? `${selectedCandidate.code} ${selectedCandidate.name || ''}` : ''}
    >
      {selectedCandidate && (
        <div className="flex flex-col gap-5" data-testid="candidate-detail">
          <div className="flex flex-wrap gap-2">
            <Badge variant="info" size="md">排名 #{selectedCandidate.rank}</Badge>
            <Badge variant={selectedCandidate.ruleScore >= 70 ? 'success' : 'default'} size="md">
              规则评分: {selectedCandidate.ruleScore.toFixed(1)}
            </Badge>
            {selectedCandidate.finalScore != null && (
              <Badge variant="history" size="md">
                综合评分: {selectedCandidate.finalScore.toFixed(1)}
              </Badge>
            )}
            {selectedCandidate.selectedForAi && (
              <Badge variant="info" size="md" glow>
                <Brain className="h-3 w-3" /> AI 已分析
              </Badge>
            )}
          </div>

          {factorSnapshot.is_hot_theme_stock && (
            <Card variant="default" padding="sm" className="border-orange/30 bg-orange/5">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-orange">
                <Flame className="h-3.5 w-3.5" /> 热点题材
              </h4>
              <div className="space-y-1.5 text-xs">
                {factorSnapshot.primary_theme && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">主题材</span>
                    <span className="font-mono text-foreground">{factorSnapshot.primary_theme}</span>
                  </div>
                )}
                {factorSnapshot.theme_heat_score != null && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">题材热度</span>
                    <span className="font-mono text-foreground">{factorSnapshot.theme_heat_score.toFixed(1)}</span>
                  </div>
                )}
                {factorSnapshot.theme_match_score != null && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">题材匹配度</span>
                    <span className="font-mono text-foreground">{(factorSnapshot.theme_match_score * 100).toFixed(0)}%</span>
                  </div>
                )}
                {factorSnapshot.leader_score != null && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">龙头特征分</span>
                    <span className="font-mono text-foreground">{factorSnapshot.leader_score.toFixed(0)}</span>
                  </div>
                )}
                {factorSnapshot.extreme_strength_score != null && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">极端强势分</span>
                    <span className="font-mono text-foreground">{factorSnapshot.extreme_strength_score.toFixed(1)}</span>
                  </div>
                )}
                {factorSnapshot.entry_reason && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">龙头选出原因</span>
                    <span className="font-mono text-foreground">{factorSnapshot.entry_reason}</span>
                  </div>
                )}
                {factorSnapshot.core_signal && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">核心技术信号</span>
                    <span className="font-mono text-foreground">{factorSnapshot.core_signal}</span>
                  </div>
                )}
                {factorSnapshot.theme_catalyst_summary && (
                  <div className="mt-2 space-y-1">
                    <div className="text-xs font-semibold text-orange">催化摘要</div>
                    <div className="rounded-lg border border-orange/20 bg-orange/5 px-2 py-1.5 text-xs text-orange">
                      {factorSnapshot.theme_catalyst_summary}
                    </div>
                  </div>
                )}
                {catalystNews.length > 0 && (
                  <div className="mt-2 space-y-1.5">
                    <div className="text-xs font-semibold text-orange">热点新闻</div>
                    {catalystNews.map((news, idx) => (
                      <div key={`${news.title}-${idx}`} className="rounded border border-orange/10 bg-orange/3 p-1.5 text-xs">
                        <div className="font-mono text-foreground">{news.title}</div>
                        {news.summary && <div className="mt-1 text-secondary-text">{news.summary}</div>}
                        <div className="mt-0.5 flex items-center justify-between text-secondary-text">
                          <span>{news.source}</span>
                          {news.url && (
                            <a
                              href={news.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-orange hover:underline"
                            >
                              查看
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          )}

          {phaseResults && (
            <Card variant="default" padding="sm" className="border-cyan/30 bg-cyan/5">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-cyan">
                <Brain className="h-3.5 w-3.5" /> 策略命中说明
              </h4>
              <div className="space-y-1 text-xs">
                {PHASE_DEFINITIONS.map((phase) => {
                  const backendExplanation = getPhaseExplanation(phaseExplanations, phase.key);
                  const isHit = backendExplanation?.hit ?? getPhaseState(phaseResults, phase.key);
                  return (
                    <div key={phase.label} className="flex items-center justify-between">
                      <span className="text-secondary-text">{backendExplanation?.label ?? phase.label}</span>
                      <span className="font-mono text-foreground">
                        {backendExplanation?.summary ?? getPhaseDescription(phase.label, isHit, factorSnapshot)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          {factorSnapshot.entry_reason && (
            <Card variant="default" padding="sm" className="border-green/30 bg-green/5">
              <h4 className="mb-2 text-xs font-semibold text-green">入场方案</h4>
              <div className="text-xs text-secondary-text">
                <div className="mb-1.5">{factorSnapshot.entry_reason}</div>
                {factorSnapshot.entry_reason.includes('涨停') && (
                  <div className="rounded border border-green/20 bg-green/3 px-2 py-1">当日追涨买入，错过不追高</div>
                )}
                {factorSnapshot.entry_reason.includes('MA100') && (
                  <div className="rounded border border-green/20 bg-green/3 px-2 py-1">切换 60 分钟 K 线，确认支撑后再入场</div>
                )}
              </div>
            </Card>
          )}

          {selectedCandidate.ruleHits.length > 0 && (
            <Card variant="default" padding="sm">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <FileText className="h-3.5 w-3.5 text-cyan" /> 命中规则
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {selectedCandidate.ruleHits.map((ruleHit) => (
                  <Badge key={ruleHit} variant="default" size="sm">{ruleHit}</Badge>
                ))}
              </div>
            </Card>
          )}

          {Array.isArray(factorSnapshot.extreme_strength_reasons) && factorSnapshot.extreme_strength_reasons.length > 0 && (
            <Card variant="default" padding="sm">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Flame className="h-3.5 w-3.5 text-orange" /> 命中原因
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {factorSnapshot.extreme_strength_reasons.map((reason) => (
                  <Badge key={reason} variant="default" size="sm">{reason}</Badge>
                ))}
              </div>
            </Card>
          )}

          <Card variant="default" padding="sm">
            <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <BarChart3 className="h-3.5 w-3.5 text-cyan" /> 因子快照
            </h4>
            <div className="max-h-60 overflow-y-auto">
              {Object.entries(factorSnapshot).map(([key, value]) => (
                <FactorRow key={key} label={key} value={value} />
              ))}
            </div>
          </Card>

          {selectedCandidate.aiSummary && (
            <Card variant="default" padding="sm">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Brain className="h-3.5 w-3.5 text-purple" /> AI 分析
              </h4>
              <p className="text-xs leading-relaxed text-secondary-text">
                {selectedCandidate.aiSummary}
              </p>
              {selectedCandidate.aiOperationAdvice && (
                <div className="mt-2 rounded-lg border border-cyan/20 bg-cyan/5 px-3 py-2 text-xs text-cyan">
                  {selectedCandidate.aiOperationAdvice}
                </div>
              )}
            </Card>
          )}

          {selectedCandidate.matchedStrategies && selectedCandidate.matchedStrategies.length > 0 && (
            <Card variant="default" padding="sm">
              <h4 className="mb-2 text-xs font-semibold text-foreground">匹配策略</h4>
              <div className="flex flex-wrap gap-1.5">
                {selectedCandidate.matchedStrategies.map((strategy) => (
                  <Badge key={strategy} variant="info" size="sm">{strategy}</Badge>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </Drawer>
  );
};
