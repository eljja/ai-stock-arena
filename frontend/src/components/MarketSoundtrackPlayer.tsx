import React, { useState, useRef, useEffect } from 'react';
import { Play, Pause, Volume2, VolumeX, Music, Disc3, Sparkles, Activity, Clock, Globe } from 'lucide-react';
import { MarketSoundtrack } from '../types';

interface MarketSoundtrackPlayerProps {
  soundtracks: MarketSoundtrack[];
}

export const MarketSoundtrackPlayer: React.FC<MarketSoundtrackPlayerProps> = ({ soundtracks }) => {
  const [selectedMarket, setSelectedMarket] = useState<'KR' | 'US'>('KR');
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(16);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const currentTrack = soundtracks.find((t) => t.market === selectedMarket) || soundtracks[0];

  useEffect(() => {
    // When track changes, pause and reset
    setIsPlaying(false);
    setCurrentTime(0);
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
  }, [selectedMarket]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().then(() => {
        setIsPlaying(true);
      }).catch((e) => {
        console.error('Audio play error:', e);
      });
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
      if (audioRef.current.duration) {
        setDuration(audioRef.current.duration);
      }
    }
  };

  const handleEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const seekTime = parseFloat(e.target.value);
    setCurrentTime(seekTime);
    if (audioRef.current) {
      audioRef.current.currentTime = seekTime;
    }
  };

  const toggleMute = () => {
    if (audioRef.current) {
      audioRef.current.muted = !isMuted;
      setIsMuted(!isMuted);
    }
  };

  const formatTime = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  if (!currentTrack) return null;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-cyan-500/20 bg-gradient-to-r from-slate-900/90 via-[#0b1329]/80 to-slate-900/90 p-5 backdrop-blur-xl shadow-2xl">
      {/* Background glow effect */}
      <div className={`absolute -right-16 -top-16 h-48 w-48 rounded-full blur-3xl opacity-20 pointer-events-none transition-colors duration-500 ${
        selectedMarket === 'KR' ? 'bg-cyan-500' : 'bg-emerald-500'
      }`} />

      {/* Audio element */}
      <audio
        ref={audioRef}
        src={currentTrack.audio_url}
        onTimeUpdate={handleTimeUpdate}
        onEnded={handleEnded}
        onLoadedMetadata={() => {
          if (audioRef.current?.duration) {
            setDuration(audioRef.current.duration);
          }
        }}
      />

      {/* Header bar: Title & Market Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/30 border border-cyan-500/30 text-cyan-400 shadow-inner">
            <Music className={`h-5 w-5 ${isPlaying ? 'animate-bounce text-cyan-300' : ''}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-1.5">
                AI Market Soundtrack
                <span className="flex items-center gap-1 rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold text-cyan-400 border border-cyan-500/20">
                  <Sparkles className="h-2.5 w-2.5" />
                  AI 음향화 & Lyria
                </span>
              </h3>
            </div>
            <p className="text-xs text-slate-400">
              시황 데이터와 투자 감성을 사운드로 변환한 데일리 마켓 브리핑 BGM
            </p>
          </div>
        </div>

        {/* Market Tabs */}
        <div className="flex items-center rounded-xl bg-slate-950/60 p-1 border border-slate-800">
          <button
            onClick={() => setSelectedMarket('KR')}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
              selectedMarket === 'KR'
                ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-md shadow-cyan-500/20'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>🇰🇷 국장 (KOSPI)</span>
          </button>
          <button
            onClick={() => setSelectedMarket('US')}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
              selectedMarket === 'US'
                ? 'bg-gradient-to-r from-emerald-500 to-teal-600 text-white shadow-md shadow-emerald-500/20'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>🇺🇸 미장 (NASDAQ)</span>
          </button>
        </div>
      </div>

      {/* Main Player Row */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 pt-4 items-center">
        {/* Left: Interactive Controls & Equalizer */}
        <div className="lg:col-span-5 flex flex-col gap-3">
          <div className="flex items-center gap-4">
            {/* Play/Pause Button */}
            <button
              onClick={togglePlay}
              className={`flex h-14 w-14 items-center justify-center rounded-2xl transition-all transform active:scale-95 shadow-lg ${
                selectedMarket === 'KR'
                  ? 'bg-gradient-to-br from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-cyan-500/30'
                  : 'bg-gradient-to-br from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white shadow-emerald-500/30'
              }`}
              title={isPlaying ? '일시정지' : '재생'}
            >
              {isPlaying ? (
                <Pause className="h-6 w-6 fill-current" />
              ) : (
                <Play className="h-6 w-6 fill-current ml-0.5" />
              )}
            </button>

            {/* Title & Date */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-cyan-400 font-mono">
                  {currentTrack.date}
                </span>
                <span className="rounded-md bg-slate-800/80 px-1.5 py-0.5 text-[10px] text-slate-300 font-mono">
                  {currentTrack.genre}
                </span>
              </div>
              <h4 className="text-sm sm:text-base font-bold text-slate-100 truncate mt-0.5">
                {currentTrack.title}
              </h4>
              <div className="flex items-center gap-3 text-xs text-slate-400 font-mono mt-1">
                <span>{currentTrack.bpm} BPM</span>
                <span>•</span>
                <span>{currentTrack.key}</span>
                <span>•</span>
                <span className="text-slate-300">{currentTrack.mood}</span>
              </div>
            </div>

            {/* Animated Equalizer Waveform Bars */}
            <div className="flex items-end gap-1 h-8 px-2 py-1 bg-slate-950/40 rounded-lg border border-slate-800/60">
              {[40, 75, 50, 95, 60, 85, 45, 100].map((h, i) => (
                <div
                  key={i}
                  className={`w-1 rounded-full transition-all duration-300 ${
                    isPlaying
                      ? selectedMarket === 'KR'
                        ? 'bg-cyan-400 animate-pulse'
                        : 'bg-emerald-400 animate-pulse'
                      : 'bg-slate-700 h-1.5'
                  }`}
                  style={{
                    height: isPlaying ? `${Math.max(20, (h * ((i % 3) + 1)) % 100)}%` : '4px',
                    animationDelay: `${i * 120}ms`,
                  }}
                />
              ))}
            </div>
          </div>

          {/* Progress Bar & Timers */}
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-mono text-slate-400 w-8 text-right">
              {formatTime(currentTime)}
            </span>
            <input
              type="range"
              min="0"
              max={duration || 16}
              step="0.1"
              value={currentTime}
              onChange={handleSeek}
              className="flex-1 h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
            />
            <span className="text-[11px] font-mono text-slate-500 w-8">
              {formatTime(duration)}
            </span>
            <button
              onClick={toggleMute}
              className="text-slate-400 hover:text-slate-200 transition-colors"
              title={isMuted ? '음소거 해제' : '음소거'}
            >
              {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* Right: Market Analysis & Music Rationale */}
        <div className="lg:col-span-7 bg-slate-950/40 rounded-xl p-3.5 border border-slate-800/60 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <Activity className="h-3.5 w-3.5 text-cyan-400" />
              <span className="text-xs font-semibold text-slate-300">
                AI 음악 해설 (Why This Sound?)
              </span>
            </div>
            <p className="text-xs leading-relaxed text-slate-300/90 font-sans">
              {currentTrack.summary}
            </p>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/40 flex items-center justify-between text-[11px] text-slate-400">
            <span className="flex items-center gap-1">
              <Globe className="h-3 w-3 text-cyan-400" />
              {currentTrack.market_name}
            </span>
            <span className="font-mono text-slate-500">
              CD Quality 44.1kHz Stereo
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
