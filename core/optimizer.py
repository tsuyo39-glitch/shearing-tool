from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from threading import Event

from .models import OptimizationResult, Placement, ProductSpec, SheetPlan, SheetType
from .weight import plate_weight_kg

EPSILON = 0.001


@dataclass(frozen=True)
class _FreeRect:
    x: float
    y: float
    width: float
    length: float


@dataclass
class _OpenSheet:
    plan: SheetPlan
    free: list[_FreeRect]


def _compatible(product: ProductSpec, sheet: SheetType) -> bool:
    thickness_matches = (
        product.thickness is None
        or sheet.thickness is None
        or abs(product.thickness - sheet.thickness) <= EPSILON
    )
    return product.spec == sheet.spec and product.coating == sheet.coating and thickness_matches


def _orientations(product: ProductSpec) -> list[tuple[float, float, bool]]:
    result = [(product.width, product.length, False)]
    if product.rotation_allowed and abs(product.width - product.length) > EPSILON:
        result.append((product.length, product.width, True))
    return result


def _fits(width: float, length: float, rect: _FreeRect, tolerance: float = EPSILON) -> bool:
    return width <= rect.width + tolerance and length <= rect.length + tolerance


def _split(rect: _FreeRect, width: float, length: float, gap: float, vertical_first: bool) -> list[_FreeRect]:
    right_x = rect.x + width + gap
    bottom_y = rect.y + length + gap
    right_w = max(0.0, rect.width - width - gap)
    bottom_h = max(0.0, rect.length - length - gap)
    pieces: list[_FreeRect] = []
    if vertical_first:
        if right_w > EPSILON:
            pieces.append(_FreeRect(right_x, rect.y, right_w, rect.length))
        if bottom_h > EPSILON:
            pieces.append(_FreeRect(rect.x, bottom_y, width, bottom_h))
    else:
        if right_w > EPSILON:
            pieces.append(_FreeRect(right_x, rect.y, right_w, length))
        if bottom_h > EPSILON:
            pieces.append(_FreeRect(rect.x, bottom_y, rect.width, bottom_h))
    return pieces


def _place_on_sheet(open_sheet: _OpenSheet, product: ProductSpec, strategy: int, tolerance: float = EPSILON) -> bool:
    choices: list[tuple[tuple[float, float, int, int], int, float, float, bool]] = []
    for rect_index, rect in enumerate(open_sheet.free):
        for orient_index, (width, length, rotated) in enumerate(_orientations(product)):
            if _fits(width, length, rect, tolerance):
                waste = rect.width * rect.length - width * length
                short_side = min(rect.width - width, rect.length - length)
                score = (waste, short_side, orient_index if strategy % 2 == 0 else -orient_index, rect_index)
                choices.append((score, rect_index, width, length, rotated))
    if not choices:
        return False
    _, rect_index, width, length, rotated = min(choices, key=lambda item: item[0])
    rect = open_sheet.free.pop(rect_index)
    open_sheet.plan.placements.append(
        Placement(product.id, rect.x, rect.y, width, length, rotated)
    )
    vertical_first = (strategy + len(open_sheet.plan.placements)) % 2 == 0
    open_sheet.free.extend(
        _split(rect, width, length, open_sheet.plan.sheet_type.cut_allowance, vertical_first)
    )
    return True


def _new_sheet(sheet: SheetType, number: int, product: ProductSpec) -> _OpenSheet:
    effective_sheet = sheet
    if sheet.thickness is None and product.thickness is not None:
        effective_sheet = replace(sheet, thickness=product.thickness)
    return _OpenSheet(
        plan=SheetPlan(effective_sheet, number),
        free=[_FreeRect(0.0, 0.0, effective_sheet.usable_width, effective_sheet.usable_length)],
    )


def _sort_items(products: list[ProductSpec], strategy: int) -> list[ProductSpec]:
    items = [product for product in products for _ in range(product.required_qty)]
    keys = [
        lambda p: (p.area, max(p.width, p.length), min(p.width, p.length)),
        lambda p: (max(p.width, p.length), p.area, min(p.width, p.length)),
        lambda p: (p.width, p.length, p.area),
        lambda p: (p.length, p.width, p.area),
    ]
    return sorted(items, key=keys[strategy % len(keys)], reverse=True)


