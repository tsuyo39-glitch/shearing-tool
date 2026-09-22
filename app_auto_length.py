from collections import Counter
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk, messagebox, filedialog

from app import ShearingApp, ScrollRows, APP_DIR
from core.auto_exporter import export_auto
from datetime import datetime
from core.models import ProductSpec
from core.auto_length import optimize_auto
from core.optimizer import group_sheet_plans
from core.weight import coating_detail, normalize_spec, coating_codes, master
from core.product_registry import ProductRegistry
from core.coating_registry import CoatingRegistry, validate as validate_coating
from dataclasses import replace as replace_coating
from core.loss_settings import LossSettings
from project_workflow import ProjectWorkflow


class AutoLengthApp(ProjectWorkflow, ShearingApp):
    def __init__(self, root):
        self.root = root
        self.data_dir=APP_DIR
        self.init_workflow()
        root.title("シャーリング取り合わせツール")
        root.geometry("1500x940")
        root.minsize(1100, 750)
        root.resizable(True, True)
        self.product_rows, self.sheet_rows, self.results = [], [], []
        self.current_products, self.current_sheets = [], []
        self.cancel_event = threading.Event()
        self.registry = ProductRegistry(APP_DIR / "登録データ" / "製品登録.sqlite3")
        try:
            self.loss_store=LossSettings(APP_DIR / "登録データ" / "ロス設定.json")
        except Exception as exc:
            messagebox.showerror("ロス設定読込エラー",str(exc))
            self.loss_store=None
        try:
            self.coating=CoatingRegistry(APP_DIR / "登録データ" / "目付マスタ.json")
        except Exception as exc:
            messagebox.showerror("目付マスタ読込エラー","JIS G 3302 Z系の初期値で起動します。 / "+str(exc))
            self.coating=None
        self._build_auto()
        self.add_product_row()
        self.finish_workflow()

    def _build_auto(self):
        for name in ("TkDefaultFont", "TkTextFont"):
            tkfont.nametofont(name).configure(family="Yu Gothic UI", size=10)
        style = ttk.Style()
        style.theme_use("clam")
        self.root.configure(background="#F7F8FA")
        style.configure(".", background="#FFFFFF", foreground="#243247", font=("Yu Gothic UI",10))
        style.configure("TFrame", background="#FFFFFF")
        style.configure("TLabel", background="#FFFFFF", foreground="#475569", font=("Yu Gothic UI", 10))
        style.configure("TLabelframe", background="#FFFFFF", bordercolor="#E2E6EC", relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background="#FFFFFF", foreground="#2563EB", font=("Yu Gothic UI",10,"bold"))
        style.configure("TEntry", fieldbackground="#FFFFFF", foreground="#172033", bordercolor="#D4DAE3", lightcolor="#FFFFFF", darkcolor="#FFFFFF", padding=4)
        style.map("TEntry", bordercolor=[("focus","#2563EB")])
        style.configure("TSpinbox", fieldbackground="#FFFFFF", bordercolor="#D4DAE3", arrowsize=12, padding=4)
        style.configure("TButton", background="#FFFFFF", foreground="#334155", bordercolor="#D4DAE3", lightcolor="#FFFFFF", darkcolor="#FFFFFF", padding=(10,6))
        style.map("TButton", background=[("disabled","#F3F4F6"),("pressed","#DBEAFE"),("active","#EFF6FF")], foreground=[("disabled","#9CA3AF")], bordercolor=[("active","#93B4F4")])
        style.configure("TCheckbutton", background="#FFFFFF", foreground="#475569")
        style.map("TCheckbutton", background=[("active","#EFF6FF")], indicatorbackground=[("selected","#2563EB"),("!selected","#FFFFFF")])
        style.configure("Treeview", rowheight=34, background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#243247", bordercolor="#E2E6EC")
        style.configure("Treeview.Heading", background="#F7F8FA", foreground="#475569", relief="flat", padding=(8,8))
        style.map("Treeview", background=[("selected","#E8F0FE")], foreground=[("selected","#1D4ED8")])
        style.configure("TScrollbar", background="#D4DAE3", troughcolor="#F7F8FA", bordercolor="#F7F8FA", arrowsize=12)
        style.configure("TScale", background="#FFFFFF", troughcolor="#E8EDF5", bordercolor="#E8EDF5")
        style.configure("TPanedwindow", background="#F7F8FA")
        style.configure("Page.TFrame", background="#E8EEF5")
        style.configure("Page.TLabel", background="#E8EEF5", foreground="#52657D")
        style.configure("Banner.TFrame", background="#173655")
        style.configure("Banner.TLabel", background="#173655", foreground="#FFFFFF", font=("Yu Gothic UI",22,"bold"))
        style.configure("BannerSub.TLabel", background="#173655", foreground="#C8DAEE")
        style.configure("TLabelframe", background="#F1F5FA", bordercolor="#B7C8DC", borderwidth=1)
        style.configure("TLabelframe.Label", background="#E8EEF5", foreground="#174B7D", font=("Yu Gothic UI",11,"bold"))
        style.configure("TLabel", background="#F1F5FA")
        style.configure("TFrame", background="#F1F5FA")
        style.configure("TCheckbutton", background="#F1F5FA")
        style.configure("TButton", background="#E2ECF8", bordercolor="#AFC3DC", foreground="#234D78")
        style.configure("Treeview.Heading", background="#244A70", foreground="#FFFFFF", font=("Yu Gothic UI",10,"bold"))
        style.map("Treeview.Heading", background=[("active","#315F8B")], foreground=[("active","#FFFFFF")])
        style.configure("Export.TButton", background="#137E82", foreground="#FFFFFF", padding=(12,8))
        style.map("Export.TButton", background=[("disabled","#DCE5ED"),("active","#16999D")], foreground=[("disabled","#8294A6"),("!disabled","#FFFFFF")])
        style.configure("Calculate.TButton", background="#2563EB", foreground="white",
                        font=("Yu Gothic UI", 10, "bold"), padding=(14, 8))
        style.map("Calculate.TButton",
                  background=[("disabled", "#CBD5E1"), ("pressed", "#1E40AF"), ("active", "#3B82F6")],
                  foreground=[("disabled", "#475569"), ("!disabled", "white")])
        main = ttk.Frame(self.root, padding=16, style="Page.TFrame")
        main.pack(fill="both", expand=True)
        banner=ttk.Frame(main,style="Banner.TFrame",padding=(16,6))
        banner.pack(fill="x",pady=(0,8))
        ttk.Label(banner, text="シャーリング取り合わせツール", style="Banner.TLabel").pack(anchor="w")
        ttk.Label(banner, text="製品サイズと必要枚数から、大板の長さ・枚数を算出します。寸法の単位：mm",style="BannerSub.TLabel").pack(anchor="w")
        buttons=ttk.Frame(banner,style="Banner.TFrame")
        buttons.place(relx=1,rely=0,anchor="ne")
        ttk.Button(buttons,text="案件を保存",command=self.save_project_dialog).pack(side="left",padx=4)
        ttk.Button(buttons,text="案件を開く",command=self.open_project_dialog).pack(side="left")
        ttk.Button(buttons,text="情報編集",command=self.project_metadata).pack(side="left",padx=4)
        settings = ttk.LabelFrame(main, text="1  大板の条件", padding=10)
        settings.pack(fill="x", pady=10)
        # 最小幅1100pxでも見切れないよう、寸法とロスを2段に分ける。
        sizes = ttk.Frame(settings)
        sizes.pack(fill="x")
        losses = ttk.Frame(settings)
        losses.pack(fill="x", pady=(8, 0))
        self.settings = []
        for label, value in [("大板幅", "1219"), ("幅ロス", "10"), ("最大大板長さ", "1219"), ("製品間切断代", "0")]:
            ttk.Label(sizes, text=label).pack(side="left", padx=(0, 6))
            var = tk.StringVar(value=value)
            ttk.Entry(sizes, textvariable=var, width=9).pack(side="left", padx=(0, 4))
            ttk.Label(sizes, text="mm").pack(side="left", padx=(0, 18))
            self.settings.append(var)
        self.length_loss_var=tk.StringVar(value="0")
        self.length_round_var=tk.StringVar(value="0")
        for label,var in [("長さロス（前後各）",self.length_loss_var),("長さ丸め",self.length_round_var)]:
            ttk.Label(losses,text=label).pack(side="left",padx=(0,6))
            ttk.Entry(losses,textvariable=var,width=9).pack(side="left",padx=(0,4))
            ttk.Label(losses,text="mm").pack(side="left",padx=(0,18))
        for key,var in [("width",self.settings[1]),("length",self.length_loss_var),("gap",self.settings[3]),("round",self.length_round_var)]:
            if self.loss_store:
                var.set(f"{self.loss_store.values[key]:g}")
            var.trace_add("write",lambda *_args,k=key,v=var:self.save_loss(k,v))
        ttk.Label(main, text="幅ロスは片側のみ、長さロスは前後各辺に適用します。長さ丸めは算出長さをその倍数へ切り上げます（0で丸めなし）。各設定は入力すると保存されます。", foreground="#536779").pack(anchor="w")
        ttk.Label(main, text="製品欄と結果欄の間の青い境界を上下にドラッグすると、表示の高さを変更できます。", foreground="#234D78").pack(anchor="w", pady=(4, 0))
        self.workspace_split = tk.PanedWindow(main, orient="vertical", sashwidth=10,
                    sashrelief="raised", showhandle=True, handlesize=8,
                    background="#AFC3DC", borderwidth=0, opaqueresize=True)
        self.workspace_split.pack(fill="both", expand=True, pady=(6, 0))
        box = ttk.LabelFrame(self.workspace_split, text="2  必要な製品", padding=8)
        self.workspace_split.add(box, minsize=170, height=200, stretch="never")
        headers = ttk.Frame(box)
        headers.pack(fill="x")
        self.product_headers=[]
        for text, width in [("製品名",14),("規格（任意）",21),("目付（めっき）",14),("板厚（任意）",10),("幅 mm",11),("長さ mm",11),("必要枚数",10)]:
            cell=ttk.Frame(headers,width=width*8,height=24)
            cell.pack(side="left",padx=2)
            cell.pack_propagate(False)
            ttk.Label(cell,text=text).pack(anchor="w")
            self.product_headers.append(cell)
        self.product_scroll = ScrollRows(box)
        self.product_scroll.canvas.configure(background="#FFFFFF",height=110)
        product_actions=ttk.Frame(box)
        product_actions.pack(side="bottom", fill="x", pady=(4, 0))
        self.product_scroll.pack(fill="both", expand=True)
        ttk.Button(product_actions,text="＋ 製品追加",command=self.add_product_row).pack(side="left")
        ttk.Button(product_actions,text="登録製品から追加・管理",command=self.open_registry).pack(side="left",padx=8)
        ttk.Button(product_actions,text="めっき目付マスタ",command=self.open_coating_master).pack(side="left",padx=4)
        ttk.Label(product_actions,text="各行の「登録」で保存できます。",foreground="#536779").pack(side="left")
        result_area = ttk.Frame(self.workspace_split, style="Page.TFrame")
        self.workspace_split.add(result_area, minsize=300, height=380, stretch="always")
        actions = ttk.Frame(result_area,style="Page.TFrame")
        actions.pack(fill="x",pady=8)
        ttk.Label(actions,text="計算時間",style="Page.TLabel").pack(side="left",padx=(0,4))
        self.time_var=tk.StringVar(value="10")
        ttk.Entry(actions,textvariable=self.time_var,width=5).pack(side="left")
        ttk.Label(actions,text="秒",style="Page.TLabel").pack(side="left",padx=(3,12))
        if self.loss_store:
            self.time_var.set(f"{self.loss_store.values['time']:g}")
        self.time_var.trace_add("write",lambda *_args:self.save_loss("time",self.time_var))
        self.calc_button=ttk.Button(actions,text="長さ・枚数を計算",command=self.start_calculation,style="Calculate.TButton")
        self.calc_button.pack(side="left")
        self.cancel_button=ttk.Button(actions,text="中止",command=self.cancel_calculation,state="disabled")
        self.cancel_button.pack(side="left",padx=6)
        self.export_button=ttk.Button(actions,text="Excel出力（図解付き）",command=self.export_excel,state="disabled",style="Export.TButton")
        self.export_button.pack(side="left",padx=6)
        self.status_var=tk.StringVar(value="製品を入力してください")
        ttk.Label(actions,textvariable=self.status_var).pack(side="left",padx=10)
        ttk.Label(result_area,text="必要数量を満たし、使用する大板の合計面積が少ない順に表示",foreground="#536779").pack(anchor="w")
        pane=ttk.Panedwindow(result_area,orient="horizontal")
        pane.pack(fill="both",expand=True,pady=6)
        left=ttk.LabelFrame(pane,text="3  計算候補・製品別数量",padding=8)
        right=ttk.LabelFrame(pane,text="4  取り合わせ図",padding=8)
        pane.add(left,weight=4)
        pane.add(right,weight=6)
        self.sheet_total_var=tk.StringVar(value="必要大板：未計算")
        ttk.Label(left,textvariable=self.sheet_total_var,font=("Yu Gothic UI",18,"bold"),foreground="#174B7D").pack(anchor="w",pady=(0,8))
        candidates=ttk.Frame(left)
        candidates.pack(fill="x")
        self.result_tree=ttk.Treeview(candidates,columns=("state","qty","yield","scrap"),show="headings",height=2)
        for key,label,width in [("state","候補",130),("qty","大板枚数",85),("yield","歩留り",85),("scrap","端材kg",90)]:
            self.result_tree.heading(key,text=label)
            self.result_tree.column(key,width=width,anchor="center")
        candidate_scroll=ttk.Scrollbar(candidates,orient="vertical",command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=candidate_scroll.set)
        candidate_scroll.pack(side="right",fill="y")
        self.result_tree.pack(side="left",fill="x",expand=True)
        self.result_tree.bind("<<TreeviewSelect>>",self.show_selected)
        details=ttk.Frame(left)
        details.pack(fill="both",expand=True,pady=(10,0))
        self.detail=tk.Text(details,wrap="word",font=("Yu Gothic UI",12),width=35,height=10,state="disabled",bg="#F7F8FA",fg="#243247",relief="flat",padx=12,pady=10)
        detail_scroll=ttk.Scrollbar(details,orient="vertical",command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side="right",fill="y")
        self.detail.pack(side="left",fill="both",expand=True)
        self.zoom=tk.DoubleVar(value=1)
        toolbar=ttk.Frame(right)
        toolbar.pack(fill="x")
        ttk.Label(toolbar,text="図の拡大").pack(side="left")
        ttk.Scale(toolbar,from_=0.6,to=2.5,variable=self.zoom,command=lambda _:self.show_selected()).pack(side="left",fill="x",expand=True)
        ttk.Label(right,text="色＝製品 ／ 灰色＝端材 ／ 斜線＝外周ロス。製品をクリックすると寸法表示。",font=("Yu Gothic UI",9)).pack(anchor="w")
        frame=ttk.Frame(right)
        frame.pack(fill="both",expand=True)
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(frame,bg="white",highlightthickness=0)
        self.canvas.grid(row=0,column=0,sticky="nsew")
        vs=ttk.Scrollbar(frame,orient="vertical",command=self.canvas.yview)
        hs=ttk.Scrollbar(frame,orient="horizontal",command=self.canvas.xview)
        vs.grid(row=0,column=1,sticky="ns")
        hs.grid(row=1,column=0,sticky="ew")
        self.canvas.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
        self.canvas.bind("<MouseWheel>",self._scroll_canvas_vertical)
        self.canvas.bind("<Shift-MouseWheel>",self._scroll_canvas_horizontal)

    def add_product_row(self):
        super().add_product_row()
        row=self.product_rows[-1]
        row["coating"]=tk.StringVar(value="なし")
        row["coating_combo"]=ttk.Combobox(row["frame"],textvariable=row["coating"],
            values=self.coating_choices(),state="readonly",width=12)
        row["coating_combo"].pack(side="left",padx=2,before=row["frame"].winfo_children()[2])
        for header,widget in zip(self.product_headers,row["frame"].pack_slaves()[:7]):
            header.configure(width=widget.winfo_reqwidth())
        for var in row["vars"]+[row["qty"],row["rotate"],row["coating"]]:
            var.trace_add("write",self.inputs_changed)
        self.inputs_changed()
        ttk.Button(row["frame"],text="登録",command=lambda:self.register_product(row)).pack(side="left",padx=4)

    def coating_choices(self):
        return ["なし"]+sorted(master())

    def restore_coating(self,row,value,spec):
        if value is None:
            value="/".join(coating_codes(spec)) or "なし"
        row["coating"].set(value or "なし")
        row["coating_combo"].configure(values=list(dict.fromkeys(self.coating_choices()+[row["coating"].get()])))

    def remove_product_row(self,row):
        super().remove_product_row(row)
        self.inputs_changed()

    def register_product(self,row):
        try:
            values=[v.get().strip() for v in row["vars"]]
            if any(p[0]==values[0] for p in self.registry.list()):
                if not messagebox.askyesno("登録内容の更新",f"「{values[0]}」は登録済みです。内容を更新しますか？"):
                    return
            self.registry.save(values,row["qty"].get(),row["rotate"].get(),row["coating"].get())
            self.status_var.set(f"登録しました：{values[0]}")
        except Exception as exc:
            messagebox.showerror("製品登録エラー",str(exc))

    def open_registry(self):
        try:
            records=self.registry.list()
        except Exception as exc:
            messagebox.showerror("登録データ読込エラー",str(exc))
            return
        window=tk.Toplevel(self.root)
        window.title("登録製品 — 選択して入力欄へ追加")
        window.geometry("960x500")
        window.minsize(780,360)
        window.columnconfigure(0,weight=1)
        window.rowconfigure(2,weight=1)
        search=tk.StringVar()
        ttk.Label(window,text="製品名・規格で検索 / 複数選択して追加できます").grid(row=0,column=0,sticky="w",padx=12,pady=6)
        ttk.Entry(window,textvariable=search).grid(row=1,column=0,sticky="ew",padx=12)
        frame=ttk.Frame(window)
        frame.grid(row=2,column=0,sticky="nsew",padx=12,pady=8)
        tree=ttk.Treeview(frame,columns=tuple(range(8)),show="headings",selectmode="extended")
        for i,label in enumerate(["製品名","規格","板厚(mm)","幅(mm)","長さ(mm)","必要枚数","回転","目付（めっき）"]):
            tree.heading(i,text=label)
            tree.column(i,width=160 if i==0 else 100)
        scroll=ttk.Scrollbar(frame,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y")
        tree.pack(fill="both",expand=True)
        def refresh(*_):
            tree.delete(*tree.get_children())
            for i,p in enumerate(records):
                if search.get().casefold() in (p[0]+" "+p[1]).casefold():
                    tree.insert("","end",iid=str(i),values=(*p[:6],"可" if p[6] else "不可",p[7] if p[7] is not None else "/".join(coating_codes(p[1])) or "なし"))
        search.trace_add("write",refresh)
        refresh()
        def add():
            selected=tree.selection()
            if not selected:
                return
            for item in selected:
                p=records[int(item)]
                blank=next((r for r in self.product_rows if not any(v.get().strip() for v in r["vars"][1:])),None)
                if blank is None:
                    self.add_product_row()
                    blank=self.product_rows[-1]
                for var,value in zip(blank["vars"],p[:5]):
                    var.set(value)
                self.restore_coating(blank,p[7],p[1])
                blank["qty"].set(p[5])
                blank["rotate"].set(bool(p[6]))
            self.status_var.set(f"登録製品を{len(selected)}件追加しました。枚数を確認して再計算してください。")
            window.destroy()
        def delete():
            selected=tree.selection()
            if not selected or not messagebox.askyesno("登録削除",f"選択した{len(selected)}件の登録を削除しますか？",parent=window):
                return
            try:
                for item in selected:
                    self.registry.delete(records[int(item)][0])
                records[:]=self.registry.list()
                refresh()
            except Exception as exc:
                messagebox.showerror("削除エラー",str(exc),parent=window)
        actions=ttk.Frame(window)
        actions.grid(row=3,column=0,sticky="ew",padx=12,pady=(4,12))
        ttk.Button(actions,text="選択した製品を追加",command=add).pack(side="left")
        ttk.Button(actions,text="選択した登録を削除",command=delete).pack(side="left",padx=8)
        tree.bind("<Double-1>",lambda _:add())

    def open_coating_master(self):
        if not self.coating:
            messagebox.showerror("めっき目付マスタ","目付マスタを読み込めませんでした。「登録データ/目付マスタ.json」を確認してください。")
            return
        values=dict(self.coating.values)
        window=tk.Toplevel(self.root)
        window.title("めっき目付マスタ — 溶融亜鉛・電気亜鉛・アロイ（F）・亜鉛・アルミニウム・マグネシウム合金めっき")
        window.geometry("920x660")
        window.minsize(840,560)
        window.columnconfigure(0,weight=1)
        window.rowconfigure(2,weight=1)
        ttk.Label(window,text="単位質量(kg/m²) ＝ 表示厚さ(mm) × 7.85 ＋ めっき量定数(kg/m²)。質量計算に使うのはめっき量定数です。",
                  wraplength=880).grid(row=0,column=0,sticky="w",padx=12,pady=(10,2))
        ttk.Label(window,text="Z：溶融亜鉛、E：電気亜鉛、F：アロイ（合金化溶融亜鉛）、K・ZAM：亜鉛・アルミニウム・マグネシウム合金めっき。数値は両面の重量計算用定数 kg/m²です。付着量の最小値 g/m²とは区別します。",
                  foreground="#9C5700",wraplength=880).grid(row=1,column=0,sticky="w",padx=12,pady=(0,6))
        frame=ttk.Frame(window)
        frame.grid(row=2,column=0,sticky="nsew",padx=12)
        frame.columnconfigure(0,weight=1)
        frame.rowconfigure(0,weight=1)
        # 既定の10行のままだと最小サイズで下部のボタンが押し出されるため高さを抑える。
        tree=ttk.Treeview(frame,columns=("code","constant","side","confirmed","note"),show="headings",selectmode="extended",height=6)
        for key,label,width in [("code","めっき記号",100),("constant","めっき量定数 kg/m²",150),
                                ("side","片面 kg/m²",100),("confirmed","確認",70),("note","出典・付着量",380)]:
            tree.heading(key,text=label)
            tree.column(key,width=width,anchor="w" if key=="note" else "center")
        tree.grid(row=0,column=0,sticky="nsew")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0,column=1,sticky="ns")
        code_var,constant_var,side_var,note_var=(tk.StringVar() for _ in range(4))
        confirmed_var=tk.BooleanVar(value=True)
        def refresh(select=None):
            tree.delete(*tree.get_children())
            for code,entry in sorted(values.items()):
                tree.insert("","end",iid=code,values=(
                    code,f"{entry.constant_kg_m2:g}",
                    "—" if entry.per_side_kg_m2 is None else f"{entry.per_side_kg_m2:g}",
                    "確認済" if entry.confirmed else "要確認",entry.note))
            if select in values:
                tree.selection_set(select)
                tree.see(select)
        def fill(_event=None):
            selected=tree.selection()
            if selected:
                entry=values[selected[0]]
                code_var.set(selected[0])
                constant_var.set(f"{entry.constant_kg_m2:g}")
                side_var.set("" if entry.per_side_kg_m2 is None else f"{entry.per_side_kg_m2:g}")
                note_var.set(entry.note)
                confirmed_var.set(entry.confirmed)
        tree.bind("<<TreeviewSelect>>",fill)
        editor=ttk.Frame(window)
        editor.grid(row=3,column=0,sticky="ew",padx=12,pady=8)
        editor.columnconfigure(0,weight=1)
        top=ttk.Frame(editor)
        top.grid(row=0,column=0,sticky="ew")
        ttk.Label(top,text="めっき記号").pack(side="left")
        ttk.Entry(top,textvariable=code_var,width=9).pack(side="left",padx=(4,12))
        ttk.Label(top,text="めっき量定数 kg/m²").pack(side="left")
        ttk.Entry(top,textvariable=constant_var,width=9).pack(side="left",padx=(4,12))
        ttk.Label(top,text="片面 kg/m²（任意）").pack(side="left")
        ttk.Entry(top,textvariable=side_var,width=9).pack(side="left",padx=(4,12))
        ttk.Checkbutton(top,text="確認済",variable=confirmed_var).pack(side="left",padx=(0,12))
        bottom=ttk.Frame(editor)
        bottom.grid(row=1,column=0,sticky="ew",pady=(6,0))
        bottom.columnconfigure(1,weight=1)
        ttk.Label(bottom,text="出典・付着量").grid(row=0,column=0,sticky="w")
        ttk.Entry(bottom,textvariable=note_var).grid(row=0,column=1,sticky="ew",padx=(4,12))
        def apply_entry():
            try:
                code,value=validate_coating(code_var.get(),constant_var.get(),side_var.get(),
                                            note_var.get(),confirmed_var.get())
            except ValueError as exc:
                messagebox.showerror("入力エラー",str(exc),parent=window)
                return
            values[code]=value
            refresh(code)
        ttk.Button(top,text="追加・更新",command=apply_entry).pack(side="left")
        def confirm_selected():
            for code in tree.selection():
                values[code]=replace_coating(values[code],confirmed=True)
            refresh()
        def delete_selected():
            selected=tree.selection()
            if not selected:
                return
            if not messagebox.askyesno("項目の削除確認",
                    "選択した項目を削除しますか？\n"+"、".join(selected)+
                    "\n\n「保存して閉じる」でマスタへ反映されます。",parent=window):
                return
            for code in selected:
                values.pop(code,None)
            refresh()
            for var in (code_var,constant_var,side_var,note_var):
                var.set("")
        def save():
            try:
                self.coating.save(values)
            except Exception as exc:
                messagebox.showerror("保存エラー",str(exc),parent=window)
                return
            for row in self.product_rows:
                self.restore_coating(row,row["coating"].get(),"")
            self.inputs_changed()
            self.status_var.set("めっき目付マスタを保存しました。再計算すると重量へ反映されます。")
            window.destroy()
        actions=ttk.Frame(window)
        actions.grid(row=4,column=0,sticky="ew",padx=12,pady=(0,12))
        edit_button=ttk.Menubutton(actions,text="編集")
        edit_menu=tk.Menu(edit_button,tearoff=False)
        edit_menu.add_command(label="選択を確認済にする",command=confirm_selected)
        edit_menu.add_command(label="項目を削除",command=delete_selected)
        def update_edit_menu():
            state="normal" if tree.selection() else "disabled"
            edit_menu.entryconfigure(0,state=state)
            edit_menu.entryconfigure(1,state=state)
        edit_menu.configure(postcommand=update_edit_menu)
        edit_button.configure(menu=edit_menu)
        edit_button.pack(side="left")
        ttk.Button(actions,text="保存して閉じる",command=save).pack(side="right")
        ttk.Button(actions,text="キャンセル",command=window.destroy).pack(side="right",padx=8)
        refresh()
        window.transient(self.root)
        window.grab_set()

    def save_loss(self,key,var):
        if self.suppress_changes: return
        if self.loss_store:
            try:
                self.loss_store.save(key,var.get())
            except OSError as exc:
                self.status_var.set(f"設定を保存できません：{exc}")

    def start_calculation(self):
        if str(self.calc_button.cget("state"))=="disabled": return
        self.result_valid=False
        self.export_button.configure(state="disabled")
        self.calculation_revision=self.input_revision
        try:
            products=[]
            for i,row in enumerate(self.product_rows,1):
                name,spec,thick,w,h=[v.get().strip() for v in row["vars"]]
                if not w and not h:
                    continue
                products.append(ProductSpec(f"P{i}",spec,float(thick) if thick else None,float(w),float(h),int(row["qty"].get()),row["rotate"].get(),name or f"製品{i}",coating="" if row["coating"].get()=="なし" else row["coating"].get()))
            settings=[float(v.get()) for v in self.settings]
            length_loss=float(self.length_loss_var.get())
            length_round=float(self.length_round_var.get())
            time_limit=float(self.time_var.get())
        except ValueError:
            messagebox.showerror("入力エラー","幅・長さ・枚数と大板条件・計算時間を正しい数値で入力してください。")
            return
        self.results=[]
        self.sheet_total_var.set("必要大板：計算中…")
        self.result_tree.delete(*self.result_tree.get_children())
        self.canvas.delete("all")
        self._set_detail("")
        self.current_products=products
        self.current_settings=tuple(settings)+(length_loss,length_round)
        self.export_button.configure(state="disabled")
        self.cancel_event=threading.Event()
        self.calc_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_var.set("計算中…")
        self.pending=None
        def worker():
            try:
                self.pending=(optimize_auto(products,*settings,time_limit=time_limit,cancel=self.cancel_event,
                                            length_loss=length_loss,length_round=length_round),None)
            except Exception as exc:
                self.pending=([],exc)
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(50,self._poll)

    def _poll(self):
        if self.pending is None:
            self.root.after(50,self._poll)
            return
        self.results,error=self.pending
        self.calc_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if error:
            self.sheet_total_var.set("必要大板：未計算")
            self.status_var.set("入力条件を確認してください")
            messagebox.showerror("計算エラー",str(error))
            return
        for i,r in enumerate(self.results):
            self.result_tree.insert("","end",iid=str(i),values=(f"候補{i+1} / {'充足' if r.complete else '不足'}",len(r.sheets),f"{r.yield_rate:.2f}%",f"{r.scrap_weight:,.1f}" if r.weight_available else "未計算"))
        if not self.results:
            self.status_var.set("候補なし・中止")
        elif self.results[0].timed_out:
            self.status_var.set("計算完了（計算時間で探索を打ち切り）")
        else:
            self.status_var.set("計算完了（探索候補）")
        if not self.results:
            self.sheet_total_var.set("必要大板：候補なし")
        if self.results:
            self.result_revision=self.calculation_revision
            self.result_valid=self.result_revision==self.input_revision and not self.cancel_event.is_set()
            self.export_button.configure(state="normal" if self.result_valid else "disabled")
            if not self.result_valid:
                self.status_var.set("入力変更または中止のため再計算してください")
            self.result_tree.selection_set("0")
            self.show_selected()

    def export_excel(self):
        if not self.result_valid or self.result_revision!=self.input_revision:
            self.status_var.set("入力が変更されています。再計算してください")
            return
        selected=self.result_tree.selection()
        if not selected:
            return
        index=int(selected[0])
        folder=APP_DIR / "計算結果"
        try:
            folder.mkdir(parents=True,exist_ok=True)
            path=filedialog.asksaveasfilename(initialdir=str(folder),
                initialfile=f"長さ自動計算_図解付き_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                defaultextension=".xlsx",filetypes=[("Excelブック","*.xlsx")])
            if not path:
                return
            if not self.result_valid or self.result_revision!=self.input_revision: return
            export_auto(path,self.results[index],self.current_products,self.current_settings,index+1)
            messagebox.showinfo("Excel出力完了",f"図解付きの結果を保存しました。\n{path}")
        except Exception as exc:
            messagebox.showerror("Excel出力エラー",f"保存できませんでした。ファイルを開いている場合は閉じてください。\n{exc}")

    def _set_detail(self,text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0","end")
        self.detail.insert("1.0",text)
        self.detail.configure(state="disabled")

    def show_result(self,result):
        self.sheet_total_var.set(f"必要大板：合計 {len(result.sheets)} 枚" + ("（不足あり）" if not result.complete else ""))
        if not self.result_valid:
            self.sheet_total_var.set("前回の計算結果："+str(len(result.sheets))+"枚（再計算が必要）")
        products={p.id:p for p in self.current_products}
        dims=Counter((s.sheet_type.spec,s.sheet_type.thickness,s.sheet_type.width,s.sheet_type.length,s.sheet_type.weight_spec) for s in result.sheets)
        lines=[f"必要大板：合計 {len(result.sheets)} 枚",f"歩留り {result.yield_rate:.2f}% ／ 歩損 {result.loss_rate:.2f}%"]
        if result.weight_available:
            lines.append(f"大板 {result.sheet_weight:,.1f} kg ／ 製品 {result.product_weight:,.1f} kg ／ 端材 {result.scrap_weight:,.1f} kg")
        else:
            lines.append("重量：板厚が空欄のため未計算")
        coatings={}
        for p in self.current_products:
            code,entry=coating_detail(p.weight_spec)
            if code:
                coatings[code]=entry
        for code,entry in sorted(coatings.items()):
            if entry is None:
                lines.append(f"めっき：{code} 未登録のためめっき量定数0で計算")
            else:
                lines.append(f"めっき：{code} めっき量定数 {entry.constant_kg_m2:g} kg/m²")
        lines.extend(["",f"幅 × 自動計算長さ / 枚数（長さ {len({key[3] for key in dims})}種類）"])
        for (spec,t,w,h,weight_spec),n in dims.items():
            lines.append(f"{w:g} × {h:g} mm … {n}枚\n  {spec or '規格未指定'} / 板厚 {str(t)+'mm' if t else '未指定'} / 目付 {weight_spec or 'なし'}")
        lines.extend(["","製品別：配置枚数 / 必要枚数"])
        for p in self.current_products:
            lines.append(f"{p.id} {p.name}：{result.placed_by_product.get(p.id,0)} / {p.required_qty} 枚")
        if not result.complete:
            lines.append("※不足あり。この候補では必要数量を満たしていません。")
        if result.timed_out:
            lines.append("※探索は計算時間・中止で打ち切りました。必要数量は満たしています。計算時間を延ばすとより良い候補が出る場合があります。"
                         if result.complete else "※時間制限または中止時点の暫定候補。必要数量を満たしていません。")
        if result.weight_available:
            lines.extend("※"+warning for warning in result.warnings)
        self._set_detail("\n".join(lines))
        c=self.canvas
        c.delete("all")
        colors=["#65C2D5","#70D1C8","#B99AD1","#A8DCD2","#8DBEDB","#75C3A3","#F5CF79","#F3B39C"]
        color={pid:colors[i%len(colors)] for i,pid in enumerate(products)}
        y=20
        for i,(plan,count,_) in enumerate(group_sheet_plans(result.sheets),1):
            s=plan.sheet_type
            scale=min(450/s.width,320/s.length)*self.zoom.get()
            w,h=s.width*scale,s.length*scale
            x=85
            c.create_text(15,y,anchor="nw",text=f"パターン {i}   {s.width:g} × {s.length:g} mm   × {count}枚",font=("Yu Gothic UI",12,"bold"),fill="#164e63")
            y+=40
            c.create_line(x,y,x+w,y,arrow="both",fill="#536779")
            c.create_text(x+w/2,y-10,text=f"幅 {s.width:g} mm")
            y+=16
            c.create_rectangle(x,y,x+w,y+h,fill="#e5e7eb",outline="#334155",width=2)
            e=s.edge_loss*scale
            le=s.length_loss*scale
            for bounds in [(x,y,x+e,y+h),(x,y,x+w,y+le),(x,y+h-le,x+w,y+h)]:
                c.create_rectangle(*bounds,fill="#64748b",stipple="gray50",outline="")
            c.create_line(x-12,y,x-12,y+h,arrow="both")
            c.create_text(x-40,y+h/2,text=f"長さ\n{s.length:g}\nmm")
            for p in plan.placements:
                x1,y1=x+p.x*scale,y+p.y*scale
                x2,y2=x1+p.width*scale,y1+p.length*scale
                tag=f"p{i}_{len(c.find_all())}"
                c.create_rectangle(x1,y1,x2,y2,fill=color[p.product_id],outline="#40566a",tags=tag)
                label=f"{p.product_id}\n{p.width:g} × {p.length:g}"
                if x2-x1>75 and y2-y1>38:
                    c.create_text((x1+x2)/2,(y1+y2)/2,text=label,font=("Yu Gothic UI",9),tags=tag)
                elif x2-x1>23 and y2-y1>18:
                    c.create_text((x1+x2)/2,(y1+y2)/2,text=p.product_id,font=("Yu Gothic UI",8),tags=tag)
                info=f"{p.product_id} {products[p.product_id].name} / 配置寸法 {p.width:g} × {p.length:g} mm / {'90度回転' if p.rotated else '回転なし'}"
                c.tag_bind(tag,"<Button-1>",lambda _,text=info:self.status_var.set(text))
            y+=h+16
            counts=Counter(p.product_id for p in plan.placements)
            for pid,n in counts.items():
                product=products[pid]
                c.create_rectangle(x,y,x+12,y+12,fill=color[pid],outline="")
                c.create_text(x+20,y-2,anchor="nw",text=f"{pid} {product.name}  {product.width:g}×{product.length:g} mm：{n}枚/大板 → 合計{n*count}枚")
                y+=23
            c.create_text(x,y,anchor="nw",text=f"幅ロス：片側 {s.edge_loss:g}mm / 長さロス：前後各 {s.length_loss:g}mm ／ 切断代：{s.cut_allowance:g}mm",fill="#536779")
            y+=50
        c.configure(scrollregion=c.bbox("all"))


if __name__ == "__main__":
    from license_gate import require_license
    root=tk.Tk()
    license_info = require_license(root, APP_DIR)
    if license_info is None:
        root.destroy()
    else:
        AutoLengthApp(root)
        from core.licensing import parse_time
        if license_info['expires_at'] is None:
            license_label = 'ライセンス：無期限'
        else:
            expiry = parse_time(license_info['expires_at']).astimezone().strftime('%Y-%m-%d %H:%M %Z')
            license_label = '有効期限 ' + expiry
        root.title(root.title() + '  | ' + license_label)
        root.deiconify()
        root.mainloop()
