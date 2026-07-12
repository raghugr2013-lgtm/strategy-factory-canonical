import React, { useState } from 'react';
import { MagnifyingGlass, CircleNotch, ShieldCheck, ShieldWarning, Warning, Lightbulb, CheckCircle, XCircle } from '@phosphor-icons/react';
import { analyzeStrategy } from '../services/api';
import { AsfEmptyState, VerdictBadge } from './ui-asf';

const RISK_CONFIG = {
  low: { icon: ShieldCheck, color: 'text-emerald-500', verdict: 'success', label: 'LOW RISK' },
  medium: { icon: ShieldWarning, color: 'text-yellow-500', verdict: 'warn', label: 'MEDIUM RISK' },
  high: { icon: Warning, color: 'text-red-500', verdict: 'danger', label: 'HIGH RISK' },
};

export default function StrategyAnalysis({ strategy, backtestResults }) {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAnalyze = async () => {
    if (!strategy) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeStrategy(strategy, backtestResults);
      setAnalysis(data.analysis);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const riskCfg = analysis ? RISK_CONFIG[analysis.risk_level] || RISK_CONFIG.medium : null;

  return (
    <div data-testid="strategy-analysis-panel" className="asf-section asf-u2-panel bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <div className="asf-section__hd border-b border-zinc-800 px-4 py-3 flex items-center justify-between">
        <div className="asf-legacy-title flex items-center gap-2">
          <MagnifyingGlass size={14} weight="bold" className="text-yellow-500" />
          <h2 className="text-sm font-semibold text-white">AI Analysis</h2>
        </div>
        <div className="asf-section__hd-spacer" />
        <div className="asf-section__hd-actions">
          <button data-testid="analyze-strategy-btn" onClick={handleAnalyze} disabled={!strategy || loading}
            className="bg-zinc-800 text-zinc-100 hover:bg-zinc-700 border border-zinc-700 rounded-md px-2.5 py-1.5 text-[10px] font-medium transition-colors duration-150 flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed">
            {loading ? <><CircleNotch size={10} className="animate-spin" /> Analyzing...</> : <><MagnifyingGlass size={10} /> Analyze</>}
          </button>
        </div>
      </div>

      <div className="p-4">
        {!strategy && !analysis && (
          <p className="text-sm text-zinc-600 text-center py-6">Select or generate a strategy to analyze</p>
        )}
        {strategy && !analysis && !loading && !error && (
          <p className="text-sm text-zinc-600 text-center py-6">Get AI-powered insights</p>
        )}
        {error && (
          <AsfEmptyState
            slug="strategy-analysis-error"
            testId="analysis-error"
            title="Analysis failed"
            body={error}
          />
        )}

        {analysis && (
          <div className="flex flex-col gap-3">
            {riskCfg && (
              <div data-testid="risk-level-badge">
                <VerdictBadge verdict={riskCfg.verdict}>{riskCfg.label}</VerdictBadge>
              </div>
            )}
            <div data-testid="analysis-strengths">
              <h3 className="text-[10px] font-medium text-emerald-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                <CheckCircle size={12} weight="bold" /> Strengths
              </h3>
              <ul className="flex flex-col gap-1">
                {analysis.strengths.map((s, i) => (
                  <li key={i} className="text-[11px] font-mono text-zinc-300 pl-3 border-l-2 border-emerald-500/30 py-0.5">{s}</li>
                ))}
              </ul>
            </div>
            <div data-testid="analysis-weaknesses">
              <h3 className="text-[10px] font-medium text-red-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                <XCircle size={12} weight="bold" /> Weaknesses
              </h3>
              <ul className="flex flex-col gap-1">
                {analysis.weaknesses.map((w, i) => (
                  <li key={i} className="text-[11px] font-mono text-zinc-300 pl-3 border-l-2 border-red-500/30 py-0.5">{w}</li>
                ))}
              </ul>
            </div>
            <div data-testid="analysis-suggestions">
              <h3 className="text-[10px] font-medium text-yellow-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                <Lightbulb size={12} weight="bold" /> Suggestions
              </h3>
              <ul className="flex flex-col gap-1">
                {analysis.suggestions.map((s, i) => (
                  <li key={i} className="text-[11px] font-mono text-zinc-300 pl-3 border-l-2 border-yellow-500/30 py-0.5">{s}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
