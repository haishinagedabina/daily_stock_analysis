import type React from 'react';
import { Shield, TrendingUp, TrendingDown } from 'lucide-react';
import { Card, Badge } from '../common';
import type { MarketEnvironmentSnapshot } from '../../types/screening';
import { MARKET_REGIME_LABELS, MARKET_REGIME_COLORS } from '../../types/screening';

interface MarketEnvironmentCardProps {
  environment?: MarketEnvironmentSnapshot;
}

function RegimeBadge({ regime }: { regime?: string }) {
  if (!regime) return null;
  const label = MARKET_REGIME_LABELS[regime] ?? regime;
  const colorClass = MARKET_REGIME_COLORS[regime] ?? 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${colorClass}`}>
      {label}
    </span>
  );
}

function formatPrice(price?: number): string {
  if (price == null) return '--';
  return price.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function computeDeviation(price?: number, ma100?: number): string {
  if (price == null || ma100 == null || ma100 === 0) return '--';
  const deviation = ((price - ma100) / ma100) * 100;
  return `${deviation >= 0 ? '+' : ''}${deviation.toFixed(1)}%`;
}

export const MarketEnvironmentCard: React.FC<MarketEnvironmentCardProps> = ({ environment }) => {
  if (!environment) {
    return (
      <Card variant="bordered" padding="sm">
        <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
          <Shield className="h-3.5 w-3.5 text-cyan" /> L1 大盘环境
        </h4>
        <p className="text-xs text-secondary-text">暂无数据</p>
      </Card>
    );
  }

  const isSafe = environment.isSafe;
  const deviation = computeDeviation(environment.indexPrice, environment.indexMa100);
  const DeviationIcon = (environment.indexPrice ?? 0) >= (environment.indexMa100 ?? 0) ? TrendingUp : TrendingDown;

  return (
    <Card variant="bordered" padding="sm">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
          <Shield className="h-3.5 w-3.5 text-cyan" /> L1 大盘环境
        </h4>
        <RegimeBadge regime={environment.marketRegime} />
      </div>

      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-secondary-text">风险等级</span>
          <Badge
            variant={environment.riskLevel === 'low' ? 'success' : environment.riskLevel === 'high' ? 'danger' : 'warning'}
            size="sm"
          >
            {environment.riskLevel === 'low' ? '低' : environment.riskLevel === 'high' ? '高' : '中'}
          </Badge>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-secondary-text">{environment.indexName ?? '上证指数'}</span>
          <span className="font-mono text-foreground">{formatPrice(environment.indexPrice)}</span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-secondary-text">MA100</span>
          <span className="font-mono text-foreground">{formatPrice(environment.indexMa100)}</span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-secondary-text">偏离 MA100</span>
          <span className="inline-flex items-center gap-1 font-mono text-foreground">
            <DeviationIcon className="h-3 w-3" />
            {deviation}
          </span>
        </div>

        {isSafe != null && (
          <div className={`mt-1 rounded-lg border px-2 py-1.5 text-xs ${isSafe ? 'border-success/20 bg-success/5 text-success' : 'border-danger/20 bg-danger/5 text-danger'}`}>
            {environment.message ?? (isSafe ? '大盘环境安全' : '大盘环境风险偏高')}
          </div>
        )}
      </div>
    </Card>
  );
};
