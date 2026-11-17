import React, { useEffect, useRef, useState } from 'react';
import {
  createChart,
  ColorType,
  IChartApi,
  LineSeries,
  UTCTimestamp,
  LineStyle,
} from 'lightweight-charts';
import { SnapshotSummary, ModelRanking } from '../types';
import {
  buildChartSeriesData,
  ChartMarketFilter,
  formatKstDateTime,
  formatKstTickMark,
} from '../utils/chartData';
import { LineChart, CheckSquare, Square } from 'lucide-react';

interface PerformanceChartProps {
  snapshots: SnapshotSummary[];
  rankings: ModelRanking[];
}

export const PerformanceChart: React.FC<PerformanceChartProps> = ({
  snapshots,
  rankings,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [marketFilter, setMarketFilter] = useState<ChartMarketFilter>('ALL');

  // Default to selecting top 3 models
  useEffect(() => {
    if (rankings.length > 0 && selectedModels.length === 0) {
      setSelectedModels(rankings.slice(0, 3).map((r) => r.model_id));
    }
  }, [rankings, selectedModels.length]);

  // Color palette for lines
  const colors = [
    '#38bdf8', // sky-400
    '#f59e0b', // amber-500
    '#a855f7', // purple-500
    '#10b981', // emerald-500
    '#ec4899', // pink-500
    '#6366f1', // indigo-500
    '#14b8a6', // teal-500
  ];

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth || 600,
      height: 400,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(51, 65, 85, 0.3)' },
        horzLines: { color: 'rgba(51, 65, 85, 0.3)' },
      },
      crosshair: {
        vertLine: { color: '#06b6d4', width: 1, style: LineStyle.Dashed },
        horzLine: { color: '#06b6d4', width: 1, style: LineStyle.Dashed },
      },
      localization: {
        timeFormatter: (time: UTCTimestamp) => formatKstDateTime(Number(time)),
      },
      rightPriceScale: {
        borderColor: 'rgba(51, 65, 85, 0.5)',
      },
      timeScale: {
        borderColor: 'rgba(51, 65, 85, 0.5)',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: UTCTimestamp) => formatKstTickMark(Number(time)),
      },
    });

    chartRef.current = chart;

    let addedZeroLine = false;

    selectedModels.forEach((modelId) => {
      const rankIdx = rankings.findIndex((r) => r.model_id === modelId);
      const color = colors[(rankIdx >= 0 ? rankIdx : 0) % colors.length];
      const displayName =
        rankings.find((r) => r.model_id === modelId)?.display_name || modelId;

      const series = chart.addSeries(LineSeries, {
        color,
        lineWidth: 2,
        title: displayName,
        priceFormat: {
          type: 'custom',
          minMove: 0.01,
          formatter: (price: number) => `${price >= 0 ? '+' : ''}${price.toFixed(2)}%`,
        },
      });

      const data = buildChartSeriesData(snapshots, modelId, marketFilter).map(
        (point) => ({
          time: point.time as UTCTimestamp,
          value: point.value,
        })
      );

      if (data.length > 0) {
        series.setData(data);
      } else {
        const nowSec = Math.floor(Date.now() / 1000);
        series.setData([
          { time: (nowSec - 86400) as UTCTimestamp, value: 0 },
          { time: nowSec as UTCTimestamp, value: 0 },
        ]);
      }

      if (!addedZeroLine) {
        series.createPriceLine({
          price: 0,
          color: 'rgba(148, 163, 184, 0.4)',
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: '0%',
        });
        addedZeroLine = true;
      }
    });

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (chartContainerRef.current && chartContainerRef.current.clientWidth > 0) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    const resizeObserver =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => handleResize())
        : null;
    if (resizeObserver) {
      resizeObserver.observe(container);
    }
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver?.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [snapshots, selectedModels, rankings, marketFilter]);

  const toggleModel = (id: string) => {
    setSelectedModels((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]
    );
  };

  const getDisplayReturn = (r: ModelRanking): number | null => {
    if (marketFilter === 'KR') return r.kr_return_pct;
    if (marketFilter === 'US') return r.us_return_pct;
    return r.current_return_pct;
  };

  return (
    <div className="glass-panel rounded-2xl border border-slate-800 p-5 shadow-xl mb-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <LineChart className="w-5 h-5 text-cyan-400" />
            <span>수익률 실시간 벤치마크 (TradingView Chart)</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            AI 모델별 누적 수익률 추이를 KST 기준 인터랙티브 캔버스 차트로 정밀 비교
          </p>
        </div>

        {/* Market Filter Switch */}
        <div className="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
          {(
            [
              { code: 'ALL', label: '통합 평균' },
              { code: 'KR', label: '국장 (KR)' },
              { code: 'US', label: '미장 (US)' },
            ] as const
          ).map((item) => (
            <button
              key={item.code}
              onClick={() => setMarketFilter(item.code)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                marketFilter === item.code
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 border border-transparent'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Model toggle chips */}
      <div className="flex flex-wrap items-center gap-2 mb-4 pb-3 border-b border-slate-800/80">
        <span className="text-xs font-semibold text-slate-400 mr-1">비교 모델:</span>
        {rankings.map((r, idx) => {
          const isSelected = selectedModels.includes(r.model_id);
          const color = colors[idx % colors.length];
          const ret = getDisplayReturn(r);
          return (
            <button
              key={r.model_id}
              onClick={() => toggleModel(r.model_id)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer border ${
                isSelected
                  ? 'bg-slate-800 text-white border-slate-600 shadow-sm'
                  : 'bg-slate-900/40 text-slate-500 border-slate-800/60 hover:text-slate-300'
              }`}
            >
              {isSelected ? (
                <CheckSquare className="w-3.5 h-3.5 shrink-0" style={{ color }} />
              ) : (
                <Square className="w-3.5 h-3.5 shrink-0" />
              )}
              <span className="truncate max-w-[140px]">{r.display_name}</span>
              {ret !== null && (
                <span
                  className={`font-mono text-[11px] ${
                    ret > 0
                      ? 'text-emerald-400'
                      : ret < 0
                        ? 'text-rose-400'
                        : 'text-slate-400'
                  }`}
                >
                  {ret > 0 ? '+' : ''}
                  {ret.toFixed(2)}%
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Canvas Chart Container */}
      <div ref={chartContainerRef} className="w-full relative min-h-[400px]" />
    </div>
  );
};
