import type { SnapshotSummary } from '../types/index.ts';
import { parseUtcDate } from './format.ts';

export type ChartMarketFilter = 'ALL' | 'KR' | 'US';

export interface ChartPoint {
  time: number;
  value: number;
}

export function toEpochSeconds(dateString: string | null | undefined): number | null {
  const parsed = parseUtcDate(dateString);
  if (!parsed) return null;
  const sec = Math.floor(parsed.getTime() / 1000);
  return Number.isFinite(sec) ? sec : null;
}

/**
 * Converts raw backend SnapshotSummary records into strictly ascending,
 * unique-timestamp series points for TradingView Lightweight Charts.
 */
export function buildChartSeriesData(
  snapshots: SnapshotSummary[],
  modelId: string,
  marketFilter: ChartMarketFilter = 'ALL'
): ChartPoint[] {
  const datedRows = snapshots
    .filter((s) => {
      if (s.model_id !== modelId) return false;
      if (marketFilter !== 'ALL' && s.market_code !== marketFilter) return false;
      return typeof s.total_return_pct === 'number' && Number.isFinite(s.total_return_pct);
    })
    .map((s) => ({
      snapshot: s,
      time: toEpochSeconds(s.created_at),
    }))
    .filter((item): item is { snapshot: SnapshotSummary; time: number } => item.time !== null)
    .sort((a, b) => a.time - b.time);

  if (datedRows.length === 0) {
    return [];
  }

  const latestByMarket: Record<string, number> = {};
  const dedupedByTime = new Map<number, number>();

  for (const { snapshot, time } of datedRows) {
    if (marketFilter === 'ALL') {
      latestByMarket[snapshot.market_code] = snapshot.total_return_pct;
      const values = Object.values(latestByMarket);
      const mean = values.reduce((acc, v) => acc + v, 0) / values.length;
      dedupedByTime.set(time, Number(mean.toFixed(4)));
    } else {
      dedupedByTime.set(time, Number(snapshot.total_return_pct.toFixed(4)));
    }
  }

  return Array.from(dedupedByTime.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time, value }));
}

export function formatKstDateTime(epochSeconds: number): string {
  const date = new Date(epochSeconds * 1000);
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatKstTickMark(epochSeconds: number): string {
  const date = new Date(epochSeconds * 1000);
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}
