import React from 'react';
import { Newspaper, ExternalLink, Clock, Tag } from 'lucide-react';
import { NewsItemSummary } from '../types';
import { timeAgo } from '../utils/format';

interface NewsWallProps {
  newsItems: NewsItemSummary[];
}

export const NewsWall: React.FC<NewsWallProps> = ({ newsItems }) => {
  return (
    <div className="glass-panel rounded-2xl border border-slate-800 p-5 shadow-xl">
      <div className="flex items-center justify-between mb-5 pb-3 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Newspaper className="w-5 h-5 text-cyan-400" />
            <span>실시간 마켓 뉴스 피드 (Shared News)</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Naver, SaveTicker, Marketaux에서 수집되어 14개 AI 모델에게 제공되는 시장 뉴스
          </p>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
          최신 {newsItems.length}건
        </span>
      </div>

      {newsItems.length === 0 ? (
        <div className="text-center py-12 text-slate-500 text-sm">
          아직 수집된 뉴스가 없습니다.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {newsItems.map((item, index) => {
            const isNaver = item.source?.toLowerCase().includes('naver');
            const isSaveTicker = item.source?.toLowerCase().includes('saveticker');

            return (
              <div
                key={index}
                className="glass-card rounded-xl p-4 border border-slate-800/80 hover:border-slate-700 transition-all flex flex-col justify-between group"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                        isNaver
                          ? 'bg-emerald-950/40 text-emerald-400 border-emerald-500/30'
                          : isSaveTicker
                          ? 'bg-blue-950/40 text-blue-400 border-blue-500/30'
                          : 'bg-indigo-950/40 text-indigo-400 border-indigo-500/30'
                      }`}
                    >
                      {item.source}
                    </span>
                    <span className="flex items-center gap-1 text-[11px] text-slate-500 font-mono">
                      <Clock className="w-3 h-3" />
                      {timeAgo(item.published_at)}
                    </span>
                  </div>

                  <h3 className="text-sm font-bold text-slate-100 group-hover:text-cyan-400 transition-colors line-clamp-2 leading-snug mb-2">
                    {item.title}
                  </h3>

                  <p className="text-xs text-slate-400 line-clamp-3 leading-relaxed mb-3">
                    {item.summary}
                  </p>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 mt-auto">
                  <div className="flex items-center gap-1 text-[11px] text-slate-500">
                    {item.tickers && item.tickers.length > 0 && (
                      <span className="flex items-center gap-1">
                        <Tag className="w-3 h-3 text-cyan-400" />
                        {item.tickers.join(', ')}
                      </span>
                    )}
                  </div>

                  {item.url && (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-cyan-400 hover:text-cyan-300 transition-colors"
                    >
                      원문 기사 <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
