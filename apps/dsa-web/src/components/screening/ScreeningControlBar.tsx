import type React from "react";
import { Play, RotateCcw, SlidersHorizontal } from "lucide-react";
import { Button, Card, ConfirmDialog, Select } from "../common";
import { useScreeningStore } from "../../stores/screeningStore";
import { StrategyTag } from "./StrategyTag";
import { cn } from "../../utils/cn";
import type { ScreeningMode } from "../../types/screening";

const MODE_OPTIONS = [
  { value: "balanced", label: "均衡模式" },
  { value: "aggressive", label: "激进模式" },
  { value: "quality", label: "质量模式" },
];

export const ScreeningControlBar: React.FC = () => {
  const {
    strategies,
    strategiesLoading,
    selectedStrategies,
    setSelectedStrategies,
    mode,
    setMode,
    tradeDate,
    setTradeDate,
    candidateLimit,
    setCandidateLimit,
    aiTopK,
    setAiTopK,
    isRunning,
    blockingDialog,
    clearBlockingDialog,
    startScreening,
    reset,
  } = useScreeningStore();

  const handleToggleStrategy = (name: string) => {
    if (selectedStrategies.includes(name)) {
      setSelectedStrategies(selectedStrategies.filter((s) => s !== name));
    } else {
      setSelectedStrategies([...selectedStrategies, name]);
    }
  };

  const handleStart = () => {
    void startScreening();
  };

  return (
    <>
      <Card variant="bordered" padding="md" data-testid="screening-control-bar">
        <div className="mb-4 flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-cyan" />
          <h3 className="text-sm font-semibold text-foreground">筛选配置</h3>
        </div>

        <div className="mb-4">
          <p className="mb-2 text-xs text-secondary-text">策略选择</p>
          <div className="flex flex-wrap gap-2" data-testid="strategy-tags">
            {strategiesLoading ? (
              <span className="text-xs text-secondary-text">加载中...</span>
            ) : (
              strategies.map((strategy) => (
                <StrategyTag
                  key={strategy.name}
                  name={strategy.displayName}
                  category={strategy.category}
                  active={selectedStrategies.includes(strategy.name)}
                  disabled={!strategy.hasScreeningRules}
                  onClick={() => handleToggleStrategy(strategy.name)}
                />
              ))
            )}
          </div>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Select
            label="筛选模式"
            value={mode}
            onChange={(value) => setMode(value as ScreeningMode)}
            options={MODE_OPTIONS}
          />
          <div className="flex flex-col">
            <label htmlFor="trade-date" className="mb-2 text-sm font-medium text-foreground">
              交易日
            </label>
            <input
              id="trade-date"
              type="date"
              value={tradeDate}
              onChange={(event) => setTradeDate(event.target.value)}
              className={cn(
                "h-11 w-full rounded-xl border border-white/10 bg-card px-4 py-2.5 text-sm text-foreground",
                "shadow-soft-card transition-all focus:outline-none focus:ring-4 focus:ring-cyan/15 focus:border-cyan/40",
              )}
            />
          </div>
          <div className="flex flex-col">
            <label htmlFor="candidate-limit" className="mb-2 text-sm font-medium text-foreground">
              候选上限
            </label>
            <input
              id="candidate-limit"
              type="number"
              min={1}
              max={200}
              value={candidateLimit}
              onChange={(event) => setCandidateLimit(Number(event.target.value))}
              className={cn(
                "h-11 w-full rounded-xl border border-white/10 bg-card px-4 py-2.5 text-sm text-foreground",
                "shadow-soft-card transition-all focus:outline-none focus:ring-4 focus:ring-cyan/15 focus:border-cyan/40",
              )}
            />
          </div>
          <div className="flex flex-col">
            <label htmlFor="ai-top-k" className="mb-2 text-sm font-medium text-foreground">
              AI 分析数
            </label>
            <input
              id="ai-top-k"
              type="number"
              min={0}
              max={50}
              value={aiTopK}
              onChange={(event) => setAiTopK(Number(event.target.value))}
              className={cn(
                "h-11 w-full rounded-xl border border-white/10 bg-card px-4 py-2.5 text-sm text-foreground",
                "shadow-soft-card transition-all focus:outline-none focus:ring-4 focus:ring-cyan/15 focus:border-cyan/40",
              )}
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            onClick={handleStart}
            isLoading={isRunning}
            loadingText="筛选中..."
            disabled={selectedStrategies.length === 0}
            glow
          >
            <Play className="h-4 w-4" />
            开始筛选
          </Button>
          <Button variant="ghost" onClick={reset} disabled={isRunning}>
            <RotateCcw className="h-4 w-4" />
            重置
          </Button>
        </div>
      </Card>

      <ConfirmDialog
        isOpen={Boolean(blockingDialog)}
        title={blockingDialog?.title || ""}
        message={blockingDialog?.message || ""}
        confirmText="我知道了"
        cancelText="关闭"
        onConfirm={clearBlockingDialog}
        onCancel={clearBlockingDialog}
      />
    </>
  );
};
