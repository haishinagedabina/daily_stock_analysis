import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { backtestApi } from '../api/backtest';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Badge, Card } from '../components/common';
import { EvaluationDetail } from '../components/backtest/EvaluationDetail';
import { JudgmentValidation } from '../components/backtest/JudgmentValidation';
import { StrategyComparison } from '../components/backtest/StrategyComparison';
import { SystemScorecard } from '../components/backtest/SystemScorecard';
import type {
  BacktestFullPipelineResponse,
  BacktestResultItem,
  BacktestRunResponse,
  BacktestSummaryItem,
  FiveLayerEvaluationMode,
  FiveLayerExecutionModel,
  FiveLayerMarket,
  RankingEffectivenessData,
} from '../types/backtest';

const EVALUATION_MODE_OPTIONS: Array<{ value: FiveLayerEvaluationMode; label: string }> = [
  { value: 'historical_snapshot', label: '历史快照' },
  { value: 'rule_replay', label: '规则回放' },
  { value: 'parameter_calibration', label: '参数校准' },
];

const EXECUTION_MODEL_OPTIONS: Array<{ value: FiveLayerExecutionModel; label: string }> = [
  { value: 'conservative', label: '保守' },
  { value: 'baseline', label: '基准' },
  { value: 'optimistic', label: '乐观' },
];

const MARKET_OPTIONS: Array<{ value: FiveLayerMarket; label: string }> = [
  { value: 'cn', label: 'A股' },
  { value: 'hk', label: '港股' },
  { value: 'us', label: '美股' },
];

