from __future__ import annotations

import json
import logging
import math
import os
import wave
from datetime import datetime
from pathlib import Path
import numpy as np
import requests

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "soundtracks"
METADATA_FILE = DATA_DIR / "metadata.json"


def ensure_soundtracks_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def synthesize_kr_soundtrack(out_path: Path, duration_sec: float = 16.0) -> None:
    """Synthesizes a 16-second Lo-Fi Cyber Ambient soundtrack for Korean market."""
    sr = 44100
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    bpm = 84.0
    beat_sec = 60.0 / bpm

    left = np.zeros_like(t)
    right = np.zeros_like(t)

    # 1. Warm chords: Am7 (A3, C4, E4, G4) -> Fmaj7 (F3, A3, C4, E4) -> C (C3, G3, C4, E4) -> Em (E3, B3, E4, G4)
    # Each chord lasts 4 beats (~2.85 sec)
    chord_freqs = [
        [220.0, 261.63, 329.63, 392.00],  # Am7
        [174.61, 220.0, 261.63, 329.63],  # Fmaj7
        [130.81, 196.0, 261.63, 329.63],  # C
        [164.81, 246.94, 329.63, 392.00],  # Em
    ]
    chord_duration = beat_sec * 4.0

    for i, t_val in enumerate(t):
        chord_idx = int(t_val // chord_duration) % len(chord_freqs)
        t_in_chord = t_val % chord_duration
        env = np.sin(np.pi * (t_in_chord / chord_duration)) ** 0.8
        
        freqs = chord_freqs[chord_idx]
        chord_sample = sum(
            0.12 * np.sin(2 * np.pi * f * t_val) +
            0.04 * np.sin(2 * np.pi * (f * 2) * t_val)
            for f in freqs
        )
        left[i] += chord_sample * env * 0.95
        right[i] += chord_sample * env * 1.05

    # 2. Deep Sub-bass (A1 -> F1 -> C1 -> E1)
    bass_freqs = [55.0, 43.65, 32.7, 41.2]
    for i, t_val in enumerate(t):
        chord_idx = int(t_val // chord_duration) % len(bass_freqs)
        t_in_beat = (t_val % (beat_sec * 2)) / (beat_sec * 2)
        bass_env = np.exp(-1.5 * t_in_beat)
        f_bass = bass_freqs[chord_idx]
        b_sample = 0.28 * np.sin(2 * np.pi * f_bass * t_val)
        left[i] += b_sample * bass_env
        right[i] += b_sample * bass_env

    # 3. Chill Lo-Fi Drums (Kick on 1 & 3, Snare on 2 & 4, Hi-hat on 8ths)
    total_beats = int(duration_sec / beat_sec)
    for b in range(total_beats):
        b_time = b * beat_sec
        # Kick drum on beat 0 and 2 of each 4-beat bar
        if b % 4 in [0, 2]:
            idx_start = int(b_time * sr)
            k_len = int(0.25 * sr)
            if idx_start + k_len < len(t):
                k_t = np.linspace(0, 0.25, k_len)
                k_pitch = 120.0 * np.exp(-18 * k_t) + 45.0
                k_sig = 0.45 * np.sin(2 * np.pi * k_pitch * k_t) * np.exp(-10 * k_t)
                left[idx_start:idx_start + k_len] += k_sig
                right[idx_start:idx_start + k_len] += k_sig

        # Soft snare on beat 1 and 3 of each 4-beat bar
        if b % 4 in [1, 3]:
            idx_start = int(b_time * sr)
            s_len = int(0.2 * sr)
            if idx_start + s_len < len(t):
                s_t = np.linspace(0, 0.2, s_len)
                noise = np.random.uniform(-0.18, 0.18, s_len) * np.exp(-15 * s_t)
                body = 0.2 * np.sin(2 * np.pi * 180 * s_t) * np.exp(-20 * s_t)
                s_sig = noise + body
                left[idx_start:idx_start + s_len] += s_sig * 0.9
                right[idx_start:idx_start + s_len] += s_sig * 1.1

    # 4. Melodic Arpeggio (Celeste / Marimba chime)
    arp_notes = [523.25, 659.25, 783.99, 880.00, 1046.50]  # C5, E5, G5, A5, C6
    sixteenth = beat_sec / 4.0
    for s_step in range(int(duration_sec / sixteenth)):
        s_time = s_step * sixteenth
        if s_time > duration_sec - 1.0:
            break
        note_f = arp_notes[s_step % len(arp_notes)]
        idx = int(s_time * sr)
        a_len = int(0.35 * sr)
        if idx + a_len < len(t):
            a_t = np.linspace(0, 0.35, a_len)
            a_sig = 0.12 * np.sin(2 * np.pi * note_f * a_t) * np.exp(-8 * a_t)
            pan = 0.5 + 0.3 * np.sin(s_step * 0.8)
            left[idx:idx + a_len] += a_sig * (1.0 - pan)
            right[idx:idx + a_len] += a_sig * pan

    # Fade out last 1.5 seconds
    fade_len = int(1.5 * sr)
    fade = np.linspace(1.0, 0.0, fade_len)
    left[-fade_len:] *= fade
    right[-fade_len:] *= fade

    # Normalize to -1.0 dB
    max_val = max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-4)
    left = (left / max_val) * 0.88
    right = (right / max_val) * 0.88

    stereo = np.zeros((len(t), 2), dtype=np.int16)
    stereo[:, 0] = np.int16(left * 32767)
    stereo[:, 1] = np.int16(right * 32767)

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())


