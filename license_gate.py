"""Startup-only offline activation screen for the auto-length application."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core.license_public_key import PUBLIC_KEY_PEM
from core.licensing import LicenseError, get_hwid, install_license, verify_file


def require_license(root, app_dir):
    root.withdraw()
    path = app_dir / 'license.dat'
    try:
        hwid = get_hwid()
    except LicenseError as exc:
        messagebox.showerror('ライセンス確認', str(exc), parent=root)
        return None
    try:
        return verify_file(path, PUBLIC_KEY_PEM, hwid)
    except LicenseError as exc:
        initial_message = str(exc)

    result = None
    window = tk.Toplevel(root)
    window.title('シャーリング取り合わせ — ライセンス登録')
    window.geometry('760x340')
    window.minsize(640, 320)
    window.configure(background='#eef2f7')
    tk.Label(window, text='オフライン ライセンス登録', bg='#24486a', fg='white',
             font=('Yu Gothic UI', 17, 'bold'), padx=20, pady=15, anchor='w').pack(fill='x')
    body = ttk.Frame(window, padding=18)
    body.pack(fill='both', expand=True)
    status = tk.StringVar(value=initial_message)
    ttk.Label(body, textvariable=status, wraplength=590).pack(anchor='w', pady=(0, 12))
    ttk.Label(body, text='このPCのHWID（発行者へお伝えください）').pack(anchor='w')
    value = tk.StringVar(value=hwid)
    ttk.Entry(body, textvariable=value, state='readonly', font=('Consolas', 10)).pack(fill='x', pady=8)
    ttk.Label(body, text='発行されたlicense.datを読み込むと起動します。通信は行いません。').pack(anchor='w')
    # Buttons are outside the expanding content, so shrinking does not hide them.
    buttons = ttk.Frame(window, padding=(18, 10))
    buttons.pack(side='bottom', fill='x')

    def copy_hwid():
        root.clipboard_clear()
        root.clipboard_append(hwid)
        status.set('HWIDをコピーしました。')

    def activate():
        nonlocal result
        source = filedialog.askopenfilename(parent=window, title='ライセンスを選択',
                    filetypes=[('ライセンス', '*.dat'), ('すべてのファイル', '*.*')])
        if not source:
            return
        try:
            result = install_license(source, path, PUBLIC_KEY_PEM, hwid)
        except LicenseError as exc:
            status.set(str(exc))
            return
        window.destroy()

    ttk.Button(buttons, text='HWIDをコピー', command=copy_hwid).pack(side='left')
    tk.Button(buttons, text='ライセンスを読み込む', command=activate, bg='#2563eb', fg='white',
              activebackground='#1d4ed8', activeforeground='white', padx=16, pady=7).pack(side='left', padx=10)
    ttk.Button(buttons, text='終了', command=window.destroy).pack(side='right')
    window.protocol('WM_DELETE_WINDOW', window.destroy)
    window.grab_set()
    root.wait_window(window)
    return result
