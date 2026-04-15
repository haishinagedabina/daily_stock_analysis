import type React from 'react';
import { useState } from 'react';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import type { BacktestSummaryItem, RankingEffectivenessData } from '../../types/backtest';

interface JudgmentValidationProps {
  tradeStageSummaries: BacktestSummaryItem[];
  maturitySummaries: BacktestSummaryItem[];
  setupTypeSummaries: BacktestSummaryItem[];
  rankingEffectiveness: RankingEffectivenessData | null;
}

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

type TabKey = 'trade-stage' | 'maturity' | 'mae';

export const JudgmentValidation: React.FC<JudgmentValidationProps> = ({
  tradeStageSummaries,
  maturitySummaries,
  setupTypeSummaries,
  rankingEffectiveness,
}) => {
  const [tab, setTab] = useState<TabKey>('trade-stage');

  const rankingComparison = rankingEffectiveness?.comparisons.find(
    (item) => item.dimension === 'entry_maturity',
  );

  return (
    <Card title="判断验证" subtitle="Validation Panels" variant="gradient">
      <div className="mb-4 flex flex-wrap gap-2">
        <button type="button" className={`btn-secondary ${tab === 'trade-stage' ? 'ring-1 ring-cyan/40' : ''}`} onClick={() => setTab('trade-stage')}>
          交易阶段
        </button>
        <button type="button" className={`btn-secondary ${tab === 'maturity' ? 'ring-1 ring-cyan/40' : ''}`} onClick={() => setTab('maturity')}>
          成熟度分级
        </button>
        <button type="button" className={`btn-secondary ${tab === 'mae' ? 'ring-1 ring-cyan/40' : ''}`} onClick={() => setTab('mae')}>
          MAE精度
        </button>
      </div>

      {tab === 'trade-stage' ? (
        <div className="overflow-x-auto rounded-2xl border border-white/8">
          <table className="w-full text-sm">
            <thead className="bg-white/5 text-left text-xs uppercase tracking-[0.18em] text-secondary-text">
              <tr>
                <th className="px-3 py-3">阶段</th>
                <th className="px-3 py-3">样本数</th>
                <th className="px-3 py-3">判断准确率</th>
                <th className="px-3 py-3">平均收益</th>
              </tr>
            </thead>
            <tbody>
              {tradeStageSummaries.map((item) => (
                <tr key={item.groupKey} className="border-t border-white/8">
                  <td className="px-3 py-3 text-foreground">{item.groupKey}</td>
                  <td className="px-3 py-3 font-mono text-secondary-text">{item.sampleCount}</td>
                  <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.stageAccuracyRate != null ? item.stageAccuracyRate * 100 : null)}</td>
                  <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.avgReturnPct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {tab === 'maturity' ? (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-2xl border border-white/8">
            <table className="w-full text-sm">
              <thead className="bg-white/5 text-left text-xs uppercase tracking-[0.18em] text-secondary-text">
                <tr>
                  <th className="px-3 py-3">等级</th>
                  <th className="px-3 py-3">样本数</th>
                  <th className="px-3 py-3">胜率</th>
                  <th className="px-3 py-3">平均收益</th>
                </tr>
              </thead>
              <tbody>
                {maturitySummaries.map((item) => (
                  <tr key={item.groupKey} className="border-t border-white/8">
                    <td className="px-3 py-3 text-foreground">{item.groupKey}</td>
                    <td className="px-3 py-3 font-mono text-secondary-text">{item.sampleCount}</td>
                    <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.winRatePct)}</td>
                    <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.avgReturnPct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-3 text-sm text-secondary-text">
            <span>分级一致性</span>
            {rankingComparison?.isEffective ? (
              <Badge variant="success">有效</Badge>
            ) : (
              <Badge variant="warning">待观察</Badge>
            )}
          </div>
        </div>
      ) : null}

      {tab === 'mae' ? (
        <div className="overflow-x-auto rounded-2xl border border-white/8">
          <table className="w-full text-sm">
            <thead className="bg-white/5 text-left text-xs uppercase tracking-[0.18em] text-secondary-text">
              <tr>
                <th className="px-3 py-3">策略</th>
                <th className="px-3 py-3">平均MAE</th>
                <th className="px-3 py-3">样本数</th>
              </tr>
            </thead>
            <tbody>
              {setupTypeSummaries.map((item) => (
                <tr key={item.groupKey} className="border-t border-white/8">
                  <td className="px-3 py-3 text-foreground">{item.groupKey}</td>
                  <td className="px-3 py-3 font-mono text-secondary-text">{pct(item.avgMae)}</td>
                  <td className="px-3 py-3 font-mono text-secondary-text">{item.sampleCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
};
