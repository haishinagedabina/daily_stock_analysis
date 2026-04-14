# -*- coding: utf-8 -*-
"""Five-layer backtest system package.

Replaces the legacy advice-based backtest with a run-based evaluation
system built on screening_candidates and five-layer decision fields.

Subpackages:
  - models: ORM tables (Run, Evaluation, GroupSummary, Calibration, Recommendation)
  - repositories: CRUD for each table
  - classifiers: SignalClassifier (trade_stage → signal_family)
  - execution: ExecutionModelResolver (conservative/baseline/optimistic)
  - evaluators: Entry / Observation / Exit signal evaluators
  - aggregators: Group summary, ranking effectiveness, stability metrics
  - recommendations: Graded recommendation engine with evidence chains
  - services: FiveLayerBacktestService orchestration
"""
