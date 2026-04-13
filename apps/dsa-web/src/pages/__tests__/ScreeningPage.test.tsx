import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import ScreeningPage from '../ScreeningPage';
import type { ScreeningRun } from '../../types/screening';

const store = {
  mode: 'balanced' as const,
  candidateLimit: 30,
  aiTopK: 5,
  tradeDate: '2026-03-18',
  currentRun: null as ScreeningRun | null,
  isRunning: false,
  pollingTimer: null,
  runHistory: [] as ScreeningRun[],
  historyLoading: false,
  candidates: [] as unknown[],
  candidatesLoading: false,
  selectedCandidate: null,
  error: null,
  blockingDialog: null,
  fetchRunHistory: vi.fn(),
  setMode: vi.fn(),
  setCandidateLimit: vi.fn(),
  setAiTopK: vi.fn(),
  setTradeDate: vi.fn(),
  startScreening: vi.fn(),
  reset: vi.fn(),
  selectRun: vi.fn(),
  fetchCandidates: vi.fn(),
  selectCandidate: vi.fn(),
  clearSelectedCandidate: vi.fn(),
  sendNotification: vi.fn(),
  pollRunStatus: vi.fn(),
  stopPolling: vi.fn(),
  setError: vi.fn(),
  clearBlockingDialog: vi.fn(),
};

vi.mock('../../stores/screeningStore', () => {
  return {
    useScreeningStore: (selector?: (state: typeof store) => unknown) =>
      selector ? selector(store) : store,
  };
});

describe('ScreeningPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    store.currentRun = null;
    store.isRunning = false;
    store.runHistory = [];
    store.historyLoading = false;
    store.candidates = [];
  });

  it('renders page header with title', () => {
    render(<ScreeningPage />);
    expect(screen.getByText('智能选股')).toBeInTheDocument();
  });

  it('renders screening eyebrow label', () => {
    render(<ScreeningPage />);
    expect(screen.getByText('SCREENING')).toBeInTheDocument();
  });

  it('renders run panel', () => {
    render(<ScreeningPage />);
    expect(screen.getByTestId('screening-run-panel')).toBeInTheDocument();
  });

  it('calls fetchRunHistory on mount', async () => {
    const { useScreeningStore } = await import('../../stores/screeningStore');
    render(<ScreeningPage />);
    const store = useScreeningStore() as unknown as Record<string, unknown>;
    expect(store.fetchRunHistory).toBeDefined();
    expect(store.fetchRunHistory).toHaveBeenCalledTimes(1);
  });

  it('renders theme pipeline section for terminal runs with theme snapshots', async () => {
    store.currentRun = {
      runId: 'run-theme-page',
      status: 'completed',
      universeSize: 5000,
      candidateCount: 12,
      aiTopK: 5,
      failedSymbols: [],
      warnings: [],
      syncFailureRatio: 0,
      configSnapshot: {},
      notificationAttempts: 0,
      fusedThemePipeline: {
        activeSources: ['local'],
        selectedThemeNames: ['机器人概念'],
        mergedThemeCount: 1,
        mergedThemes: [],
      },
    };

    render(<ScreeningPage />);
    expect(screen.getByTestId('theme-pipeline-section')).toBeInTheDocument();
    expect(screen.getByText('题材管道详情')).toBeInTheDocument();
  });

  it('does not render theme pipeline section for non-terminal runs', () => {
    store.currentRun = {
      runId: 'run-theme-running',
      status: 'screening',
      universeSize: 5000,
      candidateCount: 12,
      aiTopK: 5,
      failedSymbols: [],
      warnings: [],
      syncFailureRatio: 0,
      configSnapshot: {},
      notificationAttempts: 0,
      fusedThemePipeline: {
        activeSources: ['local'],
        selectedThemeNames: ['机器人概念'],
        mergedThemeCount: 1,
        mergedThemes: [],
      },
    };

    render(<ScreeningPage />);
    expect(screen.queryByTestId('theme-pipeline-section')).not.toBeInTheDocument();
  });
});
