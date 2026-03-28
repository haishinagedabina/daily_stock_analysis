/**
 * 筛选模块类型定义
 * 与后端 API Schema 对齐
 */

// ============ 策略 ============

export interface ScreeningStrategy {
  name: string;
  displayName: string;
  description: string;
  category: 'trend' | 'pattern' | 'reversal' | 'framework';
  hasScreeningRules: boolean;
}

export interface ScreeningStrategyListResponse {
  strategies: ScreeningStrategy[];
}

// ============ 筛选运行 ============

export type ScreeningMode = 'balanced' | 'aggressive' | 'quality';

export type ScreeningRunStatus =
  | 'pending'
  | 'resolving_universe'
  | 'ingesting'
  | 'factorizing'
  | 'screening'
  | 'ai_enriching'
  | 'completed'
  | 'completed_with_ai_degraded'
  | 'failed';

export interface CreateScreeningRunRequest {
  tradeDate?: string;
  stockCodes?: string[];
  mode?: ScreeningMode;
  candidateLimit?: number;
  aiTopK?: number;
  strategies?: string[];
  rerunFailed?: boolean;
  resumeFrom?: 'ingesting' | 'factorizing';
  market?: string;
}

export interface ScreeningRun {
  runId: string;
  mode?: string;
  status: ScreeningRunStatus;
  tradeDate?: string;
  market?: string;
  universeSize: number;
  candidateCount: number;
  aiTopK: number;
  errorSummary?: string;
  failedSymbols: string[];
  warnings: string[];
  syncFailureRatio: number;
  configSnapshot: Record<string, unknown>;
  startedAt?: string;
  completedAt?: string;
  triggerType?: string;
  notificationStatus?: string;
  notificationAttempts: number;
  notificationSentAt?: string;
  notificationError?: string;
  strategyNames?: string[];
}

export interface ScreeningRunListResponse {
  total: number;
  items: ScreeningRun[];
}

// ============ 候选 ============

export interface ScreeningCandidate {
  code: string;
  name?: string;
  rank: number;
  ruleScore: number;
  selectedForAi: boolean;
  ruleHits: string[];
  factorSnapshot: Record<string, unknown>;
  aiQueryId?: string;
  aiSummary?: string;
  aiOperationAdvice?: string;
  hasAiAnalysis?: boolean;
  newsCount?: number;
  newsSummary?: string;
  recommendationSource?: string;
  recommendationReason?: string;
  finalScore?: number;
  finalRank?: number;
  matchedStrategies?: string[];
}

export interface ScreeningCandidateListResponse {
  total: number;
  items: ScreeningCandidate[];
}

export interface ScreeningCandidateDetail extends ScreeningCandidate {
  analysisHistory?: {
    id?: number;
    queryId: string;
    stockCode: string;
    stockName?: string;
    reportType?: string;
    operationAdvice?: string;
    trendPrediction?: string;
    sentimentScore?: number;
    analysisSummary?: string;
    createdAt?: string;
  };
}

// ============ 通知 ============

export interface ScreeningNotifyRequest {
  limit?: number;
  withAiOnly?: boolean;
  force?: boolean;
}

// ============ 辅助 ============

export const SCREENING_STAGES: ScreeningRunStatus[] = [
  'resolving_universe',
  'ingesting',
  'factorizing',
  'screening',
  'ai_enriching',
  'completed',
];

export const STAGE_LABELS: Record<string, string> = {
  pending: '等待中',
  resolving_universe: '解析股票池',
  ingesting: '同步数据',
  factorizing: '构建因子',
  screening: '规则筛选',
  ai_enriching: 'AI 分析',
  completed: '已完成',
  completed_with_ai_degraded: '已完成(AI降级)',
  failed: '失败',
};

export const CATEGORY_LABELS: Record<string, string> = {
  trend: '趋势',
  pattern: '形态',
  reversal: '反转',
  framework: '框架',
};

export const CATEGORY_COLORS: Record<string, string> = {
  trend: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  pattern: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  reversal: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  framework: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
};

/**
 * The 4 target strategies for the consolidated screening page.
 * Strategies not yet implemented are shown as disabled (hasScreeningRules=false).
 */
export const TARGET_STRATEGIES: ScreeningStrategy[] = [
  {
    name: 'bottom_divergence_double_breakout',
    displayName: '底背离双突破',
    description: '基于DIF/DEA六形态底背离 + 下降趋势线/水平阻力线双突破确认',
    category: 'reversal',
    hasScreeningRules: true,
  },
  {
    name: 'ma100_low123_combined',
    displayName: 'MA100+低位123结构',
    description: '站上MA100均线 + 低位123底部反转形态联合确认',
    category: 'reversal',
    hasScreeningRules: true,
  },
  {
    name: 'ma100_60min_combined',
    displayName: 'MA100+60分钟线',
    description: '日线站上MA100 + 60分钟级别入场信号联合确认',
    category: 'trend',
    hasScreeningRules: true,
  },
  {
    name: 'extreme_momentum_combined',
    displayName: '极端强势组合',
    description: '涨停突破/缺口突破等极端强势形态联合策略',
    category: 'trend',
    hasScreeningRules: false,
  },
];

export function getStageIndex(status: ScreeningRunStatus): number {
  const idx = SCREENING_STAGES.indexOf(status);
  return idx >= 0 ? idx : 0;
}

export function isTerminalStatus(status: ScreeningRunStatus): boolean {
  return ['completed', 'completed_with_ai_degraded', 'failed'].includes(status);
}
