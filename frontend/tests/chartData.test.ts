import test from 'node:test';
import assert from 'node:assert/strict';
import { buildChartSeriesData, toEpochSeconds, formatKstDateTime } from '../src/utils/chartData.ts';
import type { SnapshotSummary } from '../src/types/index.ts';

function makeSnap(overrides: Partial<SnapshotSummary>): SnapshotSummary {
  return {
    model_id: 'model-a',
    market_code: 'KR',
    available_cash: 1000,
    invested_value: 0,
    total_equity: 1000,
    total_return_pct: 0,
    realized_pnl: 0,
    unrealized_pnl: 0,
    volatility: 0,
    sharpe_ratio: 0,
    max_drawdown: 0,
    win_rate: 0,
    profit_factor: 0,
    turnover: 0,
    avg_holding_hours: 0,
    composite_score: 0,
    created_at: '2026-11-17T10:00:00',
    ...overrides,
  };
}

test('toEpochSeconds parses naive UTC ISO timestamps as UTC (not local timezone)', () => {
  const naive = toEpochSeconds('2026-11-17T10:00:00.123456');
  const explicit = toEpochSeconds('2026-11-17T10:00:00.123456Z');
  assert.equal(naive, explicit);
  assert.equal(naive, Math.floor(Date.parse('2026-11-17T10:00:00.123Z') / 1000));
});

test('buildChartSeriesData filters by market and sorts strictly ascending without duplicate times', () => {
  const snaps: SnapshotSummary[] = [
    makeSnap({ market_code: 'KR', total_return_pct: 2.0, created_at: '2026-11-17T12:00:00' }),
    makeSnap({ market_code: 'KR', total_return_pct: 1.0, created_at: '2026-11-17T10:00:00' }),
    makeSnap({ market_code: 'KR', total_return_pct: 1.5, created_at: '2026-11-17T10:00:00.500000' }), // same second
    makeSnap({ market_code: 'US', total_return_pct: -3.0, created_at: '2026-11-17T11:00:00' }),
  ];

  const krPoints = buildChartSeriesData(snaps, 'model-a', 'KR');
  assert.equal(krPoints.length, 2);
  assert.ok(krPoints[0].time < krPoints[1].time);
  assert.equal(krPoints[0].value, 1.5);
  assert.equal(krPoints[1].value, 2.0);

  const usPoints = buildChartSeriesData(snaps, 'model-a', 'US');
  assert.equal(usPoints.length, 1);
  assert.equal(usPoints[0].value, -3.0);
});

test('buildChartSeriesData ALL mode computes running combined mean across KR and US', () => {
  const snaps: SnapshotSummary[] = [
    makeSnap({ market_code: 'KR', total_return_pct: 2.0, created_at: '2026-11-17T10:00:00' }),
    makeSnap({ market_code: 'US', total_return_pct: -1.0, created_at: '2026-11-17T11:00:00' }),
    makeSnap({ market_code: 'KR', total_return_pct: 3.0, created_at: '2026-11-17T12:00:00' }),
  ];

  const allPoints = buildChartSeriesData(snaps, 'model-a', 'ALL');
  assert.equal(allPoints.length, 3);
  assert.equal(allPoints[0].value, 2.0);  // KR=2.0
  assert.equal(allPoints[1].value, 0.5);  // (2.0 + -1.0) / 2
  assert.equal(allPoints[2].value, 1.0);  // (3.0 + -1.0) / 2
});

test('formatKstDateTime formats UTC epoch seconds in KST (+9h)', () => {
  const epoch = toEpochSeconds('2026-11-17T13:00:00Z')!;
  const formatted = formatKstDateTime(epoch);
  assert.ok(formatted.includes('22:00'), `Expected 22:00 KST, got: ${formatted}`);
});
