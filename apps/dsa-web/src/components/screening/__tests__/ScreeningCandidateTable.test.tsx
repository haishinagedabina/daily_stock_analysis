import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ScreeningCandidateTable } from '../ScreeningCandidateTable';
import type { ScreeningCandidate, ScreeningRun } from '../../../types/screening';

const mockRun: ScreeningRun = {
  runId: 'run-1',
  status: 'completed',
  universeSize: 5000,
  candidateCount: 2,
  aiTopK: 5,
  failedSymbols: [],
  warnings: [],
  syncFailureRatio: 0,
  configSnapshot: {},
  notificationAttempts: 0,
};

const mockCandidates: ScreeningCandidate[] = [
  {
    code: '600519',
    name: '贵州茅台',
    rank: 1,
    ruleScore: 85.5,
    selectedForAi: true,
    ruleHits: ['volume_surge'],
    factorSnapshot: {},
    matchedStrategies: ['volume_breakout'],
    finalScore: 92.0,
  },
  {
    code: '000858',
    name: '五粮液',
    rank: 2,
    ruleScore: 72.3,
    selectedForAi: false,
    ruleHits: [],
    factorSnapshot: {},
    matchedStrategies: [],
  },
];

const mockStore = {
  currentRun: mockRun as ScreeningRun | null,
  candidates: mockCandidates as ScreeningCandidate[],
  candidatesLoading: false,
  selectCandidate: vi.fn(),
  sendNotification: vi.fn(),
};

vi.mock('../../../stores/screeningStore', () => ({
  useScreeningStore: () => mockStore,
}));

describe('ScreeningCandidateTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.currentRun = mockRun;
    mockStore.candidates = mockCandidates;
  });

  it('renders nothing when no current run', () => {
    mockStore.currentRun = null;
    mockStore.candidates = [];
    const { container } = render(<ScreeningCandidateTable />);
    expect(container.innerHTML).toBe('');
  });

  it('renders candidate rows', () => {
    render(<ScreeningCandidateTable />);
    expect(screen.getByTestId('candidate-row-600519')).toBeInTheDocument();
    expect(screen.getByTestId('candidate-row-000858')).toBeInTheDocument();
  });

  it('shows stock code and name', () => {
    render(<ScreeningCandidateTable />);
    expect(screen.getByText('600519')).toBeInTheDocument();
    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
  });

  it('shows rule score', () => {
    render(<ScreeningCandidateTable />);
    expect(screen.getByText('85.5')).toBeInTheDocument();
    expect(screen.getByText('72.3')).toBeInTheDocument();
  });

  it('shows matched strategy badges', () => {
    render(<ScreeningCandidateTable />);
    expect(screen.getByText('volume_breakout')).toBeInTheDocument();
  });

  it('shows total count', () => {
    render(<ScreeningCandidateTable />);
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });

  it('has view detail button for each row', () => {
    render(<ScreeningCandidateTable />);
    const buttons = screen.getAllByLabelText(/查看.*详情/);
    expect(buttons).toHaveLength(2);
  });

  it('calls selectCandidate when view button is clicked', () => {
    render(<ScreeningCandidateTable />);
    const btn = screen.getByLabelText('查看 600519 详情');
    fireEvent.click(btn);
    expect(mockStore.selectCandidate).toHaveBeenCalledWith('run-1', '600519');
  });

  it('shows notification button for completed runs', () => {
    render(<ScreeningCandidateTable />);
    expect(screen.getByRole('button', { name: /推送通知/ })).toBeInTheDocument();
  });
});
