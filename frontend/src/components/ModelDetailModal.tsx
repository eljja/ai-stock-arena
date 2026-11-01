import React from 'react';
import { X, Wallet, TrendingUp, PieChart, Clock } from 'lucide-react';
import { ModelRanking, PortfolioSummary, PositionSummary, TradeSummary } from '../types';
import { formatCurrency, formatPercent, getModelBrand, timeAgo } from '../utils/format';

interface ModelDetailModalProps {
  model: ModelRanking | null;
  portfolios: PortfolioSummary[];
  positions: PositionSummary[];
  trades: TradeSummary[];
  onClose: () => void;
}

export const ModelDetailModal: React.FC<ModelDetailModalProps> = ({
  model,
  portfolios,
  positions,
  trades,
  onClose,
}) => {
  if (!model) return null;

  const brand = getModelBrand(model.model_id);
  const modelPortfolios = portfolios.filter((p) => p.model_id === model.model_id);
  const modelPositions = positions.filter((p) => p.model_id === model.model_id);
  const modelTrades = trades.filter((t) => t.model_id === model.model_id);

  const krPortfolio = modelPortfolios.find((p) => p.market_code === 'KR');
  const usPortfolio = modelPortfolios.find((p) => p.market_code === 'US');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
      <div className="glass-panel w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl border border-slate-700 shadow-2xl p-6 relative">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors cursor-pointer"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Model Title & Header */}
        <div className="flex items-center gap-3 mb-6">
          <div>
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-xs font-bold border ${brand.bgColor} ${brand.color} ${brand.borderColor}`}>
                {brand.brand}
              </span>
              <h2 className="text-xl font-bold text-white">{model.display_name}</h2>
            </div>
            <div className="text-xs text-slate-400 font-mono mt-1">{model.model_id}</div>
          </div>
        </div>

        {/* Portfolios Overview (KR & US) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {/* KRW Portfolio Card */}
          <div className="glass-card rounded-xl p-4 border border-slate-800">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800">
              <span className="flex items-center gap-2 text-sm font-bold text-white">
                <Wallet className="w-4 h-4 text-emerald-400" /> 한국 시장 (KRW)
              </span>
              <span className={`text-sm font-bold font-mono ${formatPercent(model.kr_return_pct).isPositive ? 'text-emerald-400' : 'text-slate-400'}`}>
                {formatPercent(model.kr_return_pct).text}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div>
                <span className="text-slate-400 block text-[11px]">총 자산 평가액</span>
                <span className="text-sm font-bold text-white">
                  {formatCurrency(krPortfolio?.total_equity || 10000000, 'KRW')}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">가용 현금 잔고</span>
                <span className="text-sm font-bold text-slate-300">
                  {formatCurrency(krPortfolio?.available_cash || 10000000, 'KRW')}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">주식 투자 금액</span>
                <span className="text-sm font-bold text-slate-300">
                  {formatCurrency(krPortfolio?.invested_value || 0, 'KRW')}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">실현 손익 (Realized)</span>
                <span className="text-sm font-bold text-slate-300">
                  {formatCurrency(krPortfolio?.total_realized_pnl || 0, 'KRW')}
                </span>
              </div>
            </div>
          </div>

          {/* USD Portfolio Card */}
          <div className="glass-card rounded-xl p-4 border border-slate-800">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800">
              <span className="flex items-center gap-2 text-sm font-bold text-white">
                <Wallet className="w-4 h-4 text-blue-400" /> 미국 시장 (USD)
              </span>
              <span className={`text-sm font-bold font-mono ${formatPercent(model.us_return_pct).isPositive ? 'text-emerald-400' : 'text-slate-400'}`}>
                {formatPercent(model.us_return_pct).text}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div>
                <span className="text-slate-400 block text-[11px]">총 자산 평가액</span>
                <span className="text-sm font-bold text-white">
                  {formatCurrency(usPortfolio?.total_equity || 10000, 'USD')}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">가용 현금 잔고</span>
                <span className="text-sm font-bold text-slate-300">
                  {formatCurrency(usPortfolio?.available_cash || 10000, 'USD')}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">주식 투자 금액</span>
                <span className="text-sm font-bold text-slate-300">
                  {formatCurrency(usPortfolio?.invested_value || 0, 'USD')}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">실현 손익 (Realized)</span>
                <span className="text-sm font-bold text-slate-300">
                  {formatCurrency(usPortfolio?.total_realized_pnl || 0, 'USD')}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Current Holdings / Positions */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <PieChart className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-white">보유 종목 현황 (Open Positions)</h3>
          </div>

          {modelPositions.length === 0 ? (
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-xs text-slate-400">
              현재 보유 중인 종목이 없습니다. (100% 현금 보유 상태)
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-2.5 px-3">시장</th>
                    <th className="py-2.5 px-3">종목코드</th>
                    <th className="py-2.5 px-3 text-right">보유수량</th>
                    <th className="py-2.5 px-3 text-right">평균 매수가</th>
                    <th className="py-2.5 px-3 text-right">현재가</th>
                    <th className="py-2.5 px-3 text-right">평가손익</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {modelPositions.map((pos, idx) => {
                    const isPositive = pos.unrealized_pnl > 0;
                    return (
                      <tr key={idx} className="hover:bg-slate-800/40">
                        <td className="py-2.5 px-3 text-slate-400">{pos.market_code}</td>
                        <td className="py-2.5 px-3 font-bold text-white">{pos.ticker}</td>
                        <td className="py-2.5 px-3 text-right text-slate-300">{pos.quantity} 주</td>
                        <td className="py-2.5 px-3 text-right text-slate-300">
                          {formatCurrency(pos.average_price, pos.market_code === 'KR' ? 'KRW' : 'USD')}
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-300">
                          {formatCurrency(pos.current_price, pos.market_code === 'KR' ? 'KRW' : 'USD')}
                        </td>
                        <td className={`py-2.5 px-3 text-right font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {formatCurrency(pos.unrealized_pnl, pos.market_code === 'KR' ? 'KRW' : 'USD')} ({formatPercent(pos.unrealized_pnl_pct).text})
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Recent Trades by this Model */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Clock className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-white">최근 매매 기록 ({modelTrades.length}건)</h3>
          </div>

          {modelTrades.length === 0 ? (
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-xs text-slate-400">
              최근 체결된 매매 기록이 없습니다.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800 max-h-48">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-2 px-3">시간</th>
                    <th className="py-2 px-3">시장</th>
                    <th className="py-2 px-3">주문</th>
                    <th className="py-2 px-3">종목</th>
                    <th className="py-2 px-3 text-right">수량</th>
                    <th className="py-2 px-3 text-right">단가</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {modelTrades.map((tr, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="py-2 px-3 text-slate-400 whitespace-nowrap">{timeAgo(tr.executed_at)}</td>
                      <td className="py-2 px-3 text-slate-400">{tr.market_code}</td>
                      <td className={`py-2 px-3 font-bold ${tr.action === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>{tr.action}</td>
                      <td className="py-2 px-3 font-bold text-white">{tr.ticker}</td>
                      <td className="py-2 px-3 text-right text-slate-300">{tr.shares} 주</td>
                      <td className="py-2 px-3 text-right text-slate-300">{formatCurrency(tr.price, tr.market_code === 'KR' ? 'KRW' : 'USD')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
