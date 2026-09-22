"""めっき目付マスタ。EXE横のJSONで利用者が確認・編集できる。

質量計算に使うのは「めっき量定数(kg/m2)」。付着量(g/m2)は照合用の説明で、計算には使わない。
初期値はJIS G 3302（溶融亜鉛）・JIS G 3313（電気亜鉛）・亜鉛・アルミニウム・マグネシウム合金めっきカタログの質量表。
"""
import json
import math
import os
import tempfile
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .weight import CODE_FORMAT, Coating, default_master, normalize_code, set_master

VERSION = 5
NOTE = ("めっき後の単位質量(kg/m2) ＝ 表示厚さ(mm)×7.85 ＋ constant_kg_m2。"
        "constant_kg_m2は等厚（両面合計）のめっき量定数。"
        "per_side_kg_m2は表裏で付着量が異なる場合に片面ごとを合計するための値（任意）。"
        "noteは出典と付着量の説明で、計算には使わない。")


def _number(label, value, maximum, allow_blank=False):
    if allow_blank and value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}は数値で入力してください。") from None
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label}は0より大きい数値で入力してください。")
    if result > maximum:
        raise ValueError(f"{label} {result:g} は大きすぎます。単位を確認してください。")
    return result


def validate(code, constant_kg_m2, per_side_kg_m2, note, confirmed):
    """登録できる記号と値か検査し、正規化した組を返す。"""
    key = normalize_code(code)
    if not CODE_FORMAT.match(key):
        raise ValueError(f"めっき記号「{code}」は登録できません。Z12・E24・K27・ZAM120・AZ150 のような形式で入力してください。")
    constant = _number(f"{key} のめっき量定数(kg/m²)", constant_kg_m2, 5.0)
    per_side = _number(f"{key} の片面定数(kg/m²)", per_side_kg_m2, 5.0, allow_blank=True)
    if not isinstance(note, str):
        raise ValueError(f"{key} の備考は文字列で入力してください。")
    return key, Coating(constant, per_side, note.strip(), bool(confirmed))


class CoatingRegistry:
    def __init__(self, path):
        self.path = Path(path)
        self.upgraded = False
        self.values = self._read() if self.path.exists() else default_master()
        if self.upgraded:
            backup = self.path.with_name(self.path.name + datetime.now().strftime('.%Y%m%d_%H%M%S_%f.bak'))
            shutil.copy2(self.path, backup)
            self.save(self.values)
        set_master(self.values)

    def _read(self):
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or data.get("version") not in (3, 4, VERSION):
            raise ValueError("目付マスタの形式が古いか不正です。ファイルを削除すると初期値（JIS G 3302・G 3313・ZAM）で作り直します。")
        codes = data.get("codes")
        if not isinstance(codes, dict):
            raise ValueError("目付マスタの形式が不正です。")
        values = {}
        for code, entry in codes.items():
            if not isinstance(entry, dict):
                raise ValueError(f"{code} の内容が不正です。")
            key, value = validate(code, entry.get("constant_kg_m2"), entry.get("per_side_kg_m2"),
                                  entry.get("note", ""), entry.get("confirmed", False))
            note = value.note.replace("日鉄NSジンコート：", "電気亜鉛めっき：")
            note = note.replace("ZAM®", "亜鉛・アルミニウム・マグネシウム合金めっき").replace("ZAM(R)", "亜鉛・アルミニウム・マグネシウム合金めっき")
            if note != value.note:
                value = replace(value, note=note)
                self.upgraded = True
            values[key] = value
        if data.get("version") == 3:
            # 新しいE/Fの不足分のみ補完。利用者の登録・編集値は保持する。
            for code, entry in default_master().items():
                if code.startswith(("E", "F")):
                    values.setdefault(code, entry)
            self.upgraded = True
        if data.get("version") in (3, 4):
            for code, entry in default_master().items():
                if "/" in code:
                    values.setdefault(code, entry)
            self.upgraded = True
        return values

    def save(self, values):
        checked = dict(validate(code, entry.constant_kg_m2, entry.per_side_kg_m2, entry.note, entry.confirmed)
                       for code, entry in values.items())
        payload = {"version": VERSION, "note": NOTE,
                   "codes": {code: {"constant_kg_m2": entry.constant_kg_m2,
                                    "per_side_kg_m2": entry.per_side_kg_m2,
                                    "note": entry.note,
                                    "confirmed": entry.confirmed}
                             for code, entry in sorted(checked.items())}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                             delete=False, suffix=".tmp") as stream:
                temp = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if temp is not None and temp.exists():
                temp.unlink()
        self.values = checked
        set_master(checked)
