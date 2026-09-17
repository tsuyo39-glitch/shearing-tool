"""Developer-only offline issuer UI. Keep this tool on the signing PC."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core.license_public_key import PUBLIC_KEY_PEM
from tools.license_issuer import load_key, make_license, public_bytes


class LicenseIssuerApp:
    def __init__(self, root, output_dir=None):
        self.root = root
        root.title('ライセンス発行ツール（発行者専用）')
        root.geometry('900x480')
        root.minsize(800, 440)
        root.configure(bg='#edf2f7')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TLabel', background='#edf2f7', font=('Yu Gothic UI', 11))
        style.configure('TFrame', background='#edf2f7')
        style.configure('TButton', font=('Yu Gothic UI', 11), padding=8)
        tk.Label(root, text='自分側：ライセンスを発行する', bg='#173655', fg='white',
                 font=('Yu Gothic UI', 19, 'bold'), anchor='w', padx=20, pady=16).pack(fill='x')
        body=ttk.Frame(root, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='① 相手から届いたHWIDを、下の入力欄へ貼り付けます。').pack(anchor='w', pady=(0,8))
        self.hwid=tk.StringVar()
        self.hwid_entry=ttk.Entry(body, textvariable=self.hwid, font=('Consolas', 11))
        self.hwid_entry.pack(fill='x', ipady=6)
        ttk.Label(body, text='② 保存場所を確認します。ファイル名は license.dat です。').pack(anchor='w', pady=(20,8))
        self.output=tk.StringVar(value=str((output_dir or Path.home()/'Desktop'/'発行ライセンス')/'license.dat'))
        location=ttk.Frame(body); location.pack(fill='x')
        ttk.Entry(location,textvariable=self.output,font=('Yu Gothic UI',10)).pack(side='left',fill='x',expand=True,ipady=5)
        ttk.Button(location,text='保存先を選ぶ',command=self.choose_path).pack(side='right',padx=(8,0))
        ttk.Label(body,text='③「無期限ライセンスを発行」を押します。').pack(anchor='w',pady=(20,8))
        self.issue_button=tk.Button(body,text='無期限ライセンスを発行',command=self.issue,
                    bg='#2563eb',fg='white',activebackground='#1d4ed8',activeforeground='white',
                    font=('Yu Gothic UI',12,'bold'),padx=18,pady=10)
        self.issue_button.pack(anchor='w')
        self.status=tk.StringVar(value='相手のPC専用のファイルを発行します。期限の設定は不要です。')
        ttk.Label(body,textvariable=self.status,wraplength=810,foreground='#174b7d').pack(anchor='w',pady=(16,0))

    def choose_path(self):
        path=filedialog.asksaveasfilename(parent=self.root,title='ライセンスの保存先',
                  initialfile='license.dat',defaultextension='.dat',filetypes=[('ライセンス','*.dat')])
        if path: self.output.set(path)

    def issue(self):
        try:
            key=load_key()
            if public_bytes(key)!=PUBLIC_KEY_PEM:
                raise ValueError('秘密鍵がアプリの公開鍵と一致しません。')
            data=make_license(key,self.hwid.get())
            path=Path(self.output.get().strip())
            if path.suffix.lower()!='.dat':
                raise ValueError('保存名の末尾を.datにしてください。')
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:
                stream.write(data)
            self.status.set('発行しました。保存先の license.dat を相手へ送ってください。\nこの発行ツールや秘密鍵を送る必要はありません。')
            return path
        except FileExistsError:
            messagebox.showerror('発行できません','同名ファイルが存在します。「保存先を選ぶ」で別のフォルダーまたは名前を選んでください。',parent=self.root)
        except Exception as exc:
            messagebox.showerror('発行できません',str(exc),parent=self.root)
        return None


if __name__=='__main__':
    root=tk.Tk()
    LicenseIssuerApp(root)
    root.mainloop()
