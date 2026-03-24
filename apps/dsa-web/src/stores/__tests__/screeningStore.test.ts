import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useScreeningStore } from '../screeningStore';

vi.mock('../../api/screening', () => ({
  screeningApi: {
    getStrategies: vi.fn(),
    createRun: vi.fn(),
    listRuns: vi.fn(),
    getRun: vi.fn(),
    getCandidates: vi.fn(),
    getCandidateDetail: vi.fn(),
    notifyRun: vi.fn(),
  },
}));

const { screeningApi } = await import('../../api/screening');

describe('screeningStore', () => {
  beforeEach(() => {
    useScreeningStore.setState({
      strategies: [],
      strategiesLoading: false,
      selectedStrategies: [],
      mode: 'balanced',
      candidateLimit: 5,
      aiTopK: 2,
      tradeDate: '2026-03-18',
      currentRun: null,
      isRunning: false,
      pollingTimer: null,
      runHistory: [],
      historyLoading: false,
      candidates: [],
      candidatesLoading: false,
      selectedCandidate: null,
      error: null,
    });
    vi.clearAllMocks();
  });

  describe('fetchStrategies', () => {
    it('loads strategies without auto-selecting any by default', async () => {
      vi.mocked(screeningApi.getStrategies).mockResolvedValue({
        strategies: [
          { name: 'volume_breakout', displayName: '放量突破', description: 'desc', category: 'trend', hasScreeningRules: true },
          { name: 'legacy_strat', displayName: '旧策略', description: 'desc', category: 'trend', hasScreeningRules: false },
        ],
      });

      await useScreeningStore.getState().fetchStrategies();
      const state = useScreeningStore.getState();

      expect(state.strategies).toHaveLength(2);
      expect(state.selectedStrategies).toEqual([]);
      expect(state.strategiesLoading).toBe(false);
    });
  });

  describe('config actions', () => {
    it('setMode updates mode', () => {
      useScreeningStore.getState().setMode('aggressive');
      expect(useScreeningStore.getState().mode).toBe('aggressive');
    });

    it('setSelectedStrategies updates selection', () => {
      useScreeningStore.getState().setSelectedStrategies(['a', 'b']);
      expect(useScreeningStore.getState().selectedStrategies).toEqual(['a', 'b']);
    });

    it('setCandidateLimit updates limit', () => {
      useScreeningStore.getState().setCandidateLimit(50);
      expect(useScreeningStore.getState().candidateLimit).toBe(50);
    });
  });

  describe('startScreening', () => {
    it('sets isRunning and calls createRun', async () => {
      vi.mocked(screeningApi.createRun).mockResolvedValue({
        runId: 'run-1',
        status: 'pending',
        universeSize: 0,
        candidateCount: 0,
        aiTopK: 5,
        failedSymbols: [],
        warnings: [],
        syncFailureRatio: 0,
        configSnapshot: {},
        notificationAttempts: 0,
      });
      vi.mocked(screeningApi.getRun).mockResolvedValue({
        runId: 'run-1',
        status: 'completed',
        universeSize: 5000,
        candidateCount: 30,
        aiTopK: 5,
        failedSymbols: [],
        warnings: [],
        syncFailureRatio: 0,
        configSnapshot: {},
        notificationAttempts: 0,
      });
      vi.mocked(screeningApi.listRuns).mockResolvedValue({ total: 0, items: [] });
      vi.mocked(screeningApi.getCandidates).mockResolvedValue({ total: 0, items: [] });

      await useScreeningStore.getState().startScreening();

      expect(screeningApi.createRun).toHaveBeenCalled();
      expect(useScreeningStore.getState().currentRun).not.toBeNull();
    });
  });

  describe('fetchRunHistory', () => {
    it('loads run history', async () => {
      vi.mocked(screeningApi.listRuns).mockResolvedValue({
        total: 1,
        items: [{
          runId: 'run-1',
          status: 'completed',
          universeSize: 5000,
          candidateCount: 30,
          aiTopK: 5,
          failedSymbols: [],
          warnings: [],
          syncFailureRatio: 0,
          configSnapshot: {},
          notificationAttempts: 0,
        }],
      });

      await useScreeningStore.getState().fetchRunHistory();
      expect(useScreeningStore.getState().runHistory).toHaveLength(1);
      expect(useScreeningStore.getState().historyLoading).toBe(false);
    });

    it('hydrates currentRun from the latest history item when empty', async () => {
      const latestRun = {
        runId: 'run-latest',
        status: 'completed',
        universeSize: 5000,
        candidateCount: 5,
        aiTopK: 2,
        failedSymbols: [],
        warnings: [],
        syncFailureRatio: 0,
        configSnapshot: {},
        notificationAttempts: 0,
      };
      vi.mocked(screeningApi.listRuns).mockResolvedValue({
        total: 1,
        items: [latestRun],
      });

      await useScreeningStore.getState().fetchRunHistory();

      expect(useScreeningStore.getState().currentRun).toEqual(latestRun);
    });

    it('resumes polling when the latest history item is still running', async () => {
      const inProgressRun = {
        runId: 'run-active',
        status: 'screening',
        universeSize: 5000,
        candidateCount: 3,
        aiTopK: 2,
        failedSymbols: [],
        warnings: [],
        syncFailureRatio: 0,
        configSnapshot: {},
        notificationAttempts: 0,
      };
      vi.mocked(screeningApi.listRuns).mockResolvedValue({
        total: 1,
        items: [inProgressRun],
      });
      const pollSpy = vi.spyOn(useScreeningStore.getState(), 'pollRunStatus');

      await useScreeningStore.getState().fetchRunHistory();

      expect(pollSpy).toHaveBeenCalledWith('run-active');
    });
  });

  describe('fetchCandidates', () => {
    it('loads candidates for a run', async () => {
      vi.mocked(screeningApi.getCandidates).mockResolvedValue({
        total: 2,
        items: [
          { code: '600519', name: '贵州茅台', rank: 1, ruleScore: 85, selectedForAi: true, ruleHits: [], factorSnapshot: {} },
          { code: '000858', name: '五粮液', rank: 2, ruleScore: 72, selectedForAi: false, ruleHits: [], factorSnapshot: {} },
        ],
      });

      await useScreeningStore.getState().fetchCandidates('run-1');
      expect(useScreeningStore.getState().candidates).toHaveLength(2);
    });
  });

  describe('reset', () => {
    it('clears run state', () => {
      useScreeningStore.setState({ isRunning: true, currentRun: { runId: 'r1' } as never });
      useScreeningStore.getState().reset();

      const state = useScreeningStore.getState();
      expect(state.isRunning).toBe(false);
      expect(state.currentRun).toBeNull();
      expect(state.candidates).toEqual([]);
    });
  });
});
