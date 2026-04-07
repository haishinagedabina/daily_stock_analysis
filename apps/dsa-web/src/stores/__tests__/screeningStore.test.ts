import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useScreeningStore } from '../screeningStore';
import type { ScreeningRun } from '../../types/screening';

vi.mock('../../api/screening', () => ({
  screeningApi: {
    getStrategies: vi.fn(),
    createRun: vi.fn(),
    listRuns: vi.fn(),
    getRun: vi.fn(),
    getCandidates: vi.fn(),
    getCandidateDetail: vi.fn(),
    notifyRun: vi.fn(),
    deleteRun: vi.fn(),
  },
}));

const { screeningApi } = await import('../../api/screening');

describe('screeningStore', () => {
  beforeEach(() => {
    useScreeningStore.setState({
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
      blockingDialog: null,
    });
    vi.clearAllMocks();
  });

  describe('config actions', () => {
    it('setMode updates mode', () => {
      useScreeningStore.getState().setMode('aggressive');
      expect(useScreeningStore.getState().mode).toBe('aggressive');
    });

    it('setCandidateLimit updates limit', () => {
      useScreeningStore.getState().setCandidateLimit(50);
      expect(useScreeningStore.getState().candidateLimit).toBe(50);
    });
  });

  describe('startScreening', () => {
    it('blocks local start and opens dialog before 15:00 on today trade date', async () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2026-03-18T06:30:00.000Z'));
      useScreeningStore.setState({ tradeDate: '2026-03-18' });

      await useScreeningStore.getState().startScreening();

      expect(screeningApi.createRun).not.toHaveBeenCalled();
      expect(useScreeningStore.getState().blockingDialog).toMatchObject({
        title: expect.stringContaining('今日'),
      });
      vi.useRealTimers();
    });

    it('sets isRunning and calls createRun', async () => {
      vi.mocked(screeningApi.createRun).mockResolvedValue({
        runId: 'run-1',
        status: 'pending',
        universeSize: 0,
        candidateCount: 0,
        aiTopK: 5,
        tradeDate: '2026-03-17',
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
      expect(useScreeningStore.getState().tradeDate).toBe('2026-03-17');
    });

    it('shows a pending placeholder immediately before createRun resolves', async () => {
      const holder: { resolve: ((value: ScreeningRun) => void) | null } = { resolve: null };

      vi.mocked(screeningApi.createRun).mockReturnValue(
        new Promise((resolve) => {
          holder.resolve = resolve;
        }),
      );

      useScreeningStore.setState({
        currentRun: {
          runId: 'run-old',
          status: 'completed',
          universeSize: 5000,
          candidateCount: 5,
          aiTopK: 2,
          failedSymbols: [],
          warnings: [],
          syncFailureRatio: 0,
          configSnapshot: {},
          notificationAttempts: 0,
        },
        candidates: [{ code: '600519' } as never],
      });

      const startPromise = useScreeningStore.getState().startScreening();

      expect(useScreeningStore.getState().currentRun).toMatchObject({
        runId: 'pending-local-run',
        status: 'pending',
        candidateCount: 0,
        aiTopK: 2,
      });
      expect(useScreeningStore.getState().candidates).toEqual([]);

      holder.resolve?.({
        runId: 'run-new',
        status: 'pending',
        universeSize: 0,
        candidateCount: 0,
        aiTopK: 2,
        failedSymbols: [],
        warnings: [],
        syncFailureRatio: 0,
        configSnapshot: {},
        notificationAttempts: 0,
      });

      await startPromise;

      expect(useScreeningStore.getState().currentRun).toMatchObject({
        runId: 'run-new',
        status: 'pending',
      });
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
      const latestRun: ScreeningRun = {
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
      const inProgressRun: ScreeningRun = {
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

  describe('deleteRun', () => {
    it('removes a deleted current run and clears related state', async () => {
      vi.mocked(screeningApi.deleteRun).mockResolvedValue({
        success: true,
        message: 'ok',
      });
      useScreeningStore.setState({
        currentRun: {
          runId: 'run-1',
          status: 'failed',
          universeSize: 0,
          candidateCount: 0,
          aiTopK: 0,
          failedSymbols: [],
          warnings: [],
          syncFailureRatio: 0,
          configSnapshot: {},
          notificationAttempts: 0,
        },
        runHistory: [
          {
            runId: 'run-1',
            status: 'failed',
            universeSize: 0,
            candidateCount: 0,
            aiTopK: 0,
            failedSymbols: [],
            warnings: [],
            syncFailureRatio: 0,
            configSnapshot: {},
            notificationAttempts: 0,
          },
          {
            runId: 'run-2',
            status: 'completed',
            universeSize: 10,
            candidateCount: 1,
            aiTopK: 0,
            failedSymbols: [],
            warnings: [],
            syncFailureRatio: 0,
            configSnapshot: {},
            notificationAttempts: 0,
          },
        ],
        candidates: [{ code: '600519' } as never],
        selectedCandidate: { code: '600519' } as never,
      });

      await useScreeningStore.getState().deleteRun('run-1');

      expect(screeningApi.deleteRun).toHaveBeenCalledWith('run-1');
      expect(useScreeningStore.getState().currentRun).toBeNull();
      expect(useScreeningStore.getState().runHistory.map((run) => run.runId)).toEqual(['run-2']);
      expect(useScreeningStore.getState().candidates).toEqual([]);
      expect(useScreeningStore.getState().selectedCandidate).toBeNull();
    });
  });
});
