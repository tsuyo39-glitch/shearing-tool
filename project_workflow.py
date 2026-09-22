import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from core.project_io import save_project, load_project, parse_paste


class ProjectWorkflow:
    def init_workflow(self):
        self.suppress_changes=True
        self.input_revision=0
        self.result_revision=None
        self.result_valid=False
        self.project_dirty=False
        self.project_path=None
        self.project_vars=[tk.StringVar() for _ in range(3)]

    def finish_workflow(self):
        for var in self.settings+[self.length_loss_var,self.length_round_var]:
            var.trace_add("write",self.inputs_changed)
        for var in self.project_vars:
            var.trace_add("write",self.metadata_changed)
        self.suppress_changes=False
        self.root.protocol("WM_DELETE_WINDOW",self.close_project)

    def metadata_changed(self,*_):
        if not self.suppress_changes: self.project_dirty=True

    def inputs_changed(self,*_):
        if self.suppress_changes: return
        self.input_revision+=1
        self.project_dirty=True
        self.result_valid=False
        self.export_button.configure(state="disabled")
        self.status_var.set("入力が変更されています。再計算してください")
        if self.results:
            self.show_selected()

    def snapshot(self):
        return {"version":1,"name":self.project_vars[0].get(),"customer":self.project_vars[1].get(),
                "notes":self.project_vars[2].get(),"settings":[v.get() for v in self.settings]+[self.length_loss_var.get(),self.length_round_var.get()],
                "products":[{"values":[v.get() for v in r["vars"]],"qty":r["qty"].get(),"rotate":r["rotate"].get(),"coating":r["coating"].get()} for r in self.product_rows]}

    def project_metadata(self,then=None):
        win=tk.Toplevel(self.root); win.title("案件情報"); win.geometry("620x260"); win.minsize(500,240)
        win.columnconfigure(1,weight=1)
        local=[tk.StringVar(value=v.get()) for v in self.project_vars]
        for i,(label,var) in enumerate(zip(("案件名（必須）","得意先名","備考"),local)):
            ttk.Label(win,text=label).grid(row=i,column=0,padx=12,pady=10,sticky="w")
            ttk.Entry(win,textvariable=var).grid(row=i,column=1,padx=12,pady=10,sticky="ew")
        def accept():
            if not local[0].get().strip():
                messagebox.showerror("入力エラー","案件名を入力してください",parent=win); return
            for a,b in zip(self.project_vars,local): a.set(b.get())
            win.destroy()
            if then: then()
        actions=ttk.Frame(win); actions.grid(row=3,column=0,columnspan=2,pady=12)
        ttk.Button(actions,text="確定",command=accept).pack(side="left",padx=8)
        ttk.Button(actions,text="キャンセル",command=win.destroy).pack(side="left")
        win.transient(self.root); win.grab_set(); self.root.wait_window(win)

    def save_project_dialog(self):
        if not self.project_vars[0].get().strip(): self.project_metadata()
        if not self.project_vars[0].get().strip(): return False
        try:
            folder=self.data_dir/"案件データ"; folder.mkdir(parents=True,exist_ok=True)
            path=filedialog.asksaveasfilename(initialdir=str(self.project_path.parent if self.project_path else folder),
                   initialfile=self.project_path.name if self.project_path else "案件.json",defaultextension=".json",filetypes=[("案件JSON","*.json")])
            if not path: return False
            save_project(path,self.snapshot())
            self.project_path=Path(path); self.project_dirty=False
            self.status_var.set("案件を保存しました" + ("。再計算してください" if not self.result_valid else ""))
            return True
        except Exception as exc:
            messagebox.showerror("案件保存エラー",str(exc)); return False

    def confirm_discard(self):
        if not self.project_dirty: return True
        choice=messagebox.askyesnocancel("未保存の変更","変更を保存しますか？\nはい：保存 / いいえ：破棄 / キャンセル：操作を中止")
        if choice is None: return False
        return self.save_project_dialog() if choice else True

    def apply_project(self,data):
        from core.project_io import validate_project
        validate_project(data)
        self.suppress_changes=True
        try:
            for row in list(self.product_rows): self.remove_product_row(row)
            values=list(data["settings"])
            if len(values)==5: values.append("0")  # 長さ丸め追加前の案件
            for var,value in zip(self.settings+[self.length_loss_var,self.length_round_var],values): var.set(value)
            for var,key in zip(self.project_vars,("name","customer","notes")): var.set(data[key])
            self.append_products(data["products"])
        finally:
            self.suppress_changes=False
        self.inputs_changed()
        self.project_dirty=False
        for key,var in (("width",self.settings[1]),("length",self.length_loss_var),("gap",self.settings[3]),("round",self.length_round_var)):
            self.save_loss(key,var)

    def open_project_dialog(self):
        path=filedialog.askopenfilename(initialdir=str(self.data_dir/"案件データ"),filetypes=[("案件JSON","*.json")])
        if not path: return
        try:
            data=load_project(path)
        except Exception as exc:
            messagebox.showerror("案件読込エラー",str(exc)); return
        if not self.confirm_discard(): return
        self.apply_project(data); self.project_path=Path(path)

    def close_project(self):
        if self.confirm_discard():
            self.cancel_event.set()
            self.root.destroy()

    def append_products(self,records):
        for record in records:
            self.add_product_row()
            row=self.product_rows[-1]
            for var,value in zip(row["vars"],record["values"]): var.set(value)
            self.restore_coating(row,record.get("coating"),record["values"][1])
            row["qty"].set(record["qty"]); row["rotate"].set(record["rotate"])

    def paste_excel(self):
        try:
            records,errors,preview=parse_paste(self.root.clipboard_get())
        except Exception as exc:
            messagebox.showerror("貼り付けエラー",str(exc)); return
        win=tk.Toplevel(self.root); win.title("Excel貼り付けプレビュー")
        win.geometry("1050x500"); win.minsize(780,360)
        win.columnconfigure(0,weight=1); win.rowconfigure(1,weight=1)
        ttk.Label(win,text=f"取込対象 {len(records)}件 / エラー {len(errors)}件。既存の製品一覧へ追加します。" ).grid(row=0,column=0,sticky="w",padx=12,pady=8)
        frame=ttk.Frame(win); frame.grid(row=1,column=0,sticky="nsew",padx=12)
        frame.columnconfigure(0,weight=1); frame.rowconfigure(0,weight=1)
        tree=ttk.Treeview(frame,columns=tuple(range(9)),show="headings")
        for i,label in enumerate(("元行","製品名","規格","板厚","幅","長さ","必要枚数","回転可否","確認")):
            tree.heading(i,text=label); tree.column(i,width=200 if i==8 else 95,minwidth=60)
        tree.grid(row=0,column=0,sticky="nsew")
        vs=ttk.Scrollbar(frame,orient="vertical",command=tree.yview); vs.grid(row=0,column=1,sticky="ns")
        hs=ttk.Scrollbar(frame,orient="horizontal",command=tree.xview); hs.grid(row=1,column=0,sticky="ew")
        tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
        for row in preview: tree.insert("","end",values=row)
        ttk.Label(win,text="\n".join(errors[:3]) if errors else "空欄の回転可否は「可」。寸法単位はmmです。",wraplength=750).grid(row=2,column=0,sticky="w",padx=12,pady=8)
        actions=ttk.Frame(win); actions.grid(row=3,column=0,sticky="ew",padx=12,pady=12)
        def accept():
            if errors: return
            self.append_products(records); win.destroy()
        ttk.Button(actions,text="一覧へ追加",command=accept,state="disabled" if errors else "normal").pack(side="left")
        ttk.Button(actions,text="キャンセル",command=win.destroy).pack(side="left",padx=8)
        win.transient(self.root); win.grab_set()
