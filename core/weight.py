"""板の計算質量。めっき鋼板はJISの「めっき量定数」を加算する。

  原板の単位質量(kg/m2)   ＝ 基本質量 7.85 × 表示厚さ(mm)
  めっき後の単位質量(kg/m2) ＝ 原板の単位質量 ＋ めっき量定数(kg/m2)

表示厚さはめっき前の原板厚さ。

重要：質量計算に使うのは「めっき量定数」であって、めっき付着量(g/m2)ではない。
Z08なら 0.120 kg/m2 で、付着量80 g/m2 を1000で割った 0.080 ではない。
付着量は品質規格の下限値、めっき量定数は質量計算用の値で別物。

出典
  Z系  JIS G 3302-2010 表8（日本製鉄カタログU023／日鉄鋼板ニスクジンクの規格抜粋）
  E系  JIS G 3313-2010 表25（等厚）・表26（異厚・片面）
  K系・ZAM系  日本製鉄 亜鉛・アルミニウム・マグネシウム合金めっき 総合カタログU110 の質量表
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

STEEL_BASIC_MASS = 7.85  # 基本質量 kg/(mm*m2)

# めっき記号。AZ・ZAMは短い記号より先に判定する。数字の代わりにBを取る記号（EB）もある。
_CODE_PATTERN = re.compile(r"(?:^|[-_/])(AZ|ZAM|SA|Z|F|E|K)(?:0?(\d{1,3})|(B))(?=D?(?:$|[-_/]))")
# ZAM-60 のような数字だけの付着量記号。
_ZAM_NUMERIC = re.compile(r"ZAM[-_/](\d{2,3})(?=$|[-_/])")
# めっき鋼板を示す規格の頭。記号を読み取れないときに黙って0kgにしないための判定。
_COATED_STEEL = re.compile(r"^(?:S[GEZ]|ZAM|SGL|AZ)")
# マスタに登録できる記号の形。読み取れない記号は登録しても効かない。
CODE_FORMAT = re.compile(r"^(?:(?:AZ|ZAM|SA|Z|F|E|K)(?:\d{1,3}|B)|(?:10/10|20/20|30/30|40/40))$")


@dataclass(frozen=True)
class Coating:
    constant_kg_m2: float  # 等厚（両面合計）のめっき量定数
    per_side_kg_m2: float | None  # 異厚計算用の片面あたり定数
    note: str  # 出典と付着量の説明
    confirmed: bool


def _jis_g3302():
    # 記号: (めっき量定数 kg/m2, 両面付着量の3点平均最小値 g/m2)
    table = {
        "Z06": (0.090, 60), "Z08": (0.120, 80), "Z10": (0.150, 100), "Z12": (0.183, 120),
        "Z14": (0.203, 140), "Z18": (0.244, 180), "Z20": (0.285, 200), "Z22": (0.305, 220),
        "Z25": (0.350, 250), "Z27": (0.381, 275), "Z35": (0.458, 350), "Z37": (0.481, 370),
        "Z45": (0.565, 450), "Z60": (0.722, 600),
    }
    return {code: Coating(constant, None, f"溶融亜鉛 JIS G 3302 表8。両面付着量 {coating} g/m²（3点平均最小）", True)
            for code, (constant, coating) in table.items()}


def _alloy():
    # 日本鉄鋼連盟公開 JIS G 3302 改正原案(2022-07-28)、表30。
    source = "https://www.jisf.or.jp/business/standard/jis/documents/docs_kouzai_02JISG3302_20220728.pdf"
    table = {"F04": 0.060, "F06": 0.090, "F08": 0.120,
             "F10": 0.150, "F12": 0.183, "F18": 0.244}
    return {code: Coating(value, None,
                         f"アロイ（合金化溶融亜鉛）。両面の重量計算用定数。日本鉄鋼連盟公開資料 表30：{source}", True)
            for code, value in table.items()}


def _jis_g3313():
    # 記号: (等厚の定数 kg/m2【表25】, 片面の定数 kg/m2【表26】, 片面最小付着量 g/m2【表4・等厚】)
    table = {
        "EB": (0.006, None, 2.5), "E8": (0.018, 0.009, 8.5), "E16": (0.036, 0.018, 17),
        "E24": (0.054, 0.027, 25.5), "E32": (0.072, 0.036, 34), "E40": (0.090, 0.045, 42.5),
    }
    return {code: Coating(constant, side, f"電気亜鉛 JIS G 3313 表25（等厚）。片面最小付着量 {coating} g/m²", True)
            for code, (constant, side, coating) in table.items()}


def _zam():
    # 亜鉛・アルミニウム・マグネシウム合金めっきカタログの質量表。K系は溶融亜鉛めっき相当の表示、数字系は片面付着量 g/m2。
    alloy = {"K06": 0.090, "K08": 0.120, "K10": 0.150, "K12": 0.183, "K14": 0.203,
             "K18": 0.244, "K20": 0.285, "K22": 0.305, "K25": 0.350, "K27": 0.381, "K35": 0.458}
    numeric = {"ZAM45": 0.090, "ZAM60": 0.120, "ZAM90": 0.180, "ZAM100": 0.200,
               "ZAM120": 0.240, "ZAM150": 0.300, "ZAM190": 0.380}
    values = {code: Coating(constant, None, "溶融Zn-Al-Mg 亜鉛・アルミニウム・マグネシウム合金めっき カタログ質量表。付着量記号K系（溶融亜鉛めっき相当）", True)
              for code, constant in alloy.items()}
    values.update({code: Coating(constant, None,
                                 f"溶融Zn-Al-Mg 亜鉛・アルミニウム・マグネシウム合金めっき カタログ質量表。付着量記号 {code[3:]}（片面 g/m²）", True)
                   for code, constant in numeric.items()})
    return values


def default_master() -> dict[str, Coating]:
    values = _jis_g3302()
    values.update(_jis_g3313())
    values.update(_alloy())
    for label, jis in {"10/10":"E8", "20/20":"E16", "30/30":"E24", "40/40":"E32"}.items():
        entry = values[jis]
        values[label] = Coating(entry.constant_kg_m2, entry.per_side_kg_m2,
            f"電気亜鉛めっき：表/裏の標準付着量 {label} g/m²。対応JIS {jis}の重量計算用定数を適用（標準付着量の合計とは異なる）。出典 U016 p.4-5 https://www.nipponsteel.com/product/catalog_download/pdf/U016.pdf", True)
    values.update(_zam())
    return values


_MASTER: dict[str, Coating] = {}


def set_master(values: dict[str, Coating]) -> None:
    _MASTER.clear()
    _MASTER.update(values)


def master() -> dict[str, Coating]:
    return dict(_MASTER)


def normalize_spec(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return text.strip().upper().replace(" ", "")


def normalize_code(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().upper().replace(" ", "")


def _format(prefix: str, number: str | None, letter: str | None) -> str:
    if letter:
        return f"{prefix}{letter}"
    # Z系・F系・K系は2桁ゼロ詰め（Z8→Z08）。E系・AZ系はゼロ詰めしない（E8のまま）。
    return f"{prefix}{int(number):02d}" if prefix in ("Z", "F", "K") else f"{prefix}{int(number)}"


def coating_codes(spec: str) -> list[str]:
    """規格文字列から読み取れるめっき記号。異厚指定では2個返る。"""
    text = re.sub(r"ZAM(?=[A-Z0-9])", "ZAM-", normalize_spec(spec))
    pair = re.search(r"(?:^|[-_])P?(10/10|20/20|30/30|40/40)(?=$|[-_])", text)
    if pair:
        return [pair.group(1)]
    numeric = _ZAM_NUMERIC.search(text)
    if numeric:
        return [f"ZAM{int(numeric.group(1))}"]
    return [_format(m.group(1), m.group(2), m.group(3)) for m in _CODE_PATTERN.finditer(text)]


def coating_code(spec: str) -> str | None:
    codes = coating_codes(spec)
    return codes[0] if codes else None


def coating_detail(spec: str) -> tuple[str | None, Coating | None]:
    """表示・帳票用。めっき記号と登録内容。未登録はNone。異厚は先頭の記号を返す。"""
    code = coating_code(spec)
    return code, _MASTER.get(code) if code else None


def coating_mass(spec: str) -> tuple[float, str | None]:
    """めっき量定数(kg/m2)と警告。確定しない場合は0を返し、必ず警告を添える。"""
    codes = coating_codes(spec)
    if not codes:
        if _COATED_STEEL.match(normalize_spec(spec)):
            return 0.0, f"規格 {spec} はめっき鋼板ですが、めっき記号を読み取れません（例：SGCC-Z12）。めっき量定数を0として計算しています。"
        return 0.0, None
    missing = [code for code in codes if code not in _MASTER]
    if missing:
        return 0.0, f"規格 {spec} のめっき記号 {'・'.join(missing)} は目付マスタに未登録です。めっき量定数を0として計算しています。"
    if len(codes) == 1:
        entry = _MASTER[codes[0]]
        if not entry.confirmed:
            return entry.constant_kg_m2, f"めっき記号 {codes[0]} のめっき量定数 {entry.constant_kg_m2:g} kg/m² は未確認です。規格表で確認し、目付マスタで確認済みにしてください。"
        return entry.constant_kg_m2, None
    if len(codes) > 2:
        return 0.0, f"規格 {spec} からめっき記号を{len(codes)}個読み取りました。表裏2面ぶんに整理してください。めっき量定数を0として計算しています。"
    # 異厚めっき：片面ごとの定数の和（JIS G 3313 表26の考え方）。
    entries = [_MASTER[code] for code in codes]
    if any(entry.per_side_kg_m2 is None for entry in entries):
        return 0.0, f"規格 {spec} は表裏で付着量が異なりますが、{'・'.join(codes)} に片面あたりの定数が登録されていません。めっき量定数を0として計算しています。"
    total = sum(entry.per_side_kg_m2 for entry in entries)
    unconfirmed = [code for code, entry in zip(codes, entries) if not entry.confirmed]
    if unconfirmed:
        return total, f"めっき記号 {'・'.join(unconfirmed)} の定数は未確認です。規格表で確認してください。"
    return total, None


def unit_mass_kg_m2(spec: str, thickness_mm: float) -> tuple[float, str | None]:
    """めっき後の単位質量 ＝ 表示厚さ×7.85 ＋ めっき量定数。"""
    coating, warning = coating_mass(spec)
    return thickness_mm * STEEL_BASIC_MASS + coating, warning


def plate_weight_kg(
    spec: str, thickness_mm: float, width_mm: float, length_mm: float, quantity: int = 1
) -> tuple[float, str | None]:
    unit_mass, warning = unit_mass_kg_m2(spec, thickness_mm)
    area_m2 = width_mm * length_mm / 1_000_000
    return area_m2 * unit_mass * quantity, warning


set_master(default_master())
