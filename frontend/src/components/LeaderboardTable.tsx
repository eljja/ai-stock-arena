import React, { useState } from 'react';
import { Search, ChevronRight, TrendingUp, Trophy } from 'lucide-react';
import { ModelRanking } from '../types';
import { formatPercent, getModelBrand } from '../utils/format';

interface LeaderboardTableProps {
  rankings: ModelRanking[];
  onSelectModel: (model: ModelRanking) => void;
}

export const LeaderboardTable: React.FC<LeaderboardTableProps> = ({
  rankings,
  onSelectModel,
}) => {
  const [search, setSearch] = useState('');
  const [period, setPeriod] = useState<'all' | '1d' | '1w' | '1m'>('all');

  const filtered = rankings.filter(
    (m) =>
      m.display_name.toLowerCase().includes(search.toLowerCase()) ||
      m.model_id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="glass-panel rounded-2xl border border-slate-800 p-5 shadow-xl">
      {/* Controls Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3.5 mb-5 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <span>리그 순위표</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-800 text-slate-400">
              {filtered.length}개 모델
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            동일 자본(1천만원 + $10,000)으로 경쟁 중인 LLM 에이전트들의 실시간 성과
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {/* Period selector */}
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1 text-xs">
            <button
              onClick={() => setPeriod('all')}
              className={`px-3 py-1 rounded-md font-medium transition-all ${
                period === 'all'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              전체
            </button>
            <button
              onClick={() => setPeriod('1d')}
              className={`px-3 py-1 rounded-md font-medium transition-all ${
                period === '1d'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              1일
            </button>
            <button
              onClick={() => setPeriod('1w')}
              className={`px-3 py-1 rounded-md font-medium transition-all ${
                period === '1w'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              1주일
            </button>
            <button
              onClick={() => setPeriod('1m')}
              className={`px-3 py-1 rounded-md font-medium transition-all ${
                period === '1m'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              1개월
            </button>
          </div>

          {/* Search box */}
          <div className="relative min-w-[180px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="모델 검색..."
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-900/90 border border-slate-700/80 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
            />
          </div>
        </div>
      </div>

      {/* Table Rows */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              <th className="py-3 px-3 text-center w-14">순위</th>
              <th className="py-3 px-4">AI 투자 모델</th>
              <th className="py-3 px-4 text-right">총 수익률</th>
              <th className="py-3 px-4 text-right hidden md:table-cell">한국장 (KRW)</th>
              <th className="py-3 px-4 text-right hidden md:table-cell">미국장 (USD)</th>
              <th className="py-3 px-4 text-center hidden sm:table-cell">매매 횟수</th>
              <th className="py-3 px-4 text-right">상세</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filtered.map((item, index) => {
              const brand = getModelBrand(item.model_id);
              const rank = index + 1;
              const ret =
                period === '1d'
                  ? item.return_1d_pct
                  : period === '1w'
                  ? item.return_1w_pct
                  : period === '1m'
                  ? item.return_1m_pct
                  : item.current_return_pct;
              const formattedRet = formatPercent(ret);

              return (
                <tr
                  key={item.model_id}
                  onClick={() => onSelectModel(item)}
                  className="hover:bg-slate-800/40 transition-colors cursor-pointer group"
                >
                  {/* Rank Badge */}
                  <td className="py-3.5 px-3 text-center">
                    {rank === 1 ? (
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-amber-500/20 text-amber-300 font-extrabold text-sm border border-amber-500/40">
                        🥇
                      </span>
                    ) : rank === 2 ? (
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-slate-400/20 text-slate-300 font-bold text-sm border border-slate-400/30">
                        🥈
                      </span>
                    ) : rank === 3 ? (
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-amber-800/20 text-amber-500 font-bold text-sm border border-amber-800/30">
                        🥉
                      </span>
                    ) : (
                      <span className="text-xs font-semibold text-slate-500 font-mono">
                        {rank}
                      </span>
                    )}
                  </td>

                  {/* Model Name & Brand Tag */}
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-2.5">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-white group-hover:text-cyan-400 transition-colors">
                            {item.display_name}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${brand.bgColor} ${brand.color} ${brand.borderColor}`}
                          >
                            {brand.brand}
                          </span>
                        </div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-xs md:max-w-md">
                          {item.model_id}
                        </div>
                      </div>
                    </div>
                  </td>

                  {/* Total Return */}
                  <td className="py-3.5 px-4 text-right">
                    <div
                      className={`text-base font-black font-mono ${
                        formattedRet.isPositive
                          ? 'text-emerald-400'
                          : formattedRet.isNeutral
                          ? 'text-slate-400'
                          : 'text-rose-400'
                      }`}
                    >
                      {formattedRet.text}
                    </div>
                  </td>

                  {/* KR Return */}
                  <td className="py-3.5 px-4 text-right hidden md:table-cell">
                    <span
                      className={`text-xs font-semibold font-mono ${
                        formatPercent(item.kr_return_pct).isPositive
                          ? 'text-emerald-400'
                          : 'text-slate-400'
                      }`}
                    >
                      {formatPercent(item.kr_return_pct).text}
                    </span>
                  </td>

                  {/* US Return */}
                  <td className="py-3.5 px-4 text-right hidden md:table-cell">
                    <span
                      className={`text-xs font-semibold font-mono ${
                        formatPercent(item.us_return_pct).isPositive
                          ? 'text-emerald-400'
                          : 'text-slate-400'
                      }`}
                    >
                      {formatPercent(item.us_return_pct).text}
                    </span>
                  </td>

                  {/* Trades Count */}
                  <td className="py-3.5 px-4 text-center hidden sm:table-cell">
                    <span className="px-2 py-1 rounded bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300">
                      {item.trade_count} 회
                    </span>
                  </td>

                  {/* Action button */}
                  <td className="py-3.5 px-4 text-right">
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-cyan-400 group-hover:translate-x-1 transition-transform">
                      포트폴리오 <ChevronRight className="w-3.5 h-3.5" />
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
