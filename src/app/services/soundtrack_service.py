from __future__ import annotations

import json
import logging
import math
import os
import wave
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import httpx
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import HourlyMarketPrice, SharedNewsItem

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "soundtracks"
METADATA_FILE = DATA_DIR / "metadata.json"
KST = timezone(timedelta(hours=9))
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_FREE_MODELS = [
    "cohere/north-mini-code:free",
    "nvidia/nemotron-3.5-lightning:free",
    "dots-studio/dots-3-note-preview:free",
    "openrouter/free",
]


@dataclass
class MarketContext:
    market_code: str
    market_name: str
    regime: str  # "CRASH" | "BEARISH" | "NEUTRAL" | "BULLISH" | "RALLY"
    avg_return_1d: float
    avg_volatility: float
    advancing_count: int
    declining_count: int
    total_count: int
    top_gainers: list[tuple[str, str, float]]  # (ticker, name, return_pct)
    top_losers: list[tuple[str, str, float]]   # (ticker, name, return_pct)
    key_leader_summary: str
    news_headlines: list[str]


def ensure_soundtracks_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def fetch_market_context(market_code: str, session: Session | None = None) -> MarketContext:
    """
    Extracts real-time market data (returns, volatility, gainers/losers, leaders, and news)
    and classifies the current market regime.
    """
    should_close = False
    if session is None:
        session = SessionLocal()
        should_close = True

    market_name = "대한민국 국장 (KOSPI / KOSDAQ)" if market_code == "KR" else "미국 미장 (NASDAQ / S&P500)"

    try:
        # 1. Fetch latest prices
        latest_price_row = session.scalar(
            select(HourlyMarketPrice)
            .where(HourlyMarketPrice.market_code == market_code)
            .order_by(desc(HourlyMarketPrice.as_of))
            .limit(1)
        )

        prices: list[HourlyMarketPrice] = []
        if latest_price_row is not None and latest_price_row.as_of is not None:
            prices = list(
                session.scalars(
                    select(HourlyMarketPrice)
                    .where(HourlyMarketPrice.market_code == market_code)
                    .where(HourlyMarketPrice.as_of == latest_price_row.as_of)
                )
            )

        if not prices:
            # Fallback to recent items
            prices = list(
                session.scalars(
                    select(HourlyMarketPrice)
                    .where(HourlyMarketPrice.market_code == market_code)
                    .order_by(desc(HourlyMarketPrice.created_at))
                    .limit(24)
                )
            )

        # 2. Compute market metrics
        valid_returns: list[float] = []
        valid_volatilities: list[float] = []
        advancing = 0
        declining = 0
        price_items: list[tuple[str, str, float]] = []

        for p in prices:
            ret = float(p.return_1d_pct) if p.return_1d_pct is not None else 0.0
            vol = float(p.intraday_volatility_pct) if p.intraday_volatility_pct is not None else 1.0
            valid_returns.append(ret)
            valid_volatilities.append(vol)
            name = p.instrument_name or p.ticker
            price_items.append((p.ticker, name, ret))
            if ret > 0.1:
                advancing += 1
            elif ret < -0.1:
                declining += 1

        total_count = len(price_items)
        avg_ret = (sum(valid_returns) / len(valid_returns)) if valid_returns else 0.0
        avg_vol = (sum(valid_volatilities) / len(valid_volatilities)) if valid_volatilities else 1.5

        # Sort gainers and losers
        sorted_by_ret = sorted(price_items, key=lambda x: x[2], reverse=True)
        top_gainers = sorted_by_ret[:3]
        top_losers = sorted_by_ret[-3:]
        top_losers.reverse()

        # Key leaders
        leader_parts: list[str] = []
        if market_code == "KR":
            for ticker, kor_name in [("005930.KS", "삼성전자"), ("000660.KS", "SK하이닉스"), ("035420.KS", "NAVER")]:
                match = next((item for item in price_items if item[0] == ticker), None)
                if match:
                    leader_parts.append(f"{kor_name}({match[2]:+.2f}%)")
        else:
            for ticker in ["NVDA", "AAPL", "MSFT", "TSLA"]:
                match = next((item for item in price_items if item[0] == ticker), None)
                if match:
                    leader_parts.append(f"{ticker}({match[2]:+.2f}%)")

        key_leader_summary = ", ".join(leader_parts) if leader_parts else "주요 대형주 횡보"

        # 3. Fetch latest news headlines
        news_rows = list(
            session.scalars(
                select(SharedNewsItem)
                .order_by(desc(SharedNewsItem.published_at))
                .limit(5)
            )
        )
        news_headlines = [n.title.strip() for n in news_rows if n.title][:3]

        # 4. Classify Regime
        # CRASH: Avg return <= -1.5% or severe decline skew
        if avg_ret <= -1.5 or (declining >= max(advancing * 3, 10) and avg_ret <= -0.8):
            regime = "CRASH"
        elif avg_ret <= -0.4 or (declining > advancing and avg_ret < 0):
            regime = "BEARISH"
        elif avg_ret >= 1.5 or (advancing >= max(declining * 3, 10) and avg_ret >= 0.8):
            regime = "RALLY"
        elif avg_ret >= 0.4 or (advancing > declining and avg_ret > 0):
            regime = "BULLISH"
        else:
            regime = "NEUTRAL"

        return MarketContext(
            market_code=market_code,
            market_name=market_name,
            regime=regime,
            avg_return_1d=round(avg_ret, 2),
            avg_volatility=round(avg_vol, 2),
            advancing_count=advancing,
            declining_count=declining,
            total_count=total_count,
            top_gainers=top_gainers,
            top_losers=top_losers,
            key_leader_summary=key_leader_summary,
            news_headlines=news_headlines,
        )
    finally:
        if should_close:
            session.close()


