import type React from 'react';
import { useMemo, useState } from 'react';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import type { BacktestResultItem } from '../../types/backtest';

interface EvaluationDetailProps {
  evaluations: BacktestResultItem[];
  isLoading?: boolean;
}

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

function tryParse(value?: string | null): Record<string, unknown> | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

function renderFactorSummary(payload: Record<string, unknown> | null): Array<{ label: string; value: string }> {
  if (!payload) return [];
  return [
    {
      label: 'MA100突破',
      value: typeof payload.ma100_breakout_days === 'number'
        ? `突破${payload.ma100_breakout_days}日`
        : '未突破',
    },
    {
      label: '底背离',
      value: String(payload.bottom_divergence_state ?? '--'),
    },
    {
      label: '趋势线突破',
      value: payload.trendline_breakout ? '已突破' : '未突破',
    },
    {
      label: '突破性缺口',
      value: payload.gap_is_breakaway ? '有' : '无',
    },
    {
      label: '低位结构',
      value: String(payload.low_123_state ?? '--'),
    },
  ];
}

export const EvaluationDetail: React.FC<EvaluationDetailProps> = ({ evaluations, isLoading = false }) => {
  const [tab, setTab] = useState<'entry' | 'observation'>('entry');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const filtered = useMemo(
    () => evaluations.filter((item) => item.signalFamily === tab),
    [evaluations, tab],
  );

  return (
    <Card title="个股明细" subtitle="Drill-down" variant="gradient">
      <div className="mb-4 flex gap-2">
        <button type="button" className={`btn-secondary ${tab === 'entry' ? 'ring-1 ring-cyan/40' : ''}`} onClick={() => setTab('entry')}>
          入场信号
        </button>
        <button type="button" className={`btn-secondary ${tab === 'observation' ? 'ring-1 ring-cyan/40' : ''}`} onClick={() => setTab('observation')}>
          观察信号
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-secondary-text">正在加载评估明细...</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-secondary-text">当前标签下暂无评估数据。</p>
      ) : (
        <div className="space-y-3">
          {filtered.map((item) => {
            const factorPayload = tryParse(item.factorSnapshotJson);
            const planPayload = tryParse(item.tradePlanJson);
            const isExpanded = expandedId === item.id;
            return (
              <div key={item.id ?? `${item.code}-${item.tradeDate}-${item.signalFamily}`} className="rounded-2xl border border-white/8">
                <button
                  type="button"
                  className="flex w-full flex-wrap items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/5"
                  onClick={() => setExpandedId(isExpanded ? null : item.id ?? null)}
                >
                  <div>
                    <div className="text-sm font-semibold text-foreground">{item.code} {item.name ?? ''}</div>
                    <div className="mt-1 text-xs text-secondary-text">{item.tradeDate ?? '--'} · {item.snapshotSetupType ?? item.snapshotTradeStage ?? '--'}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant={item.outcome === 'win' || item.outcome === 'correct_wait' ? 'success' : 'default'}>
                      {item.outcome ?? '--'}
                    </Badge>
                    <span className="font-mono text-secondary-text">
                      {tab === 'entry' ? pct(item.forwardReturn5d) : pct(item.riskAvoidedPct)}
                    </span>
                  </div>
                </button>

                {isExpanded ? (
                  <div className="border-t border-white/8 px-4 py-4">
                    <div className="grid gap-4 lg:grid-cols-2">
                      <div>
                        <h4 className="mb-3 text-sm font-semibold text-white">因子快照</h4>
                        <div className="space-y-2">
                          {renderFactorSummary(factorPayload).map((row) => (
                            <div key={row.label} className="flex items-center justify-between rounded-xl bg-white/5 px-3 py-2 text-sm">
                              <span className="text-secondary-text">{row.label}</span>
                              <span className="font-mono text-foreground">{row.value}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <h4 className="mb-3 text-sm font-semibold text-white">交易计划</h4>
                        <div className="space-y-2 rounded-xl bg-white/5 p-3 text-sm">
                          <div className="flex items-center justify-between">
                            <span className="text-secondary-text">止盈目标</span>
                            <span className="font-mono text-foreground">{String(planPayload?.take_profit ?? '--')}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-secondary-text">止损线</span>
                            <span className="font-mono text-foreground">{String(planPayload?.stop_loss ?? '--')}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-secondary-text">执行结果</span>
                            <span className="font-mono text-foreground">{item.planSuccess == null ? '--' : item.planSuccess ? '成功' : '失败'}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
};
