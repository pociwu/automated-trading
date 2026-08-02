from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ZhongDadan424Strategy:
    """三階段 40% / 20% / 40% 賣出配置與 S 點出場判斷。"""

    stage_ratios: tuple[Decimal, Decimal, Decimal] = (
        Decimal("0.4"),
        Decimal("0.2"),
        Decimal("0.4"),
    )

    def sell_quantity(self, base_quantity: int, remaining_quantity: int, stage: int) -> int:
        if stage not in (1, 2, 3):
            raise ValueError("stage 必須為 1、2 或 3")
        if stage == 3:
            return remaining_quantity
        target = int(Decimal(base_quantity) * self.stage_ratios[stage - 1])
        future_stages = 3 - stage
        return min(max(target, 1), remaining_quantity - future_stages)

    @staticmethod
    def should_stop(close: Decimal, stop_price: Decimal | None) -> bool:
        return stop_price is not None and close <= stop_price

