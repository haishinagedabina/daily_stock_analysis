import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { CandidateDetailDrawer } from '../CandidateDetailDrawer';
import type { ScreeningCandidateDetail } from '../../../types/screening';

const mockCandidate: ScreeningCandidateDetail = {
  code: '600519',
  name: '贵州茅台',
  rank: 1,
  ruleScore: 85.5,
  selectedForAi: true,
  ruleHits: ['volume_surge', 'ma_crossover'],
  factorSnapshot: { close: 1800.5, volume_ratio: 2.3, pct_chg: 3.5 },
  matchedStrategies: ['volume_breakout', 'ma_golden_cross'],
  aiSummary: '该股近期放量突破，趋势向好',
  aiOperationAdvice: '建议逢低布局',
  finalScore: 92.0,
};

const mockStore = {
  selectedCandidate: null as ScreeningCandidateDetail | null,
  clearSelectedCandidate: vi.fn(),
};

vi.mock('../../../stores/screeningStore', () => ({
  useScreeningStore: () => mockStore,
}));

describe('CandidateDetailDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.selectedCandidate = null;
  });

  it('renders nothing when no candidate selected', () => {
    const { container } = render(<CandidateDetailDrawer />);
    expect(container.querySelector('[data-testid="candidate-detail"]')).toBeNull();
  });

  it('renders candidate detail when selected', () => {
    mockStore.selectedCandidate = mockCandidate;
    render(<CandidateDetailDrawer />);
    expect(screen.getByTestId('candidate-detail')).toBeInTheDocument();
  });

  it('shows rank badge', () => {
    mockStore.selectedCandidate = mockCandidate;
    render(<CandidateDetailDrawer />);
    expect(screen.getByText('排名 #1')).toBeInTheDocument();
  });

  it('shows rule score badge', () => {
    mockStore.selectedCandidate = mockCandidate;
    render(<CandidateDetailDrawer />);
    expect(screen.getByText('规则评分: 85.5')).toBeInTheDocument();
  });

  it('shows rule hits', () => {
    mockStore.selectedCandidate = mockCandidate;
    render(<CandidateDetailDrawer />);
    expect(screen.getByText('volume_surge')).toBeInTheDocument();
    expect(screen.getByText('ma_crossover')).toBeInTheDocument();
  });

  it('shows factor snapshot', () => {
    mockStore.selectedCandidate = mockCandidate;
    render(<CandidateDetailDrawer />);
    expect(screen.getByText('close')).toBeInTheDocument();
    expect(screen.getByText('1800.50')).toBeInTheDocument();
  });

  it('shows AI summary', () => {
    mockStore.selectedCandidate = mockCandidate;
    render(<CandidateDetailDrawer />);
    expect(screen.getByText('该股近期放量突破，趋势向好')).toBeInTheDocument();
  });

  it('shows AI operation advice', () => {
    mockStore.selectedCandidate = mockCandidate;
    render(<CandidateDetailDrawer />);
    expect(screen.getByText('建议逢低布局')).toBeInTheDocument();
  });

  it('shows matched strategies', () => {
    mockStore.selectedCandidate = mockCandidate;
    render(<CandidateDetailDrawer />);
    expect(screen.getByText('volume_breakout')).toBeInTheDocument();
    expect(screen.getByText('ma_golden_cross')).toBeInTheDocument();
  });
});
