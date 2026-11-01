import React from 'react';
import { Activity, RefreshCw, Zap, TrendingUp } from 'lucide-react';

interface HeaderProps {
  onRefresh: () => void;
  isRefreshing: boolean;
  lastUpdated: Date;
  activeModelCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  onRefresh,
  isRefreshing,
  lastUpdated,
  activeModelCount,
}) => {
  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-slate-800/80 px-4 lg:px-8 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Logo and Brand */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 via-blue-600 to-indigo-600 shadow-lg shadow-cyan-500/20">
            <TrendingUp className="w-5 h-5 text-white" />
            <span className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500 border-2 border-slate-900"></span>
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                AI Stock Arena
              </span>
              <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-cyan-950/80 border border-cyan-500/30 text-cyan-400 flex items-center gap-1">
                <Zap className="w-3 h-3 text-cyan-400 fill-cyan-400" />
                LIVE LEAGUE
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium">
              Autonomous LLM Trading Benchmark • 14 Free AI Agents Competing 24/7
            </p>
          </div>
        </div>

        {/* Live Market Badges and Controls */}
        <div className="flex items-center flex-wrap gap-2.5">
          {/* Market Status Pills */}
          <div className="flex items-center gap-2 bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-1.5 text-xs">
            <span className="flex items-center gap-1.5 font-medium text-slate-300">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              🇰🇷 KRW 시장
            </span>
            <span className="text-slate-600">|</span>
            <span className="flex items-center gap-1.5 font-medium text-slate-300">
              <span className="w-2 h-2 rounded-full bg-blue-400"></span>
              🇺🇸 USD 시장
            </span>
          </div>

          {/* Active Agents Badge */}
          <div className="hidden sm:flex items-center gap-1.5 bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-300">
            <Activity className="w-3.5 h-3.5 text-cyan-400" />
            <span><strong className="text-white">{activeModelCount}</strong> AI Models</span>
          </div>

          {/* Manual Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700/80 border border-slate-700/60 text-xs font-medium text-slate-200 transition-all cursor-pointer disabled:opacity-50"
            title="데이터 새로고침"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`} />
            <span className="hidden sm:inline">새로고침</span>
          </button>
        </div>
      </div>
    </header>
  );
};