function toDateInputValue(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function defaultRange(): { from: string; to: string } {
  const today = new Date();
  const from = new Date(today);
  from.setDate(today.getDate() - 30);
  return { from: toDateInputValue(from), to: toDateInputValue(today) };
}

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

function formatDateTime(value?: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function statusBadge(status?: string | null) {
  switch (status) {
    case 'completed':
      return <Badge variant="success">已完成</Badge>;
    case 'running':
    case 'started':
      return <Badge variant="warning">运行中</Badge>;
    case 'failed':
    case 'error':
      return <Badge variant="danger">失败</Badge>;
    default:
      return <Badge variant="default">{status || '--'}</Badge>;
  }
}

const RunSummaryCard: React.FC<{ run: BacktestRunResponse }> = ({ run }) => (
  <Card variant="gradient" padding="md">
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        <div className="label-uppercase">当前运行</div>
        <div className="mt-1 break-all font-mono text-xs text-cyan">{run.backtestRunId}</div>
      </div>
      {statusBadge(run.status)}
    </div>
    <div className="space-y-2 text-sm">
      <div className="flex items-center justify-between">
        <span className="text-secondary-text">日期区间</span>
        <span className="font-mono text-foreground">{run.tradeDateFrom} - {run.tradeDateTo}</span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-secondary-text">样本数</span>
        <span className="font-mono text-foreground">{run.sampleCount}</span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-secondary-text">完成数</span>
        <span className="font-mono text-foreground">{run.completedCount}</span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-secondary-text">错误数</span>
        <span className="font-mono text-foreground">{run.errorCount}</span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-secondary-text">完成时间</span>
        <span className="font-mono text-foreground">{formatDateTime(run.completedAt)}</span>
      </div>
    </div>
  </Card>
);

const EmptySection: React.FC<{ title: string; hint: string }> = ({ title, hint }) => (
  <Card title={title} variant="gradient">
    <p className="text-sm text-secondary-text">{hint}</p>
  </Card>
);

const BacktestPage: React.FC = () => {
  const range = defaultRange();
  const [tradeDateFrom, setTradeDateFrom] = useState(range.from);
  const [tradeDateTo, setTradeDateTo] = useState(range.to);
  const [evaluationMode, setEvaluationMode] = useState<FiveLayerEvaluationMode>('historical_snapshot');
  const [executionModel, setExecutionModel] = useState<FiveLayerExecutionModel>('conservative');
  const [market, setMarket] = useState<FiveLayerMarket>('cn');
  const [evalDays, setEvalDays] = useState('10');
  const [generateRecommendations, setGenerateRecommendations] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [runError, setRunError] = useState<ParsedApiError | null>(null);
  const [pageError, setPageError] = useState<ParsedApiError | null>(null);
  const [runResult, setRunResult] = useState<BacktestRunResponse | null>(null);
  const [summaries, setSummaries] = useState<BacktestSummaryItem[]>([]);
  const [evaluations, setEvaluations] = useState<BacktestResultItem[]>([]);
  const [rankingEffectiveness, setRankingEffectiveness] = useState<RankingEffectivenessData | null>(null);

  useEffect(() => {
    document.title = '五层回测 - 每日股票分析';
  }, []);

  const loadRunArtifacts = useCallback(async (runId: string, payload?: BacktestFullPipelineResponse) => {
    try {
      const [run, summaryResponse, resultsResponse, rankingResponse] = await Promise.all([
        payload ? Promise.resolve(payload.run) : backtestApi.getRunDetail(runId),
        payload ? Promise.resolve({ backtestRunId: runId, items: payload.summaries }) : backtestApi.getSummaries(runId),
        backtestApi.getResults({ backtestRunId: runId, page: 1, limit: 200 }),
        backtestApi.getRankingEffectiveness(runId),
      ]);
      setRunResult(run);
      setSummaries(summaryResponse.items || []);
      setEvaluations(resultsResponse.items || []);
      setRankingEffectiveness(rankingResponse);
      setPageError(null);
    } catch (error) {
      setPageError(getParsedApiError(error));
    }
  }, []);

  const handleRun = async () => {
    setIsRunning(true);
    setRunError(null);
    try {
      const payload = await backtestApi.run({
        tradeDateFrom,
        tradeDateTo,
        evaluationMode,
        executionModel,
        market,
        evalWindowDays: parseInt(evalDays || '10', 10),
        generateRecommendations,
      });
      await loadRunArtifacts(payload.run.backtestRunId, payload);
    } catch (error) {
      setRunError(getParsedApiError(error));
    } finally {
      setIsRunning(false);
    }
  };

  const handleRefresh = async () => {
    if (!runResult) return;
    setIsRefreshing(true);
    await loadRunArtifacts(runResult.backtestRunId);
    setIsRefreshing(false);
  };

  const overallSummary = useMemo(
    () => summaries.find((item) => item.groupType === 'overall') ?? null,
    [summaries],
  );
  const strategySummaries = useMemo(
    () => summaries.filter((item) => item.groupType === 'setup_type'),
    [summaries],
  );
  const tradeStageSummaries = useMemo(
    () => summaries.filter((item) => item.groupType === 'trade_stage'),
    [summaries],
  );
  const maturitySummaries = useMemo(
    () => summaries.filter((item) => item.groupType === 'entry_maturity'),
    [summaries],
  );
  const entrySignalQuality = useMemo(() => {
    const entryItems = evaluations.filter((item) => item.signalFamily === 'entry' && item.signalQualityScore != null);
    if (entryItems.length === 0) return null;
    return entryItems.reduce((sum, item) => sum + (item.signalQualityScore ?? 0), 0) / entryItems.length;
  }, [evaluations]);

  return (
    <div className="min-h-full space-y-4">
      <header className="rounded-3xl border border-white/8 bg-card/50 p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-foreground">五层回测</h1>
            <p className="mt-1 text-sm text-secondary-text">按方案重构为体检卡、策略拆解、判断验证和个股明细四层结构。</p>
          </div>
          {runResult ? (
            <button type="button" className="btn-secondary" onClick={() => void handleRefresh()} disabled={isRefreshing || isRunning}>
              {isRefreshing ? '刷新中...' : '刷新运行'}
            </button>
          ) : null}
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <input type="date" value={tradeDateFrom} onChange={(event) => setTradeDateFrom(event.target.value)} className="input-terminal w-full" />
          <input type="date" value={tradeDateTo} onChange={(event) => setTradeDateTo(event.target.value)} className="input-terminal w-full" />
          <div className="rounded-2xl border border-white/8 bg-white/5 px-3 py-2">
            <label className="mb-1 block text-xs text-secondary-text">评估模式</label>
            <select value={evaluationMode} onChange={(event) => setEvaluationMode(event.target.value as FiveLayerEvaluationMode)} className="w-full bg-transparent text-sm outline-none">
              {EVALUATION_MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value} className="bg-base text-foreground">{option.label}</option>
              ))}
            </select>
          </div>
          <div className="rounded-2xl border border-white/8 bg-white/5 px-3 py-2">
            <label className="mb-1 block text-xs text-secondary-text">执行模型</label>
            <select value={executionModel} onChange={(event) => setExecutionModel(event.target.value as FiveLayerExecutionModel)} className="w-full bg-transparent text-sm outline-none">
              {EXECUTION_MODEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value} className="bg-base text-foreground">{option.label}</option>
              ))}
            </select>
          </div>
          <div className="rounded-2xl border border-white/8 bg-white/5 px-3 py-2">
            <label className="mb-1 block text-xs text-secondary-text">市场</label>
            <select value={market} onChange={(event) => setMarket(event.target.value as FiveLayerMarket)} className="w-full bg-transparent text-sm outline-none">
              {MARKET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value} className="bg-base text-foreground">{option.label}</option>
              ))}
            </select>
          </div>
          <div className="rounded-2xl border border-white/8 bg-white/5 px-3 py-2">
            <label className="mb-1 block text-xs text-secondary-text">评估窗口</label>
            <input type="number" min={1} max={120} value={evalDays} onChange={(event) => setEvalDays(event.target.value)} className="w-full bg-transparent text-sm outline-none" />
          </div>
          <label className="flex items-center gap-2 rounded-2xl border border-white/8 bg-white/5 px-3 py-2 text-sm text-secondary-text">
            <input type="checkbox" checked={generateRecommendations} onChange={(event) => setGenerateRecommendations(event.target.checked)} />
            生成建议
          </label>
          <button type="button" className="btn-primary" onClick={() => void handleRun()} disabled={isRunning}>
            {isRunning ? '运行中...' : '运行五层回测'}
          </button>
        </div>

        {runError ? <ApiErrorAlert error={runError} className="mt-3" /> : null}
      </header>

      {pageError ? <ApiErrorAlert error={pageError} /> : null}

      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-4">
          {runResult ? <RunSummaryCard run={runResult} /> : null}
          {overallSummary ? (
            <Card variant="gradient">
              <div className="label-uppercase">快速摘要</div>
              <div className="mt-4 grid gap-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-secondary-text">综合评分</span>
                  <span className="font-mono text-foreground">{overallSummary.systemGrade || '--'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-secondary-text">盈亏比</span>
                  <span className="font-mono text-foreground">{overallSummary.profitFactor?.toFixed(2) ?? '--'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-secondary-text">判断准确率</span>
                  <span className="font-mono text-foreground">{pct(overallSummary.stageAccuracyRate != null ? overallSummary.stageAccuracyRate * 100 : null)}</span>
                </div>
              </div>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          {overallSummary ? (
            <SystemScorecard summary={overallSummary} signalQualityScore={entrySignalQuality} />
          ) : (
            <EmptySection title="系统体检" hint="运行回测后，这里会显示系统总体评分和 KPI。" />
          )}

          {strategySummaries.length > 0 ? (
            <StrategyComparison summaries={strategySummaries} />
          ) : (
            <EmptySection title="策略拆解" hint="回测完成后会按 setup_type 展示策略优劣。" />
          )}

          {(tradeStageSummaries.length > 0 || maturitySummaries.length > 0 || strategySummaries.length > 0) ? (
            <JudgmentValidation
              tradeStageSummaries={tradeStageSummaries}
              maturitySummaries={maturitySummaries}
              setupTypeSummaries={strategySummaries}
              rankingEffectiveness={rankingEffectiveness}
            />
          ) : (
            <EmptySection title="判断验证" hint="这里会展示交易阶段、成熟度和 MAE 精度验证。" />
          )}

          {evaluations.length > 0 ? (
            <EvaluationDetail evaluations={evaluations} isLoading={isRunning || isRefreshing} />
          ) : (
            <EmptySection title="个股明细" hint="回测完成后，这里会显示入场信号和观察信号明细。" />
          )}
        </div>
      </div>
    </div>
  );
};

export default BacktestPage;
