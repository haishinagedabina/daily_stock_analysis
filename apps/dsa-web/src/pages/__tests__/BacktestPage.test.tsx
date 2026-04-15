import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BacktestPage from '../BacktestPage';

const runResponse = {
  run: {
    backtestRunId: 'flbt-test123456',
    evaluationMode: 'historical_snapshot',
    executionModel: 'conservative',
    tradeDateFrom: '2026-03-01',
    tradeDateTo: '2026-03-31',
    market: 'cn',
    status: 'completed',
    sampleCount: 20,
    completedCount: 20,
    errorCount: 0,
    createdAt: '2026-04-01T10:00:00',
    completedAt: '2026-04-01T10:05:00',
  },
  summaries: [
    {
      groupType: 'overall',
      groupKey: 'all',
      sampleCount: 20,
      avgReturnPct: 2.3,
      winRatePct: 60,
      avgDrawdown: -2.1,
      profitFactor: 1.8,
      avgHoldingDays: 4.2,
      planExecutionRate: 0.65,
      stageAccuracyRate: 0.7,
      systemGrade: 'A',
      timeBucketStability: 0.1,
    },
    {
      groupType: 'setup_type',
      groupKey: 'trend_breakout',
      sampleCount: 10,
      avgReturnPct: 3.1,
      winRatePct: 65,
      avgMae: -1.8,
      profitFactor: 2.2,
      planExecutionRate: 0.7,
      systemGrade: 'A',
    },
    {
      groupType: 'trade_stage',
      groupKey: 'probe_entry',
      sampleCount: 8,
      avgReturnPct: 2.8,
      winRatePct: 62.5,
      stageAccuracyRate: 0.75,
    },
    {
      groupType: 'entry_maturity',
      groupKey: 'HIGH',
      sampleCount: 6,
      avgReturnPct: 3.5,
      winRatePct: 66.7,
    },
  ],
  recommendations: [],
};

const resultsResponse = {
  backtestRunId: 'flbt-test123456',
  total: 2,
  page: 1,
  limit: 20,
  items: [
    {
      id: 1,
      backtestRunId: 'flbt-test123456',
      code: '600519',
      name: '贵州茅台',
      tradeDate: '2026-03-15',
      signalFamily: 'entry',
      evaluatorType: 'entry',
      signalType: 'buy',
      snapshotTradeStage: 'probe_entry',
      snapshotSetupType: 'trend_breakout',
      entryFillPrice: 1800,
      forwardReturn5d: 2.5,
      forwardReturn10d: 4.1,
      mae: -1.2,
      mfe: 5.6,
      outcome: 'win',
      planSuccess: true,
      signalQualityScore: 0.78,
      factorSnapshotJson: '{"ma100_breakout_days":3}',
      tradePlanJson: '{"take_profit":5,"stop_loss":-3}',
      evalStatus: 'evaluated',
    },
    {
      id: 2,
      backtestRunId: 'flbt-test123456',
      code: '000001',
      name: '平安银行',
      tradeDate: '2026-03-16',
      signalFamily: 'observation',
      evaluatorType: 'observation',
      snapshotTradeStage: 'watch',
      riskAvoidedPct: 3.2,
      opportunityCostPct: 1.1,
      stageSuccess: true,
      outcome: 'correct_wait',
      factorSnapshotJson: '{"low_123_state":"structure_only"}',
      tradePlanJson: '{}',
      evalStatus: 'evaluated',
    },
  ],
};

const rankingResponse = {
  comparisons: [
    {
      dimension: 'entry_maturity',
      tierHigh: 'HIGH',
      tierLow: 'LOW',
      highAvgReturn: 3.5,
      lowAvgReturn: 1.2,
      excessReturnPct: 2.3,
      highWinRate: 66.7,
      lowWinRate: 45,
      highSampleCount: 6,
      lowSampleCount: 4,
      isEffective: true,
    },
  ],
  overallEffectivenessRatio: 0.75,
  topKHitRate: 0.6,
  excessReturnPct: 1.2,
  rankingConsistency: 0.8,
};

const apiMock = vi.hoisted(() => ({
  run: vi.fn(),
  getResults: vi.fn(),
  getRunDetail: vi.fn(),
  getSummaries: vi.fn(),
  getRecommendations: vi.fn(),
  getRankingEffectiveness: vi.fn(),
}));

vi.mock('../../api/backtest', () => ({
  backtestApi: apiMock,
}));

vi.mock('../../api/error', () => ({
  getParsedApiError: vi.fn((error: unknown) => error),
}));

describe('BacktestPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.run.mockResolvedValue(runResponse);
    apiMock.getResults.mockResolvedValue(resultsResponse);
    apiMock.getRankingEffectiveness.mockResolvedValue(rankingResponse);
    apiMock.getRunDetail.mockResolvedValue(runResponse.run);
    apiMock.getSummaries.mockResolvedValue({ backtestRunId: 'flbt-test123456', items: runResponse.summaries });
    apiMock.getRecommendations.mockResolvedValue({ backtestRunId: 'flbt-test123456', items: [] });
  });

  it('renders four-layer backtest layout after running a backtest', async () => {
    render(<BacktestPage />);

    fireEvent.click(screen.getByRole('button', { name: /运行五层回测/i }));

    await waitFor(() => {
      expect(apiMock.run).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('系统体检')).toBeInTheDocument();
    expect(screen.getByText('策略拆解')).toBeInTheDocument();
    expect(screen.getByText('判断验证')).toBeInTheDocument();
    expect(screen.getByText('个股明细')).toBeInTheDocument();
    expect(screen.getByText('趋势突破')).toBeInTheDocument();
    expect(screen.getByText('入场信号')).toBeInTheDocument();
  });
});
