import type React from 'react';
import { Workflow } from 'lucide-react';
import { Card, Collapsible } from '../common';
import type {
  ExternalThemePipelineSnapshot,
  FusedThemePipelineSnapshot,
  LocalThemePipelineSnapshot,
  ScreeningRun,
  ThemePipelineThemeItem,
} from '../../types/screening';

interface ThemePipelineSectionProps {
  run: ScreeningRun;
}

function formatList(values?: string[]): string {
  if (!values || values.length === 0) return '—';
  return values.join('、');
}

function MetricPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border/25 bg-elevated/30 px-3 py-2">
      <div className="text-[10px] text-secondary-text">{label}</div>
      <div className="mt-1 text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

function FieldLine({ label, value }: { label: string; value?: string | number | null }) {
  if (value == null || value === '') return null;
  return <p className="text-[11px] text-secondary-text">{label}: {value}</p>;
}

function ThemeCard({
  item,
  sourceVariant,
}: {
  item: ThemePipelineThemeItem;
  sourceVariant: 'fused' | 'local' | 'external';
}) {
  const rawNames = item.rawNames?.length ? item.rawNames : item.rawName ? [item.rawName] : [];
  const normalizationInfo = item.normalizationStatus
    ? `${item.normalizationStatus}${item.normalizationConfidence != null ? ` (${item.normalizationConfidence.toFixed(2)})` : ''}`
    : undefined;

  return (
    <div className="rounded-xl border border-border/25 bg-card/40 px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-foreground">{item.name}</div>
          {item.normalizedName && item.normalizedName !== item.name && (
            <div className="text-[11px] text-secondary-text">规范名: {item.normalizedName}</div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
          {item.prioritySource && (
            <span className="rounded border border-purple/25 bg-purple/10 px-1.5 py-0.5 text-purple">
              优先 {item.prioritySource}
            </span>
          )}
          {item.sectorStatus && (
            <span className="rounded border border-orange/25 bg-orange/10 px-1.5 py-0.5 text-orange">
              {item.sectorStatus}
            </span>
          )}
          {item.sectorStage && (
            <span className="rounded border border-cyan/20 bg-cyan/10 px-1.5 py-0.5 text-cyan">
              {item.sectorStage}
            </span>
          )}
        </div>
      </div>

      <div className="mt-2 space-y-1">
        <FieldLine label="原始题材" value={rawNames.length > 0 ? formatList(rawNames) : undefined} />
        {sourceVariant === 'fused' && (
          <>
            <FieldLine label="来源" value={item.matchedSources?.join(' + ')} />
            <FieldLine label="热度分" value={item.heatScore != null ? item.heatScore.toFixed(1) : undefined} />
            <FieldLine label="置信度" value={item.confidence != null ? item.confidence.toFixed(2) : undefined} />
          </>
        )}
        {sourceVariant === 'local' && (
          <>
            <FieldLine label="板块" value={item.sourceBoard} />
            <FieldLine label="热度分" value={item.heatScore != null ? item.heatScore.toFixed(1) : undefined} />
            <FieldLine label="个股数" value={item.stockCount} />
            <FieldLine
              label="涨跌分布"
              value={
                item.upCount != null || item.limitUpCount != null
                  ? `${item.upCount ?? 0} 上涨 / ${item.limitUpCount ?? 0} 涨停`
                  : undefined
              }
            />
          </>
        )}
        {sourceVariant === 'external' && (
          <>
            <FieldLine label="关键词" value={item.keywords?.length ? formatList(item.keywords) : undefined} />
            <FieldLine label="关键词数" value={item.keywordCount} />
            <FieldLine label="置信度" value={item.confidence != null ? item.confidence.toFixed(2) : undefined} />
            <FieldLine label="催化摘要" value={item.catalystSummary} />
          </>
        )}
        <FieldLine label="规范化" value={normalizationInfo} />
        <FieldLine
          label="命中原因"
          value={item.normalizationMatchReasons?.length ? formatList(item.normalizationMatchReasons) : undefined}
        />
        <FieldLine
          label="命中板块"
          value={item.normalizationMatchedBoards?.length ? formatList(item.normalizationMatchedBoards) : undefined}
        />
      </div>
    </div>
  );
}

function PipelineThemeList({
  themes,
  sourceVariant,
  emptyText,
}: {
  themes: ThemePipelineThemeItem[];
  sourceVariant: 'fused' | 'local' | 'external';
  emptyText: string;
}) {
  if (themes.length === 0) {
    return <p className="text-xs text-secondary-text">{emptyText}</p>;
  }

  return (
    <div className="space-y-2">
      {themes.map((item, index) => (
        <ThemeCard
          key={`${sourceVariant}-${item.normalizedName ?? item.name}-${item.rawName ?? item.name}-${index}`}
          item={item}
          sourceVariant={sourceVariant}
        />
      ))}
    </div>
  );
}

function FusedSection({ pipeline }: { pipeline: FusedThemePipelineSnapshot }) {
  return (
    <Card variant="bordered" padding="md">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">融合结果</h3>
          <p className="mt-1 text-xs text-secondary-text">
            当前展示最终进入后续候选池判定的题材集合。
          </p>
        </div>
        <span className="rounded border border-purple/20 bg-purple/10 px-2 py-1 text-[10px] text-purple">
          {pipeline.activeSources.join(' + ') || '—'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs lg:grid-cols-4">
        <MetricPill label="融合题材数" value={pipeline.mergedThemeCount} />
        <MetricPill label="启用来源" value={pipeline.activeSources.length || '—'} />
        <MetricPill label="交易日" value={pipeline.tradeDate || '—'} />
        <MetricPill label="市场" value={pipeline.market || '—'} />
      </div>

      <div className="mt-4 rounded-xl border border-border/25 bg-elevated/20 px-3 py-3">
        <div className="text-[10px] text-secondary-text">最终题材列表</div>
        <div className="mt-1 text-sm text-foreground">{formatList(pipeline.selectedThemeNames)}</div>
      </div>

      <div className="mt-4">
        <PipelineThemeList
          themes={pipeline.mergedThemes}
          sourceVariant="fused"
          emptyText="暂无融合题材明细"
        />
      </div>
    </Card>
  );
}

function LocalSection({ pipeline }: { pipeline: LocalThemePipelineSnapshot }) {
  return (
    <Collapsible title="本地题材管道" defaultOpen={false} icon={<Workflow className="h-4 w-4" />}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-xs lg:grid-cols-4">
          <MetricPill label="热点题材" value={pipeline.hotThemeCount} />
          <MetricPill label="温和题材" value={pipeline.warmThemeCount} />
          <MetricPill label="交易日" value={pipeline.tradeDate || '—'} />
          <MetricPill label="市场" value={pipeline.market || '—'} />
        </div>
        <div className="rounded-xl border border-border/25 bg-elevated/20 px-3 py-3">
          <div className="text-[10px] text-secondary-text">入选题材</div>
          <div className="mt-1 text-sm text-foreground">{formatList(pipeline.selectedThemeNames)}</div>
        </div>
        <PipelineThemeList themes={pipeline.themes} sourceVariant="local" emptyText="暂无本地题材明细" />
      </div>
    </Collapsible>
  );
}

function ExternalSection({ pipeline }: { pipeline: ExternalThemePipelineSnapshot }) {
  return (
    <Collapsible title="外部题材管道" defaultOpen={false} icon={<Workflow className="h-4 w-4" />}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-xs lg:grid-cols-4">
          <MetricPill label="接收题材" value={pipeline.acceptedThemeCount} />
          <MetricPill label="热点题材" value={pipeline.hotThemeCount} />
          <MetricPill label="聚焦题材" value={pipeline.focusThemeCount} />
          <MetricPill label="交易日" value={pipeline.tradeDate || '—'} />
        </div>
        <div className="rounded-xl border border-border/25 bg-elevated/20 px-3 py-3">
          <div className="text-[10px] text-secondary-text">Top 题材</div>
          <div className="mt-1 text-sm text-foreground">{formatList(pipeline.topThemeNames)}</div>
        </div>
        <PipelineThemeList themes={pipeline.themes} sourceVariant="external" emptyText="暂无外部题材明细" />
      </div>
    </Collapsible>
  );
}

export const ThemePipelineSection: React.FC<ThemePipelineSectionProps> = ({ run }) => {
  const hasAnyPipeline = Boolean(
    run.fusedThemePipeline || run.localThemePipeline || run.externalThemePipeline,
  );

  if (!hasAnyPipeline) {
    return null;
  }

  return (
    <section className="space-y-4" data-testid="theme-pipeline-section">
      <Card variant="bordered" padding="sm">
        <div className="flex items-center gap-2">
          <Workflow className="h-4 w-4 text-purple" />
          <div>
            <h2 className="text-sm font-semibold text-foreground">题材管道详情</h2>
            <p className="mt-1 text-xs text-secondary-text">
              同时查看本地 L2、外部题材输入与最终融合结果。
            </p>
          </div>
        </div>
      </Card>

      {run.fusedThemePipeline && <FusedSection pipeline={run.fusedThemePipeline} />}
      {run.localThemePipeline && <LocalSection pipeline={run.localThemePipeline} />}
      {run.externalThemePipeline && <ExternalSection pipeline={run.externalThemePipeline} />}
    </section>
  );
};
