export interface ModelRanking {
  model_id: string;
  display_name: string;
  search_mode: string;
  is_free_like: boolean;
  pricing_label: string;
  current_return_pct: number;
  return_1d_pct: number | null;
  return_1w_pct: number | null;
  return_1m_pct: number | null;
  kr_return_pct: number | null;
  us_return_pct: number | null;
  composite_score: number | null;
  max_drawdown: number | null;
  win_rate: number | null;
  trade_count: number;
  llm_cost_usd: number;
  trade_fee_cost: number;
  updated_at: string | null;
}

export interface OverviewResponse {
  total_models: number;
  active_models: number;
  total_trades: number;
  open_positions: number;
  kr_active?: boolean;
  us_active?: boolean;
  last_snapshot_at: string | null;
}

export interface PortfolioSummary {
  model_id: string;
  market_code: string;
  currency: string;
  initial_cash: number;
  available_cash: number;
  invested_value: number;
  total_equity: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
}

export interface PositionSummary {
  model_id: string;
  market_code: string;
  ticker: string;
  quantity: number;
  average_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface TradeSummary {
  id?: number;
  model_id: string;
  market_code: string;
  ticker: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  shares: number;
  price: number;
  total_amount: number;
  executed_at: string;
  realized_pnl: number | null;
}

export interface NewsItemSummary {
  title: string;
  summary: string;
  source: string;
  url: string | null;
  published_at: string | null;
  tickers: string[];
}

export interface LLMDecisionLogSummary {
  id?: number;
  created_at: string;
  model_id: string;
  market_code: string;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  prompt_text: string | null;
  raw_output_text: string | null;
  parsed_output?: any;
  error_message: string | null;
}

export interface SnapshotSummary {
  model_id: string;
  market_code: string;
  snapshot_time: string;
  return_pct: number;
  total_equity: number;
  cash?: number;
}

export interface MarketSoundtrack {
  id: string;
  market: 'KR' | 'US';
  market_name: string;
  date: string;
  title: string;
  genre: string;
  bpm: number;
  key: string;
  mood: string;
  audio_url: string;
  duration_sec: number;
  summary: string;
}

export interface SchedulerMarketStatus {
  market_code: string;
  market_timezone: string;
  in_active_window: boolean;
  is_due: boolean;
  last_status: string;
  next_run_at: string | null;
}
