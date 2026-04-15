import type React from 'react';
import { Card } from '../common/Card';
import type { BacktestSummaryItem } from '../../types/backtest';

interface SystemScorecardProps {
  summary: BacktestSummaryItem | null;
  signalQualityScore?: number | null;
}

interface MetricCardProps {
  label: string;
  value: string;
  tone: 'success' | 'warning' | 'danger';
}

function formatPercent(value?: number | null, digits = 1): string {
  if (value == null) {
    return '--';
  }
  return `${value.toFixed(digits)}%`;
}

function formatNumber(value?: number | null, digits = 2): string {
  if (value == null) {
    return '--';
  }
  return value.toFixed(digits);
}

function toneClass(tone: MetricCardProps['tone']): string {
  if (tone === 'success') return 'border-emerald-400/20 bg-emerald-400/8 text-emerald-300';
  if (tone === 'warning') return 'border-amber-400/20 bg-amber-400/8 text-amber-200';
  return 'border-rose-400/20 bg-rose-400/8 text-rose-200';
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, tone }) => (
  <div className={`rounded-2xl border p-4 ${toneClass(tone)}`}>
    <div className="text-xs uppercase tracking-[0.18em] text-current/80">{label}</div>
    <div className="mt-3 text-2xl font-semibold text-white">{value}</div>
  </div>
);

function winRateTone(value?: number | null): MetricCardProps['tone'] {
  if (value == null) return 'danger';
  if (value > 55) return 'success';
  if (value >= 45) return 'warning';
  return 'danger';
}

function profitFactorTone(value?: number | null): MetricCardProps['tone'] {
  if (value == null) return 'danger';
  if (value > 1.5) return 'success';
  if (value >= 1.0) return 'warning';
  return 'danger';
}

function averageReturnTone(value?: number | null): MetricCardProps['tone'] {
  if (value == null) return 'danger';
  if (value > 2) return 'success';
  if (value >= 0) return 'warning';
  return 'danger';
}

function drawdownTone(value?: number | null): MetricCardProps['tone'] {
  if (value == null) return 'danger';
  if (value > -3) return 'success';
  if (value >= -5) return 'warning';
  return 'danger';
}

function qualityTone(value?: number | null): MetricCardProps['tone'] {
  if (value == null) return 'danger';
  if (value > 0.6) return 'success';
  if (value >= 0.4) return 'warning';
  return 'danger';
}

function gradeTone(value?: string | null): MetricCardProps['tone'] {
  if (!value) return 'danger';
  if (value === 'A+' || value === 'A' || value === 'B+') return 'success';
  if (value === 'B' || value === 'C') return 'warning';
  return 'danger';
}

export const SystemScorecard: React.FC<SystemScorecardProps> = ({ summary, signalQualityScore }) => {
  if (!summary) {
    return (
      <Card title="系统体检" subtitle="Hero Section" variant="gradient">
        <p className="text-sm text-secondary-text">运行回测后，这里会显示系统总览和综合评分。</p>
      </Card>
    );
  }

  return (
    <Card title="系统体检" subtitle="Hero Section" variant="gradient">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          label="总胜率"
          value={formatPercent(summary.winRatePct)}
          tone={winRateTone(summary.winRatePct)}
        />
        <MetricCard
          label="盈亏比"
          value={formatNumber(summary.profitFactor)}
          tone={profitFactorTone(summary.profitFactor)}
        />
        <MetricCard
          label="平均收益"
          value={formatPercent(summary.avgReturnPct)}
          tone={averageReturnTone(summary.avgReturnPct)}
        />
        <MetricCard
          label="最大回撤"
          value={formatPercent(summary.avgDrawdown)}
          tone={drawdownTone(summary.avgDrawdown)}
        />
        <MetricCard
          label="信号质量"
          value={formatNumber(signalQualityScore)}
          tone={qualityTone(signalQualityScore)}
        />
        <MetricCard
          label="综合评分"
          value={summary.systemGrade || '--'}
          tone={gradeTone(summary.systemGrade)}
        />
      </div>
    </Card>
  );
};
