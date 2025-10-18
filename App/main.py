#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA INTEGRAL DE CERTIFICADOS CON QR - VERSIÓN MODULAR
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox

# Agregar el directorio actual al path para las importaciones
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from tkinterdnd2 import TkinterDnD
    DND_ACTIVO = True
except ImportError:
    TkinterDnD = tk
    DND_ACTIVO = False

from security.security_manager import SecurityManager
from ui.login import login_window
from ui.app import CertificadosApp

def main():
    security_manager = SecurityManager()
    
    if not security_manager.credentials_exist():
        root_init = tk.Tk()
        root_init.withdraw()
        
        resp = messagebox.askyesno(
            "Configuración inicial necesaria",
            "No se encontró un archivo de credenciales. ¿Desea configurarlo ahora?",
            parent=root_init
        )
        if resp:
            if security_manager.setup_credentials_dialog(root_init):
                messagebox.showinfo("Listo", "Credenciales creadas. Reinicie la aplicación.", parent=root_init)
            else:
                messagebox.showwarning("Cancelado", "No se crearon credenciales. La aplicación se cerrará.", parent=root_init)
        else:
            messagebox.showinfo("Información", "Puede crear las credenciales manualmente más tarde.", parent=root_init)
        root_init.destroy()
        return

    if not login_window(security_manager):
        return

    root = TkinterDnD.Tk() if DND_ACTIVO else tk.Tk()
    app = CertificadosApp(root)
    app.center_window(root)
    root.mainloop()

if __name__ == "__main__":
    main()