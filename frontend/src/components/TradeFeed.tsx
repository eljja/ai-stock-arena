import React, { useState } from 'react';
import { Activity, ArrowUpRight, ArrowDownRight, Bot, Cpu, ChevronDown, ChevronUp } from 'lucide-react';
import { TradeSummary, LLMDecisionLogSummary } from '../types';
import { formatCurrency, timeAgo, getModelBrand } from '../utils/format';

interface TradeFeedProps {
  trades: TradeSummary[];
  logs: LLMDecisionLogSummary[];
}

export const TradeFeed: React.FC<TradeFeedProps> = ({ trades, logs }) => {
  const [activeTab, setActiveTab] = useState<'trades' | 'reasoning'>('trades');
  const [expandedLogId, setExpandedLogId] = useState<number | null>(null);

  return (
    <div className="glass-panel rounded-2xl border border-slate-800 p-5 shadow-xl">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-5 pb-3 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            <span>AI 트레이딩 실시간 실행 & 추론 로그</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            AI 모델들의 실시간 매매 체결 내역과 투자 의사결정 추론(Reasoning)
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1 text-xs">
          <button
            onClick={() => setActiveTab('trades')}
            className={`px-3 py-1 rounded-md font-medium transition-all ${
              activeTab === 'trades'
                ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            체결 내역 ({trades.length})
          </button>
          <button
            onClick={() => setActiveTab('reasoning')}
            className={`px-3 py-1 rounded-md font-medium transition-all ${
              activeTab === 'reasoning'
                ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            LLM 추론 로그 ({logs.length})
          </button>
        </div>
      </div>

      {activeTab === 'trades' ? (
        trades.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-sm">
            아직 체결된 매매 기록이 없습니다. (장이 열리면 AI 모델들이 자동으로 주문을 집행합니다)
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  <th className="py-2.5 px-3">시간</th>
                  <th className="py-2.5 px-4">AI 모델</th>
                  <th className="py-2.5 px-3 text-center">시장</th>
                  <th className="py-2.5 px-3 text-center">주문</th>
                  <th className="py-2.5 px-4">종목 (Ticker)</th>
                  <th className="py-2.5 px-4 text-right">수량</th>
                  <th className="py-2.5 px-4 text-right">단가</th>
                  <th className="py-2.5 px-4 text-right">총 체결금액</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                {trades.map((t, idx) => {
                  const brand = getModelBrand(t.model_id);
                  const isBuy = t.action === 'BUY';
                  return (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 px-3 text-slate-400 whitespace-nowrap">
                        {timeAgo(t.executed_at)}
                      </td>
                      <td className="py-3 px-4 font-sans font-medium text-white truncate max-w-[180px]">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] mr-1.5 border ${brand.bgColor} ${brand.color} ${brand.borderColor}`}>
                          {brand.brand}
                        </span>
                        {t.model_id.split('/')[1] || t.model_id}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">
                          {t.market_code}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
                            isBuy
                              ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-950/60 text-rose-400 border border-rose-500/30'
                          }`}
                        >
                          {isBuy ? (
                            <>
                              <ArrowUpRight className="w-3 h-3" /> 매수
                            </>
                          ) : (
                            <>
                              <ArrowDownRight className="w-3 h-3" /> 매도
                            </>
                          )}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-bold text-white">
                        {t.ticker}
                      </td>
                      <td className="py-3 px-4 text-right text-slate-300">
                        {t.shares} 주
                      </td>
                      <td className="py-3 px-4 text-right text-slate-300">
                        {formatCurrency(t.price, t.market_code === 'KR' ? 'KRW' : 'USD')}
                      </td>
                      <td className="py-3 px-4 text-right font-bold text-white">
                        {formatCurrency(t.total_amount, t.market_code === 'KR' ? 'KRW' : 'USD')}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      ) : (
        /* LLM Decision Reasoning Logs */
        logs.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-sm">
            아직 기록된 LLM 의사결정 로그가 없습니다.
          </div>
        ) : (
          <div className="space-y-3">
            {logs.map((log, idx) => {
              const isExpanded = expandedLogId === (log.id || idx);
              const brand = getModelBrand(log.model_id);
              return (
                <div
                  key={idx}
                  className="glass-card rounded-xl p-4 border border-slate-800 transition-all hover:border-slate-700"
                >
                  <div
                    onClick={() => setExpandedLogId(isExpanded ? null : (log.id || idx))}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 cursor-pointer"
                  >
                    <div className="flex items-center gap-2">
                      <Bot className="w-4 h-4 text-cyan-400" />
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${brand.bgColor} ${brand.color} ${brand.borderColor}`}>
                        {brand.brand}
                      </span>
                      <span className="text-sm font-bold text-white">
                        {log.model_id}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                        {log.market_code}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs font-mono text-slate-400">
                      <span className="flex items-center gap-1">
                        <Cpu className="w-3.5 h-3.5 text-slate-500" />
                        {log.total_tokens || 0} tokens
                      </span>
                      <span>{timeAgo(log.created_at)}</span>
                      {isExpanded ? (
                        <ChevronUp className="w-4 h-4 text-cyan-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-slate-500" />
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="mt-4 pt-4 border-t border-slate-800 space-y-3 text-xs">
                      <div>
                        <span className="font-bold text-slate-300 block mb-1">
                          🧠 LLM 투자 추론 결과 (Raw Output)
                        </span>
                        <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap">
                          {log.raw_output_text || log.error_message || '추론 텍스트가 없습니다.'}
                        </pre>
                      </div>

                      {log.prompt_text && (
                        <div>
                          <span className="font-bold text-slate-400 block mb-1">
                            📥 입력 프롬프트 요약
                          </span>
                          <pre className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 font-mono text-[11px] text-slate-400 overflow-x-auto max-h-48 whitespace-pre-wrap">
                            {log.prompt_text}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )
      )}
    </div>
  );
};
