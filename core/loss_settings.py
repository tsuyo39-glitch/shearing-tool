import json
import math
from pathlib import Path


class LossSettings:
    def __init__(self,path):
        self.path=Path(path)
        self.values={"width":10.0,"length":0.0,"gap":0.0,"round":0.0,"time":10.0}
        if self.path.exists():
            data=json.loads(self.path.read_text(encoding="utf-8"))
            for key in self.values:
                value=float(data.get(key,self.values[key]))
                if math.isfinite(value) and value>=0:
                    self.values[key]=value

    def save(self,key,text):
        try:
            value=float(text)
        except ValueError:
            return
        if not math.isfinite(value) or value<0:
            return
        values=dict(self.values,**{key:value})
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(values,ensure_ascii=False),encoding="utf-8")
        temp.replace(self.path)
        self.values=values
