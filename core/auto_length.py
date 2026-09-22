"""Variable-length guillotine plans; the original fixed-sheet solver is unchanged."""
from collections import Counter
from dataclasses import replace
import math
import time

from .models import SheetType, SheetPlan
from .optimizer import _build_candidate, _result, _signature


def optimize_auto(products, width=1219.0, edge=10.0, max_length=2438.0,
                  gap=0.0, time_limit=10.0, cancel=None, length_loss=0.0, length_round=0.0):
    values = (width, edge, max_length, gap, time_limit, length_loss, length_round)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("設定には有限の数値を入力してください。")
    if (edge < 0 or gap < 0 or length_loss < 0 or length_round < 0
            or width <= edge or max_length <= 2*length_loss or time_limit <= 0):
        raise ValueError("幅は幅ロスより大きく、最大長さ・計算時間は正の数、切断代・ロス・丸めは0以上にしてください。")
    if not products or len({p.id for p in products}) != len(products):
        raise ValueError("製品を1種類以上入力してください（IDは重複不可）。")
    for p in products:
        if not all(math.isfinite(v) and v > 0 for v in (p.width, p.length, p.required_qty)) or int(p.required_qty) != p.required_qty:
            raise ValueError(f"{p.name}: 寸法は正の数、必要枚数は正の整数にしてください。")
        if p.thickness is not None and (not math.isfinite(p.thickness) or p.thickness <= 0):
            raise ValueError(f"{p.name}: 板厚は空欄または正の数にしてください。")
        orientations = [(p.width, p.length)] + ([(p.length, p.width)] if p.rotation_allowed else [])
        if not any(w <= width - edge and h <= max_length-2*length_loss for w, h in orientations):
            raise ValueError(f"{p.name}: ロスを除く有効寸法 {width-edge:g} × {max_length-2*length_loss:g} mmに入りません。")
    if sum(p.required_qty for p in products) > 20000:
        raise ValueError("1回の計算は製品合計20,000枚以内にしてください。")
    # Separate even unspecified thickness from specified thickness to avoid mixing.
    groups = {}
    for p in products:
        groups.setdefault((p.spec, p.thickness, p.coating), []).append(p)
    deadline = time.monotonic() + time_limit
    candidates, seen = [], set()
    for strategy in range(24):
        if time.monotonic() >= deadline or (cancel and cancel.is_set()):
            break
        plans, placed, interrupted = [], Counter(), False
        for (spec, thickness, coating), items in groups.items():
            inner = SheetType("inner", "有効寸法", spec, thickness, width-edge,
                              max_length-2*length_loss, edge_loss=0, cut_allowance=gap, coating=coating)
            raw, counts, stopped = _build_candidate(items, [inner], strategy, deadline, cancel, tolerance=1e-9)
            placed.update(counts)
            interrupted |= stopped
            for plan in raw:
                length = max(p.y+p.length for p in plan.placements)+2*length_loss
                if length_round > 0:
                    # 切り上げで長さの種類をそろえる。最大長さは超えない。
                    length = float(min(max_length, math.ceil(length/length_round)*length_round))
                sheet = replace(inner, id=f"A{len(plans)+1}", name=f"{width:g}×{length:g}",
                                width=width, length=length, edge_loss=edge, length_loss=length_loss)
                plans.append(SheetPlan(sheet, len(plans)+1,
                             [replace(p, x=p.x+edge, y=p.y+length_loss) for p in plan.placements]))
        result = _result(plans, products, placed, interrupted)
        signature = _signature(result)
        if signature not in seen:
            seen.add(signature)
            candidates.append(result)
        if interrupted:
            break
    if time.monotonic() >= deadline or (cancel and cancel.is_set()):
        for candidate in candidates:
            candidate.timed_out = True
    return sorted(candidates, key=lambda r: (not r.complete, sum(r.shortage_by_product.values()),
                  sum(s.sheet_type.area for s in r.sheets), len(r.sheets),
                  len({s.sheet_type.length for s in r.sheets})))[:10]
