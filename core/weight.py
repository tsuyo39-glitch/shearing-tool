from __future__ import annotations

import re
import unicodedata

STEEL_BASIC_MASS = 7.85  # kg/(mm*m2)
COATING_MASS_KG_M2 = {
    "Z08": 0.080,
}


def normalize_spec(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return text.strip().upper().replace(" ", "")


def coating_code(spec: str) -> str | None:
    normalized = normalize_spec(spec)
    match = re.search(r"(?:^|-)Z0?(\d{1,2})(?:-|$)", normalized)
    if not match:
        return None
    return f"Z{int(match.group(1)):02d}"


def coating_mass(spec: str) -> tuple[float, str | None]:
    code = coating_code(spec)
    if code is None:
        return 0.0, None
    if code in COATING_MASS_KG_M2:
        return COATING_MASS_KG_M2[code], None
    return 0.0, f"規格 {spec} のめっき記号 {code} は目付未登録です。重量を確定できません。"


def unit_mass_kg_m2(spec: str, thickness_mm: float) -> tuple[float, str | None]:
    coating, warning = coating_mass(spec)
    return thickness_mm * STEEL_BASIC_MASS + coating, warning


def plate_weight_kg(
    spec: str, thickness_mm: float, width_mm: float, length_mm: float, quantity: int = 1
) -> tuple[float, str | None]:
    unit_mass, warning = unit_mass_kg_m2(spec, thickness_mm)
    area_m2 = width_mm * length_mm / 1_000_000
    return area_m2 * unit_mass * quantity, warning

