import type React from 'react';
import { useState } from 'react';
import { Clock, AlertTriangle, CheckCircle2, XCircle, Trash2 } from 'lucide-react';
import { Card, Badge, EmptyState, Loading } from '../common';
import { ScreeningProgressBar } from './ScreeningProgressBar';
import { useScreeningStore } from '../../stores/screeningStore';
import { STAGE_LABELS, isTerminalStatus } from '../../types/screening';
import type { ScreeningRun } from '../../types/screening';
import { cn } from '../../utils/cn';

function formatDatetime(iso?: string) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function statusVariant(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'completed') return 'success';
  if (status === 'completed_with_ai_degraded') return 'warning';
  if (status === 'failed') return 'danger';
  return 'info';
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'completed') return <CheckCircle2 className="h-3.5 w-3.5" />;
  if (status === 'failed') return <XCircle className="h-3.5 w-3.5" />;
  if (status === 'completed_with_ai_degraded') return <AlertTriangle className="h-3.5 w-3.5" />;
  return <Clock className="h-3.5 w-3.5 animate-pulse" />;
}

const RunHistoryItem: React.FC<{ run: ScreeningRun; isActive: boolean; onSelect: () => void }> = ({
  run,
  isActive,
  onSelect,
}) => (
  <button
    type="button"
    onClick={onSelect}
    data-testid={`run-history-${run.runId}`}
    className={cn(
      'flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left text-xs transition-all',
      isActive
        ? 'border-cyan/30 bg-cyan/5'
        : 'border-border/30 bg-card/50 hover:border-border/60 hover:bg-hover',
    )}
  >
    <Badge variant={statusVariant(run.status)} size="sm">
      <StatusIcon status={run.status} />
      {STAGE_LABELS[run.status] || run.status}
    </Badge>
    <span className="flex-1 truncate text-secondary-text">{run.tradeDate || '—'}</span>
    <span className="text-secondary-text">{run.candidateCount} 只</span>
    <span className="text-secondary-text/50">{formatDatetime(run.startedAt)}</span>
  </button>
);

export const ScreeningRunPanel: React.FC = () => {
  const {
    currentRun,
    isRunning,
    runHistory,
    historyLoading,
    selectRun,
    clearRunHistory,
  } = useScreeningStore();
  const [clearing, setClearing] = useState(false);

  const handleClear = async () => {
    if (runHistory.length === 0) return;
    setClearing(true);
    try {
      await clearRunHistory();
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3" data-testid="screening-run-panel">
      {/* Current run status */}
      <Card variant="bordered" padding="md" className="lg:col-span-2">
        <h3 className="mb-3 text-sm font-semibold text-foreground">运行状态</h3>
        {!currentRun && !isRunning ? (
          <EmptyState
            title="暂无运行中的筛选"
            description="点击「开始筛选」启动一次全市场扫描"
          />
        ) : currentRun ? (
          <div className="space-y-4">
            <ScreeningProgressBar status={currentRun.status} />
            <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
              <div>
                <span className="text-secondary-text">股票池</span>
                <p className="mt-0.5 font-medium text-foreground">{currentRun.universeSize}</p>
              </div>
              <div>
                <span className="text-secondary-text">候选数</span>
                <p className="mt-0.5 font-medium text-foreground">{currentRun.candidateCount}</p>
              </div>
              <div>
                <span className="text-secondary-text">AI 分析</span>
                <p className="mt-0.5 font-medium text-foreground">{currentRun.aiTopK}</p>
              </div>
              <div>
                <span className="text-secondary-text">失败率</span>
                <p className="mt-0.5 font-medium text-foreground">
                  {(currentRun.syncFailureRatio * 100).toFixed(1)}%
                </p>
              </div>
            </div>
            {currentRun.errorSummary && (
              <div className="rounded-lg border border-danger/20 bg-danger/5 px-3 py-2 text-xs text-danger">
                {currentRun.errorSummary}
              </div>
            )}
            {currentRun.warnings.length > 0 && (
              <div className="rounded-lg border border-warning/20 bg-warning/5 px-3 py-2 text-xs text-warning">
                {currentRun.warnings.join('; ')}
              </div>
            )}
          </div>
        ) : null}
      </Card>

      {/* History sidebar */}
      <Card variant="bordered" padding="md">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">历史记录</h3>
          {runHistory.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              disabled={clearing || isRunning}
              data-testid="clear-history-btn"
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-secondary-text transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-40"
            >
              <Trash2 className="h-3 w-3" />
              {clearing ? '清除中...' : '清除'}
            </button>
          )}
        </div>
        {historyLoading ? (
          <Loading label="加载历史..." />
        ) : runHistory.length === 0 ? (
          <p className="text-center text-xs text-secondary-text py-6">暂无历史记录</p>
        ) : (
          <div className="flex flex-col gap-2 max-h-100 overflow-y-auto" data-testid="run-history-list">
            {runHistory.map((run) => (
              <RunHistoryItem
                key={run.runId}
                run={run}
                isActive={currentRun?.runId === run.runId}
                onSelect={() => {
                  if (isTerminalStatus(run.status)) {
                    void selectRun(run);
                  }
                }}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
