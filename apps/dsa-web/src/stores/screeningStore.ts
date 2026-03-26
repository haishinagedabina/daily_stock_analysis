import { create } from "zustand";
import { screeningApi } from "../api/screening";
import type { ParsedApiError } from "../api/error";
import { createParsedApiError, getParsedApiError } from "../api/error";
import type {
  ScreeningCandidate,
  ScreeningCandidateDetail,
  ScreeningMode,
  ScreeningRun,
  ScreeningStrategy,
} from "../types/screening";
import { isTerminalStatus, TARGET_STRATEGIES } from "../types/screening";
import {
  buildTodayScreeningBlockDialog,
  getTodayInShanghai,
} from "../utils/screeningTradeDate";

interface ScreeningBlockingDialog {
  title: string;
  message: string;
}

interface ScreeningState {
  // strategies
  strategies: ScreeningStrategy[];
  strategiesLoading: boolean;

  // config
  selectedStrategies: string[];
  mode: ScreeningMode;
  candidateLimit: number;
  aiTopK: number;
  tradeDate: string;

  // run state
  currentRun: ScreeningRun | null;
  isRunning: boolean;
  pollingTimer: ReturnType<typeof setInterval> | null;

  // history
  runHistory: ScreeningRun[];
  historyLoading: boolean;

  // candidates
  candidates: ScreeningCandidate[];
  candidatesLoading: boolean;
  selectedCandidate: ScreeningCandidateDetail | null;

  // errors
  error: ParsedApiError | null;
  blockingDialog: ScreeningBlockingDialog | null;

  // actions
  fetchStrategies: () => Promise<void>;
  setSelectedStrategies: (names: string[]) => void;
  setMode: (mode: ScreeningMode) => void;
  setCandidateLimit: (limit: number) => void;
  setAiTopK: (k: number) => void;
  setTradeDate: (date: string) => void;
  startScreening: () => Promise<void>;
  pollRunStatus: (runId: string) => void;
  stopPolling: () => void;
  fetchRunHistory: () => Promise<void>;
  clearRunHistory: () => Promise<void>;
  deleteRun: (runId: string) => Promise<void>;
  selectRun: (run: ScreeningRun) => Promise<void>;
  fetchCandidates: (runId: string) => Promise<void>;
  selectCandidate: (runId: string, code: string) => Promise<void>;
  clearSelectedCandidate: () => void;
  sendNotification: (runId: string, force?: boolean) => Promise<void>;
  setError: (error: ParsedApiError | null) => void;
  clearBlockingDialog: () => void;
  reset: () => void;
}

const today = () => getTodayInShanghai();

