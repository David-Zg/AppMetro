"""
Módulo de gestión de seguridad y credenciales
"""

import os
import json
import time
import base64
import hmac
import hashlib
import secrets
import tkinter as tk
from tkinter import simpledialog, messagebox

class SecurityManager:
    """Gestiona toda la seguridad y credenciales del sistema"""
    
    INIT_SECRET = b"CAMBIA_POR_UNA_CLAVE_MUY_SECRETA_Y_LARGA"
    INIT_MAX_ATTEMPTS = 3
    PBKDF2_ITER = 150_000
    SALT_BYTES = 16
    
    CREDS_USER_FILE = "user_credentials.json"
    
    def __init__(self):
        self.creds_data = None
        
    def _b64u(self, x: bytes) -> str:
        return base64.urlsafe_b64encode(x).decode("ascii").rstrip("=")

    def _unb64u(self, s: str) -> bytes:
        padding = "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s + padding)

    def hash_password(self, password: str) -> dict:
        salt = secrets.token_bytes(self.SALT_BYTES)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self.PBKDF2_ITER)
        return {"salt": self._b64u(salt), "hash": self._b64u(dk), "iter": self.PBKDF2_ITER}

    def verify_password(self, password: str, stored: dict) -> bool:
        try:
            salt = self._unb64u(stored["salt"])
            iter_count = int(stored.get("iter", self.PBKDF2_ITER))
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iter_count)
            return hmac.compare_digest(self._b64u(dk), stored["hash"])
        except Exception:
            return False

    def generate_init_token_for_id(self, identifier: str) -> str:
        mac = hmac.new(self.INIT_SECRET, identifier.encode("utf-8"), hashlib.sha256).digest()
        return self._b64u(mac)

    def verify_init_token(self, identifier: str, token_input: str) -> bool:
        try:
            expected = self.generate_init_token_for_id(identifier)
            return hmac.compare_digest(expected, token_input)
        except Exception:
            return False

    def credentials_exist(self) -> bool:
        return os.path.exists(self.CREDS_USER_FILE)

    def save_credentials(self, data: dict):
        with open(self.CREDS_USER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_credentials(self) -> dict:
        with open(self.CREDS_USER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def setup_credentials_dialog(self, root) -> bool:
        """Dialogo completo de configuración inicial de credenciales"""
        identifier = self.require_init_token_dialog(root)
        if not identifier:
            return False

        messagebox.showinfo("Crear cuenta", "Ahora cree la cuenta de usuario para el programa.", parent=root)
        username = simpledialog.askstring("Usuario", "Nombre de usuario (ej: operador):", parent=root)
        if not username:
            return False

        while True:
            pwd1 = simpledialog.askstring("Contraseña", "Contraseña de usuario:", parent=root, show="*")
            if pwd1 is None:
                return False
            pwd2 = simpledialog.askstring("Confirmar contraseña", "Confirmar contraseña de usuario:", parent=root, show="*")
            if pwd2 is None:
                return False
            if pwd1 != pwd2:
                messagebox.showwarning("No coinciden", "Las contraseñas no coinciden. Intente nuevamente.", parent=root)
                continue
            if len(pwd1) < 6:
                messagebox.showwarning("Contraseña débil", "La contraseña debe tener al menos 6 caracteres.", parent=root)
                continue
            break

        while True:
            master1 = simpledialog.askstring("Contraseña maestra", "Contraseña maestra (para cambios/config):", parent=root, show="*")
            if master1 is None:
                return False
            master2 = simpledialog.askstring("Confirmar maestra", "Confirmar contraseña maestra:", parent=root, show="*")
            if master2 is None:
                return False
            if master1 != master2:
                messagebox.showwarning("No coinciden", "Las contraseñas maestras no coinciden. Intente nuevamente.", parent=root)
                continue
            if len(master1) < 6:
                messagebox.showwarning("Contraseña débil", "La contraseña maestra debe tener al menos 6 caracteres.", parent=root)
                continue
            break

        data = {
            "install_id": identifier,
            "created_at": time.time(),
            "user": {
                "username": username.strip(),
                "password": self.hash_password(pwd1),
            },
            "master": self.hash_password(master1)
        }
        self.save_credentials(data)
        messagebox.showinfo("Setup completado", "Credenciales creadas correctamente.", parent=root)
        return True

    def require_init_token_dialog(self, root) -> str:
        messagebox.showinfo(
            "Validación inicial necesaria",
            "Para crear las credenciales iniciales debe introducir un identificador y el token de activación.",
            parent=root,
        )
        for attempt in range(self.INIT_MAX_ATTEMPTS):
            identifier = simpledialog.askstring("Identificador de instalación", "Identificador (p.ej. CLIENTE-001):", parent=root)
            if identifier is None:
                return None
            token = simpledialog.askstring("Token de activación", "Token de activación:", parent=root)
            if token is None:
                return None
            if self.verify_init_token(identifier.strip(), token.strip()):
                return identifier.strip()
            else:
                messagebox.showerror("Token inválido", f"Token incorrecto. Intento {attempt+1}/{self.INIT_MAX_ATTEMPTS}", parent=root)
        messagebox.showerror("Activación fallida", "No se proporcionó un token válido.", parent=root)
        return None

    def change_credentials_dialog(self, root):
        """Dialogo para cambiar credenciales de usuario"""
        if not self.credentials_exist():
            messagebox.showerror("Error", "No hay credenciales para modificar.", parent=root)
            return

        creds = self.load_credentials()
        master_stored = creds.get("master", {})

        master_input = simpledialog.askstring("Confirmación maestra", "Ingrese la contraseña maestra para modificar credenciales:", parent=root, show="*")
        if master_input is None:
            return

        if not self.verify_password(master_input, master_stored):
            messagebox.showerror("Error", "Contraseña maestra incorrecta.", parent=root)
            return

        new_username = simpledialog.askstring("Nuevo usuario", "Nuevo nombre de usuario:", parent=root, initialvalue=creds["user"]["username"])
        if new_username is None:
            return

        while True:
            new_pwd1 = simpledialog.askstring("Nueva contraseña", "Nueva contraseña de usuario:", parent=root, show="*")
            if new_pwd1 is None:
                return
            new_pwd2 = simpledialog.askstring("Confirmar contraseña", "Confirmar nueva contraseña:", parent=root, show="*")
            if new_pwd2 is None:
                return
            if new_pwd1 != new_pwd2:
                messagebox.showwarning("No coinciden", "Las contraseñas no coinciden. Intente nuevamente.", parent=root)
                continue
            if len(new_pwd1) < 6:
                messagebox.showwarning("Contraseña débil", "La contraseña debe tener al menos 6 caracteres.", parent=root)
                continue
            break

        creds["user"]["username"] = new_username.strip()
        creds["user"]["password"] = self.hash_password(new_pwd1)
        self.save_credentials(creds)
        messagebox.showinfo("Credenciales actualizadas", "Credenciales de usuario actualizadas correctamente.", parent=root)

    def change_master_password_dialog(self, root):
        """Dialogo para cambiar contraseña maestra"""
        if not self.credentials_exist():
            messagebox.showerror("Error", "No hay credenciales para modificar.", parent=root)
            return

        creds = self.load_credentials()
        master_stored = creds.get("master", {})

        current_master = simpledialog.askstring("Confirmación maestra", "Ingrese la contraseña maestra actual:", parent=root, show="*")
        if current_master is None:
            return

        if not self.verify_password(current_master, master_stored):
            messagebox.showerror("Error", "Contraseña maestra actual incorrecta.", parent=root)
            return

        while True:
            new_master1 = simpledialog.askstring("Nueva contraseña maestra", "Nueva contraseña maestra:", parent=root, show="*")
            if new_master1 is None:
                return
            new_master2 = simpledialog.askstring("Confirmar maestra", "Confirmar nueva contraseña maestra:", parent=root, show="*")
            if new_master2 is None:
                return
            if new_master1 != new_master2:
                messagebox.showwarning("No coinciden", "Las contraseñas maestras no coinciden. Intente nuevamente.", parent=root)
                continue
            if len(new_master1) < 6:
                messagebox.showwarning("Contraseña débil", "La contraseña maestra debe tener al menos 6 caracteres.", parent=root)
                continue
            break

        creds["master"] = self.hash_password(new_master1)
        self.save_credentials(creds)
        messagebox.showinfo("Maestra actualizada", "Contraseña maestra actualizada correctamente.", parent=root)