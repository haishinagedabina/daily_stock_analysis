import type React from 'react';
import { Drawer, Badge, Card } from '../common';
import { useScreeningStore } from '../../stores/screeningStore';
import { Brain, BarChart3, FileText, Flame } from 'lucide-react';

function FactorRow({ label, value }: { label: string; value: unknown }) {
  const display = value == null ? '—' : typeof value === 'number' ? value.toFixed(2) : String(value);
  return (
    <div className="flex items-center justify-between border-b border-border/20 py-1.5 text-xs">
      <span className="text-secondary-text">{label}</span>
      <span className="font-mono text-foreground">{display}</span>
    </div>
  );
}

export const CandidateDetailDrawer: React.FC = () => {
  const { selectedCandidate, clearSelectedCandidate } = useScreeningStore();
  const isOpen = selectedCandidate != null;

  return (
    <Drawer
      isOpen={isOpen}
      onClose={clearSelectedCandidate}
      title={selectedCandidate ? `${selectedCandidate.code} ${selectedCandidate.name || ''}` : ''}
    >
      {selectedCandidate && (
        <div className="flex flex-col gap-5" data-testid="candidate-detail">
          {/* Overview */}
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

          {/* Hot theme info */}
          {selectedCandidate.factorSnapshot?.is_hot_theme_stock && (
            <Card variant="default" padding="sm" className="border-orange/30 bg-orange/5">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-orange">
                <Flame className="h-3.5 w-3.5" /> 热点题材
              </h4>
              <div className="space-y-1.5 text-xs">
                {selectedCandidate.factorSnapshot?.primary_theme && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">主题材</span>
                    <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.primary_theme}</span>
                  </div>
                )}
                {selectedCandidate.factorSnapshot?.theme_heat_score != null && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">题材热度</span>
                    <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.theme_heat_score.toFixed(1)}</span>
                  </div>
                )}
                {selectedCandidate.factorSnapshot?.theme_match_score != null && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">题材匹配度</span>
                    <span className="font-mono text-foreground">{(selectedCandidate.factorSnapshot.theme_match_score * 100).toFixed(0)}%</span>
                  </div>
                )}
                {selectedCandidate.factorSnapshot?.leader_score != null && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">龙头特征分</span>
                    <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.leader_score.toFixed(0)}</span>
                  </div>
                )}
                {selectedCandidate.factorSnapshot?.extreme_strength_score != null && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">极端强势分</span>
                    <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.extreme_strength_score.toFixed(1)}</span>
                  </div>
                )}
                {selectedCandidate.factorSnapshot?.entry_reason && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">龙头选出原因</span>
                    <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.entry_reason}</span>
                  </div>
                )}
                {selectedCandidate.factorSnapshot?.core_signal && (
                  <div className="flex items-center justify-between">
                    <span className="text-secondary-text">核心技术信号</span>
                    <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.core_signal}</span>
                  </div>
                )}
                {selectedCandidate.factorSnapshot?.theme_catalyst_summary && (
                  <div className="mt-2 rounded-lg border border-orange/20 bg-orange/5 px-2 py-1.5 text-xs text-orange">
                    {selectedCandidate.factorSnapshot.theme_catalyst_summary}
                  </div>
                )}
                {selectedCandidate.factorSnapshot?.theme_catalyst_news && selectedCandidate.factorSnapshot.theme_catalyst_news.length > 0 && (
                  <div className="mt-2 space-y-1.5">
                    <div className="text-xs font-semibold text-orange">热点新闻</div>
                    {selectedCandidate.factorSnapshot.theme_catalyst_news.map((news: any, idx: number) => (
                      <div key={idx} className="rounded border border-orange/10 bg-orange/3 p-1.5 text-xs">
                        <div className="font-mono text-foreground">{news.title}</div>
                        <div className="mt-0.5 flex items-center justify-between text-secondary-text">
                          <span>{news.source}</span>
                          {news.url && <a href={news.url} target="_blank" rel="noopener noreferrer" className="text-orange hover:underline">查看</a>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Strategy hit explanation */}
          {selectedCandidate.factorSnapshot?.phase_results && (
            <Card variant="default" padding="sm" className="border-cyan/30 bg-cyan/5">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-cyan">
                <Brain className="h-3.5 w-3.5" /> 策略命中说明
              </h4>
              <div className="space-y-1 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-secondary-text">阶段1: 市场环境</span>
                  <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.phase_results.phase1 ? '✓ 大盘强势' : '✗'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-secondary-text">阶段2: 题材验证</span>
                  <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.phase_results.phase2 ? '✓ 热点题材' : '✗'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-secondary-text">阶段3: 龙头特征</span>
                  <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.phase_results.phase3 ? `✓ 龙头评分: ${selectedCandidate.factorSnapshot.leader_score}` : '✗'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-secondary-text">阶段4: 核心信号</span>
                  <span className="font-mono text-foreground">{selectedCandidate.factorSnapshot.phase_results.phase4 ? `✓ ${selectedCandidate.factorSnapshot.core_signal}` : '✗'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-secondary-text">阶段5: 风险控制</span>
                  <span className="font-mono text-foreground">止损: {selectedCandidate.factorSnapshot.risk_params?.stop_loss?.toFixed(2)} | 仓位: {selectedCandidate.factorSnapshot.risk_params?.position_size}</span>
                </div>
              </div>
            </Card>
          )}

          {/* Entry method */}
          {selectedCandidate.factorSnapshot?.entry_reason && (
            <Card variant="default" padding="sm" className="border-green/30 bg-green/5">
              <h4 className="mb-2 text-xs font-semibold text-green">入场方案</h4>
              <div className="text-xs text-secondary-text">
                <div className="mb-1.5">{selectedCandidate.factorSnapshot.entry_reason}</div>
                {selectedCandidate.factorSnapshot.entry_reason.includes('涨停') && (
                  <div className="rounded border border-green/20 bg-green/3 px-2 py-1">当日追涨买入，错过不追高</div>
                )}
                {selectedCandidate.factorSnapshot.entry_reason.includes('MA100') && (
                  <div className="rounded border border-green/20 bg-green/3 px-2 py-1">切换60分钟K线，确认支撑后买入</div>
                )}
              </div>
            </Card>
          )}

          {/* Rule hits */}
          {selectedCandidate.ruleHits.length > 0 && (
            <Card variant="default" padding="sm">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <FileText className="h-3.5 w-3.5 text-cyan" /> 命中规则
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {selectedCandidate.ruleHits.map((h) => (
                  <Badge key={h} variant="default" size="sm">{h}</Badge>
                ))}
              </div>
            </Card>
          )}

          {/* Extreme strength reasons */}
          {selectedCandidate.factorSnapshot?.extreme_strength_reasons &&
           Array.isArray(selectedCandidate.factorSnapshot.extreme_strength_reasons) &&
           selectedCandidate.factorSnapshot.extreme_strength_reasons.length > 0 && (
            <Card variant="default" padding="sm">
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Flame className="h-3.5 w-3.5 text-orange" /> 命中原因
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {selectedCandidate.factorSnapshot.extreme_strength_reasons.map((reason: string) => (
                  <Badge key={reason} variant="default" size="sm">{reason}</Badge>
                ))}
              </div>
            </Card>
          )}

          {/* Factor snapshot */}
          <Card variant="default" padding="sm">
            <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <BarChart3 className="h-3.5 w-3.5 text-cyan" /> 因子快照
            </h4>
            <div className="max-h-60 overflow-y-auto">
              {Object.entries(selectedCandidate.factorSnapshot).map(([k, v]) => (
                <FactorRow key={k} label={k} value={v} />
              ))}
            </div>
          </Card>

          {/* AI analysis */}
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

          {/* Matched strategies */}
          {selectedCandidate.matchedStrategies && selectedCandidate.matchedStrategies.length > 0 && (
            <Card variant="default" padding="sm">
              <h4 className="mb-2 text-xs font-semibold text-foreground">匹配策略</h4>
              <div className="flex flex-wrap gap-1.5">
                {selectedCandidate.matchedStrategies.map((s) => (
                  <Badge key={s} variant="info" size="sm">{s}</Badge>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </Drawer>
  );
};
