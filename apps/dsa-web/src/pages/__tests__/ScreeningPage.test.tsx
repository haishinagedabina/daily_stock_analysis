import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import ScreeningPage from '../ScreeningPage';

vi.mock('../../stores/screeningStore', () => {
  const store = {
    strategies: [],
    strategiesLoading: false,
    selectedStrategies: [],
    mode: 'balanced' as const,
    candidateLimit: 30,
    aiTopK: 5,
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
    fetchStrategies: vi.fn(),
    fetchRunHistory: vi.fn(),
    setSelectedStrategies: vi.fn(),
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
  return {
    useScreeningStore: (selector?: (state: typeof store) => unknown) =>
      selector ? selector(store) : store,
  };
});

describe('ScreeningPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders page header with title', () => {
    render(<ScreeningPage />);
    expect(screen.getByText('智能选股')).toBeInTheDocument();
  });

  it('renders screening eyebrow label', () => {
    render(<ScreeningPage />);
    expect(screen.getByText('SCREENING')).toBeInTheDocument();
  });

  it('renders control bar', () => {
    render(<ScreeningPage />);
    expect(screen.getByText('筛选配置')).toBeInTheDocument();
  });

  it('renders run panel', () => {
    render(<ScreeningPage />);
    expect(screen.getByTestId('screening-run-panel')).toBeInTheDocument();
  });

  it('calls fetchStrategies and fetchRunHistory on mount', async () => {
    const { useScreeningStore } = await import('../../stores/screeningStore');
    render(<ScreeningPage />);
    const store = useScreeningStore() as unknown as Record<string, unknown>;
    expect(store.fetchStrategies).toBeDefined();
    expect(store.fetchRunHistory).toBeDefined();
  });
});
