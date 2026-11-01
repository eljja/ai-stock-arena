from __future__ import annotations

import json
import logging
import math
import os
import wave
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "soundtracks"
METADATA_FILE = DATA_DIR / "metadata.json"
KST = timezone(timedelta(hours=9))


def ensure_soundtracks_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def synthesize_kr_soundtrack(
    out_path: Path,
    duration_sec: float = 120.0,
    title_suffix: str = "",
) -> None:
    """Synthesizes a 120-second (2-minute) Lo-Fi Cyber Ambient Suite for Korean market."""
    sr = 32000
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)

    bpm = 84.0
    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4.0

    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)

    # 1. Warm vinyl / tape crackle bed
    noise = np.random.uniform(-0.007, 0.007, n).astype(np.float32)
    left += noise
    right += noise

    # 2. Electric Piano Chords progression (Am7 -> Fmaj7 -> Cmaj7 -> Em7)
    chords = np.array([
        [220.0, 261.63, 329.63, 392.00],  # Am7 (A3, C4, E4, G4)
        [174.61, 220.0, 261.63, 329.63],  # Fmaj7 (F3, A3, C4, E4)
        [130.81, 196.0, 261.63, 329.63],  # Cmaj7 (C3, G3, C4, E4)
        [164.81, 246.94, 329.63, 392.00],  # Em7 (E3, B3, E4, G4)
    ], dtype=np.float32)

    chord_idx = ((t // bar_sec) % len(chords)).astype(np.int32)
    t_bar = t % bar_sec
    chord_env = (np.sin(np.pi * (t_bar / bar_sec)) ** 0.65).astype(np.float32)

    for i in range(4):
        freqs = chords[chord_idx, i]
        phase = 2 * np.pi * np.cumsum(freqs) / sr
        sig = 0.08 * np.sin(phase) + 0.03 * np.sin(phase * 2.0) + 0.01 * np.sin(phase * 3.0)
        left += sig * chord_env * 0.95
        right += sig * chord_env * 1.05

    # 3. Lo-Fi Boom-Bap Drums (Active from bar 7 ~20s to bar 37 ~105s)
    drum_start_time = 7 * bar_sec
    drum_end_time = 37 * bar_sec
    total_beats = int(duration_sec / beat_sec)

    for b in range(total_beats):
        b_time = b * beat_sec
        if b_time < drum_start_time or b_time > drum_end_time:
            continue

        # Kick drum on beat 0 and beat 2 of each 4-beat bar
        if b % 4 in [0, 2]:
            idx = int(b_time * sr)
            k_len = int(0.28 * sr)
            if idx + k_len < n:
                k_t = np.linspace(0, 0.28, k_len, dtype=np.float32)
                k_pitch = 110.0 * np.exp(-16 * k_t) + 42.0
                k_sig = 0.42 * np.sin(2 * np.pi * k_pitch * k_t) * np.exp(-8 * k_t)
                left[idx:idx + k_len] += k_sig
                right[idx:idx + k_len] += k_sig

        # Snare / rimshot on beat 1 and beat 3
        if b % 4 in [1, 3]:
            idx = int(b_time * sr)
            s_len = int(0.22 * sr)
            if idx + s_len < n:
                s_t = np.linspace(0, 0.22, s_len, dtype=np.float32)
                noise_s = np.random.uniform(-0.16, 0.16, s_len).astype(np.float32) * np.exp(-14 * s_t)
                tone_s = 0.18 * np.sin(2 * np.pi * 175 * s_t) * np.exp(-18 * s_t)
                left[idx:idx + s_len] += (noise_s + tone_s) * 0.9
                right[idx:idx + s_len] += (noise_s + tone_s) * 1.1

        # Swung 8th-note Hi-hats
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

    # 4. Deep Sub-bassline (A1 -> F1 -> C1 -> E1)
    bass_roots = np.array([55.0, 43.65, 32.7, 41.2], dtype=np.float32)
    bass_start = 7 * bar_sec
    bass_end = 39 * bar_sec
    for b in range(total_beats):
        b_time = b * beat_sec
        if b_time < bass_start or b_time > bass_end:
            continue
        bar_i = int(b_time // bar_sec) % len(bass_roots)
        root = bass_roots[bar_i]
        if b % 2 == 0:
            idx = int(b_time * sr)
            b_len = int(beat_sec * 1.8 * sr)
            if idx + b_len < n:
                b_t = np.linspace(0, beat_sec * 1.8, b_len, dtype=np.float32)
                b_sig = 0.28 * np.sin(2 * np.pi * root * b_t) * np.exp(-1.2 * b_t)
                b_sig += 0.09 * np.sin(2 * np.pi * (root * 2) * b_t) * np.exp(-2.0 * b_t)
                left[idx:idx + b_len] += b_sig
                right[idx:idx + b_len] += b_sig

    # 5. Celeste / Marimba Arpeggio (Bars 12 ~34s to 38 ~108s)
    arp_notes = [523.25, 659.25, 783.99, 880.00, 1046.50, 880.00, 783.99, 659.25]
    sixteenth = beat_sec / 4.0
    for s_step in range(int(duration_sec / sixteenth)):
        s_time = s_step * sixteenth
        if s_time < 12 * bar_sec or s_time > 38 * bar_sec:
            continue
        note = arp_notes[s_step % len(arp_notes)]
        idx = int(s_time * sr)
        a_len = int(0.3 * sr)
        if idx + a_len < n:
            a_t = np.linspace(0, 0.3, a_len, dtype=np.float32)
            a_sig = 0.09 * np.sin(2 * np.pi * note * a_t) * np.exp(-7 * a_t)
            pan = 0.5 + 0.35 * np.sin(s_step * 0.7)
            left[idx:idx + a_len] += a_sig * (1.0 - pan)
            right[idx:idx + a_len] += a_sig * pan

    # 6. Smooth Fade in (2.5s) and Fade out (4.5s)
    fade_in = int(2.5 * sr)
    fade_out = int(4.5 * sr)
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


def synthesize_us_soundtrack(
    out_path: Path,
    duration_sec: float = 120.0,
    title_suffix: str = "",
) -> None:
    """Synthesizes a 120-second (2-minute) High-Voltage Cyberpunk Synthwave Suite for US market."""
    sr = 32000
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)

    bpm = 124.0
    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4.0
    sixteenth = beat_sec / 4.0

    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)

    # Roots and Chords (Dm -> Bb -> F -> C)
    roots = np.array([73.42, 58.27, 43.65, 65.41], dtype=np.float32)  # D2, Bb1, F1, C2
    chords = np.array([
        [293.66, 349.23, 440.00],  # Dm (D4, F4, A4)
        [233.08, 293.66, 349.23],  # Bb (Bb3, D4, F4)
        [174.61, 261.63, 349.23],  # F (F3, C4, F4)
        [261.63, 329.63, 392.00],  # C (C4, E4, G4)
    ], dtype=np.float32)

    # 1. Analog Pad Drone (swelling across bars)
    pad_idx = ((t // bar_sec) % len(chords)).astype(np.int32)
    for i in range(3):
        freqs = chords[pad_idx, i]
        phase = 2 * np.pi * np.cumsum(freqs) / sr
        sig = 0.05 * np.sin(phase) + 0.025 * np.sin(phase * 1.008)
        left += sig * 0.9
        right += sig * 1.1

    # 2. Four-on-the-Floor Kick, Gated Snare & Hi-hats (Bars 8 ~15.5s to 55 ~106s)
    drum_start = 8 * bar_sec
    drum_end = 55 * bar_sec
    total_beats = int(duration_sec / beat_sec)

    for b in range(total_beats):
        b_time = b * beat_sec
        if b_time < drum_start or b_time > drum_end:
            continue

        # Punchy Kick on every quarter beat
        idx = int(b_time * sr)
        k_len = int(0.20 * sr)
        if idx + k_len < n:
            k_t = np.linspace(0, 0.20, k_len, dtype=np.float32)
            k_pitch = 160.0 * np.exp(-24 * k_t) + 48.0
            k_sig = 0.50 * np.sin(2 * np.pi * k_pitch * k_t) * np.exp(-9 * k_t)
            left[idx:idx + k_len] += k_sig
            right[idx:idx + k_len] += k_sig

        # Gated 80s Snare on beats 2 & 4
        if b % 2 == 1:
            s_len = int(0.24 * sr)
            if idx + s_len < n:
                s_t = np.linspace(0, 0.24, s_len, dtype=np.float32)
                noise = np.random.uniform(-0.32, 0.32, s_len).astype(np.float32) * np.exp(-12 * s_t)
                tone = 0.24 * np.sin(2 * np.pi * 210 * s_t) * np.exp(-16 * s_t)
                left[idx:idx + s_len] += (noise + tone) * 0.95
                right[idx:idx + s_len] += (noise + tone) * 1.05

        # Off-beat Open Hi-hat
        h_time = b_time + 0.5 * beat_sec
        h_idx = int(h_time * sr)
        h_len = int(0.12 * sr)
        if h_idx + h_len < n:
            h_t = np.linspace(0, 0.12, h_len, dtype=np.float32)
            h_sig = np.random.uniform(-0.10, 0.10, h_len).astype(np.float32) * np.exp(-22 * h_t)
            left[h_idx:h_idx + h_len] += h_sig * 0.7
            right[h_idx:h_idx + h_len] += h_sig * 1.3

    # 3. Rolling 16th-note Synthwave Bass (Bars 8 ~15.5s to 56 ~108s)
    bass_start = 8 * bar_sec
    bass_end = 56 * bar_sec
    total_16ths = int(duration_sec / sixteenth)
    for s_step in range(total_16ths):
        s_time = s_step * sixteenth
        if s_time < bass_start or s_time > bass_end:
            continue
        bar_i = int(s_time // bar_sec) % len(roots)
        root = roots[bar_i]
        f_play = root * (2.0 if s_step % 2 == 1 else 1.0)
        idx = int(s_time * sr)
        b_len = int(sixteenth * 0.82 * sr)
        if idx + b_len < n:
            b_t = np.linspace(0, sixteenth * 0.82, b_len, dtype=np.float32)
            saw = sum((0.24 / k) * np.sin(2 * np.pi * (f_play * k) * b_t) for k in range(1, 5))
            b_sig = saw * np.exp(-6 * b_t)
            left[idx:idx + b_len] += b_sig
            right[idx:idx + b_len] += b_sig

    # 4. Neon Arpeggiator (Bars 24 ~46s to 52 ~100s)
    arp_freqs = [587.33, 698.46, 880.00, 1046.50, 1174.66, 1046.50, 880.00, 698.46]
    for s_step in range(total_16ths):
        s_time = s_step * sixteenth
        if s_time < 24 * bar_sec or s_time > 52 * bar_sec:
            continue
        freq = arp_freqs[s_step % len(arp_freqs)]
        idx = int(s_time * sr)
        a_len = int(0.18 * sr)
        if idx + a_len < n:
            a_t = np.linspace(0, 0.18, a_len, dtype=np.float32)
            a_sig = 0.08 * (np.sin(2 * np.pi * freq * a_t) + 0.5 * np.sin(2 * np.pi * freq * 2 * a_t)) * np.exp(-10 * a_t)
            pan = 0.5 + 0.4 * np.sin(s_step * 0.9)
            left[idx:idx + a_len] += a_sig * (1.0 - pan)
            right[idx:idx + a_len] += a_sig * pan

    # 5. Climax Lead Melody (Bars 42 ~81s to 54 ~104s)
    melody_notes = [587.33, 783.99, 880.00, 1046.50, 880.00, 783.99, 698.46, 587.33]
    for b in range(total_beats):
        b_time = b * beat_sec
        if b_time < 42 * bar_sec or b_time > 54 * bar_sec:
            continue
        m_freq = melody_notes[(b // 2) % len(melody_notes)]
        idx = int(b_time * sr)
        m_len = int(beat_sec * 1.6 * sr)
        if idx + m_len < n:
            m_t = np.linspace(0, beat_sec * 1.6, m_len, dtype=np.float32)
            m_sig = 0.12 * np.sin(2 * np.pi * m_freq * m_t) + 0.06 * np.sin(2 * np.pi * (m_freq * 1.005) * m_t)
            m_sig *= np.exp(-1.5 * m_t)
            left[idx:idx + m_len] += m_sig * 0.9
            right[idx:idx + m_len] += m_sig * 1.1

    # 6. Fade in and out
    fade_in = int(2.0 * sr)
    fade_out = int(4.5 * sr)
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


def init_default_soundtracks() -> list[dict]:
    """Generates default 2-minute soundtracks and writes metadata."""
    data_dir = ensure_soundtracks_dir()
    kr_file = data_dir / "kr-20261030.wav"
    us_file = data_dir / "us-20261030.wav"

    if not kr_file.exists():
        synthesize_kr_soundtrack(kr_file, duration_sec=120.0)
    if not us_file.exists():
        synthesize_us_soundtrack(us_file, duration_sec=120.0)

    metadata = [
        {
            "id": "kr-20261030",
            "market": "KR",
            "market_name": "대한민국 국장 (KOSPI / KOSDAQ)",
            "date": "2026-10-30 (지난주 금요일)",
            "title": "Cautious Twilight Suite: 신중한 반도체 횡보와 균형",
            "genre": "Lo-Fi Cyber Ambient Suite",
            "bpm": 84,
            "key": "A Minor",
            "mood": "신중함, 절제미, 관망세, 점진적 회복",
            "audio_url": "/api/soundtracks/kr-20261030.wav",
            "duration_sec": 120,
            "summary": "3분기 대형 반도체 호실적과 내수 소비 둔화 우려가 팽팽하게 맞선 국장 시황. 지수 하단을 지켜낸 신중한 관망세를 84 BPM의 칠한 비트, 따뜻한 일렉트릭 피아노, 그리고 몽환적인 마림바 아르페지오로 담아낸 2분 오케스트레이션 BGM입니다."
        },
        {
            "id": "us-20261030",
            "market": "US",
            "market_name": "미국 미장 (NASDAQ / S&P500)",
            "date": "2026-10-30 (지난주 금요일)",
            "title": "High-Voltage Pulse Suite: 빅테크 파고와 에너지 긴장",
            "genre": "Cyberpunk Synthwave Suite",
            "bpm": 124,
            "key": "D Minor",
            "mood": "긴박함, 높은 변동성, 테크 파워, 야간 질주",
            "audio_url": "/api/soundtracks/us-20261030.wav",
            "duration_sec": 120,
            "summary": "중동 호르무즈 해협 지정학적 긴장감과 빅테크 실적 발표 후 나타난 격렬한 장중 변동성을 124 BPM의 질주하는 16비트 롤링 베이스라인, 파워풀한 4-on-the-floor 킥, 그리고 네온 신스 브라스로 표현한 2분 사이버펑크 BGM입니다."
        }
    ]

    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return metadata


def get_soundtracks() -> list[dict]:
    """Returns the list of available market soundtracks."""
    if not METADATA_FILE.exists():
        return init_default_soundtracks()
    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure 120s duration in returned metadata
            for item in data:
                if item.get("duration_sec") != 120:
                    item["duration_sec"] = 120
            return data
    except Exception:
        return init_default_soundtracks()


def generate_daily_soundtracks_if_due(now_kst: datetime | None = None) -> list[str]:
    """
    Checks if today's 07:30 KST (KR market) or 19:30 KST (US market) soundtracks are due,
    and synthesizes them if not yet generated for today.
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
    is_kr_due = (now_kst.hour > 7) or (now_kst.hour == 7 and now_kst.minute >= 30)
    if is_kr_due and kr_id not in existing_ids:
        kr_filename = f"{kr_id}.wav"
        kr_file = data_dir / kr_filename
        logger.info(f"Generating 2-min KR soundtrack for {today_formatted} at {current_time_str} KST...")
        synthesize_kr_soundtrack(kr_file, duration_sec=120.0)

        new_kr_meta = {
            "id": kr_id,
            "market": "KR",
            "market_name": "대한민국 국장 (KOSPI / KOSDAQ)",
            "date": f"{today_formatted} (당일 아침 브리핑)",
            "title": f"Morning Bell Resonance ({today_formatted}): 국장 오프닝 테마",
            "genre": "Lo-Fi Cyber Ambient Suite",
            "bpm": 84,
            "key": "A Minor",
            "mood": "신중함, 절제미, 관망세, 점진적 회복",
            "audio_url": f"/api/soundtracks/{kr_filename}",
            "duration_sec": 120,
            "summary": f"{today_formatted} 한국 시장 개장 전 전일 수급 및 업종별 동향을 반영한 2분 인공지능 사운드트랙입니다. 차분한 84 BPM 로우파이 피아노와 절제된 비트로 안정적인 오전 세션을 이끕니다."
        }
        # Update or prepend
        current_tracks = [t for t in current_tracks if t["id"] != kr_id]
        current_tracks.insert(0, new_kr_meta)
        messages.append(f"Regenerated 2-min KR soundtrack: {kr_id} ({kr_filename})")

    # 2. US Market Track Regeneration: Due at or after 19:30 KST
    us_id = f"us-{today_str}"
    is_us_due = (now_kst.hour > 19) or (now_kst.hour == 19 and now_kst.minute >= 30)
    if is_us_due and us_id not in existing_ids:
        us_filename = f"{us_id}.wav"
        us_file = data_dir / us_filename
        logger.info(f"Generating 2-min US soundtrack for {today_formatted} at {current_time_str} KST...")
        synthesize_us_soundtrack(us_file, duration_sec=120.0)

        new_us_meta = {
            "id": us_id,
            "market": "US",
            "market_name": "미국 미장 (NASDAQ / S&P500)",
            "date": f"{today_formatted} (당일 저녁 브리핑)",
            "title": f"Electric Night Pulse ({today_formatted}): 미장 테크 파워 테마",
            "genre": "Cyberpunk Synthwave Suite",
            "bpm": 124,
            "key": "D Minor",
            "mood": "긴박함, 높은 변동성, 테크 파워, 야간 질주",
            "audio_url": f"/api/soundtracks/{us_filename}",
            "duration_sec": 120,
            "summary": f"{today_formatted} 미국 시장 개장 전 프리마켓 선물 및 글로벌 매크로 지표를 반영한 2분 신스웨이브 사운드트랙입니다. 124 BPM의 에너제틱한 킥과 네온 아르페지오로 월스트리트의 밤을 밝힙니다."
        }
        # Update or insert after KR or at index 1
        current_tracks = [t for t in current_tracks if t["id"] != us_id]
        insert_idx = 1 if len(current_tracks) > 0 and current_tracks[0]["market"] == "KR" else 0
        current_tracks.insert(insert_idx, new_us_meta)
        messages.append(f"Regenerated 2-min US soundtrack: {us_id} ({us_filename})")

    if messages:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(current_tracks, f, indent=2, ensure_ascii=False)

    return messages