def synthesize_market_soundtrack(
    out_path: Path,
    market_code: str,
    context: MarketContext,
    duration_sec: float = 120.0,
) -> dict:
    """
    Vectorized DSP synthesizer that generates 120 seconds of dynamic, market-driven audio.
    Adapts BPM, harmony, bassline distortion, percussion weight, and textures based on market regime.
    """
    sr = 32000
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)

    regime = context.regime
    is_kr = market_code == "KR"

    # 1. Parameter Mapping based on Market Regime
    if regime == "CRASH":
        bpm = 72.0 if is_kr else 88.0
        key_str = "D Minor (Tense)"
        genre = "Dark Cinematic Ambient & Industrial Tension Suite" if is_kr else "Dystopian Cyberpunk & Dark Electro Suite"
        # Dm7 -> Bbm7 -> Gm7 -> A7b9 (Suspenseful, alarming minor descending chords)
        chords = np.array([
            [293.66, 349.23, 440.00, 523.25],  # Dm7 (D4, F4, A4, C5)
            [233.08, 277.18, 349.23, 415.30],  # Bbm7 (Bb3, Db4, F4, Ab4)
            [196.00, 233.08, 293.66, 349.23],  # Gm7 (G3, Bb3, D4, F4)
            [220.00, 277.18, 329.63, 415.30],  # A7b9 (A3, C#4, E4, Bb4)
        ], dtype=np.float32)
        bass_roots = np.array([36.71, 29.14, 24.50, 27.50], dtype=np.float32)  # D1, Bb0, G0, A0
        distort_bass = True
        drone_depth = 0.08
    elif regime == "BEARISH":
        bpm = 78.0 if is_kr else 108.0
        key_str = "A Minor (Melancholic)"
        genre = "Melancholic Lo-Fi & Rainy Noir Suite" if is_kr else "Dark Synthwave & Subdued Chillwave"
        # Am7 -> Dm7 -> Fmaj7 -> E7
        chords = np.array([
            [220.0, 261.63, 329.63, 392.00],  # Am7
            [146.83, 174.61, 220.0, 261.63],  # Dm7
            [174.61, 220.0, 261.63, 329.63],  # Fmaj7
            [164.81, 207.65, 246.94, 329.63],  # E7
        ], dtype=np.float32)
        bass_roots = np.array([55.0, 36.71, 43.65, 41.2], dtype=np.float32)
        distort_bass = False
        drone_depth = 0.03
    elif regime == "RALLY":
        bpm = 110.0 if is_kr else 132.0
        key_str = "D Major (Euphoric)"
        genre = "High-Energy Cyber Anthem & Euphoric Electro" if is_kr else "High-Voltage Outrun & Turbo Synthwave"
        # D -> A -> Bm -> G (Celebratory, soaring anthemic)
        chords = np.array([
            [293.66, 369.99, 440.00, 587.33],  # Dmaj
            [220.00, 277.18, 329.63, 440.00],  # Amaj
            [246.94, 293.66, 369.99, 493.88],  # Bm
            [196.00, 246.94, 293.66, 392.00],  # Gmaj
        ], dtype=np.float32)
        bass_roots = np.array([73.42, 55.0, 61.74, 49.0], dtype=np.float32)
        distort_bass = True
        drone_depth = 0.02
    elif regime == "BULLISH":
        bpm = 96.0 if is_kr else 126.0
        key_str = "G Major / C Major (Uplifting)"
        genre = "Uplifting Future Chill & Groovy Electric Suite" if is_kr else "Retro Electro & Driving Synthpop"
        # Cmaj7 -> Gmaj7 -> Fmaj7 -> Am7
        chords = np.array([
            [261.63, 329.63, 392.00, 493.88],  # Cmaj7
            [196.00, 246.94, 293.66, 392.00],  # Gmaj7
            [174.61, 220.0, 261.63, 329.63],  # Fmaj7
            [220.0, 261.63, 329.63, 392.00],  # Am7
        ], dtype=np.float32)
        bass_roots = np.array([65.41, 49.0, 43.65, 55.0], dtype=np.float32)
        distort_bass = False
        drone_depth = 0.02
    else:  # NEUTRAL
        bpm = 84.0 if is_kr else 120.0
        key_str = "A Minor / D Dorian (Chill)"
        genre = "Lo-Fi Cyber Ambient Suite" if is_kr else "Neon Synthwave & Mellow Electronic"
        # Am7 -> Fmaj7 -> Cmaj7 -> Em7
        chords = np.array([
            [220.0, 261.63, 329.63, 392.00],  # Am7
            [174.61, 220.0, 261.63, 329.63],  # Fmaj7
            [130.81, 196.0, 261.63, 329.63],  # Cmaj7
            [164.81, 246.94, 329.63, 392.00],  # Em7
        ], dtype=np.float32)
        bass_roots = np.array([55.0, 43.65, 32.7, 41.2], dtype=np.float32)
        distort_bass = False
        drone_depth = 0.01

    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4.0
    sixteenth = beat_sec / 4.0

    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)

    # Layer 1: Ambient Bed (Vinyl noise or Dark drone)
    noise = np.random.uniform(-0.008, 0.008, n).astype(np.float32)
    left += noise
    right += noise

    if drone_depth > 0:
        drone_freq = 55.0 if regime == "CRASH" else 110.0
        drone = np.sin(2 * np.pi * drone_freq * t + 0.5 * np.sin(2 * np.pi * 0.2 * t))
        if regime == "CRASH":
            # Add subtle dissonant minor 2nd clash (58.27 Hz) for tension
            drone += 0.6 * np.sin(2 * np.pi * 58.27 * t)
        left += (drone * drone_depth * 0.9).astype(np.float32)
        right += (drone * drone_depth * 1.1).astype(np.float32)

    # Layer 2: Main Harmonic Chords
    chord_idx = ((t // bar_sec) % len(chords)).astype(np.int32)
    t_bar = t % bar_sec
    chord_env = (np.sin(np.pi * (t_bar / bar_sec)) ** 0.65).astype(np.float32)

    for i in range(4):
        freqs = chords[chord_idx, i]
        phase = 2 * np.pi * np.cumsum(freqs) / sr
        sig = 0.07 * np.sin(phase) + 0.03 * np.sin(phase * 2.0) + 0.01 * np.sin(phase * 3.0)
        left += sig * chord_env * 0.95
        right += sig * chord_env * 1.05

    # Layer 3: Dynamic Percussion
    drum_start_time = 4 * bar_sec
    drum_end_time = int(duration_sec / bar_sec - 4) * bar_sec
    total_beats = int(duration_sec / beat_sec)

    for b in range(total_beats):
        b_time = b * beat_sec
        if b_time < drum_start_time or b_time > drum_end_time:
            continue

        bar_beat = b % 4
        # Kick: On beat 0 and beat 2 (or four-on-the-floor for RALLY)
        is_kick = (bar_beat in [0, 2]) or (regime == "RALLY" and bar_beat in [0, 1, 2, 3])
        if is_kick:
            idx = int(b_time * sr)
            k_len = int(0.28 * sr)
            if idx + k_len < n:
                k_t = np.linspace(0, 0.28, k_len, dtype=np.float32)
                k_start_pitch = 140.0 if regime in ["CRASH", "RALLY"] else 110.0
                k_pitch = k_start_pitch * np.exp(-18 * k_t) + 38.0
                k_sig = 0.45 * np.sin(2 * np.pi * k_pitch * k_t) * np.exp(-7.5 * k_t)
                left[idx:idx + k_len] += k_sig
                right[idx:idx + k_len] += k_sig

        # Snare on beat 1 and beat 3 (or beat 2 for half-time)
        if bar_beat in [1, 3]:
            idx = int(b_time * sr)
            s_len = int(0.24 * sr)
            if idx + s_len < n:
                s_t = np.linspace(0, 0.24, s_len, dtype=np.float32)
                noise_decay = -12 if regime == "CRASH" else -15
                noise_s = np.random.uniform(-0.18, 0.18, s_len).astype(np.float32) * np.exp(noise_decay * s_t)
                tone_s = 0.20 * np.sin(2 * np.pi * 180 * s_t) * np.exp(-18 * s_t)
                left[idx:idx + s_len] += (noise_s + tone_s) * 0.95
                right[idx:idx + s_len] += (noise_s + tone_s) * 1.05

        # Hi-hats
        for h_sub in [0.0, 0.5]:
            h_time = b_time + h_sub * beat_sec
            idx = int(h_time * sr)
            h_len = int(0.06 * sr)
            if idx + h_len < n:
                h_t = np.linspace(0, 0.06, h_len, dtype=np.float32)
                h_sig = np.random.uniform(-0.06, 0.06, h_len).astype(np.float32) * np.exp(-35 * h_t)
                pan = 0.35 if h_sub == 0.0 else 0.65
                left[idx:idx + h_len] += h_sig * (1.0 - pan)
                right[idx:idx + h_len] += h_sig * pan

    # Layer 4: Bassline
    bass_start = 4 * bar_sec
    bass_end = int(duration_sec / bar_sec - 2) * bar_sec
    for b in range(total_beats):
        b_time = b * beat_sec
        if b_time < bass_start or b_time > bass_end:
            continue
        bar_i = int(b_time // bar_sec) % len(bass_roots)
        root = bass_roots[bar_i]
        if b % 2 == 0:
            idx = int(b_time * sr)
            b_len = int(beat_sec * 1.7 * sr)
            if idx + b_len < n:
                b_t = np.linspace(0, beat_sec * 1.7, b_len, dtype=np.float32)
                b_sig = 0.30 * np.sin(2 * np.pi * root * b_t) * np.exp(-1.0 * b_t)
                b_sig += 0.12 * np.sin(2 * np.pi * (root * 2) * b_t) * np.exp(-1.8 * b_t)

                if distort_bass:
                    # Saturated tape / tube distortion for heavy dark drive
                    b_sig = np.tanh(b_sig * 2.8) * 0.38

                left[idx:idx + b_len] += b_sig
                right[idx:idx + b_len] += b_sig

    # Layer 5: Melodic / Arpeggio Layer
    arp_notes = (
        [349.23, 440.0, 523.25, 622.25, 523.25, 440.0] if regime == "CRASH"
        else [523.25, 659.25, 783.99, 880.00, 1046.50, 880.00] if regime in ["BULLISH", "RALLY"]
        else [440.0, 523.25, 659.25, 783.99, 659.25, 523.25]
    )
    for s_step in range(int(duration_sec / sixteenth)):
        s_time = s_step * sixteenth
        if s_time < 8 * bar_sec or s_time > (duration_sec - 6 * bar_sec):
            continue
        note = arp_notes[s_step % len(arp_notes)]
        idx = int(s_time * sr)
        a_len = int(0.25 * sr)
        if idx + a_len < n:
            a_t = np.linspace(0, 0.25, a_len, dtype=np.float32)
            decay = -9 if regime == "CRASH" else -7
            a_sig = 0.08 * np.sin(2 * np.pi * note * a_t) * np.exp(decay * a_t)
            pan = 0.5 + 0.35 * np.sin(s_step * 0.7)
            left[idx:idx + a_len] += a_sig * (1.0 - pan)
            right[idx:idx + a_len] += a_sig * pan

    # Layer 6: Master Fade In & Out
    fade_in = min(int(2.5 * sr), max(1, int(n * 0.1)))
    fade_out = min(int(4.5 * sr), max(1, int(n * 0.15)))
    left[:fade_in] *= np.linspace(0.0, 1.0, fade_in)
    right[:fade_in] *= np.linspace(0.0, 1.0, fade_in)
    left[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)
    right[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)

    # Master Normalize
    max_val = max(float(np.max(np.abs(left))), float(np.max(np.abs(right))), 1e-4)
    left = (left / max_val) * 0.88
    right = (right / max_val) * 0.88

    stereo = np.zeros((n, 2), dtype=np.int16)
    stereo[:, 0] = np.int16(left * 32767)
    stereo[:, 1] = np.int16(right * 32767)

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())

    return {
        "bpm": int(bpm),
        "key": key_str,
        "genre": genre,
    }


def build_fallback_metadata(
    market_code: str,
    today_formatted: str,
    context: MarketContext,
    bpm: int,
    key_str: str,
    genre: str,
    filename: str,
) -> dict:
    """
    Constructs high-fidelity, data-grounded Korean narrative metadata matching the exact market numbers.
    Used whenever the LLM API is unavailable, rate-limited, or disabled.
    """
    is_kr = market_code == "KR"
    regime = context.regime
    avg_ret = context.avg_return_1d
    adv = context.advancing_count
    dec = context.declining_count
    leader_text = context.key_leader_summary
    headline = context.news_headlines[0] if context.news_headlines else "글로벌 매크로 불확실성 지속"

    if regime == "CRASH":
        title = f"Dark Tempest Suite ({today_formatted}): {leader_text.split(',')[0]} 급락과 투매의 긴장"
        mood = "극도의 공포, 대형주 급락 충격, 외인 투매, 지수 하단 위협"
        summary = (
            f"{today_formatted} {'한국' if is_kr else '미국'} 시장은 {leader_text}을 필두로 평균 {avg_ret:+.2f}% 급락하며 "
            f"하락 {dec}개 종목이 상승 {adv}개 종목을 압도하는 거센 투매 공포가 장을 덮쳤습니다. "
            f"'{headline}' 등의 악재가 겹치며 방어선이 무너진 패닉 국면을 무겁고 불길한 {bpm} BPM 마이너 텐션과 "
            f"디스토션 서브베이스로 생생히 담아낸 2분 사운드트랙입니다."
        )
    elif regime == "BEARISH":
        title = f"Subdued Twilight Suite ({today_formatted}): {leader_text.split(',')[0]} 조정과 신중한 관망세"
        mood = "차익 실현 매물, 지수 조정, 신중한 관망세, 저가 매수 탐색"
        summary = (
            f"{today_formatted} {'한국' if is_kr else '미국'} 시장은 전일 대비 평균 {avg_ret:+.2f}% 조정을 보이며 "
            f"하락 {dec}종목이 우세한 신중한 관망세를 나타냈습니다. "
            f"{leader_text}의 약세와 '{headline}' 이슈 속 차익 매물이 출회된 장세를 "
            f"차분하고 멜랑콜리한 {bpm} BPM 로우파이 피아노와 절제된 비트로 표현한 2분 사운드트랙입니다."
        )
    elif regime == "RALLY":
        title = f"High-Voltage Neon Anthem ({today_formatted}): {leader_text.split(',')[0]} 주도 폭발적 랠리"
        mood = "전방위 불장, 신고가 랠리, 강력한 매수세, 환호와 모멘텀"
        summary = (
            f"{today_formatted} {'한국' if is_kr else '미국'} 시장은 {leader_text} 등 주도주의 폭발적인 랠리로 "
            f"평균 {avg_ret:+.2f}% 급등하며 상승 {adv}종목이 시장을 완전히 장악했습니다. "
            f"'{headline}' 등 강력한 호재 속 신고가 랠리를 질주하는 "
            f"{bpm} BPM 하이파이 신스웨이브와 파워풀한 4-on-the-floor 비트로 담아낸 2분 사운드트랙입니다."
        )
    elif regime == "BULLISH":
        title = f"Ascent Pulse Suite ({today_formatted}): {leader_text.split(',')[0]} 반등과 매수 모멘텀"
        mood = "매수세 유입, 지수 반등 모멘텀, 업종 동반 상승, 회복 기대감"
        summary = (
            f"{today_formatted} {'한국' if is_kr else '미국'} 시장은 {leader_text}의 견조한 매수세에 힘입어 "
            f"평균 {avg_ret:+.2f}% 상승하며 긍정적인 반등 모멘텀을 형성했습니다. "
            f"'{headline}' 등 호재와 수급 개선이 지수를 견인한 활기찬 장세를 "
            f"경쾌한 {bpm} BPM 그루브와 밝은 일렉트릭 피아노로 담아낸 2분 사운드트랙입니다."
        )
    else:  # NEUTRAL
        title = f"Equilibrium Resonance ({today_formatted}): {leader_text.split(',')[0]} 수급 균형과 순환매"
        mood = "수급 균형, 업종별 순환매, 박스권 등락, 방향성 모색"
        summary = (
            f"{today_formatted} {'한국' if is_kr else '미국'} 시장은 평균 {avg_ret:+.2f}%로 보합권에 머물며 "
            f"상승 {adv}종목과 하락 {dec}종목이 팽팽히 맞서는 수급 균형을 보였습니다. "
            f"{leader_text} 등 업종별 순환매가 이어진 박스권 흐름을 "
            f"{bpm} BPM의 칠한 비트와 따뜻한 로우파이 피아노 아르페지오로 담아낸 2분 사운드트랙입니다."
        )

    return {
        "id": f"{market_code.lower()}-{today_formatted.replace('-', '')}",
        "market": market_code,
        "market_name": context.market_name,
        "date": f"{today_formatted} ({'당일 아침 브리핑' if is_kr else '당일 저녁 브리핑'})",
        "title": title,
        "genre": genre,
        "bpm": bpm,
        "key": key_str,
        "mood": mood,
        "audio_url": f"/api/soundtracks/{filename}",
        "duration_sec": 120,
        "summary": summary,
    }


def generate_soundtrack_metadata(
    market_code: str,
    today_formatted: str,
    context: MarketContext,
    bpm: int,
    key_str: str,
    genre: str,
    filename: str,
    session: Session | None = None,
) -> dict:
    """
    Attempts to call OpenRouter LLM to generate creative, market-grounded narrative metadata.
    Falls back gracefully to build_fallback_metadata on any network or parsing error.
    """
    fallback = build_fallback_metadata(
        market_code, today_formatted, context, bpm, key_str, genre, filename
    )

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key and session is not None:
        try:
            secrets = get_runtime_secrets(session)
            api_key = secrets.get("openrouter_api_key")
        except Exception:
            pass

    if not api_key:
        return fallback

    is_kr = market_code == "KR"
    headline_text = "\n".join([f"- {h}" for h in context.news_headlines]) or "특이 뉴스 없음"

    prompt = f"""너는 금융 시장 시황 분석가이자 인공지능 사운드트랙 기획자야.
아래 실제 시장 데이터를 분석하고, 이를 음악적으로 표현한 2분 AI 사운드트랙의 메타데이터를 작성해줘.

[실제 시장 현황]
- 대상 시장: {'한국 국장 (KOSPI/KOSDAQ)' if is_kr else '미국 미장 (NASDAQ/S&P500)'}
- 기준 날짜: {today_formatted}
- 시장 국면: {context.regime}
- 평균 등락률: {context.avg_return_1d:+.2f}% (상승 {context.advancing_count}종목 / 하락 {context.declining_count}종목)
- 주요 대형주 동향: {context.key_leader_summary}
- 최근 주요 뉴스:
{headline_text}

[생성된 음악 스펙]
- 장르: {genre}
- 템포: {bpm} BPM
- 조성: {key_str}

반드시 아래 JSON 형식으로만 응답해 (Markdown 코드블록 없이 순수 JSON만 출력):
{{
  "title": "곡 제목 (시황의 긴박감이나 분위기, 주요 대형주 흐름을 직관적으로 드러내는 멋진 제목)",
  "mood": "분위기 키워드 4~5개 (예: 공포, 투매 충격, 긴장감, 패닉 방어)",
  "summary": "실제 시장의 평균 등락률과 대장주 등락 수치, 뉴스 헤드라인을 사실적으로 언급하고, 이 장세를 음악적으로 어떻게 담아냈는지 설명하는 2~3문장의 생생한 한국어 해설"
}}"""

    for model in DEFAULT_FREE_MODELS:
        try:
            resp = httpx.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                },
                timeout=8.0,
            )
            if resp.status_code == 200:
                raw = resp.json()["choices"][0]["message"]["content"].strip()
                # strip potential markdown fences
                if raw.startswith("```"):
                    raw = raw.strip("`").replace("json\n", "", 1).strip()
                parsed = json.loads(raw)
                if "title" in parsed and "summary" in parsed:
                    fallback["title"] = f"{parsed['title']} ({today_formatted})"
                    fallback["mood"] = parsed.get("mood", fallback["mood"])
                    fallback["summary"] = parsed["summary"]
                    logger.info(f"Generated soundtrack metadata with OpenRouter ({model})")
                    return fallback
        except Exception as exc:
            logger.warning(f"OpenRouter metadata gen failed with {model}: {exc}")
            continue

    return fallback


