import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  BacktestRunRequest,
  BacktestFullPipelineResponse,
  BacktestRecommendationsResponse,
  RankingEffectivenessData,
  BacktestRunResponse,
  BacktestSummariesResponse,
  BacktestResultsResponse,
  BacktestResultItem,
} from '../types/backtest';

const DEFAULT_PAGE_SIZE = 20;

function normalizeEvaluationItem(item: Record<string, unknown>): BacktestResultItem {
  const normalized = toCamelCase<Record<string, unknown>>(item) as Record<string, unknown> & Partial<BacktestResultItem> & {
    forwardReturn1D?: number | null;
    forwardReturn3D?: number | null;
    forwardReturn5D?: number | null;
    forwardReturn10D?: number | null;
  };
  return {
    ...(normalized as unknown as BacktestResultItem),
    forwardReturn1d: (normalized.forwardReturn1d ?? normalized.forwardReturn1D ?? null) as number | null,
    forwardReturn3d: (normalized.forwardReturn3d ?? normalized.forwardReturn3D ?? null) as number | null,
    forwardReturn5d: (normalized.forwardReturn5d ?? normalized.forwardReturn5D ?? null) as number | null,
    forwardReturn10d: (normalized.forwardReturn10d ?? normalized.forwardReturn10D ?? null) as number | null,
  };
}

export const backtestApi = {
  run: async (params: BacktestRunRequest): Promise<BacktestFullPipelineResponse> => {
    const requestData: Record<string, unknown> = {
      trade_date_from: params.tradeDateFrom,
      trade_date_to: params.tradeDateTo,
      evaluation_mode: params.evaluationMode ?? 'historical_snapshot',
      execution_model: params.executionModel ?? 'conservative',
      market: params.market ?? 'cn',
      eval_window_days: params.evalWindowDays ?? 10,
      generate_recommendations: params.generateRecommendations ?? true,
    };

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/five-layer-backtest/run',
      requestData,
    );
    return toCamelCase<BacktestFullPipelineResponse>(response.data);
  },

  getResults: async (params: {
    backtestRunId: string;
    signalFamily?: string;
    page?: number;
    limit?: number;
  }): Promise<BacktestResultsResponse> => {
    const {
      backtestRunId,
      signalFamily,
      page = 1,
      limit = DEFAULT_PAGE_SIZE,
    } = params;

    const queryParams: Record<string, string | number> = { page, limit };
    if (signalFamily) queryParams.signal_family = signalFamily;

    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/five-layer-backtest/runs/${encodeURIComponent(backtestRunId)}/evaluations`,
      { params: queryParams },
    );

    const data = toCamelCase<BacktestResultsResponse>(response.data);
    return {
      backtestRunId: data.backtestRunId,
      total: data.total,
      page: data.page,
      limit: data.limit,
      items: (data.items || []).map((item) => normalizeEvaluationItem(item as unknown as Record<string, unknown>)),
    };
  },

  getRunDetail: async (backtestRunId: string): Promise<BacktestRunResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/five-layer-backtest/runs/${encodeURIComponent(backtestRunId)}`,
    );
    return toCamelCase<BacktestRunResponse>(response.data);
  },

  getSummaries: async (
    backtestRunId: string,
    groupType?: string,
  ): Promise<BacktestSummariesResponse> => {
    const params: Record<string, string> = {};
    if (groupType) params.group_type = groupType;

    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/five-layer-backtest/runs/${encodeURIComponent(backtestRunId)}/summaries`,
      { params },
    );
    return toCamelCase<BacktestSummariesResponse>(response.data);
  },

  getRecommendations: async (
    backtestRunId: string,
    recommendationLevel?: string,
  ): Promise<BacktestRecommendationsResponse> => {
    const params: Record<string, string> = {};
    if (recommendationLevel) params.recommendation_level = recommendationLevel;

    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/five-layer-backtest/runs/${encodeURIComponent(backtestRunId)}/recommendations`,
      { params },
    );
    return toCamelCase<BacktestRecommendationsResponse>(response.data);
  },

  getRankingEffectiveness: async (
    backtestRunId: string,
  ): Promise<RankingEffectivenessData> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/five-layer-backtest/runs/${encodeURIComponent(backtestRunId)}/ranking-effectiveness`,
    );
    return toCamelCase<RankingEffectivenessData>(response.data);
  },
};
