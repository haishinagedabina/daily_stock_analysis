import type React from 'react';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import type { BacktestSummaryItem } from '../../types/backtest';

interface StrategyComparisonProps {
  summaries: BacktestSummaryItem[];
  cohortSummaries?: BacktestSummaryItem[];
}

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

function num(value?: number | null): string {
  if (value == null) return '--';
  return value.toFixed(2);
}

function label(groupKey: string): string {
  switch (groupKey) {
    case 'trend_breakout':
      return '趋势突破';
    case 'trend_pullback':
      return '趋势回踩';
    case 'gap_breakout':
      return '跳空突破';
    case 'limitup_structure':
      return '涨停结构';
    case 'bottom_divergence_breakout':
      return '底背离突破';
    case 'bottom_volume':
      return '底量启动';
    case 'volume_breakout':
      return '放量突破';
    default:
      return groupKey || '--';
  }
}

function grade(summary: BacktestSummaryItem): { text: string; variant: 'success' | 'warning' | 'danger' } {
  if ((summary.winRatePct ?? 0) > 55 && (summary.profitFactor ?? 0) > 1.5) {
    return { text: '优', variant: 'success' };
  }
  if ((summary.winRatePct ?? 0) > 45 || (summary.profitFactor ?? 0) > 1.0) {
    return { text: '中', variant: 'warning' };
  }
  return { text: '差', variant: 'danger' };
}

export const StrategyComparison: React.FC<StrategyComparisonProps> = ({ summaries, cohortSummaries = [] }) => {
  const items = [...summaries].sort((left, right) => (right.profitFactor ?? -Infinity) - (left.profitFactor ?? -Infinity));
  const p0Items = [...cohortSummaries]
    .filter((item) => item.strategyCohortContext?.primaryStrategy)
    .sort((left, right) => (right.avgReturnPct ?? -Infinity) - (left.avgReturnPct ?? -Infinity));

  return (
    <Card title="策略拆解" subtitle="Setup Type" variant="gradient">
      {items.length === 0 && p0Items.length === 0 ? (
        <p className="text-sm text-secondary-text">暂无策略对比数据。</p>
      ) : (
        <div className="space-y-4">
          {items.length > 0 ? (
            <div className="overflow-x-auto rounded-2xl border border-white/8">
              <table className="w-full text-sm">
                <thead className="bg-white/5 text-left text-xs uppercase tracking-[0.18em] text-secondary-text">
                  <tr>
                    <th className="px-3 py-3">策略</th>
                    <th className="px-3 py-3">样本数</th>
                    <th className="px-3 py-3">胜率</th>
                    <th className="px-3 py-3">盈亏比</th>
                    <th className="px-3 py-3">平均5日收益</th>
                    <th className="px-3 py-3">平均MAE</th>
                    <th className="px-3 py-3">止盈执行率</th>
                    <th className="px-3 py-3">评级</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const badge = grade(item);
                    return (
                      <tr key={`${item.groupType}-${item.groupKey}`} className="border-t border-white/8">
                        <td className="px-3 py-3 text-foreground">{label(item.groupKey)}</td>
                        <td className="px-3 py-3 font-mono text-secondary-text">{item.sampleCount}</td>
                        <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.winRatePct)}</td>
                        <td className="px-3 py-3 font-mono text-secondary-text">{num(item.profitFactor)}</td>
                        <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.avgReturnPct)}</td>
                        <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.avgMae)}</td>
                        <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.planExecutionRate != null ? item.planExecutionRate * 100 : null)}</td>
                        <td className="px-3 py-3">
                          <Badge variant={badge.variant}>{badge.text}</Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}

          {p0Items.length > 0 ? (
            <div>
              <div className="mb-2 text-sm font-semibold text-white">P0策略归因</div>
              <div className="overflow-x-auto rounded-2xl border border-white/8">
                <table className="w-full text-sm">
                  <thead className="bg-white/5 text-left text-xs uppercase tracking-[0.18em] text-secondary-text">
                    <tr>
                      <th className="px-3 py-3">主策略</th>
                      <th className="px-3 py-3">样本分层</th>
                      <th className="px-3 py-3">样本数</th>
                      <th className="px-3 py-3">平均收益</th>
                      <th className="px-3 py-3">Entry样本</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p0Items.map((item) => (
                      <tr key={`${item.groupType}-${item.groupKey}`} className="border-t border-white/8">
                        <td className="px-3 py-3 text-foreground">
                          {item.strategyCohortContext?.primaryStrategy ?? item.groupKey}
                        </td>
                        <td className="px-3 py-3 font-mono text-secondary-text">
                          {item.strategyCohortContext?.sampleBucket ?? '--'}
                        </td>
                        <td className="px-3 py-3 font-mono text-secondary-text">{item.sampleCount}</td>
                        <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.avgReturnPct)}</td>
                        <td className="px-3 py-3 font-mono text-secondary-text">
                          {item.familyBreakdown?.entry?.sampleCount ?? '--'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </Card>
  );
};
