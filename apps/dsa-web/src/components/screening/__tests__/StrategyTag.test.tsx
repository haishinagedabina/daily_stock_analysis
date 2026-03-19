import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StrategyTag } from '../StrategyTag';

describe('StrategyTag', () => {
  it('renders name and category label', () => {
    render(<StrategyTag name="放量突破" category="trend" />);
    expect(screen.getByText('放量突破')).toBeInTheDocument();
    expect(screen.getByText('(趋势)')).toBeInTheDocument();
  });

  it('applies active styling', () => {
    const { container } = render(<StrategyTag name="放量突破" category="trend" active />);
    const btn = container.querySelector('button');
    expect(btn?.className).toContain('text-blue-400');
  });

  it('is disabled when disabled prop is set', () => {
    render(<StrategyTag name="旧策略" category="trend" disabled />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('calls onClick handler', () => {
    const onClick = vi.fn();
    render(<StrategyTag name="放量突破" category="trend" onClick={onClick} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
