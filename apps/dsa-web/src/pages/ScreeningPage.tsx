import type React from 'react';
import { useEffect } from 'react';
import { AppPage, PageHeader } from '../components/common';
import { ScreeningControlBar } from '../components/screening/ScreeningControlBar';
import { ScreeningRunPanel } from '../components/screening/ScreeningRunPanel';
import { ScreeningCandidateTable } from '../components/screening/ScreeningCandidateTable';
import { CandidateDetailDrawer } from '../components/screening/CandidateDetailDrawer';
import { useScreeningStore } from '../stores/screeningStore';

const ScreeningPage: React.FC = () => {
  const fetchStrategies = useScreeningStore((s) => s.fetchStrategies);
  const fetchRunHistory = useScreeningStore((s) => s.fetchRunHistory);

  useEffect(() => {
    void fetchStrategies();
    void fetchRunHistory();
  }, [fetchStrategies, fetchRunHistory]);

  return (
    <AppPage>
      <div className="flex flex-col gap-5">
        <PageHeader
          eyebrow="SCREENING"
          title="智能选股"
          description="基于策略引擎的全市场筛选，支持多维因子过滤与 AI 二次分析"
        />
        <ScreeningControlBar />
        <ScreeningRunPanel />
        <ScreeningCandidateTable />
      </div>
      <CandidateDetailDrawer />
    </AppPage>
  );
};

export default ScreeningPage;
