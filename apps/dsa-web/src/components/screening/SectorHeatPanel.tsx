import type React from 'react';
import { useState } from 'react';
import { Flame, ChevronDown, ChevronUp } from 'lucide-react';
import { Card } from '../common';
import type { SectorHeatSnapshot } from '../../types/screening';

interface SectorHeatPanelProps {
  sectors: SectorHeatSnapshot[];
  hotCount: number;
  warmCount: number;
}

const STATUS_STYLES: Record<string, string> = {
  hot: 'border-danger/30 bg-danger/10 text-danger',
  warm: 'border-orange/30 bg-orange/10 text-orange',
  neutral: 'border-gray-500/30 bg-gray-500/10 text-gray-400',
  cold: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
};

const STATUS_LABELS: Record<string, string> = {
  hot: 'HOT',
  warm: 'WARM',
  neutral: 'NEUTRAL',
  cold: 'COLD',
};

const STAGE_LABELS: Record<string, string> = {
  launch: '启动',
  ferment: '发酵',
  expand: '扩散',
  climax: '高潮',
  fade: '退潮',
};

function StatusTag({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.neutral;
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${style}`}>
      {label}
    </span>
  );
}

function StageTag({ stage }: { stage: string }) {
  const label = STAGE_LABELS[stage] ?? stage;
  return (
    <span className="inline-flex rounded border border-border/40 bg-elevated/40 px-1.5 py-0.5 text-[10px] text-secondary-text">
      {label}
    </span>
  );
}

const DEFAULT_VISIBLE = 6;

export const SectorHeatPanel: React.FC<SectorHeatPanelProps> = ({ sectors, hotCount, warmCount }) => {
  const [expanded, setExpanded] = useState(false);

  if (sectors.length === 0) {
    return (
      <Card variant="bordered" padding="sm">
        <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
          <Flame className="h-3.5 w-3.5 text-orange" /> L2 热点板块
        </h4>
        <p className="text-xs text-secondary-text">暂无数据</p>
      </Card>
    );
  }

  const sorted = [...sectors].sort((a, b) => b.sectorHotScore - a.sectorHotScore);
  const visible = expanded ? sorted : sorted.slice(0, DEFAULT_VISIBLE);
  const hasMore = sorted.length > DEFAULT_VISIBLE;

  return (
    <Card variant="bordered" padding="sm">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
          <Flame className="h-3.5 w-3.5 text-orange" /> L2 热点板块
        </h4>
        <div className="flex items-center gap-2 text-[10px]">
          <span className="text-danger">
            {hotCount} 热点
          </span>
          <span className="text-orange">
            {warmCount} 温和
          </span>
          <span className="text-secondary-text">
            共 {sectors.length} 板块
          </span>
        </div>
      </div>

      <div className="space-y-1.5">
        {visible.map((sector) => (
          <div
            key={`${sector.boardName}-${sector.boardType}`}
            className="flex items-center gap-2 rounded-lg border border-border/20 bg-elevated/20 px-2 py-1.5 text-xs"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="font-medium text-foreground truncate">
                  {sector.canonicalTheme ?? sector.boardName}
                </span>
                {sector.canonicalTheme && sector.canonicalTheme !== sector.boardName && (
                  <span className="text-[10px] text-secondary-text/60 truncate">
                    {sector.boardName}
                  </span>
                )}
              </div>
            </div>
            <span className="font-mono text-foreground tabular-nums">
              {sector.sectorHotScore.toFixed(1)}
            </span>
            <StatusTag status={sector.sectorStatus} />
            <StageTag stage={sector.sectorStage} />
            <span className="text-[10px] text-secondary-text tabular-nums">
              {sector.limitUpCount > 0 && `${sector.limitUpCount}涨停 `}
              {sector.upCount}/{sector.stockCount}
            </span>
          </div>
        ))}
      </div>

      {hasMore && (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg py-1 text-[10px] text-secondary-text transition-colors hover:bg-hover/50 hover:text-foreground"
        >
          {expanded ? (
            <>收起 <ChevronUp className="h-3 w-3" /></>
          ) : (
            <>展开全部 ({sorted.length - DEFAULT_VISIBLE} 更多) <ChevronDown className="h-3 w-3" /></>
          )}
        </button>
      )}
    </Card>
  );
};
