"""
Módulo de ventana de login
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox

def login_window(security_manager) -> bool:
    login_root = tk.Tk()
    login_root.title("Inicio de Sesión - Sistema Integral de Certificados")
    login_root.geometry("400x300")
    login_root.configure(bg="#e9eef7")
    login_root.resizable(False, False)
    
    login_root.update_idletasks()
    width = login_root.winfo_width()
    height = login_root.winfo_height()
    x = (login_root.winfo_screenwidth() // 2) - (width // 2)
    y = (login_root.winfo_screenheight() // 2) - (height // 2)
    login_root.geometry(f'400x300+{x}+{y}')
    
    try:
        creds = security_manager.load_credentials()
        stored_user = creds.get("user", {})
        stored_username = stored_user.get("username", "")
    except FileNotFoundError:
        messagebox.showerror("Error de Credenciales", "Archivo de credenciales no encontrado.", parent=login_root)
        login_root.destroy()
        return False
    
    logged_in = False
    MAX_ATTEMPTS = 5
    attempt_count = 0

    def try_login(event=None):
        nonlocal logged_in, attempt_count
        
        username = user_entry.get().strip()
        password = pass_entry.get()
        
        attempt_count += 1
        
        if username != stored_username:
            messagebox.showerror("Error de acceso", "Usuario incorrecto.", parent=login_root)
        elif security_manager.verify_password(password, stored_user.get("password", {})):
            logged_in = True
            login_root.quit()
        else:
            messagebox.showerror("Error de acceso", f"Contraseña incorrecta. Intento {attempt_count}/{MAX_ATTEMPTS}", parent=login_root)
        
        if attempt_count >= MAX_ATTEMPTS:
            messagebox.showerror("Demasiados intentos", "Se alcanzó el número máximo de intentos. Saliendo.", parent=login_root)
            login_root.quit()
            
        pass_entry.delete(0, tk.END)
        if stored_username:
            pass_entry.focus_set()
        else:
            user_entry.focus_set()

    def on_closing():
        if not logged_in:
            sys.exit(0)
        login_root.quit()

    login_root.protocol("WM_DELETE_WINDOW", on_closing)

    header_frame = tk.Frame(login_root, bg="#1f618d")
    header_frame.pack(fill=tk.X, pady=(0, 20))
    tk.Label(header_frame, text="Acceso al Sistema Integral de Certificados", bg="#1f618d", fg="white",
             font=("Segoe UI", 14, "bold")).pack(pady=15)

    form_frame = tk.Frame(login_root, bg="#e9eef7", padx=30, pady=20)
    form_frame.pack(fill=tk.BOTH, expand=True)

    user_label = tk.Label(form_frame, text="👤 Usuario:", bg="#e9eef7", font=("Segoe UI", 11, "bold"), fg="#1f618d")
    user_label.grid(row=0, column=0, sticky="w", pady=8)
    user_entry = ttk.Entry(form_frame, width=25, font=("Segoe UI", 11))
    user_entry.grid(row=0, column=1, pady=8, padx=10, sticky="ew")
    user_entry.insert(0, stored_username)
    user_entry.bind('<Return>', try_login)

    pass_label = tk.Label(form_frame, text="🔒 Contraseña:", bg="#e9eef7", font=("Segoe UI", 11, "bold"), fg="#1f618d")
    pass_label.grid(row=1, column=0, sticky="w", pady=8)
    pass_entry = ttk.Entry(form_frame, width=25, show="*", font=("Segoe UI", 11))
    pass_entry.grid(row=1, column=1, pady=8, padx=10, sticky="ew")
    pass_entry.bind('<Return>', try_login)
    
    form_frame.columnconfigure(1, weight=1)
    
    login_button = tk.Button(form_frame, text="➡️  INGRESAR AL SISTEMA", command=try_login, 
                           bg="#28a745", fg="white", font=("Segoe UI", 10, "bold"), 
                           relief=tk.FLAT, padx=5, pady=5)
    login_button.grid(row=2, column=0, columnspan=2, pady=25, sticky="ew")
    
    if stored_username:
        pass_entry.focus_set()
    else:
        user_entry.focus_set()

    login_root.mainloop()
    
    success = logged_in
    login_root.destroy()
    
    return success