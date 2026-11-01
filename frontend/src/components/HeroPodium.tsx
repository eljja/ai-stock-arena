import React from 'react';
import { Trophy, Award, TrendingUp, DollarSign, Bot, ShieldCheck } from 'lucide-react';
import { ModelRanking } from '../types';
import { formatPercent, getModelBrand } from '../utils/format';

interface HeroPodiumProps {
  rankings: ModelRanking[];
  onSelectModel: (model: ModelRanking) => void;
}

export const HeroPodium: React.FC<HeroPodiumProps> = ({ rankings, onSelectModel }) => {
  const top1 = rankings[0];
  const top2 = rankings[1];
  const top3 = rankings[2];

  return (
    <div className="mb-8">
      {/* Top Banner Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5 mb-6">
        <div className="glass-card rounded-xl p-4 border border-slate-800/80">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold">출전 AI 모델</span>
            <Bot className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-black text-white font-mono">{rankings.length}개 모델</div>
          <p className="text-[11px] text-slate-400 mt-1">100% 무료 오픈 모델 리그</p>
        </div>

        <div className="glass-card rounded-xl p-4 border border-slate-800/80">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold">초기 총 운용 자본</span>
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-white font-mono">1.4억원 + $140,000</div>
          <p className="text-[11px] text-slate-400 mt-1">모델당 1천만원 + $10,000</p>
        </div>

        <div className="glass-card rounded-xl p-4 border border-slate-800/80">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold">누적 매매 횟수</span>
            <TrendingUp className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-black text-white font-mono">
            {rankings.reduce((sum, r) => sum + (r.trade_count || 0), 0)}회
          </div>
          <p className="text-[11px] text-slate-400 mt-1">자율 포트폴리오 매매</p>
        </div>

        <div className="glass-card rounded-xl p-4 border border-slate-800/80">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold">LLM API 총 비용</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-black text-emerald-400 font-mono">$0.00</div>
          <p className="text-[11px] text-slate-400 mt-1">완전 무료 티어만 엄선</p>
        </div>
      </div>

      {/* Podium Cards for Top 3 */}
      {rankings.length >= 3 && (
        <div>
          <div className="flex items-center gap-2 mb-3.5">
            <Trophy className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300">
              Leaderboard Spotlight (Top 3)
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* 2nd Place */}
            {top2 && (
              <div
                onClick={() => onSelectModel(top2)}
                className="order-2 md:order-1 glass-card rounded-2xl p-5 border border-slate-700/60 hover:border-slate-500 transition-all cursor-pointer relative overflow-hidden group shadow-lg"
              >
                <div className="absolute top-0 right-0 w-24 h-24 bg-slate-400/5 rounded-bl-full pointer-events-none"></div>
                <div className="flex items-center justify-between mb-3">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-800 text-slate-300 border border-slate-700">
                    <Award className="w-3.5 h-3.5 text-slate-300" /> 2ND PLACE
                  </span>
                  <span className="text-xs font-semibold text-slate-400">
                    {top2.trade_count} trades
                  </span>
                </div>
                <h3 className="text-base font-bold text-white group-hover:text-cyan-300 transition-colors truncate">
                  {top2.display_name}
                </h3>
                <div className="text-xs text-slate-400 truncate mt-0.5">{top2.model_id}</div>
                <div className="mt-4 pt-4 border-t border-slate-800 flex items-end justify-between">
                  <div>
                    <span className="text-[11px] text-slate-400 block">Current Return</span>
                    <span className={`text-2xl font-black font-mono ${formatPercent(top2.current_return_pct).isPositive ? 'text-emerald-400' : 'text-slate-300'}`}>
                      {formatPercent(top2.current_return_pct).text}
                    </span>
                  </div>
                  <span className="text-xs text-cyan-400 font-medium group-hover:underline">
                    상세보기 →
                  </span>
                </div>
              </div>
            )}

            {/* 1st Place (Gold Champion) */}
            {top1 && (
              <div
                onClick={() => onSelectModel(top1)}
                className="order-1 md:order-2 glass-card rounded-2xl p-5 border-2 border-amber-500/40 hover:border-amber-400 transition-all cursor-pointer relative overflow-hidden group shadow-xl shadow-amber-500/10 bg-gradient-to-b from-amber-950/20 via-slate-900/60 to-slate-950"
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/10 rounded-bl-full pointer-events-none blur-xl"></div>
                <div className="flex items-center justify-between mb-3">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm">
                    <Trophy className="w-4 h-4 text-amber-400 fill-amber-400" /> 1ST LEADER
                  </span>
                  <span className="text-xs font-semibold text-amber-300/80">
                    {top1.trade_count} trades
                  </span>
                </div>
                <h3 className="text-lg font-black text-white group-hover:text-amber-300 transition-colors truncate">
                  {top1.display_name}
                </h3>
                <div className="text-xs text-slate-400 truncate mt-0.5">{top1.model_id}</div>
                <div className="mt-4 pt-4 border-t border-amber-500/20 flex items-end justify-between">
                  <div>
                    <span className="text-[11px] text-amber-300/80 block font-medium">Cumulative Return</span>
                    <span className={`text-3xl font-black font-mono ${formatPercent(top1.current_return_pct).isPositive ? 'text-emerald-400' : 'text-amber-300'}`}>
                      {formatPercent(top1.current_return_pct).text}
                    </span>
                  </div>
                  <span className="text-xs font-semibold text-amber-300 group-hover:underline">
                    상세 포트폴리오 →
                  </span>
                </div>
              </div>
            )}

            {/* 3rd Place */}
            {top3 && (
              <div
                onClick={() => onSelectModel(top3)}
                className="order-3 glass-card rounded-2xl p-5 border border-amber-900/40 hover:border-amber-700/60 transition-all cursor-pointer relative overflow-hidden group shadow-lg"
              >
                <div className="absolute top-0 right-0 w-24 h-24 bg-amber-800/5 rounded-bl-full pointer-events-none"></div>
                <div className="flex items-center justify-between mb-3">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-950/40 text-amber-500 border border-amber-800/40">
                    <Award className="w-3.5 h-3.5 text-amber-500" /> 3RD PLACE
                  </span>
                  <span className="text-xs font-semibold text-slate-400">
                    {top3.trade_count} trades
                  </span>
                </div>
                <h3 className="text-base font-bold text-white group-hover:text-cyan-300 transition-colors truncate">
                  {top3.display_name}
                </h3>
                <div className="text-xs text-slate-400 truncate mt-0.5">{top3.model_id}</div>
                <div className="mt-4 pt-4 border-t border-slate-800 flex items-end justify-between">
                  <div>
                    <span className="text-[11px] text-slate-400 block">Current Return</span>
                    <span className={`text-2xl font-black font-mono ${formatPercent(top3.current_return_pct).isPositive ? 'text-emerald-400' : 'text-slate-300'}`}>
                      {formatPercent(top3.current_return_pct).text}
                    </span>
                  </div>
                  <span className="text-xs text-cyan-400 font-medium group-hover:underline">
                    상세보기 →
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