def synthesize_kr_soundtrack(
    out_path: Path,
    duration_sec: float = 120.0,
    title_suffix: str = "",
) -> None:
    """Synthesizes dynamic KR soundtrack based on current database market data."""
    context = fetch_market_context("KR")
    synthesize_market_soundtrack(out_path, "KR", context, duration_sec=duration_sec)


def synthesize_us_soundtrack(
    out_path: Path,
    duration_sec: float = 120.0,
    title_suffix: str = "",
) -> None:
    """Synthesizes dynamic US soundtrack based on current database market data."""
    context = fetch_market_context("US")
    synthesize_market_soundtrack(out_path, "US", context, duration_sec=duration_sec)


def get_soundtracks() -> list[dict]:
    """Returns the list of available market soundtracks."""
    if not METADATA_FILE.exists():
        return init_default_soundtracks()
    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                if item.get("duration_sec") != 120:
                    item["duration_sec"] = 120
            return data
    except Exception:
        return init_default_soundtracks()


def init_default_soundtracks() -> list[dict]:
    """Generates initial dynamic 2-minute soundtracks based on current DB state."""
    data_dir = ensure_soundtracks_dir()
    now_kst = datetime.now(KST)
    today_str = now_kst.strftime("%Y%m%d")
    today_formatted = now_kst.strftime("%Y-%m-%d")

    kr_id = f"kr-{today_str}"
    us_id = f"us-{today_str}"
    kr_file = data_dir / f"{kr_id}.wav"
    us_file = data_dir / f"{us_id}.wav"

    # 1. KR Soundtrack
    kr_ctx = fetch_market_context("KR")
    kr_spec = synthesize_market_soundtrack(kr_file, "KR", kr_ctx, duration_sec=120.0)
    kr_meta = generate_soundtrack_metadata(
        "KR", today_formatted, kr_ctx, kr_spec["bpm"], kr_spec["key"], kr_spec["genre"], f"{kr_id}.wav"
    )

    # 2. US Soundtrack
    us_ctx = fetch_market_context("US")
    us_spec = synthesize_market_soundtrack(us_file, "US", us_ctx, duration_sec=120.0)
    us_meta = generate_soundtrack_metadata(
        "US", today_formatted, us_ctx, us_spec["bpm"], us_spec["key"], us_spec["genre"], f"{us_id}.wav"
    )

    metadata = [kr_meta, us_meta]
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return metadata


