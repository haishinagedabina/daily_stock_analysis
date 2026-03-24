import type React from 'react';
import { useState } from 'react';
import { Eye, ArrowUpDown, ArrowUp, ArrowDown, Brain, Bell } from 'lucide-react';
import { Card, Badge, Button, Loading } from '../common';
import { useScreeningStore } from '../../stores/screeningStore';
import { cn } from '../../utils/cn';
import type { ScreeningCandidate } from '../../types/screening';

type SortKey = 'rank' | 'ruleScore' | 'finalScore' | 'code';
type SortDir = 'asc' | 'desc';

function sortCandidates(items: ScreeningCandidate[], key: SortKey, dir: SortDir): ScreeningCandidate[] {
  return [...items].sort((a, b) => {
    let va: number | string;
    let vb: number | string;
    switch (key) {
      case 'rank':
        va = a.rank; vb = b.rank; break;
      case 'ruleScore':
        va = a.ruleScore; vb = b.ruleScore; break;
      case 'finalScore':
        va = a.finalScore ?? 0; vb = b.finalScore ?? 0; break;
      case 'code':
      default:
        va = a.code; vb = b.code; break;
    }
    if (typeof va === 'string') return dir === 'asc' ? va.localeCompare(vb as string) : (vb as string).localeCompare(va);
    return dir === 'asc' ? (va as number) - (vb as number) : (vb as number) - (va as number);
  });
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 text-secondary-text/40" />;
  return dir === 'asc' ? <ArrowUp className="h-3 w-3 text-cyan" /> : <ArrowDown className="h-3 w-3 text-cyan" />;
}

export const ScreeningCandidateTable: React.FC = () => {
  const { currentRun, candidates, candidatesLoading, strategies, selectCandidate, sendNotification } =
    useScreeningStore();
  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  if (!currentRun || candidates.length === 0) {
    if (candidatesLoading) return <Loading label="加载候选..." />;
    return null;
  }

  const sorted = sortCandidates(candidates, sortKey, sortDir);
  const strategyNameMap = new Map(
    strategies.map((strategy) => [strategy.name, strategy.displayName]),
  );

  const thClass = 'px-3 py-2.5 text-left text-xs font-medium text-secondary-text cursor-pointer select-none hover:text-foreground transition-colors';

  return (
    <Card variant="bordered" padding="none" data-testid="candidate-table">
      <div className="flex items-center justify-between px-5 py-3 border-b border-border/40">
        <h3 className="text-sm font-semibold text-foreground">
          候选结果 <span className="text-secondary-text font-normal">({candidates.length})</span>
        </h3>
        <div className="flex items-center gap-2">
          {currentRun.status === 'completed' && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void sendNotification(currentRun.runId)}
            >
              <Bell className="h-3.5 w-3.5" />
              推送通知
            </Button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border/30 bg-elevated/30">
              <th className={thClass} onClick={() => toggleSort('rank')}>
                <span className="inline-flex items-center gap-1">排名 <SortIcon active={sortKey === 'rank'} dir={sortDir} /></span>
              </th>
              <th className={cn(thClass, 'cursor-default hover:text-secondary-text')}>代码</th>
              <th className={cn(thClass, 'cursor-default hover:text-secondary-text')}>名称</th>
              <th className={thClass} onClick={() => toggleSort('ruleScore')}>
                <span className="inline-flex items-center gap-1">规则评分 <SortIcon active={sortKey === 'ruleScore'} dir={sortDir} /></span>
              </th>
              <th className={thClass} onClick={() => toggleSort('finalScore')}>
                <span className="inline-flex items-center gap-1">综合评分 <SortIcon active={sortKey === 'finalScore'} dir={sortDir} /></span>
              </th>
              <th className={cn(thClass, 'cursor-default hover:text-secondary-text')}>策略</th>
              <th className={cn(thClass, 'cursor-default hover:text-secondary-text')}>AI</th>
              <th className={cn(thClass, 'cursor-default hover:text-secondary-text text-center')}>操作</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => (
              <tr
                key={c.code}
                data-testid={`candidate-row-${c.code}`}
                className="border-b border-border/20 transition-colors hover:bg-hover/50"
              >
                <td className="px-3 py-2.5 text-xs font-medium text-foreground">{c.rank}</td>
                <td className="px-3 py-2.5 text-xs font-mono text-cyan">{c.code}</td>
                <td className="px-3 py-2.5 text-xs text-foreground">{c.name || '—'}</td>
                <td className="px-3 py-2.5 text-xs">
                  <span className="font-medium text-foreground">{c.ruleScore.toFixed(1)}</span>
                </td>
                <td className="px-3 py-2.5 text-xs">
                  {c.finalScore != null ? (
                    <span className="font-medium text-foreground">{c.finalScore.toFixed(1)}</span>
                  ) : (
                    <span className="text-secondary-text/40">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex flex-wrap gap-1">
                    {c.matchedStrategies?.map((s) => (
                      <Badge key={s} variant="info" size="sm">
                        {strategyNameMap.get(s) ?? s}
                      </Badge>
                    ))}
                  </div>
                </td>
                <td className="px-3 py-2.5 text-center">
                  {c.selectedForAi ? (
                    <Brain className="mx-auto h-3.5 w-3.5 text-purple" />
                  ) : (
                    <span className="text-secondary-text/30">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-center">
                  <button
                    type="button"
                    onClick={() => void selectCandidate(currentRun.runId, c.code)}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-secondary-text transition-colors hover:bg-cyan/10 hover:text-cyan"
                    aria-label={`查看 ${c.code} 详情`}
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
};
