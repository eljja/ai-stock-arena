from __future__ import annotations

import tempfile
import wave
from pathlib import Path
import pytest

from app.services.soundtrack_service import (
    MarketContext,
    synthesize_market_soundtrack,
    build_fallback_metadata,
)


def test_fallback_metadata_crash_regime():
    ctx = MarketContext(
        market_code="KR",
        market_name="대한민국 국장 (KOSPI / KOSDAQ)",
        regime="CRASH",
        avg_return_1d=-2.29,
        avg_volatility=2.45,
        advancing_count=4,
        declining_count=17,
        total_count=22,
        top_gainers=[("035420.KS", "NAVER", 5.34)],
        top_losers=[("000660.KS", "SK hynix", -8.13), ("005930.KS", "Samsung Electronics", -3.98)],
        key_leader_summary="삼성전자(-3.98%), SK하이닉스(-8.13%)",
        news_headlines=["코스피 폭락에 개미들 2조원 순매수", "반도체주 일제히 급락"],
    )

    meta = build_fallback_metadata(
        market_code="KR",
        today_formatted="2026-11-06",
        context=ctx,
        bpm=72,
        key_str="D Minor (Tense)",
        genre="Dark Cinematic Ambient & Industrial Tension Suite",
        filename="kr-20261106.wav",
    )

    assert meta["market"] == "KR"
    assert meta["bpm"] == 72
    assert "72 BPM" in meta["summary"]
    assert "-2.29%" in meta["summary"]
    assert "삼성전자(-3.98%)" in meta["summary"]
    assert meta["key"] == "D Minor (Tense)"
    assert "Dark Tempest" in meta["title"]


def test_fallback_metadata_rally_regime():
    ctx = MarketContext(
        market_code="US",
        market_name="미국 미장 (NASDAQ / S&P500)",
        regime="RALLY",
        avg_return_1d=2.45,
        avg_volatility=1.80,
        advancing_count=18,
        declining_count=2,
        total_count=20,
        top_gainers=[("NVDA", "NVIDIA", 5.80), ("AAPL", "Apple", 3.20)],
        top_losers=[],
        key_leader_summary="NVDA(+5.80%), AAPL(+3.20%)",
        news_headlines=["빅테크 주도 나스닥 사상 최고치 경신"],
    )

    meta = build_fallback_metadata(
        market_code="US",
        today_formatted="2026-11-06",
        context=ctx,
        bpm=132,
        key_str="D Major (Euphoric)",
        genre="High-Voltage Outrun & Turbo Synthwave",
        filename="us-20261106.wav",
    )

    assert meta["market"] == "US"
    assert meta["bpm"] == 132
    assert "132 BPM" in meta["summary"]
    assert "+2.45%" in meta["summary"]
    assert "NVDA(+5.80%)" in meta["summary"]
    assert "High-Voltage Neon Anthem" in meta["title"]


def test_synthesize_audio_rendering():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_wav = Path(tmpdir) / "test_crash.wav"
        ctx = MarketContext(
            market_code="KR",
            market_name="대한민국 국장",
            regime="CRASH",
            avg_return_1d=-2.5,
            avg_volatility=2.0,
            advancing_count=2,
            declining_count=20,
            total_count=22,
            top_gainers=[],
            top_losers=[],
            key_leader_summary="SK하이닉스(-8.1%)",
            news_headlines=[],
        )

        # Synthesize a short 3-second test clip
        spec = synthesize_market_soundtrack(out_wav, "KR", ctx, duration_sec=3.0)
        assert out_wav.exists()
        assert spec["bpm"] == 72
        assert "D Minor" in spec["key"]

        with wave.open(str(out_wav), "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 32000
            assert wf.getnframes() == 32000 * 3


def test_synthesize_full_120s_rally():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_wav = Path(tmpdir) / "test_rally_120s.wav"
        ctx = MarketContext(
            market_code="US",
            market_name="미국 미장",
            regime="RALLY",
            avg_return_1d=2.2,
            avg_volatility=1.5,
            advancing_count=18,
            declining_count=1,
            total_count=19,
            top_gainers=[("NVDA", "NVIDIA", 5.2)],
            top_losers=[],
            key_leader_summary="NVDA(+5.2%)",
            news_headlines=[],
        )

        spec = synthesize_market_soundtrack(out_wav, "US", ctx, duration_sec=120.0)
        assert out_wav.exists()
        assert spec["bpm"] == 132
        assert "D Major" in spec["key"]
        assert "High-Voltage" in spec["genre"]

        with wave.open(str(out_wav), "rb") as wf:
            assert wf.getnframes() == 32000 * 120

