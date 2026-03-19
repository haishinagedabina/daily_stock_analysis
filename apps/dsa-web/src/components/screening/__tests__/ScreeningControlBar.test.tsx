import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ScreeningControlBar } from '../ScreeningControlBar';

const mockStore = {
  strategies: [
    { name: 'volume_breakout', displayName: '放量突破', description: 'd', category: 'trend', hasScreeningRules: true },
    { name: 'bottom_volume', displayName: '底部放量', description: 'd', category: 'reversal', hasScreeningRules: true },
    { name: 'legacy', displayName: '旧策略', description: 'd', category: 'trend', hasScreeningRules: false },
  ],
  strategiesLoading: false,
  selectedStrategies: ['volume_breakout'],
  setSelectedStrategies: vi.fn(),
  mode: 'balanced' as const,
  setMode: vi.fn(),
  tradeDate: '2026-03-18',
  setTradeDate: vi.fn(),
  candidateLimit: 30,
  setCandidateLimit: vi.fn(),
  aiTopK: 5,
  setAiTopK: vi.fn(),
  isRunning: false,
  startScreening: vi.fn().mockResolvedValue(undefined),
  reset: vi.fn(),
};

vi.mock('../../../stores/screeningStore', () => ({
  useScreeningStore: () => mockStore,
}));

describe('ScreeningControlBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.selectedStrategies = ['volume_breakout'];
  });

  it('renders strategy tags', () => {
    render(<ScreeningControlBar />);
    expect(screen.getByText('放量突破')).toBeInTheDocument();
    expect(screen.getByText('底部放量')).toBeInTheDocument();
    expect(screen.getByText('旧策略')).toBeInTheDocument();
  });

  it('shows start button', () => {
    render(<ScreeningControlBar />);
    expect(screen.getByRole('button', { name: /开始筛选/ })).toBeInTheDocument();
  });

  it('disables start button when no strategies selected', () => {
    mockStore.selectedStrategies = [];
    render(<ScreeningControlBar />);
    expect(screen.getByRole('button', { name: /开始筛选/ })).toBeDisabled();
  });

  it('shows reset button', () => {
    render(<ScreeningControlBar />);
    expect(screen.getByRole('button', { name: /重置/ })).toBeInTheDocument();
  });

  it('shows loading state when running', () => {
    mockStore.isRunning = true;
    render(<ScreeningControlBar />);
    expect(screen.getByRole('button', { name: /筛选中/ })).toBeDisabled();
    mockStore.isRunning = false;
  });

  it('renders mode select', () => {
    render(<ScreeningControlBar />);
    expect(screen.getByLabelText('筛选模式')).toBeInTheDocument();
  });

  it('renders date input', () => {
    render(<ScreeningControlBar />);
    expect(screen.getByLabelText('交易日')).toBeInTheDocument();
  });
});
