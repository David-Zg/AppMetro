"""
Módulo de ventana de login
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox


def login_window(security_manager) -> bool:
    # =========================
    # CONFIGURACIÓN INICIAL
    # =========================
    login_root = tk.Tk()
    login_root.withdraw()  # Ocultar ventana mientras se prepara
    login_root.title("Inicio de Sesión - Sistema Integral de Certificados")
    login_root.configure(bg="#e9eef7")
    login_root.resizable(False, False)

    # Tamaño fijo antes de mostrar
    window_width = 400
    window_height = 300

    # Calcular posición centrada ANTES de mostrar
    screen_width = login_root.winfo_screenwidth()
    screen_height = login_root.winfo_screenheight()
    x = (screen_width // 2) - (window_width // 2)
    y = (screen_height // 2) - (window_height // 2)
    login_root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # Mostrar ventana ya centrada
    login_root.deiconify()

    # =========================
    # CARGA DE CREDENCIALES
    # =========================
    try:
        creds = security_manager.load_credentials()
        stored_user = creds.get("user", {})
        stored_username = stored_user.get("username", "")
    except FileNotFoundError:
        messagebox.showerror("Error de Credenciales",
                             "Archivo de credenciales no encontrado.",
                             parent=login_root)
        login_root.destroy()
        return False

    logged_in = False
    MAX_ATTEMPTS = 5
    attempt_count = 0

    # =========================
    # FUNCIÓN DE VERIFICACIÓN
    # =========================
    def try_login(event=None):
        nonlocal logged_in, attempt_count

        username = user_entry.get().strip()
        password = pass_entry.get()
        attempt_count += 1

        if username != stored_username:
            messagebox.showerror("Error de acceso", "Usuario incorrecto.", parent=login_root)
        elif security_manager.verify_password(password, stored_user.get("password", {})):
            logged_in = True
            login_root.after(100, login_root.destroy)
        else:
            messagebox.showerror(
                "Error de acceso",
                f"Contraseña incorrecta. Intento {attempt_count}/{MAX_ATTEMPTS}",
                parent=login_root
            )

        if attempt_count >= MAX_ATTEMPTS:
            messagebox.showerror(
                "Demasiados intentos",
                "Se alcanzó el número máximo de intentos. Saliendo.",
                parent=login_root
            )
            login_root.after(100, login_root.destroy)

        pass_entry.delete(0, tk.END)
        if stored_username:
            pass_entry.focus_set()
        else:
            user_entry.focus_set()

    # =========================
    # EVENTO DE CIERRE MANUAL
    # =========================
    def on_closing():
        if not logged_in:
            sys.exit(0)
        login_root.destroy()

    login_root.protocol("WM_DELETE_WINDOW", on_closing)

    # =========================
    # CABECERA
    # =========================
    header_frame = tk.Frame(login_root, bg="#1f618d")
    header_frame.pack(fill=tk.X, pady=(0, 20))
    tk.Label(
        header_frame,
        text="Acceso al Sistema Integral de Certificados",
        bg="#1f618d", fg="white",
        font=("Segoe UI", 14, "bold")
    ).pack(pady=15)

    # =========================
    # FORMULARIO
    # =========================
    form_frame = tk.Frame(login_root, bg="#e9eef7", padx=30, pady=20)
    form_frame.pack(fill=tk.BOTH, expand=True)

    tk.Label(form_frame, text="👤 Usuario:", bg="#e9eef7",
             font=("Segoe UI", 11, "bold"), fg="#1f618d").grid(row=0, column=0, sticky="w", pady=8)
    user_entry = ttk.Entry(form_frame, width=25, font=("Segoe UI", 11))
    user_entry.grid(row=0, column=1, pady=8, padx=10, sticky="ew")
    user_entry.insert(0, stored_username)
    user_entry.bind("<Return>", try_login)

    tk.Label(form_frame, text="🔒 Contraseña:", bg="#e9eef7",
             font=("Segoe UI", 11, "bold"), fg="#1f618d").grid(row=1, column=0, sticky="w", pady=8)
    pass_entry = ttk.Entry(form_frame, width=25, show="*", font=("Segoe UI", 11))
    pass_entry.grid(row=1, column=1, pady=8, padx=10, sticky="ew")
    pass_entry.bind("<Return>", try_login)

    form_frame.columnconfigure(1, weight=1)

    login_button = tk.Button(
        form_frame,
        text="➡️  INGRESAR AL SISTEMA",
        command=try_login,
        bg="#28a745", fg="white",
        font=("Segoe UI", 10, "bold"),
        relief=tk.FLAT, padx=5, pady=5
    )
    login_button.grid(row=2, column=0, columnspan=2, pady=25, sticky="ew")

    # Foco inicial
    if stored_username:
        pass_entry.focus_set()
    else:
        user_entry.focus_set()

    # =========================
    # LOOP PRINCIPAL
    # =========================
    login_root.mainloop()

    return logged_in