def synthesize_us_soundtrack(out_path: Path, duration_sec: float = 16.0) -> None:
    """Synthesizes a 16-second High-Voltage Synthwave soundtrack for US Tech market."""
    sr = 44100
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    bpm = 126.0
    beat_sec = 60.0 / bpm

    left = np.zeros_like(t)
    right = np.zeros_like(t)

    # 1. Driving Four-on-the-Floor Kick
    total_beats = int(duration_sec / beat_sec)
    for b in range(total_beats):
        b_time = b * beat_sec
        idx = int(b_time * sr)
        k_len = int(0.22 * sr)
        if idx + k_len < len(t):
            k_t = np.linspace(0, 0.22, k_len)
            k_pitch = 160.0 * np.exp(-22 * k_t) + 48.0
            k_sig = 0.55 * np.sin(2 * np.pi * k_pitch * k_t) * np.exp(-8 * k_t)
            left[idx:idx + k_len] += k_sig
            right[idx:idx + k_len] += k_sig

        # Snare on beats 2 & 4
        if b % 2 == 1:
            s_len = int(0.25 * sr)
            if idx + s_len < len(t):
                s_t = np.linspace(0, 0.25, s_len)
                noise = np.random.uniform(-0.35, 0.35, s_len) * np.exp(-12 * s_t)
                tone = 0.3 * np.sin(2 * np.pi * 210 * s_t) * np.exp(-16 * s_t)
                left[idx:idx + s_len] += (noise + tone) * 0.95
                right[idx:idx + s_len] += (noise + tone) * 1.05

    # 2. 16th-note Rolling Bassline (Dm -> Bb -> F -> C)
    roots = [73.42, 58.27, 43.65, 65.41]  # D2, Bb1, F1, C2
    bar_sec = beat_sec * 4.0
    sixteenth = beat_sec / 4.0

    for s_step in range(int(duration_sec / sixteenth)):
        s_time = s_step * sixteenth
        bar_idx = int(s_time // bar_sec) % len(roots)
        root_f = roots[bar_idx]
        # Octave bounce
        f_play = root_f * (2.0 if s_step % 2 == 1 else 1.0)
        idx = int(s_time * sr)
        b_len = int(sixteenth * 0.85 * sr)
        if idx + b_len < len(t):
            b_t = np.linspace(0, sixteenth * 0.85, b_len)
            # Sawtooth-like rich bass
            saw = sum((1.0 / n) * np.sin(2 * np.pi * (f_play * n) * b_t) for n in range(1, 5))
            b_sig = 0.22 * saw * np.exp(-6 * b_t)
            left[idx:idx + b_len] += b_sig
            right[idx:idx + b_len] += b_sig

    # 3. Bright Synth Brass Chords (Dm -> Bb -> F -> C)
    chords = [
        [293.66, 349.23, 440.00],  # Dm (D4, F4, A4)
        [233.08, 293.66, 349.23],  # Bb (Bb3, D4, F4)
        [174.61, 261.63, 349.23],  # F (F3, C4, F4)
        [261.63, 329.63, 392.00],  # C (C4, E4, G4)
    ]
    for b in range(total_beats):
        if b % 2 == 0:  # on beat 1 and 3 of each bar
            b_time = b * beat_sec
            bar_idx = int(b_time // bar_sec) % len(chords)
            chord = chords[bar_idx]
            idx = int(b_time * sr)
            c_len = int(beat_sec * 1.5 * sr)
            if idx + c_len < len(t):
                c_t = np.linspace(0, beat_sec * 1.5, c_len)
                c_sig = sum(
                    0.09 * np.sin(2 * np.pi * f * c_t) +
                    0.05 * np.sin(2 * np.pi * (f * 1.01) * c_t)
                    for f in chord
                ) * np.exp(-2.2 * c_t)
                left[idx:idx + c_len] += c_sig * 0.8
                right[idx:idx + c_len] += c_sig * 1.2

    # Fade out last 1.5 seconds
    fade_len = int(1.5 * sr)
    fade = np.linspace(1.0, 0.0, fade_len)
    left[-fade_len:] *= fade
    right[-fade_len:] *= fade

    # Normalize
    max_val = max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-4)
    left = (left / max_val) * 0.90
    right = (right / max_val) * 0.90

    stereo = np.zeros((len(t), 2), dtype=np.int16)
    stereo[:, 0] = np.int16(left * 32767)
    stereo[:, 1] = np.int16(right * 32767)

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())


