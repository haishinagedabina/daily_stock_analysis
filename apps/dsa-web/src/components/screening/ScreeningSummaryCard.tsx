import type React from 'react';
import { BarChart3 } from 'lucide-react';
import { Card } from '../common';
import type { ScreeningCandidate } from '../../types/screening';
import {
  TRADE_STAGE_LABELS,
  POOL_LEVEL_LABELS,
} from '../../types/screening';

interface ScreeningSummaryCardProps {
  candidates: ScreeningCandidate[];
}

function countByField(
  items: ScreeningCandidate[],
  getter: (c: ScreeningCandidate) => string | undefined,
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    const val = getter(item);
    if (val) {
      counts[val] = (counts[val] ?? 0) + 1;
    }
  }
  return counts;
}

function StatRow({ label, value, colorClass }: { label: string; value: string | number; colorClass?: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-secondary-text">{label}</span>
      <span className={`font-mono ${colorClass ?? 'text-foreground'}`}>{value}</span>
    </div>
  );
}

function DistributionBar({ counts, labelMap, colorMap }: {
  counts: Record<string, number>;
  labelMap: Record<string, string>;
  colorMap?: Record<string, string>;
}) {
  const entries = Object.entries(counts).sort(([, a], [, b]) => b - a);
  if (entries.length === 0) return <span className="text-xs text-secondary-text">--</span>;

  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([key, count]) => {
        const label = labelMap[key] ?? key;
        const color = colorMap?.[key];
        return (
          <span
            key={key}
            className={`inline-flex items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${color ?? 'border-border/40 bg-elevated/40 text-secondary-text'}`}
          >
            {label}: {count}
          </span>
        );
      })}
    </div>
  );
}

const POOL_COLORS: Record<string, string> = {
  leader_pool: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
  focus_list: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
  watchlist: 'border-gray-500/30 bg-gray-500/10 text-gray-400',
};

const STAGE_COLORS: Record<string, string> = {
  probe_entry: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
  add_on_strength: 'border-green-500/30 bg-green-500/10 text-green-400',
  focus: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
  watch: 'border-gray-500/30 bg-gray-500/10 text-gray-400',
  stand_aside: 'border-orange-500/30 bg-orange-500/10 text-orange-400',
  reject: 'border-red-500/30 bg-red-500/10 text-red-400',
};

export const ScreeningSummaryCard: React.FC<ScreeningSummaryCardProps> = ({ candidates }) => {
  if (candidates.length === 0) {
    return (
      <Card variant="bordered" padding="sm">
        <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
          <BarChart3 className="h-3.5 w-3.5 text-cyan" /> 筛选概览
        </h4>
        <p className="text-xs text-secondary-text">暂无候选数据</p>
      </Card>
    );
  }

  const poolCounts = countByField(candidates, (c) => c.candidatePoolLevel);
  const stageCounts = countByField(candidates, (c) => c.tradeStage);
  const aiConfidences = candidates
    .map((c) => c.aiConfidence)
    .filter((v): v is number => v != null);
  const avgConfidence = aiConfidences.length > 0
    ? ((aiConfidences.reduce((a, b) => a + b, 0) / aiConfidences.length) * 100).toFixed(0)
    : null;

  return (
    <Card variant="bordered" padding="sm">
      <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-foreground">
        <BarChart3 className="h-3.5 w-3.5 text-cyan" /> 筛选概览
      </h4>

      <div className="space-y-3">
        <div>
          <StatRow label="候选总数" value={candidates.length} />
        </div>

        {Object.keys(poolCounts).length > 0 && (
          <div>
            <div className="mb-1 text-[10px] text-secondary-text uppercase tracking-wider">候选池分布</div>
            <DistributionBar counts={poolCounts} labelMap={POOL_LEVEL_LABELS} colorMap={POOL_COLORS} />
          </div>
        )}

        {Object.keys(stageCounts).length > 0 && (
          <div>
            <div className="mb-1 text-[10px] text-secondary-text uppercase tracking-wider">交易阶段分布</div>
            <DistributionBar counts={stageCounts} labelMap={TRADE_STAGE_LABELS} colorMap={STAGE_COLORS} />
          </div>
        )}

        {avgConfidence != null && (
          <StatRow label="AI 平均信心" value={`${avgConfidence}%`} colorClass="text-purple" />
        )}
      </div>
    </Card>
  );
};
