import csv
import io
import json
import math
import os
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path


def number(text, positive=True):
    value=float(unicodedata.normalize("NFKC",str(text)).strip())
    if not math.isfinite(value) or (value<=0 if positive else value<0):
        raise ValueError("正の数値" if positive else "0以上の数値")
    return value


def validate_product(row, allow_blank=False):
    if not isinstance(row,dict) or not isinstance(row.get("values"),list) or len(row["values"])!=5:
        raise ValueError("製品の列構成が不正です")
    if not all(isinstance(v,str) for v in row["values"]) or not isinstance(row.get("qty"),str) or type(row.get("rotate")) is not bool:
        raise ValueError("製品データの型が不正です")
    name,spec,t,w,h=row["values"]
    q=number(row["qty"])
    if q!=int(q): raise ValueError("必要枚数は正の整数です")
    if allow_blank and not any((spec,t,w,h)):
        return
    number(w); number(h)
    if t: number(t)


def validate_project(data):
    if not isinstance(data,dict) or data.get("version")!=1:
        raise ValueError("対応していない案件形式です")
    for key in ("name","customer","notes"):
        if not isinstance(data.get(key),str): raise ValueError("案件情報が不正です")
    if not data["name"].strip(): raise ValueError("案件名を入力してください")
    settings=data.get("settings")
    if not isinstance(settings,list) or len(settings)!=5 or not all(isinstance(v,str) for v in settings):
        raise ValueError("大板条件が不正です")
    w,e,h,g,l=[number(v,positive=i in (0,2)) for i,v in enumerate(settings)]
    if w<=e or h<=2*l: raise ValueError("ロスを除く有効寸法が0以下です")
    if not isinstance(data.get("products"),list): raise ValueError("製品一覧が不正です")
    for row in data["products"]: validate_product(row,True)
    return data


def save_project(path,data):
    validate_project(data)
    payload=dict(data,saved_at=datetime.now().astimezone().isoformat())
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,delete=False,suffix=".tmp") as f:
            temp=Path(f.name)
            json.dump(payload,f,ensure_ascii=False,indent=2,allow_nan=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp and temp.exists(): temp.unlink()


def load_project(path):
    return validate_project(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def parse_paste(text):
    rows=[]; errors=[]; preview=[]
    reader=csv.reader(io.StringIO(text),delimiter="\t")
    first=True
    for fields in reader:
        line=reader.line_num
        if not any(v.strip() for v in fields): continue
        values=[unicodedata.normalize("NFKC",v).strip() for v in fields]
        if first and len(values)>=6 and values[3] in ("幅","幅(mm)","幅 mm") and values[4] in ("長さ","長さ(mm)","長さ mm"):
            first=False; continue
        first=False
        try:
            if len(values) not in (6,7): raise ValueError("7列（回転可否の省略時は6列）で貼り付けてください")
            if len(values)==6: values.append("")
            rotation=values[6].lower()
            if rotation not in ("","可","不可","true","false","1","0"):
                raise ValueError("回転可否は可/不可、TRUE/FALSE、1/0です")
            record={"values":values[:5],"qty":values[5],"rotate":rotation in ("","可","true","1")}
            validate_product(record)
            record["qty"]=str(int(number(values[5])))
            rows.append(record)
            preview.append((line,*values,"OK"))
        except ValueError as exc:
            errors.append(f"{line}行目：{exc}")
            preview.append((line,*(values+[""]*7)[:7],str(exc)))
    if not preview: errors.append("貼り付ける製品がありません")
    return rows,errors,preview
