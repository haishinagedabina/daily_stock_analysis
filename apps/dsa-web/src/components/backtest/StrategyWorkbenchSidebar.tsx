import type React from 'react';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';

export interface StrategySidebarItem {
  key: string;
  strategyKey: string;
  displayName: string;
  metaLabel?: string | null;
  sampleCount: number;
  winRatePct?: number | null;
  avgReturnPct?: number | null;
  profitFactor?: number | null;
  warningTag?: string | null;
}

interface StrategyWorkbenchSidebarProps {
  items: StrategySidebarItem[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

export const StrategyWorkbenchSidebar: React.FC<StrategyWorkbenchSidebarProps> = ({
  items,
  selectedKey,
  onSelect,
}) => {
  return (
    <Card title="策略分布" subtitle="Strategy Navigator" variant="gradient" className="sticky top-20">
      <div className="mb-4 rounded-2xl border border-white/8 bg-white/3 p-4 text-sm text-secondary-text">
        <div className="flex items-center justify-between gap-2">
          <span>按策略聚焦本次回测样本与证据链</span>
          <span className="rounded-full border border-cyan/20 bg-cyan/10 px-2 py-0.5 text-xs text-cyan">
            当前导航
          </span>
        </div>
        <div className="mt-3 rounded-xl border border-white/8 bg-black/10 px-3 py-2 text-xs text-secondary-text">
          {items.length} 个策略
        </div>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-secondary-text">当前运行尚未产出可研究的策略分布。</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const isSelected = item.key === selectedKey;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => onSelect(item.key)}
                className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                  isSelected
                    ? 'border-cyan/40 bg-[linear-gradient(135deg,rgba(0,212,255,0.14),rgba(255,255,255,0.03))] shadow-lg shadow-cyan/10'
                    : 'border-white/8 bg-white/3 hover:bg-white/5'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
                      <span>{item.displayName}</span>
                      {item.warningTag ? <Badge variant="warning">{`提醒: ${item.warningTag}`}</Badge> : null}
                    </div>
                    <div className="mt-1 text-xs leading-5 text-secondary-text">
                      {item.metaLabel || '研究策略'} · 样本 {item.sampleCount}
                    </div>
                  </div>
                  <span className={`mt-0.5 h-2.5 w-2.5 rounded-full ${isSelected ? 'bg-cyan shadow-[0_0_10px_rgba(0,212,255,0.7)]' : 'bg-white/15'}`} />
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div className="rounded-xl bg-black/10 px-2 py-2">
                    <div className="text-secondary-text">胜率</div>
                    <div className="mt-1 font-mono text-foreground">{pct(item.winRatePct)}</div>
                  </div>
                  <div className="rounded-xl bg-black/10 px-2 py-2">
                    <div className="text-secondary-text">收益</div>
                    <div className="mt-1 font-mono text-foreground">{pct(item.avgReturnPct)}</div>
                  </div>
                  <div className="rounded-xl bg-black/10 px-2 py-2">
                    <div className="text-secondary-text">盈亏比</div>
                    <div className="mt-1 font-mono text-foreground">
                      {item.profitFactor == null ? '--' : item.profitFactor.toFixed(2)}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </Card>
  );
};
