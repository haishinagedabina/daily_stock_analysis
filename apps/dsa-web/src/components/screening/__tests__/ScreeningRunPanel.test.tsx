import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ScreeningRunPanel } from '../ScreeningRunPanel';
import type { ScreeningRun } from '../../../types/screening';

const baseRun: ScreeningRun = {
  runId: 'run-1',
  status: 'completed',
  universeSize: 5000,
  candidateCount: 30,
  aiTopK: 5,
  failedSymbols: [],
  warnings: [],
  syncFailureRatio: 0.02,
  configSnapshot: {},
  notificationAttempts: 0,
  tradeDate: '2026-03-18',
  startedAt: '2026-03-18T10:00:00Z',
};

const defaultStore = {
  currentRun: null as ScreeningRun | null,
  isRunning: false,
  runHistory: [] as ScreeningRun[],
  historyLoading: false,
  selectRun: vi.fn(),
  deleteRun: vi.fn(),
  clearRunHistory: vi.fn(),
};

vi.mock('../../../stores/screeningStore', () => ({
  useScreeningStore: () => defaultStore,
}));

describe('ScreeningRunPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    defaultStore.currentRun = null;
    defaultStore.runHistory = [];
    defaultStore.historyLoading = false;
    defaultStore.isRunning = false;
  });

  it('shows empty state when no run', () => {
    render(<ScreeningRunPanel />);
    expect(screen.getByText('暂无运行中的筛选')).toBeInTheDocument();
  });

  it('shows progress bar when run is active', () => {
    defaultStore.currentRun = { ...baseRun, status: 'screening' };
    render(<ScreeningRunPanel />);
    expect(screen.getByTestId('screening-progress-bar')).toBeInTheDocument();
  });

  it('shows run stats when completed', () => {
    defaultStore.currentRun = baseRun;
    render(<ScreeningRunPanel />);
    expect(screen.getByText('5000')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
  });

  it('shows error summary when present', () => {
    defaultStore.currentRun = { ...baseRun, status: 'failed', errorSummary: 'timeout error' };
    render(<ScreeningRunPanel />);
    expect(screen.getByText('timeout error')).toBeInTheDocument();
  });

  it('shows fused theme pipeline summary when present', () => {
    defaultStore.currentRun = {
      ...baseRun,
      fusedThemePipeline: {
        activeSources: ['local', 'external'],
        selectedThemeNames: ['AI芯片', '机器人概念'],
        mergedThemeCount: 2,
        mergedThemes: [],
      },
    };
    render(<ScreeningRunPanel />);
    expect(screen.getByText('题材管道')).toBeInTheDocument();
    expect(screen.getByText('AI芯片、机器人概念')).toBeInTheDocument();
    expect(screen.getByText('2 个融合题材')).toBeInTheDocument();
  });

  it('shows history list', () => {
    defaultStore.runHistory = [baseRun];
    render(<ScreeningRunPanel />);
    expect(screen.getByTestId('run-history-list')).toBeInTheDocument();
    expect(screen.getByTestId('run-history-run-1')).toBeInTheDocument();
  });

  it('shows loading for history', () => {
    defaultStore.historyLoading = true;
    render(<ScreeningRunPanel />);
    expect(screen.getByText('加载历史...')).toBeInTheDocument();
  });

  it('shows empty history message', () => {
    defaultStore.historyLoading = false;
    defaultStore.runHistory = [];
    render(<ScreeningRunPanel />);
    expect(screen.getByText('暂无历史记录')).toBeInTheDocument();
  });

  it('deletes a run from history when delete button is clicked', () => {
    defaultStore.runHistory = [baseRun];
    render(<ScreeningRunPanel />);

    fireEvent.click(screen.getByTestId('delete-run-run-1'));

    expect(defaultStore.deleteRun).toHaveBeenCalledWith('run-1');
  });
});
