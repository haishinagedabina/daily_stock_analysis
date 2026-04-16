import type { BacktestResultItem } from '../../types/backtest';

export type ResearchSampleFocus = 'all' | 'abnormal' | 'timing_issue' | 'validation_risk' | 'noise_boundary';

export function getEvaluationAbnormalTags(item: BacktestResultItem): string[] {
  const tags: string[] = [];
  if (item.sampleBucket === 'noise' || item.sampleBucket === 'boundary') {
    tags.push('noise_boundary');
  }
  if (item.entryTimingLabel === 'too_early' || item.entryTimingLabel === 'too_late') {
    tags.push('timing_issue');
  }
  if (item.ma100Low123ValidationStatus != null && item.ma100Low123ValidationStatus !== 'confirmed') {
    tags.push('validation_risk');
  }
  if (tags.length > 0) {
    tags.push('abnormal');
  }
  return tags;
}

export function matchesResearchSampleFocus(
  item: BacktestResultItem,
  focus: ResearchSampleFocus,
): boolean {
  if (focus === 'all') {
    return true;
  }
  return getEvaluationAbnormalTags(item).includes(focus);
}

export function getPrimaryResearchSampleFocus(
  item: BacktestResultItem,
): ResearchSampleFocus {
  const tags = getEvaluationAbnormalTags(item);
  if (tags.includes('timing_issue')) {
    return 'timing_issue';
  }
  if (tags.includes('validation_risk')) {
    return 'validation_risk';
  }
  if (tags.includes('noise_boundary')) {
    return 'noise_boundary';
  }
  if (tags.includes('abnormal')) {
    return 'abnormal';
  }
  return 'all';
}
