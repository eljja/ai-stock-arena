import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, LineSeries } from 'lightweight-charts';
import { SnapshotSummary, ModelRanking } from '../types';
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

  // Default to selecting top 3 models
  useEffect(() => {
    if (rankings.length > 0 && selectedModels.length === 0) {
      setSelectedModels(rankings.slice(0, 3).map((r) => r.model_id));
    }
  }, [rankings]);

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
    if (!chartContainerRef.current) return;

    // Initialize Lightweight Chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(51, 65, 85, 0.3)' },
        horzLines: { color: 'rgba(51, 65, 85, 0.3)' },
      },
      crosshair: {
        vertLine: { color: '#06b6d4', width: 1, style: 1 },
        horzLine: { color: '#06b6d4', width: 1, style: 1 },
      },
      rightPriceScale: {
        borderColor: 'rgba(51, 65, 85, 0.5)',
      },
      timeScale: {
        borderColor: 'rgba(51, 65, 85, 0.5)',
        timeVisible: true,
        secondsVisible: false,
      },
      height: 380,
    });

    chartRef.current = chart;

    // Add series for each selected model
    const seriesMap: { [key: string]: ISeriesApi<'Line'> } = {};

    selectedModels.forEach((modelId, idx) => {
      const color = colors[idx % colors.length];
      const series = chart.addSeries(LineSeries, {
        color,
        lineWidth: 2,
        title: rankings.find((r) => r.model_id === modelId)?.display_name || modelId,
      });

      // Filter snapshots for this model
      const modelSnapshots = snapshots
        .filter((s) => s.model_id === modelId)
        .sort(
          (a, b) =>
            new Date(a.snapshot_time).getTime() -
            new Date(b.snapshot_time).getTime()
        );

      if (modelSnapshots.length > 0) {
        const data = modelSnapshots.map((s) => ({
          time: Math.floor(new Date(s.snapshot_time).getTime() / 1000) as any,
          value: s.return_pct,
        }));
        series.setData(data);
      } else {
        // Fallback baseline point if no trade snapshot yet
        const nowSec = Math.floor(Date.now() / 1000);
        series.setData([
          { time: (nowSec - 86400) as any, value: 0 },
          { time: nowSec as any, value: 0 },
        ]);
      }

      seriesMap[modelId] = series;
    });

    chart.timeScale().fitContent();

    // Resize listener
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [snapshots, selectedModels, rankings]);

  const toggleModel = (id: string) => {
    setSelectedModels((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]
    );
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
            AI 모델별 누적 수익률 추이를 인터랙티브 캔버스 차트로 정밀 비교
          </p>
        </div>
      </div>

      {/* Model toggle chips */}
      <div className="flex flex-wrap items-center gap-2 mb-4 pb-3 border-b border-slate-800/80">
        <span className="text-xs font-semibold text-slate-400 mr-1">비교 모델:</span>
        {rankings.map((r, idx) => {
          const isSelected = selectedModels.includes(r.model_id);
          const color = colors[idx % colors.length];
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
                <CheckSquare className="w-3.5 h-3.5" style={{ color }} />
              ) : (
                <Square className="w-3.5 h-3.5" />
              )}
              <span className="truncate max-w-[140px]">{r.display_name}</span>
            </button>
          );
        })}
      </div>

      {/* Canvas Chart Container */}
      <div ref={chartContainerRef} className="w-full relative min-h-[380px]" />
    </div>
  );
};
