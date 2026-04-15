/**
 * Five-layer backtest API type definitions
 * Mirrors api/v1/schemas/five_layer_backtest.py
 */

export type FiveLayerEvaluationMode =
  | 'historical_snapshot'
  | 'rule_replay'
  | 'parameter_calibration';

export type FiveLayerExecutionModel =
  | 'conservative'
  | 'baseline'
  | 'optimistic';

export type FiveLayerMarket = 'cn' | 'us' | 'hk';

export interface BacktestRunRequest {
  evaluationMode?: FiveLayerEvaluationMode;
  executionModel?: FiveLayerExecutionModel;
  tradeDateFrom: string;
  tradeDateTo: string;
  market?: FiveLayerMarket;
  evalWindowDays?: number;
  generateRecommendations?: boolean;
}

export interface BacktestRunResponse {
  backtestRunId: string;
  evaluationMode: string;
  executionModel: string;
  tradeDateFrom?: string | null;
  tradeDateTo?: string | null;
  market: string;
  status: string;
  sampleCount: number;
  completedCount: number;
  errorCount: number;
  dataVersion?: string | null;
  marketDataVersion?: string | null;
  themeMappingVersion?: string | null;
  candidateSnapshotVersion?: string | null;
  rulesVersion?: string | null;
  createdAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
}

export interface BacktestResultItem {
  id?: number | null;
  backtestRunId: string;
  tradeDate?: string | null;
  code: string;
  name?: string | null;
  signalFamily: string;
  signalType?: string | null;
  evaluatorType: string;
  evaluationMode?: string | null;
  executionModel?: string | null;
  snapshotSource?: string | null;
  replayed?: boolean | null;
  snapshotTradeStage?: string | null;
  snapshotSetupType?: string | null;
  snapshotEntryMaturity?: string | null;
  snapshotMarketRegime?: string | null;
  snapshotThemePosition?: string | null;
  snapshotCandidatePoolLevel?: string | null;
  snapshotRiskLevel?: string | null;
  entryFillStatus?: string | null;
  entryFillPrice?: number | null;
  exitFillPrice?: number | null;
  limitBlocked?: boolean | null;
  gapAdjusted?: boolean | null;
  forwardReturn1d?: number | null;
  forwardReturn3d?: number | null;
  forwardReturn5d?: number | null;
  forwardReturn10d?: number | null;
  mae?: number | null;
  mfe?: number | null;
  maxDrawdownFromPeak?: number | null;
  holdingDays?: number | null;
  planSuccess?: boolean | null;
  signalQualityScore?: number | null;
  riskAvoidedPct?: number | null;
  opportunityCostPct?: number | null;
  outcome?: string | null;
  stageSuccess?: boolean | null;
  evalStatus?: string | null;
  factorSnapshotJson?: string | null;
  tradePlanJson?: string | null;
}

export interface BacktestResultsResponse {
  backtestRunId: string;
  total: number;
  page: number;
  limit: number;
  items: BacktestResultItem[];
}

export interface BacktestSummaryItem {
  groupType: string;
  groupKey: string;
  sampleCount: number;
  avgReturnPct?: number | null;
  medianReturnPct?: number | null;
  winRatePct?: number | null;
  avgMae?: number | null;
  avgMfe?: number | null;
  avgDrawdown?: number | null;
  topKHitRate?: number | null;
  excessReturnPct?: number | null;
  rankingConsistency?: number | null;
  p25ReturnPct?: number | null;
  p75ReturnPct?: number | null;
  extremeSampleRatio?: number | null;
  timeBucketStability?: number | null;
  profitFactor?: number | null;
  avgHoldingDays?: number | null;
  maxConsecutiveLosses?: number | null;
  planExecutionRate?: number | null;
  stageAccuracyRate?: number | null;
  systemGrade?: string | null;
}

export interface BacktestSummariesResponse {
  backtestRunId: string;
  items: BacktestSummaryItem[];
}

export interface BacktestRecommendationItem {
  recommendationType: string;
  targetScope?: string | null;
  targetKey?: string | null;
  currentRule?: string | null;
  suggestedChange?: string | null;
  recommendationLevel: string;
  sampleCount?: number | null;
  confidence?: number | null;
  validationStatus?: string | null;
  evidenceJson?: string | null;
}

export interface BacktestRecommendationsResponse {
  backtestRunId: string;
  items: BacktestRecommendationItem[];
}

export interface BacktestFullPipelineResponse {
  run: BacktestRunResponse;
  summaries: BacktestSummaryItem[];
  recommendations: BacktestRecommendationItem[];
}

export interface RankingComparisonItem {
  dimension: string;
  tierHigh: string;
  tierLow: string;
  highAvgReturn?: number | null;
  lowAvgReturn?: number | null;
  excessReturnPct?: number | null;
  highWinRate?: number | null;
  lowWinRate?: number | null;
  highSampleCount: number;
  lowSampleCount: number;
  isEffective: boolean;
}

export interface RankingEffectivenessData {
  comparisons: RankingComparisonItem[];
  overallEffectivenessRatio: number;
  topKHitRate?: number | null;
  excessReturnPct?: number | null;
  rankingConsistency?: number | null;
}
