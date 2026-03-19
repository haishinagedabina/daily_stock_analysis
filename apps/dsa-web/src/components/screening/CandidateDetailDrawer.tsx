import type React from 'react';
import { Drawer, Badge, Card } from '../common';
import { useScreeningStore } from '../../stores/screeningStore';
import { Brain, BarChart3, FileText } from 'lucide-react';

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
