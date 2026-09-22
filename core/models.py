from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ProductSpec:
    id: str
    spec: str
    thickness: Optional[float]
    width: float
    length: float
    required_qty: int = 1
    rotation_allowed: bool = True
    name: str = ""
    destination: str = ""
    monthly_usage: float = 0.0
    remarks: str = ""
    coating: Optional[str] = None

    @property
    def weight_spec(self) -> str:
        return self.spec if self.coating is None else self.coating

    @property
    def area(self) -> float:
        return self.width * self.length


@dataclass(frozen=True)
class SheetType:
    id: str
    name: str
    spec: str
    thickness: Optional[float]
    width: float
    length: float
    max_sheets: Optional[int] = None
    edge_loss: float = 10.0
    cut_allowance: float = 0.0
    length_loss: float = 0.0
    coating: Optional[str] = None

    @property
    def weight_spec(self) -> str:
        return self.spec if self.coating is None else self.coating

    @property
    def usable_width(self) -> float:
        return self.width

    @property
    def usable_length(self) -> float:
        return self.length

    @property
    def area(self) -> float:
        return self.width * self.length


@dataclass(frozen=True)
class Placement:
    product_id: str
    x: float
    y: float
    width: float
    length: float
    rotated: bool


@dataclass
class SheetPlan:
    sheet_type: SheetType
    sheet_no: int
    placements: list[Placement] = field(default_factory=list)


@dataclass
class OptimizationResult:
    sheets: list[SheetPlan]
    required_by_product: dict[str, int]
    placed_by_product: dict[str, int]
    yield_rate: float
    loss_rate: float
    sheet_weight: float
    product_weight: float
    scrap_weight: float
    cut_count: int
    complete: bool
    timed_out: bool = False
    warnings: list[str] = field(default_factory=list)
    candidate_sheet_ids: tuple[str, ...] = ()

    @property
    def weight_available(self) -> bool:
        """板厚が1つでも空欄だと_resultが重量を0にするため、表示可否の判定に使う。"""
        return self.sheet_weight > 0

    @property
    def shortage_by_product(self) -> dict[str, int]:
        return {
            key: max(0, qty - self.placed_by_product.get(key, 0))
            for key, qty in self.required_by_product.items()
        }
