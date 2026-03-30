import type React from 'react';
import { BarChart3, Brain, FileText, Flame } from 'lucide-react';

import { Badge, Card, Drawer } from '../common';
import { useScreeningStore } from '../../stores/screeningStore';
import { extractTechnicalPatterns, TechnicalPatternCards } from './TechnicalPatternCards';
import type {
  HotThemeNewsItem,
  ScreeningFactorSnapshot,
  ScreeningPhaseExplanation,
  ScreeningPhaseResults,
} from '../../types/screening';

const EMPTY_VALUE = '—';

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

const RULE_HIT_LABELS: Record<string, string> = {
  is_hot_theme_stock: '热点题材股',
  above_ma100: '站上 MA100',
  pattern_123_low_trendline: '低位 123 趋势线突破',
  gap_breakaway: '跳空突破',
  is_limit_up: '涨停',
  bottom_divergence_double_breakout: '底背离双突破',
  strategy: '极端强势组合',
};

const TECHNICAL_RULE_KEYS = new Set([
  'above_ma100',
  'pattern_123_low_trendline',
  'gap_breakaway',
  'is_limit_up',
  'bottom_divergence_double_breakout',
]);

function formatPrimitiveValue(value: unknown): string {
  if (value == null) return EMPTY_VALUE;
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
}

function formatStructuredValue(value: unknown): string {
  if (value == null || typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') {
    return formatPrimitiveValue(value);
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';
    return value.map((item) => formatStructuredValue(item)).join('\n');
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return '{}';

    return entries
      .map(([key, entryValue]) => {
        const formattedEntry =
          entryValue != null && typeof entryValue === 'object'
            ? formatStructuredValue(entryValue)
            : formatPrimitiveValue(entryValue);
        return `${key}: ${formattedEntry}`;
      })
      .join('\n');
  }

  return String(value);
}

function parseRuleHit(ruleHit: string): { key: string; value?: string } {
  if (ruleHit.includes(':==:')) {
    const [key, value] = ruleHit.split(':==:');
    return { key, value };
  }

  if (ruleHit.includes(':')) {
    const [key, ...rest] = ruleHit.split(':');
    return { key, value: rest.join(':') };
  }

  return { key: ruleHit };
}

function translateRuleHit(ruleHit: string): string {
  const { key, value } = parseRuleHit(ruleHit);
  const translatedKey = RULE_HIT_LABELS[key];

  if (!translatedKey) {
    return ruleHit;
  }

  if (key === 'strategy' && value === 'extreme_strength_combo') {
    return translatedKey;
  }

  if (value == null || value === '' || value === 'True') {
    return translatedKey;
  }

  if (value === 'False') {
    return `未命中${translatedKey}`;
  }

  return `${translatedKey}: ${value}`;
}

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
    return `龙头评分: ${snapshot.leader_score ?? EMPTY_VALUE}`;
  }
  if (label === '阶段3: 核心信号') {
    return snapshot.core_signal ?? '已命中强势信号';
  }
  if (label === '阶段4: 入场准备') {
    return snapshot.entry_reason ?? '已形成入场方案';
  }
  return `止损: ${snapshot.risk_params?.stop_loss?.toFixed(2) ?? EMPTY_VALUE} | 仓位: ${snapshot.risk_params?.position_size ?? EMPTY_VALUE}`;
}

function FactorRow({ label, value }: { label: string; value: unknown }) {
  const display = formatStructuredValue(value);

  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/20 py-1.5 text-xs">
      <span className="shrink-0 text-secondary-text">{label}</span>
      <span className="whitespace-pre-wrap text-right font-mono text-foreground">{display}</span>
    </div>
  );
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
  const rawRuleHits = Array.isArray(factorSnapshot.rule_hits_display) && factorSnapshot.rule_hits_display.length > 0
    ? factorSnapshot.rule_hits_display
    : selectedCandidate?.ruleHits ?? [];
  const translatedRuleHits = rawRuleHits.map((ruleHit) => {
    const parsed = parseRuleHit(ruleHit);
    return {
      key: parsed.key,
      translated: translateRuleHit(ruleHit),
    };
  });
  const generalRuleHits = translatedRuleHits
    .filter((item) => !TECHNICAL_RULE_KEYS.has(item.key))
    .map((item) => item.translated);
  const technicalHitsFromRules = translatedRuleHits
    .filter((item) => TECHNICAL_RULE_KEYS.has(item.key))
    .map((item) => item.translated);
  const technicalPatterns = extractTechnicalPatterns(factorSnapshot, technicalHitsFromRules);

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
                    <span className="text-secondary-text">主题</span>
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
                    <span className="text-secondary-text">入选原因</span>
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
                    <div key={phase.label} className="flex items-center justify-between gap-4">
                      <span className="text-secondary-text">{backendExplanation?.label ?? phase.label}</span>
                      <span className="text-right font-mono text-foreground">
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
                  <div className="rounded border border-green/20 bg-green/3 px-2 py-1">当日追涨买入，错过则不追高</div>
                )}
                {factorSnapshot.entry_reason.includes('MA100') && (
                  <div className="rounded border border-green/20 bg-green/3 px-2 py-1">切换 60 分钟 K 线，确认支撑后再入场</div>
                )}
              </div>
            </Card>
          )}

          {generalRuleHits.length > 0 && (
            <Card variant="default" padding="sm">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <FileText className="h-3.5 w-3.5 text-cyan" /> 命中规则
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {generalRuleHits.map((ruleHit) => (
                  <Badge key={ruleHit} variant="default" size="sm">{ruleHit}</Badge>
                ))}
              </div>
            </Card>
          )}

          {technicalPatterns.length > 0 && (
            <Card variant="default" padding="sm" className="border-orange/30 bg-orange/5">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-orange">
                <Flame className="h-3.5 w-3.5" /> 技术形态命中
              </h4>
              <TechnicalPatternCards patterns={technicalPatterns} />
            </Card>
          )}

          {Object.keys(factorSnapshot).length > 0 && (
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
          )}

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