def _build_candidate(products: list[ProductSpec], sheets: list[SheetType], strategy: int, deadline: float, cancel: Event | None, tolerance: float = EPSILON) -> tuple[list[SheetPlan], Counter[str], bool]:
    opened: list[_OpenSheet] = []
    used_counts: Counter[str] = Counter()
    placed: Counter[str] = Counter()
    timed_out = False
    for product in _sort_items(products, strategy):
        if time.monotonic() >= deadline or (cancel and cancel.is_set()):
            timed_out = True
            break
        compatible_open = [sheet for sheet in opened if _compatible(product, sheet.plan.sheet_type)]
        if strategy % 3 == 1:
            compatible_open.reverse()
        done = any(_place_on_sheet(sheet, product, strategy, tolerance) for sheet in compatible_open)
        if not done:
            new_options: list[tuple[float, SheetType]] = []
            for sheet in sheets:
                if not _compatible(product, sheet):
                    continue
                if sheet.max_sheets is not None and used_counts[sheet.id] >= sheet.max_sheets:
                    continue
                fits = any(
                    width <= sheet.usable_width + tolerance and length <= sheet.usable_length + tolerance
                    for width, length, _ in _orientations(product)
                )
                if fits:
                    new_options.append((sheet.area - product.area, sheet))
            if new_options:
                new_options.sort(key=lambda item: (item[0], item[1].area), reverse=strategy % 3 == 2)
                selected = new_options[0][1]
                used_counts[selected.id] += 1
                opened_sheet = _new_sheet(selected, used_counts[selected.id], product)
                opened.append(opened_sheet)
                done = _place_on_sheet(opened_sheet, product, strategy, tolerance)
        if done:
            placed[product.id] += 1
    return [sheet.plan for sheet in opened], placed, timed_out


def _result(plans: list[SheetPlan], products: list[ProductSpec], placed: Counter[str], timed_out: bool) -> OptimizationResult:
    product_map = {product.id: product for product in products}
    required = {product.id: product.required_qty for product in products}
    sheet_area = sum(plan.sheet_type.area for plan in plans)
    product_area = sum(product_map[p.product_id].area for plan in plans for p in plan.placements)
    sheet_weight = 0.0
    product_weight = 0.0
    weight_incomplete = False
    warnings: list[str] = []
    for plan in plans:
        if plan.sheet_type.thickness is None:
            weight_incomplete = True
            warning = "板厚が空欄のため重量は計算していません。"
            if warning not in warnings:
                warnings.append(warning)
        else:
            weight, warning = plate_weight_kg(
                plan.sheet_type.weight_spec,
                plan.sheet_type.thickness,
                plan.sheet_type.width,
                plan.sheet_type.length,
            )
            sheet_weight += weight
            if warning and warning not in warnings:
                warnings.append(warning)
        for placement in plan.placements:
            product = product_map[placement.product_id]
            if product.thickness is None:
                weight_incomplete = True
                warning = "板厚が空欄のため重量は計算していません。"
                if warning not in warnings:
                    warnings.append(warning)
            else:
                weight, warning = plate_weight_kg(product.weight_spec, product.thickness, product.width, product.length)
                product_weight += weight
                if warning and warning not in warnings:
                    warnings.append(warning)
    yield_rate = product_area / sheet_area * 100 if sheet_area else 0.0
    complete = all(placed.get(key, 0) >= qty for key, qty in required.items())
    if weight_incomplete:
        sheet_weight = 0.0
        product_weight = 0.0
    scrap_weight = 0.0 if weight_incomplete else max(0.0, sheet_weight - product_weight)
    return OptimizationResult(
        sheets=plans,
        required_by_product=required,
        placed_by_product=dict(placed),
        yield_rate=yield_rate,
        loss_rate=100 - yield_rate if sheet_area else 100.0,
        sheet_weight=sheet_weight,
        product_weight=product_weight,
        scrap_weight=scrap_weight,
        cut_count=sum(len(plan.placements) * 2 for plan in plans),
        complete=complete,
        timed_out=timed_out,
        warnings=warnings,
    )


def _score(result: OptimizationResult) -> tuple:
    shortages = result.shortage_by_product
    sheet_types = {plan.sheet_type.id for plan in result.sheets}
    return (
        sum(1 for qty in shortages.values() if qty > 0),
        sum(shortages.values()),
        len(result.sheets),
        result.loss_rate,
        result.cut_count,
        len(sheet_types),
    )


def sheet_pattern_key(plan: SheetPlan) -> tuple:
    """大板番号や入力行IDに依存しない、配置パターンの比較キー。"""
    sheet = plan.sheet_type
    sheet_key = (
        sheet.spec, sheet.thickness if sheet.thickness is not None else -1.0, sheet.width, sheet.length,
        sheet.edge_loss, sheet.cut_allowance, sheet.weight_spec,
    )
    placements = tuple(sorted(
        (
            placement.product_id,
            round(placement.x, 6), round(placement.y, 6),
            round(placement.width, 6), round(placement.length, 6),
        )
        for placement in plan.placements
    ))
    if abs(sheet.width - sheet.length) <= EPSILON:
        rotated_90 = tuple(sorted(
            (
                placement.product_id,
                round(sheet.length - placement.y - placement.length, 6),
                round(placement.x, 6),
                round(placement.length, 6),
                round(placement.width, 6),
            )
            for placement in plan.placements
        ))
        rotated_180 = tuple(sorted(
            (
                placement.product_id,
                round(sheet.width - placement.x - placement.width, 6),
                round(sheet.length - placement.y - placement.length, 6),
                round(placement.width, 6),
                round(placement.length, 6),
            )
            for placement in plan.placements
        ))
        rotated_270 = tuple(sorted(
            (
                placement.product_id,
                round(placement.y, 6),
                round(sheet.width - placement.x - placement.width, 6),
                round(placement.length, 6),
                round(placement.width, 6),
            )
            for placement in plan.placements
        ))
        placements = min(placements, rotated_90, rotated_180, rotated_270)
    return sheet_key, placements