def generate_daily_soundtracks_if_due(
    now_kst: datetime | None = None,
    force: bool = False,
    target_market: str | None = None,
) -> list[str]:
    """
    Checks if today's 07:30 KST (KR market) or 19:30 KST (US market) soundtracks are due,
    and synthesizes dynamic, market-grounded soundtracks.
    """
    if now_kst is None:
        now_kst = datetime.now(KST)

    data_dir = ensure_soundtracks_dir()
    today_str = now_kst.strftime("%Y%m%d")
    today_formatted = now_kst.strftime("%Y-%m-%d")
    current_time_str = now_kst.strftime("%H:%M")

    current_tracks = get_soundtracks()
    existing_ids = {t["id"] for t in current_tracks}
    messages: list[str] = []

    # 1. KR Market Track Regeneration: Due at or after 07:30 KST
    kr_id = f"kr-{today_str}"
    is_kr_due = (now_kst.hour > 7) or (now_kst.hour == 7 and now_kst.minute >= 30) or force
    if (target_market in [None, "KR"]) and is_kr_due and (kr_id not in existing_ids or force):
        kr_filename = f"{kr_id}.wav"
        kr_file = data_dir / kr_filename
        logger.info(f"Generating dynamic KR soundtrack for {today_formatted} at {current_time_str} KST (force={force})...")

        kr_ctx = fetch_market_context("KR")
        kr_spec = synthesize_market_soundtrack(kr_file, "KR", kr_ctx, duration_sec=120.0)
        new_kr_meta = generate_soundtrack_metadata(
            "KR", today_formatted, kr_ctx, kr_spec["bpm"], kr_spec["key"], kr_spec["genre"], kr_filename
        )

        current_tracks = [t for t in current_tracks if t["id"] != kr_id]
        current_tracks.insert(0, new_kr_meta)
        messages.append(f"Regenerated dynamic KR soundtrack ({kr_ctx.regime}): {kr_id} ({new_kr_meta['title']})")

    # 2. US Market Track Regeneration: Due at or after 19:30 KST
    us_id = f"us-{today_str}"
    is_us_due = (now_kst.hour > 19) or (now_kst.hour == 19 and now_kst.minute >= 30) or force
    if (target_market in [None, "US"]) and is_us_due and (us_id not in existing_ids or force):
        us_filename = f"{us_id}.wav"
        us_file = data_dir / us_filename
        logger.info(f"Generating dynamic US soundtrack for {today_formatted} at {current_time_str} KST (force={force})...")

        us_ctx = fetch_market_context("US")
        us_spec = synthesize_market_soundtrack(us_file, "US", us_ctx, duration_sec=120.0)
        new_us_meta = generate_soundtrack_metadata(
            "US", today_formatted, us_ctx, us_spec["bpm"], us_spec["key"], us_spec["genre"], us_filename
        )

        current_tracks = [t for t in current_tracks if t["id"] != us_id]
        insert_idx = 1 if len(current_tracks) > 0 and current_tracks[0]["market"] == "KR" else 0
        current_tracks.insert(insert_idx, new_us_meta)
        messages.append(f"Regenerated dynamic US soundtrack ({us_ctx.regime}): {us_id} ({new_us_meta['title']})")

    if messages:
        # Keep maximum 10 latest soundtracks
        current_tracks = current_tracks[:10]
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(current_tracks, f, indent=2, ensure_ascii=False)

    return messages


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing dynamic soundtrack generation...")
    msgs = generate_daily_soundtracks_if_due(force=True)
    print("Result messages:", msgs)
    print("Current tracks in metadata.json:")
    for t in get_soundtracks()[:2]:
        print(f"[{t['market']}] {t['title']} | BPM: {t['bpm']} | Regime: {t['genre']}")
        print(f"Summary: {t['summary']}\n")
