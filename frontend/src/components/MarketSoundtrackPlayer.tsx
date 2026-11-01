import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Music,
  Disc3,
  Sparkles,
  Activity,
  Clock,
  Globe,
  Radio,
  Repeat,
  Zap,
} from 'lucide-react';
import { MarketSoundtrack } from '../types';

interface MarketSoundtrackPlayerProps {
  soundtracks: MarketSoundtrack[];
}

export const MarketSoundtrackPlayer: React.FC<MarketSoundtrackPlayerProps> = ({ soundtracks }) => {
  // Determine default market based on KST (08:00 ~ 20:00: KR, otherwise: US)
  const getKSTStatus = useCallback(() => {
    try {
      const now = new Date();
      const kstString = now.toLocaleString('en-US', { timeZone: 'Asia/Seoul' });
      const kstDate = new Date(kstString);
      const hours = kstDate.getHours();
      const minutes = kstDate.getMinutes();
      const isKRSchedule = hours >= 8 && hours < 20;
      const formattedTime = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')} KST`;
      return {
        defaultMarket: (isKRSchedule ? 'KR' : 'US') as 'KR' | 'US',
        isKRSchedule,
        formattedTime,
      };
    } catch {
      const hours = new Date().getHours();
      const isKRSchedule = hours >= 8 && hours < 20;
      return {
        defaultMarket: (isKRSchedule ? 'KR' : 'US') as 'KR' | 'US',
        isKRSchedule,
        formattedTime: 'KST',
      };
    }
  }, []);

  const [kstStatus, setKstStatus] = useState(getKSTStatus);
  const [selectedMarket, setSelectedMarket] = useState<'KR' | 'US'>(kstStatus.defaultMarket);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(120);
  const [volume, setVolume] = useState<number>(0.85);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [isBgmMode, setIsBgmMode] = useState<boolean>(true); // default BGM loop mode
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Update KST clock periodically
  useEffect(() => {
    const timer = setInterval(() => {
      setKstStatus(getKSTStatus());
    }, 30000);
    return () => clearInterval(timer);
  }, [getKSTStatus]);

  const currentTrack =
    soundtracks.find((t) => t.market === selectedMarket) ||
    soundtracks[0];

  // When selected track changes, load new audio
  useEffect(() => {
    setCurrentTime(0);
    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      if (isPlaying) {
        audioRef.current.play().catch((err) => {
          console.warn('Autoplay prevented on switch:', err);
          setIsPlaying(false);
        });
      }
    }
  }, [selectedMarket]);

  // Set audio volume & loop whenever ref changes
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = isMuted ? 0 : volume;
      audioRef.current.loop = isBgmMode;
    }
  }, [volume, isMuted, isBgmMode]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current
        .play()
        .then(() => {
          setIsPlaying(true);
        })
        .catch((e) => {
          console.error('Audio play error:', e);
        });
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
      if (audioRef.current.duration && !isNaN(audioRef.current.duration)) {
        setDuration(audioRef.current.duration);
      }
    }
  };

  const handleEnded = () => {
    if (!isBgmMode) {
      setIsPlaying(false);
      setCurrentTime(0);
    }
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

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newVol = parseFloat(e.target.value);
    setVolume(newVol);
    if (audioRef.current) {
      audioRef.current.volume = newVol;
      if (newVol > 0 && isMuted) {
        setIsMuted(false);
        audioRef.current.muted = false;
      }
    }
  };

  const formatTime = (sec: number) => {
    if (isNaN(sec)) return '0:00';
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  if (!currentTrack) return null;

  const isCurrentMarketScheduled =
    (selectedMarket === 'KR' && kstStatus.isKRSchedule) ||
    (selectedMarket === 'US' && !kstStatus.isKRSchedule);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-cyan-500/20 bg-gradient-to-r from-slate-900/90 via-[#0b1329]/80 to-slate-900/90 p-5 backdrop-blur-xl shadow-2xl">
      {/* Background ambient lighting */}
      <div
        className={`absolute -right-20 -top-20 h-56 w-56 rounded-full blur-3xl opacity-20 pointer-events-none transition-all duration-700 ${
          selectedMarket === 'KR' ? 'bg-cyan-500' : 'bg-emerald-500'
        }`}
      />
      <div
        className={`absolute -left-20 -bottom-20 h-56 w-56 rounded-full blur-3xl opacity-10 pointer-events-none transition-all duration-700 ${
          selectedMarket === 'KR' ? 'bg-blue-600' : 'bg-teal-500'
        }`}
      />

      {/* HTML5 Audio element */}
      <audio
        ref={audioRef}
        src={currentTrack.audio_url}
        loop={isBgmMode}
        onTimeUpdate={handleTimeUpdate}
        onEnded={handleEnded}
        onLoadedMetadata={() => {
          if (audioRef.current?.duration && !isNaN(audioRef.current.duration)) {
            setDuration(audioRef.current.duration);
          }
        }}
      />

      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <div
            className={`flex h-11 w-11 items-center justify-center rounded-xl border shadow-inner transition-all duration-500 ${
              isPlaying
                ? selectedMarket === 'KR'
                  ? 'bg-cyan-500/20 border-cyan-400/40 text-cyan-300 shadow-cyan-500/20'
                  : 'bg-emerald-500/20 border-emerald-400/40 text-emerald-300 shadow-emerald-500/20'
                : 'bg-slate-800/60 border-slate-700/60 text-slate-400'
            }`}
          >
            {isPlaying ? (
              <Disc3 className="h-6 w-6 animate-spin text-cyan-400 duration-1000" />
            ) : (
              <Music className="h-5 w-5" />
            )}
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-1.5">
                AI Market Soundtrack
                <span className="flex items-center gap-1 rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold text-cyan-400 border border-cyan-500/20">
                  <Sparkles className="h-2.5 w-2.5" />
                  2분 데일리 마켓 BGM
                </span>
              </h3>
              {/* Scheduled Market Broadcast Indicator */}
              <div
                className={`flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium border ${
                  kstStatus.isKRSchedule
                    ? 'bg-cyan-950/60 border-cyan-500/30 text-cyan-300'
                    : 'bg-emerald-950/60 border-emerald-500/30 text-emerald-300'
                }`}
              >
                <Radio className="h-3 w-3 animate-pulse" />
                <span>
                  {kstStatus.isKRSchedule
                    ? '🇰🇷 KST 08:00~20:00 국장 BGM 편성'
                    : '🇺🇸 KST 20:00~08:00 미장 BGM 편성'}
                </span>
                <span className="text-[10px] opacity-75 font-mono">({kstStatus.formattedTime})</span>
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              실시간 시장 시황 데이터를 기반으로 생성된 2분 연속 배경음악(BGM) • 매일 07:30 / 19:30 KST 자동 갱신
            </p>
          </div>
        </div>

        {/* Market Selection Tabs */}
        <div className="flex items-center gap-2 self-start md:self-auto">
          <div className="flex items-center rounded-xl bg-slate-950/80 p-1 border border-slate-800">
            <button
              onClick={() => setSelectedMarket('KR')}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                selectedMarket === 'KR'
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-md shadow-cyan-500/20'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>🇰🇷 국장 (Lo-Fi 84 BPM)</span>
              {kstStatus.isKRSchedule && (
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-300 animate-ping" />
              )}
            </button>
            <button
              onClick={() => setSelectedMarket('US')}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                selectedMarket === 'US'
                  ? 'bg-gradient-to-r from-emerald-500 to-teal-600 text-white shadow-md shadow-emerald-500/20'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>🇺🇸 미장 (Synthwave 124 BPM)</span>
              {!kstStatus.isKRSchedule && (
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 animate-ping" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Main Player Row */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 pt-4 items-center">
        {/* Left: Player Controls & Visualizer */}
        <div className="lg:col-span-6 flex flex-col gap-3">
          <div className="flex items-center gap-4">
            {/* Play/Pause Button */}
            <button
              onClick={togglePlay}
              className={`flex h-14 w-14 items-center justify-center rounded-2xl transition-all transform active:scale-95 shadow-lg shrink-0 ${
                selectedMarket === 'KR'
                  ? 'bg-gradient-to-br from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-cyan-500/30'
                  : 'bg-gradient-to-br from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white shadow-emerald-500/30'
              }`}
              title={isPlaying ? '일시정지' : 'BGM 재생'}
            >
              {isPlaying ? (
                <Pause className="h-6 w-6 fill-current" />
              ) : (
                <Play className="h-6 w-6 fill-current ml-0.5" />
              )}
            </button>

            {/* Title, Date & Genre */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-cyan-400 font-mono">
                  {currentTrack.date}
                </span>
                <span className="rounded-md bg-slate-800/80 px-1.5 py-0.5 text-[10px] text-slate-300 font-mono">
                  {currentTrack.genre}
                </span>
                {isCurrentMarketScheduled && (
                  <span className="rounded-md bg-cyan-500/10 px-1.5 py-0.5 text-[10px] text-cyan-400 font-mono border border-cyan-500/20">
                    현재 편성곡
                  </span>
                )}
              </div>
              <h4 className="text-sm sm:text-base font-bold text-slate-100 truncate mt-0.5">
                {currentTrack.title}
              </h4>
              <div className="flex items-center gap-2 text-xs text-slate-400 font-mono mt-1">
                <span>{currentTrack.bpm} BPM</span>
                <span>•</span>
                <span>{currentTrack.key}</span>
                <span>•</span>
                <span className="text-slate-300 truncate">{currentTrack.mood}</span>
              </div>
            </div>

            {/* Animated Equalizer Waveform Bars */}
            <div className="hidden sm:flex items-end gap-1 h-9 px-2.5 py-1.5 bg-slate-950/60 rounded-xl border border-slate-800/60">
              {[45, 80, 55, 95, 65, 85, 50, 100, 70, 90].map((h, i) => (
                <div
                  key={i}
                  className={`w-1 rounded-full transition-all duration-200 ${
                    isPlaying
                      ? selectedMarket === 'KR'
                        ? 'bg-cyan-400 animate-pulse'
                        : 'bg-emerald-400 animate-pulse'
                      : 'bg-slate-700 h-1'
                  }`}
                  style={{
                    height: isPlaying ? `${Math.max(20, (h * ((i % 4) + 1)) % 100)}%` : '3px',
                    animationDelay: `${i * 90}ms`,
                  }}
                />
              ))}
            </div>
          </div>

          {/* Progress Bar & Seek */}
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-mono text-cyan-400 w-9 text-right font-semibold">
              {formatTime(currentTime)}
            </span>
            <input
              type="range"
              min="0"
              max={duration || 120}
              step="0.1"
              value={currentTime}
              onChange={handleSeek}
              className="flex-1 h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 hover:accent-cyan-300 transition-colors"
            />
            <span className="text-[11px] font-mono text-slate-400 w-9">
              {formatTime(duration)}
            </span>

            {/* Loop BGM Toggle */}
            <button
              onClick={() => setIsBgmMode(!isBgmMode)}
              className={`p-1.5 rounded-lg border text-xs flex items-center gap-1 transition-colors ${
                isBgmMode
                  ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300'
                  : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:text-slate-200'
              }`}
              title="BGM 무한 반복 재생 모드"
            >
              <Repeat className={`h-3.5 w-3.5 ${isBgmMode ? 'text-cyan-400' : ''}`} />
              <span className="text-[10px] font-mono hidden sm:inline">LOOP</span>
            </button>

            {/* Volume / Mute Controls */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={toggleMute}
                className="text-slate-400 hover:text-slate-200 transition-colors p-1"
                title={isMuted ? '음소거 해제' : '음소거'}
              >
                {isMuted || volume === 0 ? (
                  <VolumeX className="h-4 w-4 text-rose-400" />
                ) : (
                  <Volume2 className="h-4 w-4" />
                )}
              </button>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={isMuted ? 0 : volume}
                onChange={handleVolumeChange}
                className="w-16 h-1 bg-slate-800 rounded appearance-none cursor-pointer accent-cyan-400"
                title="음량 조절"
              />
            </div>
          </div>
        </div>

        {/* Right: AI Market Analysis & Music Rationale */}
        <div className="lg:col-span-6 bg-slate-950/50 rounded-xl p-4 border border-slate-800/60 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-cyan-400" />
                <span className="text-xs font-semibold text-slate-200">
                  AI 시장 음향화 해설 (Sonification Analysis)
                </span>
              </div>
              <span className="text-[11px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded-full border border-cyan-800/40">
                2분 확장 스위트
              </span>
            </div>
            <p className="text-xs leading-relaxed text-slate-300/95 font-sans">
              {currentTrack.summary}
            </p>
          </div>

          <div className="mt-3 pt-2.5 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-400">
            <div className="flex items-center gap-2">
              <Globe className="h-3.5 w-3.5 text-cyan-400" />
              <span>{currentTrack.market_name}</span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[10px] text-slate-500">
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                매일 07:30 / 19:30 KST 갱신
              </span>
              <span>16-bit 32kHz Stereo</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
