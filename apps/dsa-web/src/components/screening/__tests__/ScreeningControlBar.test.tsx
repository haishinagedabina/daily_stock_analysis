import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ScreeningControlBar } from '../ScreeningControlBar';

const mockStore = {
  strategies: [
    { name: 'volume_breakout', displayName: '放量突破', description: 'd', category: 'trend', hasScreeningRules: true },
    { name: 'bottom_volume', displayName: '底部放量', description: 'd', category: 'reversal', hasScreeningRules: true },
    { name: 'legacy', displayName: '旧策略', description: 'd', category: 'trend', hasScreeningRules: false },
  ],
  strategiesLoading: false,
  selectedStrategies: [] as string[],
  setSelectedStrategies: vi.fn(),
  mode: 'balanced' as const,
  setMode: vi.fn(),
  tradeDate: '2026-03-18',
  setTradeDate: vi.fn(),
  candidateLimit: 5,
  setCandidateLimit: vi.fn(),
  aiTopK: 2,
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
    mockStore.selectedStrategies = [];
    mockStore.isRunning = false;
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
  });

  it('renders mode select', () => {
    render(<ScreeningControlBar />);
    expect(screen.getByLabelText('筛选模式')).toBeInTheDocument();
  });

  it('renders date input', () => {
    render(<ScreeningControlBar />);
    expect(screen.getByLabelText('交易日')).toBeInTheDocument();
  });

  it('uses the new default candidate and AI limits', () => {
    render(<ScreeningControlBar />);
    expect(document.getElementById('candidate-limit')).toHaveValue(5);
    expect(document.getElementById('ai-top-k')).toHaveValue(2);
  });
});
