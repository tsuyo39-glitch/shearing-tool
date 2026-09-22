"""Persistent product presets stored beside the portable executable."""
import math
import sqlite3
from pathlib import Path


class ProductRegistry:
    def __init__(self, path):
        self.path=Path(path)

    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        connection=sqlite3.connect(self.path)
        connection.execute("CREATE TABLE IF NOT EXISTS products (name TEXT PRIMARY KEY, spec TEXT, thickness TEXT, width TEXT, length TEXT, qty INTEGER, rotation INTEGER)")
        if "coating" not in [r[1] for r in connection.execute("PRAGMA table_info(products)")]:
            connection.execute("ALTER TABLE products ADD COLUMN coating TEXT")
            connection.commit()
        return connection

    def list(self):
        connection=self.connect()
        try:
            return connection.execute("SELECT name,spec,thickness,width,length,qty,rotation,coating FROM products ORDER BY name").fetchall()
        finally:
            connection.close()

    def save(self, values, quantity, rotation, coating=None):
        name,spec,thickness,width,length=[str(v).strip() for v in values]
        if not name:
            raise ValueError("登録する製品名を入力してください。")
        for value in [width,length]+([thickness] if thickness else []):
            if not math.isfinite(float(value)) or float(value)<=0:
                raise ValueError("寸法・板厚は正の数値で入力してください。")
        qty=int(quantity)
        if qty<=0 or qty>20000:
            raise ValueError("必要枚数は1～20,000の整数で入力してください。")
        connection=self.connect()
        try:
            with connection:
                connection.execute("INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?)",
                                   (name,spec,thickness,width,length,qty,int(rotation),coating))
        finally:
            connection.close()

    def delete(self,name):
        connection=self.connect()
        try:
            with connection:
                connection.execute("DELETE FROM products WHERE name=?",(name,))
        finally:
            connection.close()