def init_default_soundtracks() -> list[dict]:
    """Generates initial soundtracks for last Friday (2026-10-30) and writes metadata."""
    data_dir = ensure_soundtracks_dir()
    kr_file = data_dir / "kr-20261030.wav"
    us_file = data_dir / "us-20261030.wav"

    if not kr_file.exists():
        synthesize_kr_soundtrack(kr_file, duration_sec=16.0)
    if not us_file.exists():
        synthesize_us_soundtrack(us_file, duration_sec=16.0)

    metadata = [
        {
            "id": "kr-20261030",
            "market": "KR",
            "market_name": "대한민국 국장 (KOSPI / KOSDAQ)",
            "date": "2026-10-30 (지난주 금요일)",
            "title": "Cautious Twilight: 신중한 반도체 횡보",
            "genre": "Lo-Fi Cyber Ambient",
            "bpm": 84,
            "key": "A Minor",
            "mood": "신중함, 절제미, 관망세",
            "audio_url": "/api/soundtracks/kr-20261030.wav",
            "duration_sec": 16,
            "summary": "3분기 대형 반도체 호실적과 내수 소비 둔화 우려가 팽팽하게 맞선 지난주 금요일 국장. 지수 하단을 지켜낸 신중한 관망세를 절제된 84 BPM 로우파이 비트와 따뜻한 신스 패드로 구현했습니다."
        },
        {
            "id": "us-20261030",
            "market": "US",
            "market_name": "미국 미장 (NASDAQ / S&P500)",
            "date": "2026-10-30 (지난주 금요일)",
            "title": "High-Voltage Pulse: 빅테크 파고와 에너지 긴장",
            "genre": "Cyberpunk Synthwave",
            "bpm": 126,
            "key": "D Minor",
            "mood": "긴박함, 높은 변동성, 테크 파워",
            "audio_url": "/api/soundtracks/us-20261030.wav",
            "duration_sec": 16,
            "summary": "중동 호르무즈 해협 지정학적 긴장감과 AMD 등 빅테크 실적 발표 후 나타난 격렬한 장중 변동성을 126 BPM의 질주하는 16비트 베이스라인과 날카로운 신스 브라스로 담아냈습니다."
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
            return json.load(f)
    except Exception:
        return init_default_soundtracks()
