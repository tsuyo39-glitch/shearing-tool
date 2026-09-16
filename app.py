from __future__ import annotations

import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.exporter import default_output_path, export_result
from core.models import OptimizationResult, ProductSpec, SheetType
from core.optimizer import group_sheet_plans, optimize, validate_layout
from core.weight import normalize_spec


APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


class ScrollRows(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, height=145, highlightthickness=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))


class ShearingApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("シャーリング取り合わせツール")
        self.root.geometry("1500x900")
        self.root.minsize(1120, 720)
        self.product_rows: list[dict] = []
        self.sheet_rows: list[dict] = []
        self.results: list[OptimizationResult] = []
        self.current_products: list[ProductSpec] = []
        self.current_sheets: list[SheetType] = []
        self.cancel_event = threading.Event()
        self._build()
        for _ in range(1):
            self.add_sheet_row()
        self.add_product_row()

    def _build(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Yu Gothic UI", 18, "bold"), foreground="#1F4E78")
        style.configure("Section.TLabelframe.Label", font=("Yu Gothic UI", 11, "bold"))

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="シャーリング取り合わせツール", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text="大板の公称寸法で配置・90度回転可・必要枚数入力。加工可否は設備条件を確認してください。", foreground="#9C5700").pack(anchor="w", pady=(0, 8))

        sheet_box = ttk.LabelFrame(main, text="1. 大板種類（初期1行・任意追加）", style="Section.TLabelframe", padding=6)
        sheet_box.pack(fill="x", pady=6)
        headers = ["名称", "規格", "板厚", "幅", "長さ", "枚数", "四辺ロス(参考)", "切断代", ""]
        for col, text in enumerate(headers):
            ttk.Label(sheet_box, text=text, anchor="center").grid(row=0, column=col, sticky="ew", padx=2)
        self.sheet_container = ttk.Frame(sheet_box)
        self.sheet_container.grid(row=1, column=0, columnspan=len(headers), sticky="ew")
        ttk.Button(sheet_box, text="＋ 大板を追加", command=self.add_sheet_row).grid(row=2, column=0, sticky="w", pady=(5, 0))
        ttk.Label(sheet_box, text="※枚数が空欄の場合、製品の必要枚数から必要大板枚数を計算します。", foreground="#595959").grid(
            row=2, column=1, columnspan=6, sticky="w", padx=(8, 0), pady=(5, 0)
        )

        product_box = ttk.LabelFrame(main, text="2. 製品サイズ（手入力・初期1行・任意追加）", style="Section.TLabelframe", padding=6)
        product_box.pack(fill="x", pady=6)
        product_headers = ttk.Frame(product_box)
        product_headers.pack(fill="x")
        for text, width in [
            ("製品名", 14), ("規格", 21), ("板厚(mm)", 10), ("幅(mm)", 11),
            ("長さ(mm)", 11), ("必要枚数", 10), ("", 13), ("", 7),
        ]:
            ttk.Label(product_headers, text=text, width=width, anchor="center").pack(side="left", padx=2)
        self.product_scroll = ScrollRows(product_box)
        self.product_scroll.pack(fill="x")
        ttk.Button(product_box, text="＋ 製品を追加", command=self.add_product_row).pack(anchor="w", pady=(5, 0))

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=4)
        ttk.Label(actions, text="最大計算時間(秒):").pack(side="left")
        self.time_var = tk.StringVar(value="10")
        ttk.Entry(actions, textvariable=self.time_var, width=7).pack(side="left", padx=4)
        self.calc_button = ttk.Button(actions, text="取り合わせ計算", command=self.start_calculation)
        self.calc_button.pack(side="left", padx=5)
        self.cancel_button = ttk.Button(actions, text="中止", command=self.cancel_calculation, state="disabled")
        self.cancel_button.pack(side="left")
        self.export_button = ttk.Button(actions, text="Excel出力", command=self.export_excel, state="disabled")
        self.export_button.pack(side="left", padx=5)
        self.status_var = tk.StringVar(value="待機中")
        ttk.Label(actions, textvariable=self.status_var).pack(side="left", padx=12)

        result_pane = ttk.Panedwindow(main, orient="horizontal")
        result_pane.pack(fill="both", expand=True, pady=(4, 0))
        left = ttk.LabelFrame(result_pane, text="3. 候補一覧", padding=5)
        right = ttk.LabelFrame(result_pane, text="4. 配置図", padding=5)
        result_pane.add(left, weight=5)
        result_pane.add(right, weight=7)
        cols = ("rank", "state", "sheet_names", "sheets", "breakdown", "yield", "loss", "weight")
        self.result_tree = ttk.Treeview(left, columns=cols, show="headings", height=10)
        for key, label, width in [
            ("rank", "順位", 45), ("state", "状態", 80), ("sheet_names", "大板名称", 90),
            ("sheets", "合計枚数", 70),
            ("breakdown", "大板別必要枚数", 190),
            ("yield", "歩留り", 75), ("loss", "歩損", 75), ("weight", "端材kg", 80),
        ]:
            self.result_tree.heading(key, text=label)
            self.result_tree.column(key, width=width, anchor="center")
        self.result_tree.pack(fill="both", expand=True)
        self.result_tree.bind("<<TreeviewSelect>>", self.show_selected)
        canvas_frame = ttk.Frame(right)
        canvas_frame.pack(fill="both", expand=True)
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=1, highlightbackground="#A6A6A6")
        self.canvas_vscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas_hscroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.canvas_vscroll.set, xscrollcommand=self.canvas_hscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas_vscroll.grid(row=0, column=1, sticky="ns")
        self.canvas_hscroll.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<MouseWheel>", self._scroll_canvas_vertical)
        self.canvas.bind("<Shift-MouseWheel>", self._scroll_canvas_horizontal)

    def add_sheet_row(self):
        index = len(self.sheet_rows) + 1
        row = ttk.Frame(self.sheet_container)
        row.pack(fill="x", pady=2)
        defaults = [f"大板{index}", "", "", "", "", "", "10", "0"]
        widths = [12, 20, 8, 10, 10, 10, 10, 9]
        vars_ = []
        for value, width in zip(defaults, widths):
            var = tk.StringVar(value=value)
            ttk.Entry(row, textvariable=var, width=width).pack(side="left", padx=2)
            vars_.append(var)
        data = {"frame": row, "vars": vars_}
        ttk.Button(row, text="削除", command=lambda: self.remove_sheet_row(data)).pack(side="left", padx=2)
        self.sheet_rows.append(data)

    def remove_sheet_row(self, data):
        data["frame"].destroy()
        self.sheet_rows.remove(data)

    def add_product_row(self):
        frame = ttk.Frame(self.product_scroll.inner)
        frame.pack(fill="x", pady=2)
        defaults = [f"製品{len(self.product_rows) + 1}", "", "", "", ""]
        widths = [14, 21, 10, 11, 11]
        vars_ = []
        for value, width in zip(defaults, widths):
            var = tk.StringVar(value=value)
            ttk.Entry(frame, textvariable=var, width=width).pack(side="left", padx=2)
            vars_.append(var)
        qty = tk.StringVar(value="1")
        ttk.Spinbox(frame, from_=1, to=99999, textvariable=qty, width=8).pack(side="left", padx=2)
        rotate = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="90度回転可", variable=rotate).pack(side="left", padx=5)
        data = {"frame": frame, "vars": vars_, "qty": qty, "rotate": rotate}
        ttk.Button(frame, text="削除", command=lambda: self.remove_product_row(data)).pack(side="left")
        self.product_rows.append(data)

    def remove_product_row(self, data):
        data["frame"].destroy()
        self.product_rows.remove(data)

    def _read_inputs(self):
        products: list[ProductSpec] = []
        for index, row in enumerate(self.product_rows, 1):
            name, spec, thick, width, length = [var.get().strip() for var in row["vars"]]
            if not any((width, length)):
                continue
            if not all((width, length)):
                raise ValueError(f"製品{index}の幅・長さをすべて入力してください。")
            products.append(ProductSpec(
                id=f"P{index}", name=name or f"製品{index}", spec=normalize_spec(spec),
                thickness=float(thick) if thick else None, width=float(width), length=float(length),
                required_qty=int(row["qty"].get()), rotation_allowed=row["rotate"].get(),
            ))
        if not products:
            raise ValueError("製品サイズを1種類以上入力してください。")

        product_specs = {product.spec for product in products}
        product_thicknesses = {product.thickness for product in products if product.thickness is not None}
        sheets: list[SheetType] = []
        for index, row in enumerate(self.sheet_rows, 1):
            name, spec, thick, width, length, quantity, edge, cut = [var.get().strip() for var in row["vars"]]
            if not any((spec, thick, width, length, quantity)):
                continue
            sheet_name = name or f"大板{index}"
            if not all((width, length)):
                raise ValueError(f"{sheet_name}の幅・長さをすべて入力してください。")
            if thick:
                sheet_thickness = float(thick)
            elif len(product_thicknesses) == 1:
                sheet_thickness = next(iter(product_thicknesses))
            else:
                sheet_thickness = None
            if spec:
                sheet_spec = normalize_spec(spec)
            elif len(product_specs) == 1:
                sheet_spec = next(iter(product_specs))
            else:
                raise ValueError(f"{sheet_name}の規格を入力してください。製品が複数規格のため自動判定できません。")
            sheets.append(SheetType(
                id=f"S{index}", name=sheet_name, spec=sheet_spec,
                thickness=sheet_thickness, width=float(width), length=float(length),
                max_sheets=int(quantity) if quantity else None,
                edge_loss=float(edge), cut_allowance=float(cut),
            ))
        return products, sheets

    def start_calculation(self):
        try:
            products, sheets = self._read_inputs()
            limit = float(self.time_var.get())
        except Exception as exc:
            messagebox.showerror("入力エラー", f"数値入力を確認してください。\n{exc}")
            return
        self.current_products, self.current_sheets = products, sheets
        self.cancel_event = threading.Event()
        self.calc_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.export_button.config(state="disabled")
        self.status_var.set("計算中…")
        threading.Thread(target=self._calculate, args=(products, sheets, limit), daemon=True).start()

    def _calculate(self, products, sheets, limit):
        try:
            results = optimize(products, sheets, limit, self.cancel_event)
            self.root.after(0, lambda: self._calculation_done(results, None))
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self._calculation_done([], exc))

    def cancel_calculation(self):
        self.cancel_event.set()
        self.status_var.set("中止処理中…")

    def _calculation_done(self, results, error):
        self.calc_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        if error:
            self.status_var.set("入力エラー")
            messagebox.showerror("計算エラー", str(error))
            return
        self.results = results
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        for index, result in enumerate(results, 1):
            state = "全数充足" if result.complete else "不足あり"
            if result.timed_out:
                state += "※"
            self.result_tree.insert("", "end", iid=str(index - 1), values=(
                index, state, self._sheet_name_text(result), len(result.sheets),
                self._sheet_count_text(result), f"{result.yield_rate:.2f}%",
                f"{result.loss_rate:.2f}%", f"{result.scrap_weight:,.1f}",
            ))
        if results:
            self.result_tree.selection_set("0")
            self.show_result(results[0])
            self.export_button.config(state="normal")
            self.status_var.set("暫定最良解" if results[0].timed_out else "計算完了")
        else:
            self.status_var.set("候補なし")

    def show_selected(self, _event=None):
        selected = self.result_tree.selection()
        if selected:
            self.show_result(self.results[int(selected[0])])

    def _sheet_count_text(self, result: OptimizationResult) -> str:
        counts = {sheet.id: 0 for sheet in self.current_sheets}
        for plan in result.sheets:
            counts[plan.sheet_type.id] = counts.get(plan.sheet_type.id, 0) + 1
        return " / ".join(
            f"{sheet.name}-{counts.get(sheet.id, 0)}枚" for sheet in self.current_sheets
        )

    def _sheet_name_text(self, result: OptimizationResult) -> str:
        used_ids = {plan.sheet_type.id for plan in result.sheets}
        if not used_ids:
            used_ids = set(result.candidate_sheet_ids)
        names = [sheet.name for sheet in self.current_sheets if sheet.id in used_ids]
        return "＋".join(names) if names else "配置不可"

    def show_result(self, result: OptimizationResult):
        self.canvas.delete("all")
        width = max(600, self.canvas.winfo_width())
        # 上部の集計タイトル・操作説明と、各パターン見出しが重ならないよう
        # 配置図の開始位置を固定で十分に下げる。
        x_cursor, y_cursor = 20, 110
        max_h = 0
        colors = ["#BDD7EE", "#C6E0B4", "#FFE699", "#F4B084", "#D9E1F2", "#E4DFEC"]
        product_ids = sorted({p.product_id for s in result.sheets for p in s.placements})
        color_map = {pid: colors[i % len(colors)] for i, pid in enumerate(product_ids)}
        grouped = group_sheet_plans(result.sheets)
        self.canvas.create_text(
            12, 12, anchor="nw",
            text=f"大板 {len(result.sheets)}枚 / 配置 {len(grouped)}パターン / 歩留り {result.yield_rate:.2f}% / 歩損 {result.loss_rate:.2f}%",
            font=("Yu Gothic UI", 10, "bold"),
        )
        self.canvas.create_text(
            12, 37, anchor="nw",
            text="同じ配置はまとめて表示しています。縦横スクロールバーまたはマウスホイールで移動できます。",
            fill="#595959", font=("Yu Gothic UI", 9),
        )
        for pattern_no, (plan, pattern_count, sheet_numbers) in enumerate(grouped, 1):
            scale = min(360 / plan.sheet_type.width, 250 / plan.sheet_type.length)
            draw_w, draw_h = plan.sheet_type.width * scale, plan.sheet_type.length * scale
            if x_cursor + draw_w > width - 20:
                x_cursor = 20
                y_cursor += max_h + 45
                max_h = 0
            if pattern_count == 1:
                count_text = f"使用板 #{sheet_numbers[0]}"
            else:
                count_text = f"同一配置 × {pattern_count}枚"
            self.canvas.create_text(
                x_cursor, y_cursor - 24, anchor="nw",
                text=f"パターン{pattern_no}｜{plan.sheet_type.name}｜{count_text}",
                font=("Yu Gothic UI", 9, "bold"),
            )
            self.canvas.create_rectangle(x_cursor, y_cursor, x_cursor + draw_w, y_cursor + draw_h, outline="#1F1F1F", width=2, fill="#F2F2F2")
            for placement in plan.placements:
                x1 = x_cursor + placement.x * scale
                y1 = y_cursor + placement.y * scale
                x2 = x1 + placement.width * scale
                y2 = y1 + placement.length * scale
                self.canvas.create_rectangle(x1, y1, x2, y2, outline="#5B5B5B", fill=color_map[placement.product_id])
                self.canvas.create_text((x1+x2)/2, (y1+y2)/2, text=placement.product_id, font=("Yu Gothic UI", 9, "bold"))
            x_cursor += draw_w + 25
            max_h = max(max_h, draw_h)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _scroll_canvas_vertical(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _scroll_canvas_horizontal(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def export_excel(self):
        selected = self.result_tree.selection()
        if not selected:
            return
        result = self.results[int(selected[0])]
        layout_errors = validate_layout(result)
        if layout_errors:
            messagebox.showerror("配置検証エラー", "\n".join(layout_errors[:10]))
            return
        default = default_output_path(APP_DIR)
        path = filedialog.asksaveasfilename(
            initialdir=str(default.parent), initialfile=default.name,
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        try:
            output = export_result(path, result, self.current_products, self.current_sheets)
            messagebox.showinfo("出力完了", f"保存しました。\n{output}")
        except Exception as exc:
            messagebox.showerror("出力エラー", str(exc))


def main():
    root = tk.Tk()
    ShearingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
