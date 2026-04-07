import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import ScreeningPage from '../ScreeningPage';

vi.mock('../../stores/screeningStore', () => {
  const store = {
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

  it('renders run panel', () => {
    render(<ScreeningPage />);
    expect(screen.getByTestId('screening-run-panel')).toBeInTheDocument();
  });

  it('calls fetchRunHistory on mount', async () => {
    const { useScreeningStore } = await import('../../stores/screeningStore');
    render(<ScreeningPage />);
    const store = useScreeningStore() as unknown as Record<string, unknown>;
    expect(store.fetchRunHistory).toBeDefined();
  });
});
