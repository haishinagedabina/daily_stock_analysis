import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ScreeningProgressBar } from '../ScreeningProgressBar';

describe('ScreeningProgressBar', () => {
  it('renders status label', () => {
    render(<ScreeningProgressBar status="screening" />);
    const matches = screen.getAllByText('规则筛选');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('shows percentage', () => {
    render(<ScreeningProgressBar status="factorizing" />);
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('shows 100% for completed', () => {
    render(<ScreeningProgressBar status="completed" />);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('renders failed state with danger styling', () => {
    render(<ScreeningProgressBar status="failed" />);
    expect(screen.getByText('失败')).toBeInTheDocument();
  });

  it('renders all stage labels', () => {
    render(<ScreeningProgressBar status="resolving_universe" />);
    expect(screen.getAllByText('解析股票池').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('同步数据')).toBeInTheDocument();
    expect(screen.getByText('构建因子')).toBeInTheDocument();
    expect(screen.getByText('规则筛选')).toBeInTheDocument();
  });
});
