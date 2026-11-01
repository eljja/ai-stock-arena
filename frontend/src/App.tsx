import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { HeroPodium } from './components/HeroPodium';
import { LeaderboardTable } from './components/LeaderboardTable';
import { PerformanceChart } from './components/PerformanceChart';
import { NewsWall } from './components/NewsWall';
import { TradeFeed } from './components/TradeFeed';
import { ModelDetailModal } from './components/ModelDetailModal';
import { MarketSoundtrackPlayer } from './components/MarketSoundtrackPlayer';
import { api } from './services/api';
import {
  ModelRanking,
  PortfolioSummary,
  PositionSummary,
  TradeSummary,
  NewsItemSummary,
  LLMDecisionLogSummary,
  SnapshotSummary,
  MarketSoundtrack,
} from './types';
import { Trophy, LineChart, Newspaper, Activity, Sparkles } from 'lucide-react';

export function App() {
  const [activeTab, setActiveTab] = useState<'ranking' | 'charts' | 'news' | 'trades'>('ranking');
  const [rankings, setRankings] = useState<ModelRanking[]>([]);
  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [positions, setPositions] = useState<PositionSummary[]>([]);
  const [trades, setTrades] = useState<TradeSummary[]>([]);
  const [newsItems, setNewsItems] = useState<NewsItemSummary[]>([]);
  const [llmLogs, setLlmLogs] = useState<LLMDecisionLogSummary[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [soundtracks, setSoundtracks] = useState<MarketSoundtrack[]>([]);

  const [selectedModel, setSelectedModel] = useState<ModelRanking | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [error, setError] = useState<string | null>(null);

  const loadData = async (isManual = false) => {
    if (isManual) setIsRefreshing(true);
    setError(null);
    try {
      const [
        rankingsData,
        portfoliosData,
        positionsData,
        tradesData,
        newsData,
        logsData,
        snapshotsData,
        soundtracksData,
      ] = await Promise.all([
        api.getRankings(),
        api.getPortfolios(),
        api.getPositions(),
        api.getTrades(50),
        api.getNewsItems(30),
        api.getLLMLogs(30),
        api.getSnapshots(300),
        api.getMarketSoundtracks().catch(() => []),
      ]);

      setRankings(rankingsData);
      setPortfolios(portfoliosData);
      setPositions(positionsData);
      setTrades(tradesData);
      setNewsItems(newsData);
      setLlmLogs(logsData);
      setSnapshots(snapshotsData);
      if (soundtracksData && soundtracksData.length > 0) {
        setSoundtracks(soundtracksData);
      }
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error('Data fetch error:', err);
      setError(err?.message || '데이터를 불러오는 중 오류가 발생했습니다.');
    } finally {
      if (isManual) setIsRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
    // Auto refresh every 30 seconds
    const interval = setInterval(() => {
      loadData();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-100 flex flex-col selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* Top Fixed Header */}
      <Header
        onRefresh={() => loadData(true)}
        isRefreshing={isRefreshing}
        lastUpdated={lastUpdated}
        activeModelCount={rankings.length}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 lg:px-8 py-6">
        {/* Error notification banner if any */}
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-rose-950/40 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <span>{error}</span>
            <button
              onClick={() => loadData(true)}
              className="px-2 py-1 rounded bg-rose-900/60 hover:bg-rose-800 text-white font-bold cursor-pointer"
            >
              다시 시도
            </button>
          </div>
        )}

        {/* Hero Spotlight (Top 3 Podium & Platform Stats) */}
        <HeroPodium rankings={rankings} onSelectModel={setSelectedModel} />

        {/* AI Daily Market Soundtrack Player */}
        {soundtracks.length > 0 && (
          <div className="mb-8">
            <MarketSoundtrackPlayer soundtracks={soundtracks} />
          </div>
        )}

        {/* Section Navigation Tabs */}
        <div className="flex items-center gap-2 mb-6 pb-2 border-b border-slate-800/80 overflow-x-auto">
          <button
            onClick={() => setActiveTab('ranking')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'ranking'
                ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg shadow-cyan-500/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
            }`}
          >
            <Trophy className="w-4 h-4" />
            <span>리그 순위표 (Ranking)</span>
          </button>

          <button
            onClick={() => setActiveTab('charts')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'charts'
                ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg shadow-cyan-500/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
            }`}
          >
            <LineChart className="w-4 h-4" />
            <span>수익률 벤치마크 차트</span>
          </button>

          <button
            onClick={() => setActiveTab('news')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'news'
                ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg shadow-cyan-500/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
            }`}
          >
            <Newspaper className="w-4 h-4" />
            <span>실시간 마켓 뉴스 ({newsItems.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('trades')}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'trades'
                ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg shadow-cyan-500/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
            }`}
          >
            <Activity className="w-4 h-4" />
            <span>AI 매매 & 추론 피드 ({trades.length})</span>
          </button>
        </div>

        {/* Tab Content Display */}
        <div>
          {activeTab === 'ranking' && (
            <LeaderboardTable rankings={rankings} onSelectModel={setSelectedModel} />
          )}

          {activeTab === 'charts' && (
            <PerformanceChart snapshots={snapshots} rankings={rankings} />
          )}

          {activeTab === 'news' && <NewsWall newsItems={newsItems} />}

          {activeTab === 'trades' && <TradeFeed trades={trades} logs={llmLogs} />}
        </div>
      </main>

      {/* Model Detail Popup Modal */}
      <ModelDetailModal
        model={selectedModel}
        portfolios={portfolios}
        positions={positions}
        trades={trades}
        onClose={() => setSelectedModel(null)}
      />

      {/* Modern Footer */}
      <footer className="border-t border-slate-900 py-6 px-4 text-center text-xs text-slate-500 mt-auto">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-400">AI Stock Arena v2.0</span>
            <span>•</span>
            <span>Autonomous Multi-Agent FinTech Benchmark</span>
          </div>
          <div>
            Powered by FastAPI • React 19 • Tailwind CSS • OpenRouter Free Models
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
