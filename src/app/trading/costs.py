from __future__ import annotations

from dataclasses import dataclass

from app.db.models import MarketSetting


@dataclass(slots=True)
class CostBreakdown:
    gross_amount: float
    commission_amount: float
    tax_amount: float
    regulatory_fee_amount: float
    net_cash_change: float


def calculate_buy_costs(market: MarketSetting, quantity: float, price: float) -> CostBreakdown:
    gross_amount = quantity * price
    commission_amount = gross_amount * market.buy_commission_rate
    tax_amount = 0.0
    regulatory_fee_amount = 0.0
    net_cash_change = -(gross_amount + commission_amount)
    return CostBreakdown(
        gross_amount=gross_amount,
        commission_amount=commission_amount,
        tax_amount=tax_amount,
        regulatory_fee_amount=regulatory_fee_amount,
        net_cash_change=net_cash_change,
    )


def calculate_sell_costs(market: MarketSetting, quantity: float, price: float) -> CostBreakdown:
    gross_amount = quantity * price
    commission_amount = gross_amount * market.sell_commission_rate
    tax_amount = gross_amount * market.sell_tax_rate
    regulatory_fee_amount = gross_amount * market.sell_regulatory_fee_rate
    net_cash_change = gross_amount - commission_amount - tax_amount - regulatory_fee_amount
    return CostBreakdown(
        gross_amount=gross_amount,
        commission_amount=commission_amount,
        tax_amount=tax_amount,
        regulatory_fee_amount=regulatory_fee_amount,
        net_cash_change=net_cash_change,
    )
