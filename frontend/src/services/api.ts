import {
  ModelRanking,
  OverviewResponse,
  PortfolioSummary,
  PositionSummary,
  TradeSummary,
  NewsItemSummary,
  LLMDecisionLogSummary,
  SnapshotSummary,
} from '../types';

const API_BASE = '/api';

export const api = {
  async getRankings(): Promise<ModelRanking[]> {
    const res = await fetch(`${API_BASE}/rankings`);
    if (!res.ok) throw new Error(`Failed to load rankings: ${res.statusText}`);
    return res.json();
  },

  async getOverview(): Promise<OverviewResponse> {
    const res = await fetch(`${API_BASE}/overview`);
    if (!res.ok) throw new Error(`Failed to load overview: ${res.statusText}`);
    return res.json();
  },

  async getPortfolios(): Promise<PortfolioSummary[]> {
    const res = await fetch(`${API_BASE}/portfolios`);
    if (!res.ok) throw new Error(`Failed to load portfolios: ${res.statusText}`);
    return res.json();
  },

  async getPositions(): Promise<PositionSummary[]> {
    const res = await fetch(`${API_BASE}/positions`);
    if (!res.ok) throw new Error(`Failed to load positions: ${res.statusText}`);
    return res.json();
  },

  async getTrades(limit = 40): Promise<TradeSummary[]> {
    const res = await fetch(`${API_BASE}/trades?limit=${limit}`);
    if (!res.ok) throw new Error(`Failed to load trades: ${res.statusText}`);
    return res.json();
  },

  async getNewsItems(limit = 40): Promise<NewsItemSummary[]> {
    const res = await fetch(`${API_BASE}/news-items?limit=${limit}`);
    if (!res.ok) throw new Error(`Failed to load news items: ${res.statusText}`);
    return res.json();
  },

  async getLLMLogs(limit = 20): Promise<LLMDecisionLogSummary[]> {
    const res = await fetch(`${API_BASE}/llm-logs?limit=${limit}`);
    if (!res.ok) throw new Error(`Failed to load LLM logs: ${res.statusText}`);
    return res.json();
  },

  async getSnapshots(limit = 200): Promise<SnapshotSummary[]> {
    const res = await fetch(`${API_BASE}/snapshots?limit=${limit}`);
    if (!res.ok) throw new Error(`Failed to load snapshots: ${res.statusText}`);
    return res.json();
  },

  async getSchedulerStatus(): Promise<any> {
    const res = await fetch(`${API_BASE}/scheduler`);
    if (!res.ok) throw new Error(`Failed to load scheduler status: ${res.statusText}`);
    return res.json();
  },
};
