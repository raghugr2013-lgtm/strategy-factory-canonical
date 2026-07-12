/**
 * Workspace Composite — Legacy 1-vCPU MORE-1 single-page lab
 * ----------------------------------------------------------------------------
 * Restores the single-page operator workspace from the legacy 1-vCPU UI
 * (old1vcpu/src/App.js LL 320-365). One screen, eight panels, three columns:
 *
 *   Left col (lg:col-span-3):
 *     • StrategyPanel  (generator)
 *     • StrategyAnalysis
 *
 *   Right col (lg:col-span-9):
 *     • BacktestPanel
 *     • StrategyDescription   (only when a strategy is loaded)
 *     • CbotPanel
 *     • OptimizationPanel | ValidationPanel  (xl: side-by-side)
 *     • StrategyComparison     (only when rankedStrategies.length >= 1)
 *
 * State is local to this composite — the eight component homes under
 * /c/lab/{panel,analysis,backtest,cbot,optim,validate} remain unchanged and
 * usable by themselves. This composite is purely additive.
 *
 * Mounted at: /c/lab/workspace
 * Tracked: POST_HYDRATION_UI_RECOVERY.md P1.1
 */
import React, { useCallback, useState } from 'react';
import StrategyPanel from './StrategyPanel';
import StrategyAnalysis from './StrategyAnalysis';
import BacktestPanel from './BacktestPanel';
import StrategyDescription from './StrategyDescription';
import CbotPanel from './CbotPanel';
import OptimizationPanel from './OptimizationPanel';
import ValidationPanel from './ValidationPanel';
import StrategyComparison from './StrategyComparison';

export default function WorkspaceComposite() {
  const [strategy, setStrategy] = useState(null);
  const [backtestResults, setBacktestResults] = useState(null);
  const [currentPair, setCurrentPair] = useState('EURUSD');
  const [currentTimeframe, setCurrentTimeframe] = useState('M15');
  const [rankedStrategies, setRankedStrategies] = useState([]);

  const handleStrategyGenerated = useCallback((strategyText, pair, timeframe) => {
    setStrategy(strategyText);
    if (pair) setCurrentPair(pair);
    if (timeframe) setCurrentTimeframe(timeframe);
    // New strategy => clear previous backtest so the description / cbot /
    // validate panels don't show stale results.
    setBacktestResults(null);
  }, []);

  const handleBacktestRun = useCallback((results) => {
    setBacktestResults(results);
  }, []);

  const handleStrategySaved = useCallback(() => {
    // Library section refreshes itself on mount; nothing to do here.
  }, []);

  const handleSelectRanked = useCallback((s) => {
    if (!s) return;
    setStrategy(s.strategy || s.strategy_text || null);
    if (s.pair) setCurrentPair(s.pair);
    if (s.timeframe) setCurrentTimeframe(s.timeframe);
    setBacktestResults(s.backtest || s.backtest_results || null);
  }, []);

  return (
    <div className="space-y-4" data-testid="workspace-composite">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 md:gap-6">
        {/* Left sidebar — controls (3 cols on lg+) */}
        <div className="lg:col-span-3 flex flex-col gap-4" data-testid="workspace-left">
          <StrategyPanel onStrategyGenerated={handleStrategyGenerated} />
          <StrategyAnalysis strategy={strategy} backtestResults={backtestResults} />
        </div>

        {/* Right column — results (9 cols on lg+) */}
        <div className="lg:col-span-9 flex flex-col gap-4" data-testid="workspace-right">
          <BacktestPanel
            strategy={strategy}
            backtestResults={backtestResults}
            onBacktestRun={handleBacktestRun}
            onStrategySaved={handleStrategySaved}
            pair={currentPair}
            timeframe={currentTimeframe}
          />

          {strategy && (
            <StrategyDescription
              strategy_text={strategy}
              pair={currentPair}
              timeframe={currentTimeframe}
              backtest={backtestResults}
            />
          )}

          <CbotPanel
            strategy={strategy}
            pair={currentPair}
            timeframe={currentTimeframe}
            backtestResults={backtestResults}
          />

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <OptimizationPanel
              strategy={strategy}
              pair={currentPair}
              timeframe={currentTimeframe}
            />
            <ValidationPanel
              strategy={strategy}
              pair={currentPair}
              timeframe={currentTimeframe}
            />
          </div>

          {rankedStrategies.length >= 1 && (
            <StrategyComparison
              strategies={rankedStrategies}
              onSelectStrategy={handleSelectRanked}
            />
          )}
        </div>
      </div>
    </div>
  );
}