def group_sheet_plans(plans: list[SheetPlan]) -> list[tuple[SheetPlan, int, list[int]]]:
    """同じ大板条件・同じ配置の使用板を、代表パターンと枚数へまとめる。"""
    groups: dict[tuple, list[SheetPlan]] = defaultdict(list)
    order: list[tuple] = []
    for plan in plans:
        key = sheet_pattern_key(plan)
        if key not in groups:
            order.append(key)
        groups[key].append(plan)
    return [
        (groups[key][0], len(groups[key]), [plan.sheet_no for plan in groups[key]])
        for key in order
    ]


def _signature(result: OptimizationResult) -> tuple:
    """同じ配置パターンと枚数の候補を、探索順に関係なく重複除外する。"""
    counts = Counter(sheet_pattern_key(plan) for plan in result.sheets)
    context = result.candidate_sheet_ids if not result.sheets else ()
    return context, tuple(sorted((key, count) for key, count in counts.items()))


def validate_inputs(products: list[ProductSpec], sheets: list[SheetType]) -> None:
    if not products:
        raise ValueError("製品を1種類以上入力してください。")
    if not sheets:
        raise ValueError("大板を1種類以上入力してください。")
    for product in products:
        if min(product.width, product.length, product.required_qty) <= 0:
            raise ValueError(f"製品 {product.id} の寸法・必要枚数は0より大きくしてください。")
        if product.thickness is not None and product.thickness <= 0:
            raise ValueError(f"製品 {product.id} の板厚は空欄または0より大きい値にしてください。")
        if not any(_compatible(product, sheet) for sheet in sheets):
            raise ValueError(f"製品 {product.id} と規格・板厚が一致する大板がありません。")
    for sheet in sheets:
        if min(sheet.width, sheet.length) <= 0:
            raise ValueError(f"大板 {sheet.name} の寸法は0より大きくしてください。")
        if sheet.thickness is not None and sheet.thickness <= 0:
            raise ValueError(f"大板 {sheet.name} の板厚は空欄または0より大きい値にしてください。")
        if sheet.edge_loss < 0 or sheet.cut_allowance < 0:
            raise ValueError(f"大板 {sheet.name} のロス・切断代は0以上にしてください。")
        if sheet.usable_width <= 0 or sheet.usable_length <= 0:
            raise ValueError(f"大板 {sheet.name} は四辺ロスを引くと有効寸法が0以下です。")


def optimize(products: list[ProductSpec], sheets: list[SheetType], time_limit: float = 10.0, cancel: Event | None = None) -> list[OptimizationResult]:
    validate_inputs(products, sheets)
    deadline = time.monotonic() + max(0.05, time_limit)
    candidates: list[OptimizationResult] = []
    signatures: set[tuple] = set()
    sheet_groups = [[sheet] for sheet in sheets]
    if len(sheets) > 1:
        sheet_groups.append(sheets)
    for candidate_sheets in sheet_groups:
        strategy_count = 8 if len(candidate_sheets) == 1 else 24
        for strategy in range(strategy_count):
            if time.monotonic() >= deadline or (cancel and cancel.is_set()):
                break
            plans, placed, timed_out = _build_candidate(products, candidate_sheets, strategy, deadline, cancel)
            result = _result(plans, products, placed, timed_out)
            result.candidate_sheet_ids = tuple(sheet.id for sheet in candidate_sheets)
            signature = _signature(result)
            if signature not in signatures:
                signatures.add(signature)
                candidates.append(result)
    timed_out = time.monotonic() >= deadline or bool(cancel and cancel.is_set())
    if timed_out:
        for candidate in candidates:
            candidate.timed_out = True
    return sorted(candidates, key=_score)[:10]


def validate_layout(result: OptimizationResult) -> list[str]:
    errors: list[str] = []
    for plan in result.sheets:
        sheet = plan.sheet_type
        for index, placement in enumerate(plan.placements):
            if placement.x < -EPSILON or placement.y < -EPSILON:
                errors.append(f"{sheet.name}#{plan.sheet_no}: {placement.product_id} が大板外です")
            if placement.x + placement.width > sheet.width + EPSILON:
                errors.append(f"{sheet.name}#{plan.sheet_no}: {placement.product_id} が幅方向へはみ出しています")
            if placement.y + placement.length > sheet.length + EPSILON:
                errors.append(f"{sheet.name}#{plan.sheet_no}: {placement.product_id} が長さ方向へはみ出しています")
            for other in plan.placements[index + 1 :]:
                separated = (
                    placement.x + placement.width <= other.x + EPSILON
                    or other.x + other.width <= placement.x + EPSILON
                    or placement.y + placement.length <= other.y + EPSILON
                    or other.y + other.length <= placement.y + EPSILON
                )
                if not separated:
                    errors.append(f"{sheet.name}#{plan.sheet_no}: {placement.product_id} と {other.product_id} が重なっています")
    return errors
