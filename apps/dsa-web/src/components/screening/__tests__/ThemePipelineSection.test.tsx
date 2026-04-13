import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ThemePipelineSection } from '../ThemePipelineSection';
import type { ScreeningRun } from '../../../types/screening';

const baseRun: ScreeningRun = {
  runId: 'run-theme-1',
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

describe('ThemePipelineSection', () => {
  it('returns null when no theme pipeline snapshots exist', () => {
    const { container } = render(<ThemePipelineSection run={baseRun} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders fused theme pipeline summary', () => {
    render(
      <ThemePipelineSection
        run={{
          ...baseRun,
          fusedThemePipeline: {
            activeSources: ['local', 'external'],
            selectedThemeNames: ['AI芯片', '机器人概念'],
            mergedThemeCount: 2,
            mergedThemes: [
              {
                name: 'AI芯片',
                rawNames: ['AI芯片', '算力芯片'],
                matchedSources: ['local', 'external'],
                prioritySource: 'local',
                heatScore: 92,
                confidence: 0.9,
              },
            ],
          },
        }}
      />,
    );

    expect(screen.getByText('题材管道详情')).toBeInTheDocument();
    expect(screen.getByText('融合结果')).toBeInTheDocument();
    expect(screen.getByText('AI芯片、机器人概念')).toBeInTheDocument();
    expect(screen.getByText('local + external')).toBeInTheDocument();
    expect(screen.getByText('原始题材: AI芯片、算力芯片')).toBeInTheDocument();
  });

  it('expands local and external pipeline panels', () => {
    render(
      <ThemePipelineSection
        run={{
          ...baseRun,
          localThemePipeline: {
            source: 'local',
            hotThemeCount: 1,
            warmThemeCount: 1,
            selectedThemeNames: ['机器人概念'],
            themes: [
              {
                name: '机器人概念',
                rawName: '机器人',
                sourceBoard: '机器人',
                sectorStatus: 'warm',
                sectorStage: 'expand',
                stockCount: 15,
              },
            ],
          },
          externalThemePipeline: {
            source: 'openclaw',
            acceptedThemeCount: 1,
            hotThemeCount: 1,
            focusThemeCount: 0,
            topThemeNames: ['AI芯片'],
            themes: [
              {
                name: 'AI芯片',
                rawName: '算力芯片',
                confidence: 0.91,
                keywords: ['算力', '芯片'],
              },
            ],
          },
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /本地题材管道/i }));
    expect(screen.getAllByText('机器人概念').length).toBeGreaterThan(0);
    expect(screen.getByText('板块: 机器人')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /外部题材管道/i }));
    expect(screen.getByText('原始题材: 算力芯片')).toBeInTheDocument();
    expect(screen.getByText('关键词: 算力、芯片')).toBeInTheDocument();
  });
});