export const useScreeningStore = create<ScreeningState>((set, get) => ({
  strategies: [],
  strategiesLoading: false,
  selectedStrategies: [],
  mode: "balanced",
  candidateLimit: 5,
  aiTopK: 2,
  tradeDate: today(),
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

  fetchStrategies: async () => {
    set({ strategiesLoading: true });
    try {
      const data = await screeningApi.getStrategies();
      const backendNames = new Set(
        data.strategies
          .filter((s) => s.hasScreeningRules)
          .map((s) => s.name),
      );
      // Show only the 4 target strategies; mark as enabled only if backend has rules
      const merged = TARGET_STRATEGIES.map((t) => ({
        ...t,
        hasScreeningRules: t.hasScreeningRules && backendNames.has(t.name),
      }));
      set({
        strategies: merged,
        selectedStrategies: [],
        strategiesLoading: false,
      });
    } catch {
      // On API failure, still show target strategies with predefined states
      set({
        strategies: TARGET_STRATEGIES,
        selectedStrategies: [],
        strategiesLoading: false,
      });
    }
  },

  setSelectedStrategies: (names) => set({ selectedStrategies: names }),
  setMode: (mode) => set({ mode }),
  setCandidateLimit: (limit) => set({ candidateLimit: limit }),
  setAiTopK: (k) => set({ aiTopK: k }),
  setTradeDate: (date) => set({ tradeDate: date }),

  startScreening: async () => {
    const { mode, candidateLimit, aiTopK, selectedStrategies, tradeDate } =
      get();
    const blockingDialog = buildTodayScreeningBlockDialog(tradeDate);
    if (blockingDialog) {
      set({
        isRunning: false,
        error: null,
        blockingDialog,
      });
      return;
    }
    set({
      currentRun: {
        runId: "pending-local-run",
        mode,
        status: "pending",
        tradeDate: tradeDate || undefined,
        universeSize: 0,
        candidateCount: 0,
        aiTopK,
        failedSymbols: [],
        warnings: [],
        syncFailureRatio: 0,
        configSnapshot: {
          mode,
          candidate_limit: candidateLimit,
          ai_top_k: aiTopK,
          strategies: selectedStrategies,
        },
        notificationAttempts: 0,
      },
      isRunning: true,
      candidates: [],
      selectedCandidate: null,
      error: null,
      blockingDialog: null,
    });
    try {
      const run = await screeningApi.createRun({
        mode,
        candidateLimit,
        aiTopK,
        strategies:
          selectedStrategies.length > 0 ? selectedStrategies : undefined,
        tradeDate: tradeDate || undefined,
      });
      set({
        currentRun: run,
        tradeDate: run.tradeDate || tradeDate,
      });
      get().pollRunStatus(run.runId);
    } catch (err) {
      const parsedError = getParsedApiError(err);
      if (parsedError.category === "screening_trade_time_not_ready") {
        set({
          isRunning: false,
          blockingDialog: {
            title: parsedError.title,
            message: parsedError.message,
          },
          error: null,
        });
        return;
      }
      set({
        isRunning: false,
        error: parsedError,
      });
    }
  },

  pollRunStatus: (runId) => {
    get().stopPolling();
    let pollCount = 0;
    let consecutiveErrors = 0;
    const MAX_POLLS = 200;
    const timer = setInterval(async () => {
      pollCount++;
      if (pollCount > MAX_POLLS) {
        get().stopPolling();
        set({
          isRunning: false,
          error: createParsedApiError({
            title: "轮询超时",
            message: "轮询超时，请刷新页面重试",
            category: "unknown",
          }),
        });
        return;
      }
      try {
        const run = await screeningApi.getRun(runId);
        consecutiveErrors = 0;
        set({ currentRun: run });
        if (isTerminalStatus(run.status)) {
          get().stopPolling();
          set({ isRunning: false });
          if (run.status !== "failed") {
            get().fetchCandidates(runId);
          }
          get().fetchRunHistory();
        }
      } catch {
        consecutiveErrors++;
        if (consecutiveErrors >= 3) {
          get().stopPolling();
          set({ isRunning: false });
          void get().fetchRunHistory();
        }
      }
    }, 30000);
    set({ pollingTimer: timer, isRunning: true });
  },

  stopPolling: () => {
    const { pollingTimer } = get();
    if (pollingTimer) {
      clearInterval(pollingTimer);
      set({ pollingTimer: null });
    }
  },

  fetchRunHistory: async () => {
    set({ historyLoading: true });
    try {
      const data = await screeningApi.listRuns(20);
      const latestRun = data.items[0] ?? null;
      const currentRun = get().currentRun;
      const nextCurrentRun =
        latestRun && (!currentRun || currentRun.runId === latestRun.runId)
          ? latestRun
          : currentRun;

      set({
        runHistory: data.items,
        currentRun: nextCurrentRun,
        historyLoading: false,
        isRunning: nextCurrentRun ? !isTerminalStatus(nextCurrentRun.status) : false,
      });

      if (
        nextCurrentRun &&
        !isTerminalStatus(nextCurrentRun.status) &&
        get().pollingTimer == null
      ) {
        get().pollRunStatus(nextCurrentRun.runId);
      }
    } catch {
      set({ historyLoading: false });
    }
  },

  selectRun: async (run) => {
    set({ currentRun: run, candidates: [], selectedCandidate: null });
    if (isTerminalStatus(run.status) && run.status !== "failed") {
      await get().fetchCandidates(run.runId);
    }
  },

  clearRunHistory: async () => {
    try {
      await screeningApi.clearRuns();
      set({
        runHistory: [],
        currentRun: null,
        candidates: [],
        selectedCandidate: null,
        isRunning: false,
      });
      get().stopPolling();
    } catch (err) {
      set({
        error:
          (err as { parsedApiError?: ParsedApiError }).parsedApiError || null,
      });
    }
  },

  deleteRun: async (runId) => {
    try {
      await screeningApi.deleteRun(runId);
      const { currentRun, pollingTimer, runHistory } = get();
      const deletingCurrentRun = currentRun?.runId === runId;

      if (deletingCurrentRun && pollingTimer) {
        get().stopPolling();
      }

      set({
        runHistory: runHistory.filter((run) => run.runId !== runId),
        currentRun: deletingCurrentRun ? null : currentRun,
        candidates: deletingCurrentRun ? [] : get().candidates,
        selectedCandidate: deletingCurrentRun ? null : get().selectedCandidate,
        isRunning: deletingCurrentRun ? false : get().isRunning,
      });
    } catch (err) {
      set({
        error:
          (err as { parsedApiError?: ParsedApiError }).parsedApiError || null,
      });
    }
  },

  fetchCandidates: async (runId) => {
    set({ candidatesLoading: true });
    try {
      const data = await screeningApi.getCandidates(runId);
      set({ candidates: data.items, candidatesLoading: false });
    } catch {
      set({ candidatesLoading: false });
    }
  },

  selectCandidate: async (runId, code) => {
    try {
      const detail = await screeningApi.getCandidateDetail(runId, code);
      set({ selectedCandidate: detail });
    } catch {
      /* ignore */
    }
  },

  clearSelectedCandidate: () => set({ selectedCandidate: null }),

  sendNotification: async (runId, force = false) => {
    try {
      await screeningApi.notifyRun(runId, { force });
      get().fetchRunHistory();
    } catch (err) {
      set({
        error:
          (err as { parsedApiError?: ParsedApiError }).parsedApiError || null,
      });
    }
  },

  setError: (error) => set({ error }),
  clearBlockingDialog: () => set({ blockingDialog: null }),

  reset: () => {
    get().stopPolling();
    set({
      currentRun: null,
      isRunning: false,
      candidates: [],
      selectedCandidate: null,
      error: null,
      blockingDialog: null,
    });
  },
}));
