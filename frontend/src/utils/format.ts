export function formatCurrency(amount: number, currency: 'USD' | 'KRW' = 'USD'): string {
  if (currency === 'KRW') {
    return new Intl.NumberFormat('ko-KR', {
      style: 'currency',
      currency: 'KRW',
      maximumFractionDigits: 0,
    }).format(amount);
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatPercent(value: number | null | undefined): {
  text: string;
  isPositive: boolean;
  isNeutral: boolean;
} {
  if (value === null || value === undefined) {
    return { text: '0.00%', isPositive: false, isNeutral: true };
  }
  const isPositive = value > 0;
  const isNeutral = value === 0;
  const sign = isPositive ? '+' : '';
  return {
    text: `${sign}${value.toFixed(2)}%`,
    isPositive,
    isNeutral,
  };
}

export function timeAgo(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  const date = new Date(dateString);
  const now = new Date();
  const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffSec < 60) return '방금 전';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}일 전`;
}

export function getModelBrand(modelId: string): {
  brand: string;
  color: string;
  bgColor: string;
  borderColor: string;
} {
  const lower = modelId.toLowerCase();
  if (lower.includes('nvidia')) {
    return {
      brand: 'NVIDIA',
      color: 'text-emerald-400',
      bgColor: 'bg-emerald-950/40',
      borderColor: 'border-emerald-500/30',
    };
  }
  if (lower.includes('google') || lower.includes('gemma')) {
    return {
      brand: 'Google',
      color: 'text-blue-400',
      bgColor: 'bg-blue-950/40',
      borderColor: 'border-blue-500/30',
    };
  }
  if (lower.includes('cohere')) {
    return {
      brand: 'Cohere',
      color: 'text-purple-400',
      bgColor: 'bg-purple-950/40',
      borderColor: 'border-purple-500/30',
    };
  }
  if (lower.includes('liquid')) {
    return {
      brand: 'LiquidAI',
      color: 'text-cyan-400',
      bgColor: 'bg-cyan-950/40',
      borderColor: 'border-cyan-500/30',
    };
  }
  if (lower.includes('xingchen')) {
    return {
      brand: 'XingChen',
      color: 'text-amber-400',
      bgColor: 'bg-amber-950/40',
      borderColor: 'border-amber-500/30',
    };
  }
  if (lower.includes('dots')) {
    return {
      brand: 'Dots Studio',
      color: 'text-pink-400',
      bgColor: 'bg-pink-950/40',
      borderColor: 'border-pink-500/30',
    };
  }
  if (lower.includes('thinkingmachines') || lower.includes('inkling')) {
    return {
      brand: 'Thinking Machines',
      color: 'text-teal-400',
      bgColor: 'bg-teal-950/40',
      borderColor: 'border-teal-500/30',
    };
  }
  if (lower.includes('recursive') || lower.includes('flint')) {
    return {
      brand: 'Recursive',
      color: 'text-indigo-400',
      bgColor: 'bg-indigo-950/40',
      borderColor: 'border-indigo-500/30',
    };
  }
  return {
    brand: 'OpenRouter',
    color: 'text-violet-400',
    bgColor: 'bg-violet-950/40',
    borderColor: 'border-violet-500/30',
  };
}
