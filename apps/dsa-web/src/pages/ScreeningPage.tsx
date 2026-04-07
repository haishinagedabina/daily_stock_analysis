import type React from 'react';
import { useEffect } from 'react';
import { AppPage, PageHeader } from '../components/common';
import { ScreeningControlBar } from '../components/screening/ScreeningControlBar';
import { ScreeningRunPanel } from '../components/screening/ScreeningRunPanel';
import { DecisionContextSection } from '../components/screening/DecisionContextSection';
import { ScreeningCandidateTable } from '../components/screening/ScreeningCandidateTable';
import { CandidateDetailDrawer } from '../components/screening/CandidateDetailDrawer';
import { useScreeningStore } from '../stores/screeningStore';
import { isTerminalStatus } from '../types/screening';

const ScreeningPage: React.FC = () => {
  const fetchRunHistory = useScreeningStore((s) => s.fetchRunHistory);
  const currentRun = useScreeningStore((s) => s.currentRun);
  const candidates = useScreeningStore((s) => s.candidates);

  useEffect(() => {
    void fetchRunHistory();
  }, [fetchRunHistory]);

  const showContext =
    currentRun != null &&
    isTerminalStatus(currentRun.status) &&
    (currentRun.decisionContext != null || candidates.length > 0);

  return (
    <AppPage>
      <div className="flex flex-col gap-5">
        <PageHeader
          eyebrow="SCREENING"
          title="智能选股"
          description="基于五层决策引擎的全市场筛选，支持市场环境门控、板块热度分析与 AI 二次分析"
        />
        <ScreeningControlBar />
        <ScreeningRunPanel />
        {showContext && (
          <DecisionContextSection
            context={currentRun.decisionContext}
            candidates={candidates}
          />
        )}
        <ScreeningCandidateTable />
      </div>
      <CandidateDetailDrawer />
    </AppPage>
  );
};

export default ScreeningPage;
