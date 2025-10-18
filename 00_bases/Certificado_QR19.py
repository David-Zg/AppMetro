#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA INTEGRAL DE CERTIFICADOS CON QR - VERSIÓN MEJORADA
Combina gestión por magnitud con sistema completo de credenciales
"""

import os
import sys
import json
import time
import base64
import hmac
import hashlib
import secrets
import threading
import re
from glob import glob
from datetime import datetime
import shutil

import fitz
import qrcode
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from pydrive2.files import GoogleDriveFile
from asn1crypto import cms, x509

import tkinter as tk
from tkinter import simpledialog, filedialog, scrolledtext, ttk, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_ACTIVO = True
except ImportError:
    TkinterDnD = tk
    DND_ACTIVO = False

# ======================================================
# CLASE DE SEGURIDAD Y CREDENCIALES (DEL SEGUNDO CÓDIGO)
# ======================================================

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

# ======================================================
# CLASE PARA ANÁLISIS DE FIRMAS DIGITALES
# ======================================================

class SignatureAnalyzer:
    """Analiza firmas digitales en documentos PDF"""
    
    def __init__(self):
        self.regex_patron = re.compile(r"PT[-\s]?[A-Z0-9]+(?:[-\s/]?\d+){0,3}", re.I)
        self.regex_cert = re.compile(r"(LT[-\s]?\d{2,4}[-\s]?\d{3,6}|E\d{3,4}[-A-Z0-9]+[-]?\d{0,3})", re.I)
    
    def extraer_firmante_asn1(self, ruta_pdf):
        try:
            with open(ruta_pdf, "rb") as f:
                data = f.read()

            m = re.search(rb"/Contents\s*<([0-9A-Fa-f\s\n\r\t]+)>", data)
            if not m:
                return "No se encontró /Contents"

            hexdata = re.sub(rb"\s+", b"", m.group(1))
            firma_bin = bytes.fromhex(hexdata.decode("ascii", errors="ignore"))

            content = cms.ContentInfo.load(firma_bin)
            if content["content_type"].native != "signed_data":
                return "Firma inválida o formato desconocido"

            signed_data = content["content"]
            certs = signed_data["certificates"]
            if not certs:
                return "Sin certificados embebidos"

            firmantes = []
            for cert_obj in certs:
                cert = x509.Certificate.load(cert_obj.dump())
                subject = cert.subject.native
                cn = subject.get("common_name", "")
                org = subject.get("organization_name", "")
                if cn or org:
                    firmantes.append(f"{cn} ({org})" if org else cn)

            return ", ".join(firmantes) if firmantes else "Firmante no identificado"

        except Exception as e:
            return f"Error: {e}"

    def extraer_fecha_firma(self, ruta_pdf):
        try:
            with open(ruta_pdf, "rb") as f:
                data = f.read()
            m = re.search(rb"/M\s*\(D:([\d]{8,14})", data)
            if not m:
                return "—"
            raw = m.group(1).decode(errors="ignore")
            if len(raw) >= 14:
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]} {raw[8:10]}:{raw[10:12]}:{raw[12:14]}"
            elif len(raw) >= 8:
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
            return "—"
        except Exception:
            return "—"

    def analizar_pdf_firma(self, ruta_pdf):
        try:
            with open(ruta_pdf, "rb") as f:
                data = f.read()

            tiene_firma = b"/ByteRange" in data
            sub = None
            m = re.search(rb"/SubFilter\s*/([A-Za-z0-9\.\-]+)", data)
            if m:
                sub = m.group(1).decode(errors="ignore")

            fecha = self.extraer_fecha_firma(ruta_pdf)

            if tiene_firma and sub and ("CAdES" in sub or "pkcs7" in sub):
                firmante = self.extraer_firmante_asn1(ruta_pdf)
                return ("✅ Firmado", sub, firmante, fecha)
            else:
                return ("❌ No firmado", sub or "—", "—", "—")
        except Exception as e:
            return (f"⚠️ Error: {e}", "—", "—", "—")

    def verificar_si_pdf_firmado(self, ruta_pdf: str) -> bool:
        """Verifica si el PDF tiene una firma digital válida."""
        estado, _, _, _ = self.analizar_pdf_firma(ruta_pdf)
        return "✅ Firmado" in estado

# ======================================================
# CLASE PARA GESTIÓN DE CARPETAS POR MAGNITUD (MEJORADA)
# ======================================================

class MagnitudeManager:
    """Gestiona las carpetas por magnitud en Google Drive con configuración"""
    
    CONFIG_FILE = "drive_config.json"
    
    # Definición de magnitudes disponibles
    MAGNITUDES = {
        "temperatura": "🌡️ Temperatura",
        "masa": "⚖️ Masa", 
        "volumen": "🧪 Volumen",
        "longitud": "📏 Longitud",
        "presion": "🎯 Presión",
        "electricidad": "⚡ Electricidad",
        "tiempo": "⏰ Tiempo",
        "otros": "📁 Otros"
    }
    
    def __init__(self):
        self.drive = None
        self.folder_patrones = "1siUFkAiSHbiPH3YskX3DGFCJ1k8rbnRJ"
        self.folder_certificados = "1xHUXnymGCFHr58ptJTNhIHH8NhL3A9cr"
        self.folder_patrones_nombre = "No configurado"
        self.folder_certificados_nombre = "No configurado"
        self.magnitudes_config = {}
        self.magnitud_seleccionada = None
        self.load_config()
        
    def load_config(self):
        """Carga la configuración de carpetas desde archivo"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                
                self.folder_patrones = config_data.get("folder_patrones", self.folder_patrones)
                self.folder_certificados = config_data.get("folder_certificados", self.folder_certificados)
                self.folder_patrones_nombre = config_data.get("folder_patrones_nombre", "No configurado")
                self.folder_certificados_nombre = config_data.get("folder_certificados_nombre", "No configurado")
                self.magnitudes_config = config_data.get("magnitudes", {})
                return True
        except Exception as e:
            print(f"Error cargando configuración: {e}")
        return False
    
    def save_config(self):
        """Guarda la configuración completa"""
        config_data = {
            "folder_patrones": self.folder_patrones,
            "folder_certificados": self.folder_certificados,
            "folder_patrones_nombre": self.folder_patrones_nombre,
            "folder_certificados_nombre": self.folder_certificados_nombre,
            "magnitudes": self.magnitudes_config,
            "configurado_en": datetime.now().isoformat()
        }
        with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
    
    def autenticar(self):
        """Autentica con Google Drive"""
        gauth = GoogleAuth()

        # Verificar que exista el archivo client_secrets.json necesario para el flujo OAuth
        client_secrets_file = "client_secrets.json"
        if not os.path.exists(client_secrets_file):
            raise RuntimeError(
                "Archivo 'client_secrets.json' no encontrado en el directorio del proyecto.\n\n"
                "Instrucciones rápidas:\n"
                "1) Abra Google Cloud Console -> APIs & Services -> Credentials.\n"
                "2) Cree un OAuth 2.0 Client ID (Application type: Desktop app).\n"
                "3) Descargue el JSON resultante y guárdelo en esta carpeta como 'client_secrets.json'.\n\n"
                "También puede usar un service account, pero el flujo actual usa OAuth de usuario."
            )

        try:
            # Cargar credenciales almacenadas si existen
            gauth.LoadCredentialsFile("credentials.json")
            if gauth.credentials is None:
                # No hay credenciales guardadas: iniciar flujo web local (usa client_secrets.json)
                gauth.LocalWebserverAuth()
            elif gauth.access_token_expired:
                gauth.Refresh()
            else:
                gauth.Authorize()
        except Exception as e:
            # Intento de reintento para proporcionar mensaje más claro
            try:
                gauth.LocalWebserverAuth()
            except Exception as e2:
                raise RuntimeError(f"Error autenticación Drive: {e2}")
        # Guardar credenciales para futuros arranques
        gauth.SaveCredentialsFile("credentials.json")
        self.drive = GoogleDrive(gauth)
        return self.drive
# ...existing code...
    
    def configurar_carpetas_drive(self, root):
        """Permite configurar las carpetas de Drive mediante búsqueda interactiva"""
        
        def buscar_carpetas():
            try:
                # Buscar carpetas en el drive del usuario
                query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
                folders = self.drive.ListFile({'q': query}).GetList()
                
                # Limpiar lista
                lista_carpetas.delete(0, tk.END)
                
                for folder in folders:
                    lista_carpetas.insert(tk.END, f"{folder['title']} - {folder['id']}")
                    
                return len(folders)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudieron cargar las carpetas: {e}")
                return 0
        
        def seleccionar_carpeta(tipo):
            seleccion = lista_carpetas.curselection()
            if not seleccion:
                messagebox.showwarning("Selección requerida", "Por favor seleccione una carpeta de la lista.")
                return
            
            item_text = lista_carpetas.get(seleccion[0])
            folder_id = item_text.split(" - ")[-1]
            folder_name = item_text.split(" - ")[0]
            
            if tipo == "patrones":
                self.folder_patrones = folder_id
                self.folder_patrones_nombre = folder_name
                lbl_patrones.config(text=f"Patrones: {folder_name}")
            else:
                self.folder_certificados = folder_id
                self.folder_certificados_nombre = folder_name
                lbl_certificados.config(text=f"Certificados: {folder_name}")
        
        def guardar_configuracion():
            if not self.folder_patrones or not self.folder_certificados:
                messagebox.showwarning("Configuración incompleta", "Debe seleccionar ambas carpetas.")
                return
            
            # Crear subcarpetas de magnitudes automáticamente
            try:
                self.crear_subcarpetas_magnitudes()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudieron crear las subcarpetas: {e}")
                return
            
            self.save_config()
            
            messagebox.showinfo("Configuración guardada", 
                               f"Carpetas configuradas:\n\n"
                               f"📁 Patrones: {self.folder_patrones_nombre}\n"
                               f"📁 Certificados: {self.folder_certificados_nombre}\n\n"
                               f"✅ Subcarpetas de magnitudes creadas automáticamente.")
            config_window.destroy()
        
        # Crear ventana de configuración
        config_window = tk.Toplevel(root)
        config_window.title("Configuración de Carpetas Google Drive")
        config_window.geometry("700x500")
        config_window.configure(bg="#e9eef7")
        config_window.resizable(False, False)
        config_window.transient(root)
        config_window.grab_set()
        
        self.center_window(config_window)
        
        # Header
        header_frame = tk.Frame(config_window, bg="#1f618d")
        header_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(header_frame, text="Configuración de Carpetas Google Drive", 
                 bg="#1f618d", fg="white", font=("Segoe UI", 14, "bold")).pack(pady=15)
        
        # Instrucciones
        instrucciones = tk.Label(config_window, 
                                text="Seleccione las carpetas de Google Drive donde se almacenarán los archivos:",
                                bg="#e9eef7", fg="#2c3e50", font=("Segoe UI", 11), justify=tk.LEFT)
        instrucciones.pack(pady=(0, 15), padx=20, anchor="w")
        
        # Frame para carpetas seleccionadas
        selected_frame = tk.Frame(config_window, bg="#e9eef7")
        selected_frame.pack(fill=tk.X, pady=(0, 15), padx=20)
        
        lbl_patrones = tk.Label(selected_frame, text=f"Patrones: {self.folder_patrones_nombre}", 
                               bg="#e9eef7", fg="#e67e22", font=("Segoe UI", 10, "bold"))
        lbl_patrones.pack(anchor="w")
        
        lbl_certificados = tk.Label(selected_frame, text=f"Certificados: {self.folder_certificados_nombre}", 
                                   bg="#e9eef7", fg="#27ae60", font=("Segoe UI", 10, "bold"))
        lbl_certificados.pack(anchor="w")
        
        # Frame para búsqueda y lista
        search_frame = tk.LabelFrame(config_window, text="📁 Carpetas disponibles en Google Drive", 
                                    bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 11, "bold"))
        search_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        
        # Botones de búsqueda
        btn_frame = tk.Frame(search_frame, bg="#e9eef7")
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(btn_frame, text="🔄 Actualizar lista de carpetas", 
                  command=buscar_carpetas, bg="#3498db", fg="white",
                  font=("Segoe UI", 10), relief=tk.FLAT, padx=15, pady=5).pack(side=tk.LEFT)
        
        # Lista de carpetas
        list_frame = tk.Frame(search_frame, bg="#e9eef7")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        lista_carpetas = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Consolas", 9))
        lista_carpetas.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=lista_carpetas.yview)
        
        # Botones de selección
        select_frame = tk.Frame(search_frame, bg="#e9eef7")
        select_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(select_frame, text="📋 Seleccionar para Patrones", 
                  command=lambda: seleccionar_carpeta("patrones"),
                  bg="#e67e22", fg="white", font=("Segoe UI", 10),
                  relief=tk.FLAT, padx=10, pady=5).pack(side=tk.LEFT, padx=5)
        
        tk.Button(select_frame, text="📄 Seleccionar para Certificados", 
                  command=lambda: seleccionar_carpeta("certificados"),
                  bg="#27ae60", fg="white", font=("Segoe UI", 10),
                  relief=tk.FLAT, padx=10, pady=5).pack(side=tk.LEFT, padx=5)
        
        # Botones finales
        button_frame = tk.Frame(config_window, bg="#e9eef7")
        button_frame.pack(fill=tk.X, padx=20, pady=15)
        
        tk.Button(button_frame, text="💾 Guardar Configuración", 
                  command=guardar_configuracion, bg="#2ecc71", fg="white",
                  font=("Segoe UI", 11, "bold"), relief=tk.FLAT, padx=20, pady=8).pack(side=tk.RIGHT, padx=5)
        
        tk.Button(button_frame, text="❌ Cancelar", 
                  command=config_window.destroy, bg="#95a5a6", fg="white",
                  font=("Segoe UI", 11), relief=tk.FLAT, padx=20, pady=8).pack(side=tk.RIGHT, padx=5)
        
        # Cargar carpetas automáticamente al abrir
        config_window.after(100, buscar_carpetas)
    
    def crear_subcarpetas_magnitudes(self):
        """Crea las subcarpetas de magnitudes si no existen"""
        try:
            for magnitud_key, magnitud_nombre in self.MAGNITUDES.items():
                if magnitud_key not in self.magnitudes_config:
                    # Verificar si ya existe una carpeta con ese nombre
                    query = f"'{self.folder_certificados}' in parents and title='{magnitud_nombre}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                    folders = self.drive.ListFile({'q': query}).GetList()
                    
                    if folders:
                        # Usar la carpeta existente
                        self.magnitudes_config[magnitud_key] = {
                            "id": folders[0]['id'],
                            "nombre": magnitud_nombre,
                            "creada_el": datetime.now().isoformat()
                        }
                    else:
                        # Crear nueva carpeta
                        folder = self.drive.CreateFile({
                            'title': magnitud_nombre,
                            'parents': [{'id': self.folder_certificados}],
                            'mimeType': 'application/vnd.google-apps.folder'
                        })
                        folder.Upload()
                        
                        self.magnitudes_config[magnitud_key] = {
                            "id": folder['id'],
                            "nombre": magnitud_nombre,
                            "creada_el": datetime.now().isoformat()
                        }
            
            self.save_config()
            return True
            
        except Exception as e:
            raise RuntimeError(f"Error creando subcarpetas: {e}")
    
    def get_folder_id_magnitud(self, magnitud_key):
        """Obtiene el ID de la carpeta para una magnitud específica"""
        if magnitud_key in self.magnitudes_config:
            return self.magnitudes_config[magnitud_key]["id"]
        return self.folder_certificados  # Fallback a carpeta principal
    
    def subir_pdf(self, ruta_pdf: str, magnitud_key: str = None) -> tuple[str, str, str, str]:
        """Sube un PDF a la carpeta de magnitud específica"""
        if not magnitud_key:
            magnitud_key = self.magnitud_seleccionada or "otros"
        
        nombre = os.path.basename(ruta_pdf)
        folder_id = self.get_folder_id_magnitud(magnitud_key)
        
        # Verificar si el archivo ya existe en esa carpeta
        query = f"title = '{nombre}' and trashed = false and '{folder_id}' in parents"
        file_list = self.drive.ListFile({'q': query}).GetList()

        if file_list:
            file = file_list[0]
            file_id = file['id']
            enlace = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
            file.SetContentFile(ruta_pdf)
            file.Upload()
            return file_id, enlace, "reemplazado 🔁", magnitud_key
        else:
            file = self.drive.CreateFile({
                'title': nombre, 
                'parents': [{'id': folder_id}]
            })
            file.SetContentFile(ruta_pdf)
            file.Upload()
            file.InsertPermission({
                'type': 'anyone', 
                'value': 'anyone', 
                'role': 'reader'
            })
            file_id = file['id']
            enlace = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
            return file_id, enlace, "nuevo ☁️", magnitud_key
    
    def buscar_en_drive_patrones(self, cert: str, patron: str) -> str | None:
        """Busca archivos en la carpeta de PATRONES"""
        try:
            candidatos = []
            
            if cert:
                query_cert = f"'{self.folder_patrones}' in parents and trashed=false and title contains '{cert}'"
                res_cert = self.drive.ListFile({'q': query_cert}).GetList()
                candidatos = res_cert
            
            if not candidatos and patron:
                query_pat = f"'{self.folder_patrones}' in parents and trashed=false and title contains '{patron}'"
                candidatos = self.drive.ListFile({'q': query_pat}).GetList()
            
            if not candidatos:
                return None
                
            file = sorted(candidatos, key=lambda x: x['modifiedDate'], reverse=True)[0]
            return f"https://drive.google.com/file/d/{file['id']}/view?usp=sharing"
        except Exception as e:
            raise RuntimeError(f"Error buscando en Drive: {e}")

    def center_window(self, window):
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry('{}x{}+{}+{}'.format(width, height, x, y))

# ======================================================
# CLASE PARA LA INTERFAZ DE SELECCIÓN DE MAGNITUD
# ======================================================

class MagnitudeSelector:
    """Interfaz para seleccionar la magnitud del certificado"""
    
    def __init__(self, parent, magnitude_manager):
        self.parent = parent
        self.magnitude_manager = magnitude_manager
        self.selected_magnitude = None
        
    def show_selector(self):
        """Muestra el selector de magnitud y retorna la selección"""
        selector_window = tk.Toplevel(self.parent)
        selector_window.title("Seleccionar Magnitud del Certificado")
        selector_window.geometry("500x500")
        selector_window.configure(bg="#e9eef7")
        selector_window.resizable(True, True)
        selector_window.transient(self.parent)
        selector_window.grab_set()
        
        self.center_window(selector_window)
        
        # Header
        header_frame = tk.Frame(selector_window, bg="#1f618d")
        header_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(header_frame, text="Seleccionar Magnitud del Certificado", 
                bg="#1f618d", fg="white", font=("Segoe UI", 14, "bold")).pack(pady=15)
        
        # Instrucciones
        instrucciones = tk.Label(selector_window, 
                                text="Seleccione el tipo de magnitud para clasificar el certificado:",
                                bg="#e9eef7", fg="#2c3e50", font=("Segoe UI", 11), 
                                justify=tk.LEFT, wraplength=450)
        instrucciones.pack(pady=(0, 15), padx=20, anchor="w")
        
        # Frame principal con scrollbar
        main_frame = tk.Frame(selector_window, bg="#e9eef7")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        
        # Canvas y scrollbar
        canvas = tk.Canvas(main_frame, bg="#e9eef7", highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#e9eef7")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Frame para botones de magnitud dentro del frame desplazable
        magnitudes_frame = tk.Frame(scrollable_frame, bg="#e9eef7")
        magnitudes_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Crear botones para cada magnitud
        self.magnitude_var = tk.StringVar()
        
        for i, (magnitud_key, magnitud_nombre) in enumerate(self.magnitude_manager.MAGNITUDES.items()):
            # Frame para cada opción de magnitud
            option_frame = tk.Frame(magnitudes_frame, bg="#e9eef7")
            option_frame.pack(fill=tk.X, pady=8)
            
            # Radio button
            btn = tk.Radiobutton(
                option_frame,
                text=magnitud_nombre,
                variable=self.magnitude_var,
                value=magnitud_key,
                bg="#e9eef7",
                fg="#2c3e50",
                font=("Segoe UI", 11, "bold"),
                selectcolor="#d5dbdb",
                indicatoron=1,
                width=20,
                anchor="w"
            )
            btn.pack(side=tk.LEFT, padx=(10, 0))
            
            # Mostrar estado de configuración
            folder_id = self.magnitude_manager.get_folder_id_magnitud(magnitud_key)
            if folder_id != self.magnitude_manager.folder_certificados:
                status_text = "✅ Configurada"
                status_color = "#27ae60"
            else:
                status_text = "⚠️ Por configurar"
                status_color = "#f39c12"
            
            status_label = tk.Label(
                option_frame,
                text=status_text,
                bg="#e9eef7",
                fg=status_color,
                font=("Segoe UI", 9),
                padx=10
            )
            status_label.pack(side=tk.RIGHT, padx=(0, 10))
        
        # Configurar el canvas y scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Botones de acción
        button_frame = tk.Frame(selector_window, bg="#e9eef7")
        button_frame.pack(fill=tk.X, padx=20, pady=15)
        
        # Botón ACEPTAR (más prominente)
        tk.Button(button_frame, text="✅ ACEPTAR", 
                 command=lambda: self.confirm_selection(selector_window),
                 bg="#27ae60", fg="white", font=("Segoe UI", 12, "bold"),
                 relief=tk.RAISED, padx=25, pady=10, cursor="hand2",
                 borderwidth=2).pack(side=tk.RIGHT, padx=10)
        
        # Botón CANCELAR
        tk.Button(button_frame, text="❌ CANCELAR", 
                 command=selector_window.destroy,
                 bg="#e74c3c", fg="white", font=("Segoe UI", 11),
                 relief=tk.RAISED, padx=20, pady=8, cursor="hand2").pack(side=tk.RIGHT, padx=5)
        
        # Configurar eventos de teclado
        selector_window.bind('<Return>', lambda e: self.confirm_selection(selector_window))
        selector_window.bind('<Escape>', lambda e: selector_window.destroy())
        
        # Seleccionar "temperatura" por defecto
        self.magnitude_var.set("temperatura")
        
        # Hacer focus en la ventana
        selector_window.focus_set()
        
        selector_window.wait_window()
        return self.selected_magnitude
    
    def confirm_selection(self, window):
        """Confirma la selección y cierra la ventana"""
        if self.magnitude_var.get():
            self.selected_magnitude = self.magnitude_var.get()
            window.destroy()
        else:
            messagebox.showwarning("Selección requerida", "Por favor seleccione una magnitud.", parent=window)
    
    def center_window(self, window):
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry('{}x{}+{}+{}'.format(width, height, x, y))

# ======================================================
# CLASE PDFProcessor MEJORADA
# ======================================================

class PDFProcessor:
    """Procesa documentos PDF (vinculación, QR, etc.) - MEJORADA"""
    
    def __init__(self, magnitude_manager, signature_analyzer):
        self.magnitude_manager = magnitude_manager
        self.signature_analyzer = signature_analyzer
        self.qr_size = 40
        self.temp_pdf = "temp_output.pdf"
        self.log_file = "vinculados.json"
        self.log_error_file = "errores_qr_log.txt"
    
    def procesar_vinculacion_pdf(self, ruta_pdf: str, log_widget: scrolledtext.ScrolledText, 
                               root: tk.Tk, callback, progress: ttk.Progressbar | None, 
                               lbl_estado_global: tk.Label):
        """Procesa vinculación de patrones en PDF"""
        def _run():
            nombre = os.path.basename(ruta_pdf)
            temp_path = os.path.join(os.path.dirname(ruta_pdf), self.temp_pdf)

            cambios_realizados = False
            total_vinculos = 0
            pares = []
            
            try:
                log_widget.insert(tk.END, f"\n🔗 Procesando vinculación: {nombre}\n", "proceso")
                log_widget.see(tk.END)
                
                shutil.copy2(ruta_pdf, temp_path)
                doc = fitz.open(temp_path)

                for page_index, page in enumerate(doc):
                    texto = page.get_text("text")
                    patrones = self.signature_analyzer.regex_patron.findall(texto)
                    
                    cert_doc_match = self.signature_analyzer.regex_cert.search(texto)
                    cert_asociado = cert_doc_match.group(0).strip() if cert_doc_match else ""

                    patrones_unicos = sorted(list(set(patrones))) 

                    if not patrones_unicos:
                        continue

                    for patron in patrones_unicos:
                        enlace = self.magnitude_manager.buscar_en_drive_patrones(cert_asociado, patron)
                        
                        if not enlace:
                            continue 

                        areas_texto = page.search_for(patron)
                        
                        if not areas_texto:
                            continue

                        for area in areas_texto:
                            try:
                                rect_expandido = fitz.Rect(area.x0 - 2, area.y0 - 2, area.x1 + 2, area.y1 + 2)
                                page.insert_link({
                                    "kind": fitz.LINK_URI,
                                    "from": rect_expandido,
                                    "uri": enlace
                                })
                                total_vinculos += 1
                                cambios_realizados = True
                            except Exception:
                                pass

                        pares.append({"patron": patron, "certificado": cert_asociado, "enlace": enlace})

                doc.save(ruta_pdf, garbage=4, deflate=True)
                doc.close()
                
                if cambios_realizados:
                    self.guardar_log_vinculacion(pares)
                    log_widget.insert(tk.END, f"   ✅ VINCULACIÓN COMPLETA: {nombre} actualizado con {total_vinculos} vínculo(s).\n", "success")
                else:
                    log_widget.insert(tk.END, f"   ℹ️ VINCULACIÓN INCOMPLETA: {nombre}. No se encontraron patrones válidos.\n", "info")

            except Exception as e:
                error_msg = str(e)
                log_widget.insert(tk.END, f"   ❌ ERROR EN VINCULACIÓN: {error_msg}\n", "error")
                with open(self.log_error_file, "a", encoding="utf-8") as ferr:
                    ferr.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | VINCULACIÓN | {nombre} | {error_msg}\n")
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

                if progress:
                    progress.step()
                root.after(100, callback, ruta_pdf)
                lbl_estado_global.config(text=f"Vinculación completada: {nombre}", fg="#1a5276")

        threading.Thread(target=_run).start()
    
    def guardar_log_vinculacion(self, entradas):
        data = {}
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        for e in entradas:
            data[e["patron"]] = {"certificado": e["certificado"], "enlace": e["enlace"]}
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def procesar_pdf_con_qr(self, ruta_pdf: str, log_widget: scrolledtext.ScrolledText, 
                          root: tk.Tk, callback, progress: ttk.Progressbar | None, 
                          lbl_estado_global: tk.Label, app_instance):
        """Procesa PDF completo - MEJORADO para usar magnitud"""
        def _run():
            nombre = os.path.basename(ruta_pdf)
            ruta_para_subir_temporal = None
            
            estado_firma, subfilter, firmante, fecha_firma = self.signature_analyzer.analizar_pdf_firma(ruta_pdf)
            esta_firmado = "✅ Firmado" in estado_firma

            root.after(0, lambda: app_instance.actualizar_tabla_firmas(
                ruta_pdf, estado_firma, subfilter, firmante, fecha_firma,
                self.magnitude_manager.magnitud_seleccionada
            ))

            try:
                magnitud_actual = self.magnitude_manager.magnitud_seleccionada or "otros"
                nombre_magnitud = self.magnitude_manager.MAGNITUDES[magnitud_actual]
                
                if esta_firmado:
                    log_widget.insert(tk.END, f"\n📄 PDF FIRMADO detectado: {nombre}\n", "proceso")
                    log_widget.see(tk.END)

                    file_id, enlace, modo, magnitud = self.magnitude_manager.subir_pdf(ruta_pdf, magnitud_actual)
                    log_widget.insert(tk.END, f"   ✅ REEMPLAZO EN DRIVE: {nombre} ({modo}).\n", "success")
                    log_widget.insert(tk.END, f"   📁 Carpeta: {nombre_magnitud}\n", "magnitud")
                    log_widget.insert(tk.END, f"   🔗 Enlace: {enlace}\n", "enlace")
                    
                else:
                    log_widget.insert(tk.END, f"\n📱 Procesando PDF NO FIRMADO: {nombre}\n", "proceso")
                    log_widget.see(tk.END)

                    file_id, enlace, modo, magnitud = self.magnitude_manager.subir_pdf(ruta_pdf, magnitud_actual)
                    ruta_qr = self.generar_qr(enlace)
                    ruta_con_qr, sobrescrito = self.insertar_qr_en_pdf(ruta_pdf, ruta_qr)
                    
                    if not sobrescrito:
                        ruta_para_subir_temporal = ruta_con_qr 

                    file = self.magnitude_manager.drive.CreateFile({'id': file_id})
                    file.SetContentFile(ruta_con_qr)
                    file.Upload()

                    log_widget.insert(tk.END, f"   ✅ QR INSERTADO Y SUBIDO: {nombre} ({modo}).\n", "success")
                    log_widget.insert(tk.END, f"   📁 Carpeta: {nombre_magnitud}\n", "magnitud")
                    log_widget.insert(tk.END, f"   🔗 Enlace: {enlace}\n", "enlace")

            except Exception as e:
                error_msg = str(e)
                log_widget.insert(tk.END, f"   ❌ Error en proceso: {error_msg}\n", "error")
                with open(self.log_error_file, "a", encoding="utf-8") as ferr:
                    ferr.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | QR | {nombre} | {error_msg}\n")

            finally:
                self.limpiar_temporales_individual(ruta_para_subir_temporal)

                if progress:
                    progress.step()
                root.after(100, callback)
                lbl_estado_global.config(text=f"Proceso completado: {nombre}", fg="#1a5276")

        threading.Thread(target=_run).start()

    def generar_qr(self, enlace, salida="qr_temp.png"):
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=2)
        qr.add_data(enlace)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(salida)
        return salida

    def buscar_palabra_coordenadas(self, ruta_pdf, palabra="QR"):
        try:
            doc = fitz.open(ruta_pdf)
            pagina = doc[0]
            resultados = pagina.search_for(palabra)
            doc.close()
            if resultados:
                return resultados[0]
            else:
                return None
        except Exception:
            return None

    def insertar_qr_en_pdf(self, ruta_pdf, ruta_qr):
        doc = None
        try:
            doc = fitz.open(ruta_pdf)
            pagina = doc[0]

            rect_palabra = self.buscar_palabra_coordenadas(ruta_pdf, "QR")

            if rect_palabra:
                x_centro = (rect_palabra.x0 + rect_palabra.x1) / 2
                y_centro = (rect_palabra.y0 + rect_palabra.y1) / 2
                rect = fitz.Rect(x_centro - self.qr_size / 2, y_centro - self.qr_size / 2, 
                               x_centro + self.qr_size / 2, y_centro + self.qr_size / 2)
            else:
                rect = fitz.Rect(pagina.rect.width - self.qr_size - 30, pagina.rect.height - self.qr_size - 30, 
                               pagina.rect.width - 30, pagina.rect.height - 30)

            pagina.insert_image(rect, filename=ruta_qr)
            doc.save(ruta_pdf, garbage=4, deflate=True, clean=True)
            return ruta_pdf, True

        except Exception as e:
            try:
                if doc is not None:
                    temp_path = os.path.splitext(ruta_pdf)[0] + "_temp_qr.pdf"
                    doc.save(temp_path, garbage=4, deflate=True, clean=True)
                    doc.close()
                    return temp_path, False
            except Exception:
                pass
            raise RuntimeError(f"No se pudo insertar QR: {str(e)}")
        finally:
            if doc is not None and not doc.is_closed:
                doc.close()

    def limpiar_temporales_individual(self, ruta_archivo_temporal=None):
        try:
            if os.path.exists("qr_temp.png"):
                os.remove("qr_temp.png")
        except Exception:
            pass

        if ruta_archivo_temporal and ruta_archivo_temporal.endswith("_temp_qr.pdf") and os.path.exists(ruta_archivo_temporal):
            try:
                os.remove(ruta_archivo_temporal)
            except Exception:
                pass

    def limpiar_directorio_temporal_global(self):
        archivos_temporales = [
            self.temp_pdf,
            "qr_temp.png",
            "temp_vinculacion.pdf"
        ]
        
        patrones_temporales = [
            "*_temp_qr.pdf",
            "temp_*.pdf",
            "*_vinculacion.pdf"
        ]
        
        for archivo in archivos_temporales:
            if os.path.exists(archivo):
                try:
                    os.remove(archivo)
                except Exception:
                    pass
        
        for patron in patrones_temporales:
            for archivo in glob(patron):
                try:
                    os.remove(archivo)
                except Exception:
                    pass

# ======================================================
# CLASE PRINCIPAL DE LA APLICACIÓN (MEJORADA)
# ======================================================

class CertificadosApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema Integral de Certificados con QR - Por Magnitud")
        self.root.geometry("900x700")
        self.root.configure(bg="#e9eef7")
        
        # Inicializar managers
        self.security_manager = SecurityManager()
        self.magnitude_manager = MagnitudeManager()
        self.signature_analyzer = SignatureAnalyzer()
        self.pdf_processor = PDFProcessor(self.magnitude_manager, self.signature_analyzer)
        
        # Variables de estado
        self.archivos_pendientes = []
        self.procesando = False
        self.archivos_procesados = 0
        self.total_archivos = 0
        self.datos_firmas = []
        
        # Elementos de UI
        self.progress = None
        self.lbl_estado_global = None
        self.log_widget = None
        self.btn_procesar = None
        self.tree_firmas = None
        self.lista_archivos = None
        self.lbl_magnitud_actual = None
        self.lbl_magnitud_archivos = None
        
        self.setup_ui()
        self.inicializar_drive()
    
    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg="#1f618d")
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header_frame, text="SISTEMA INTEGRAL DE CERTIFICADOS CON QR", 
                bg="#1f618d", fg="white", font=("Segoe UI", 16, "bold")).pack(pady=10)
        
        # Barra de información de magnitud actual
        info_frame = tk.Frame(header_frame, bg="#1a5276")
        info_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.lbl_magnitud_actual = tk.Label(info_frame, 
                                          text="🌡️ Magnitud actual: Temperatura", 
                                          bg="#1a5276", fg="white", 
                                          font=("Segoe UI", 10, "bold"))
        self.lbl_magnitud_actual.pack(side=tk.LEFT)
        
        tk.Button(info_frame, text="📁 Cambiar Magnitud", 
                 command=self.cambiar_magnitud,
                 bg="#3498db", fg="white", font=("Segoe UI", 9),
                 relief=tk.FLAT, padx=10, pady=2).pack(side=tk.RIGHT)
        
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        tab_procesamiento = tk.Frame(notebook, bg="#e9eef7")
        notebook.add(tab_procesamiento, text="🔄 Procesamiento")
        self.setup_tab_procesamiento(tab_procesamiento)
        
        tab_firmas = tk.Frame(notebook, bg="#e9eef7")
        notebook.add(tab_firmas, text="📋 Información de Firmas")
        self.setup_tab_firmas(tab_firmas)
        
        # Actualizar display de magnitud actual
        self.actualizar_display_magnitud()
    
    def setup_tab_procesamiento(self, parent):
        file_frame = tk.LabelFrame(parent, text="📁 Archivos PDF a procesar", 
                                  bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 11, "bold"))
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_frame = tk.Frame(file_frame, bg="#e9eef7")
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(btn_frame, text="📂 Seleccionar archivos PDF", command=self.seleccionar_archivos,
                 bg="#3498db", fg="white", font=("Segoe UI", 10, "bold"), 
                 relief=tk.FLAT, padx=15, pady=8).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="🗑️ Limpiar TODO", command=self.limpiar_todo,
                 bg="#e74c3c", fg="white", font=("Segoe UI", 10, "bold"), 
                 relief=tk.FLAT, padx=15, pady=8).pack(side=tk.LEFT, padx=5)
        
        self.lista_archivos = tk.Listbox(file_frame, height=6, font=("Segoe UI", 9))
        self.lista_archivos.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        # Información de magnitud en el panel de archivos
        magnitud_info = tk.Frame(file_frame, bg="#e9eef7")
        magnitud_info.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.lbl_magnitud_archivos = tk.Label(magnitud_info, 
                                            text="Los archivos se guardarán en: 🌡️ Temperatura",
                                            bg="#e9eef7", fg="#e67e22", font=("Segoe UI", 9, "bold"))
        self.lbl_magnitud_archivos.pack(anchor="w")
        
        progress_frame = tk.LabelFrame(parent, text="📊 Progreso", 
                                      bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 11, "bold"))
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=10)
        
        self.lbl_estado_global = tk.Label(progress_frame, text="Esperando archivos...", 
                                         bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        self.lbl_estado_global.pack(pady=(0, 10))
        
        log_frame = tk.LabelFrame(parent, text="📝 Log de Procesamiento", 
                                 bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 11, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=15, font=("Consolas", 9))
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_widget.config(state=tk.DISABLED)
        
        # Configurar tags para el log
        for tag, color in [("proceso", "#1f618d"), ("success", "#27ae60"), 
                          ("error", "#e74c3c"), ("info", "#f39c12"), 
                          ("enlace", "#3498db"), ("magnitud", "#9b59b6")]:
            self.log_widget.tag_config(tag, foreground=color, font=("Consolas", 9, "bold"))
        
        action_frame = tk.Frame(parent, bg="#e9eef7")
        action_frame.pack(fill=tk.X, pady=10)
        
        self.btn_procesar = tk.Button(action_frame, text="🚀 INICIAR PROCESAMIENTO", 
                                    command=self.iniciar_procesamiento,
                                    bg="#27ae60", fg="white", font=("Segoe UI", 12, "bold"), 
                                    relief=tk.FLAT, padx=20, pady=12)
        self.btn_procesar.pack(side=tk.LEFT, padx=5)
        
        tk.Button(action_frame, text="⚙️ Configuración", command=self.mostrar_configuracion,
                 bg="#95a5a6", fg="white", font=("Segoe UI", 10, "bold"), 
                 relief=tk.FLAT, padx=15, pady=8).pack(side=tk.RIGHT, padx=5)
        
        if DND_ACTIVO:
            self.lista_archivos.drop_target_register(DND_FILES)
            self.lista_archivos.dnd_bind('<<Drop>>', self.archivos_arrastrados)
    
    def setup_tab_firmas(self, parent):
        info_frame = tk.LabelFrame(parent, text="ℹ️ Información", 
                                  bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 11, "bold"))
        info_frame.pack(fill=tk.X, pady=(0, 10), padx=10)
        
        info_text = tk.Label(info_frame, 
                            text="La información de firmas se genera automáticamente durante el procesamiento.",
                            bg="#e9eef7", fg="#7f8c8d", font=("Segoe UI", 9), justify=tk.LEFT)
        info_text.pack(padx=10, pady=10)
        
        results_frame = tk.LabelFrame(parent, text="📊 Resultados de Firmas Digitales", 
                                     bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 11, "bold"))
        results_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        columns = ("Archivo", "Estado", "Firmante", "Fecha", "Tipo", "Magnitud")
        self.tree_firmas = ttk.Treeview(results_frame, columns=columns, show="headings", height=12)
        
        for col in columns:
            self.tree_firmas.heading(col, text=col)
        
        self.tree_firmas.column("Archivo", width=180)
        self.tree_firmas.column("Estado", width=80)
        self.tree_firmas.column("Firmante", width=180)
        self.tree_firmas.column("Fecha", width=100)
        self.tree_firmas.column("Tipo", width=120)
        self.tree_firmas.column("Magnitud", width=100)
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree_firmas.yview)
        self.tree_firmas.configure(yscrollcommand=scrollbar.set)
        
        self.tree_firmas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=10)
    
    def cambiar_magnitud(self):
        """Permite cambiar la magnitud seleccionada"""
        selector = MagnitudeSelector(self.root, self.magnitude_manager)
        nueva_magnitud = selector.show_selector()
        
        if nueva_magnitud:
            self.magnitude_manager.magnitud_seleccionada = nueva_magnitud
            self.actualizar_display_magnitud()
            self._insertar_log(f"📁 Magnitud cambiada a: {self.magnitude_manager.MAGNITUDES[nueva_magnitud]}\n", "magnitud")
    
    def actualizar_display_magnitud(self):
        """Actualiza los displays de magnitud en la interfaz"""
        magnitud_actual = self.magnitude_manager.magnitud_seleccionada or "temperatura"
        nombre_magnitud = self.magnitude_manager.MAGNITUDES[magnitud_actual]
        
        self.lbl_magnitud_actual.config(text=f"📁 Magnitud actual: {nombre_magnitud}")
        self.lbl_magnitud_archivos.config(text=f"Los archivos se guardarán en: {nombre_magnitud}")
    
    def inicializar_drive(self):
        try:
            self.magnitude_manager.autenticar()
            self._insertar_log("✅ Autenticación con Google Drive exitosa.\n", "success")
            
            # Crear subcarpetas de magnitudes si no existen
            self.magnitude_manager.crear_subcarpetas_magnitudes()
            self._insertar_log("✅ Subcarpetas de magnitudes configuradas.\n", "success")
            
        except Exception as e:
            self._insertar_log(f"❌ Error autenticando con Google Drive: {e}\n", "error")
            messagebox.showerror("Error de Autenticación", f"No se pudo autenticar con Google Drive:\n{e}")
    
    def _insertar_log(self, mensaje, tag=None):
        self.log_widget.config(state=tk.NORMAL)
        if tag:
            self.log_widget.insert(tk.END, mensaje, tag)
        else:
            self.log_widget.insert(tk.END, mensaje)
        self.log_widget.see(tk.END)
        self.log_widget.config(state=tk.DISABLED)
    
    def seleccionar_archivos(self):
        archivos = filedialog.askopenfilenames(
            title="Seleccionar archivos PDF",
            filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")]
        )
        if archivos:
            self.agregar_archivos(archivos)
    
    def archivos_arrastrados(self, event):
        if DND_ACTIVO:
            archivos = self.root.tk.splitlist(event.data)
            archivos_pdf = [f for f in archivos if f.lower().endswith('.pdf')]
            if archivos_pdf:
                self.agregar_archivos(archivos_pdf)
    
    def agregar_archivos(self, archivos):
        for archivo in archivos:
            if archivo not in self.archivos_pendientes:
                self.archivos_pendientes.append(archivo)
                nombre = os.path.basename(archivo)
                self.lista_archivos.insert(tk.END, nombre)
        self.actualizar_estado()
    
    def actualizar_estado(self):
        total = len(self.archivos_pendientes)
        self.lbl_estado_global.config(text=f"Archivos listos: {total}")
        self.btn_procesar.config(state=tk.NORMAL if total > 0 else tk.DISABLED, 
                               bg="#27ae60" if total > 0 else "#95a5a6")
    
    def limpiar_todo(self):
        self.procesando = False
        self.archivos_pendientes.clear()
        self.lista_archivos.delete(0, tk.END)
        self.archivos_procesados = 0
        self.total_archivos = 0
        self.progress["value"] = 0
        self.progress["maximum"] = 100
        
        self.log_widget.config(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.config(state=tk.DISABLED)
        
        self.limpiar_tabla_firmas()
        self.lbl_estado_global.config(text="Esperando archivos...", fg="#1f618d")
        self.btn_procesar.config(state=tk.NORMAL, bg="#27ae60")
        self.pdf_processor.limpiar_directorio_temporal_global()
        self._insertar_log("🧹 TODO ha sido limpiado correctamente.\n", "success")
    
    def limpiar_tabla_firmas(self):
        """Limpia la tabla de información de firmas"""
        for item in self.tree_firmas.get_children():
            self.tree_firmas.delete(item)
        self.datos_firmas.clear()
    
    def actualizar_tabla_firmas(self, ruta_pdf, estado, tipo, firmante, fecha, magnitud):
        """Actualiza la tabla de firmas con la información del archivo procesado"""
        nombre_archivo = os.path.basename(ruta_pdf)
        nombre_magnitud = self.magnitude_manager.MAGNITUDES.get(magnitud, magnitud)
        
        # Agregar a la lista de datos
        self.datos_firmas.append({
            "archivo": nombre_archivo,
            "estado": estado,
            "tipo": tipo,
            "firmante": firmante,
            "fecha": fecha,
            "magnitud": nombre_magnitud
        })
        
        # Actualizar la tabla
        self.tree_firmas.insert("", "end", values=(
            nombre_archivo, estado, firmante, fecha, tipo, nombre_magnitud
        ))
    
    def iniciar_procesamiento(self):
        if not self.archivos_pendientes or self.procesando:
            return
        
        # Verificar si hay magnitud seleccionada
        if not self.magnitude_manager.magnitud_seleccionada:
            self.cambiar_magnitud()
            if not self.magnitude_manager.magnitud_seleccionada:
                messagebox.showwarning("Magnitud no seleccionada", 
                                     "Debe seleccionar una magnitud antes de procesar.")
                return
        
        self.procesando = True
        self.archivos_procesados = 0
        self.total_archivos = len(self.archivos_pendientes)
        
        self.progress.config(maximum=self.total_archivos)
        self.progress["value"] = 0
        self.btn_procesar.config(state=tk.DISABLED, bg="#95a5a6")
        
        self.log_widget.config(state=tk.NORMAL)
        self.log_widget.delete(1.0, tk.END)
        
        magnitud_nombre = self.magnitude_manager.MAGNITUDES[self.magnitude_manager.magnitud_seleccionada]
        self._insertar_log(f"🚀 INICIANDO PROCESAMIENTO DE {self.total_archivos} ARCHIVO(S)\n", "proceso")
        self._insertar_log(f"📁 Magnitud seleccionada: {magnitud_nombre}\n\n", "magnitud")
        
        self.procesar_siguiente_archivo()
    
    def procesar_siguiente_archivo(self):
        if not self.archivos_pendientes:
            self.procesamiento_completado()
            return
        
        archivo = self.archivos_pendientes.pop(0)
        
        if self.signature_analyzer.verificar_si_pdf_firmado(archivo):
            self.procesar_pdf_firmado(archivo)
        else:
            self.procesar_pdf_no_firmado(archivo)
    
    def procesar_pdf_firmado(self, archivo):
        def callback():
            self.archivos_procesados += 1
            self.procesar_siguiente_archivo()
        
        self.pdf_processor.procesar_pdf_con_qr(
            archivo, self.log_widget, self.root, 
            callback, self.progress, self.lbl_estado_global, self
        )
    
    def procesar_pdf_no_firmado(self, archivo):
        def callback_vinculacion(ruta_pdf):
            def callback_qr():
                self.archivos_procesados += 1
                self.procesar_siguiente_archivo()
            
            self.pdf_processor.procesar_pdf_con_qr(
                ruta_pdf, self.log_widget, self.root,
                callback_qr, self.progress, self.lbl_estado_global, self
            )
        
        self.pdf_processor.procesar_vinculacion_pdf(
            archivo, self.log_widget, self.root,
            callback_vinculacion, self.progress, self.lbl_estado_global
        )
    
    def procesamiento_completado(self):
        self.procesando = False
        self.btn_procesar.config(state=tk.NORMAL, bg="#27ae60")
        self.lbl_estado_global.config(text=f"Procesamiento completado: {self.archivos_procesados}/{self.total_archivos} archivos", fg="#27ae60")
        self._insertar_log(f"\n✅ PROCESAMIENTO COMPLETADO: {self.archivos_procesados} de {self.total_archivos} archivos procesados.\n", "success")
        self.pdf_processor.limpiar_directorio_temporal_global()
    
    def mostrar_configuracion(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configuración del Sistema")
        config_window.geometry("400x400")
        config_window.configure(bg="#e9eef7")
        config_window.resizable(False, False)
        config_window.transient(self.root)
        config_window.grab_set()
        
        self.center_window(config_window)
        
        header = tk.Frame(config_window, bg="#1f618d")
        header.pack(fill=tk.X, pady=(0, 20))
        tk.Label(header, text="Configuración del Sistema", bg="#1f618d", fg="white",
                font=("Segoe UI", 14, "bold")).pack(pady=15)
        
        btn_frame = tk.Frame(config_window, bg="#e9eef7")
        btn_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)
        
        tk.Button(btn_frame, text="👤 Cambiar credenciales de usuario", 
                 command=lambda: self.verificar_master_y_ejecutar(self.security_manager.change_credentials_dialog, config_window),
                 bg="#3498db", fg="white", font=("Segoe UI", 11), 
                 relief=tk.FLAT, pady=10, cursor="hand2").pack(fill=tk.X, pady=10)
        
        tk.Button(btn_frame, text="🔐 Cambiar contraseña maestra", 
                 command=lambda: self.verificar_master_y_ejecutar(self.security_manager.change_master_password_dialog, config_window),
                 bg="#9b59b6", fg="white", font=("Segoe UI", 11), 
                 relief=tk.FLAT, pady=10, cursor="hand2").pack(fill=tk.X, pady=10)
        
        tk.Button(btn_frame, text="📁 Configurar carpetas Google Drive", 
                 command=lambda: self.verificar_master_y_ejecutar(self.magnitude_manager.configurar_carpetas_drive, config_window),
                 bg="#e67e22", fg="white", font=("Segoe UI", 11), 
                 relief=tk.FLAT, pady=10, cursor="hand2").pack(fill=tk.X, pady=10)
        
        tk.Button(btn_frame, text="ℹ️ Información del sistema", 
                 command=self.mostrar_info_sistema,
                 bg="#2ecc71", fg="white", font=("Segoe UI", 11), 
                 relief=tk.FLAT, pady=10, cursor="hand2").pack(fill=tk.X, pady=10)
        
        tk.Button(btn_frame, text="❌ Cerrar", 
                 command=config_window.destroy,
                 bg="#e74c3c", fg="white", font=("Segoe UI", 11), 
                 relief=tk.FLAT, pady=10, cursor="hand2").pack(fill=tk.X, pady=10)
    
    def verificar_master_y_ejecutar(self, funcion, parent_window):
        """Verifica la contraseña maestra antes de ejecutar una función"""
        if not self.security_manager.credentials_exist():
            messagebox.showerror("Error", "No hay credenciales configuradas.", parent=parent_window)
            return

        creds = self.security_manager.load_credentials()
        master_stored = creds.get("master", {})

        master_input = simpledialog.askstring("Verificación maestra", 
                                            "Ingrese la contraseña maestra para continuar:", 
                                            parent=parent_window, show="*")
        if master_input is None:
            return

        if not self.security_manager.verify_password(master_input, master_stored):
            messagebox.showerror("Error", "Contraseña maestra incorrecta.", parent=parent_window)
            return
        
        # Ejecutar la función solicitada
        funcion(parent_window)
    
    def mostrar_info_sistema(self):
        creds = self.security_manager.load_credentials()
        
        # Cargar información de configuración de Drive
        drive_config_info = "No configurado"
        try:
            if os.path.exists("drive_config.json"):
                with open("drive_config.json", "r", encoding="utf-8") as f:
                    drive_config = json.load(f)
                drive_config_info = f"Patrones: {drive_config.get('folder_patrones_nombre', 'N/A')}\nCertificados: {drive_config.get('folder_certificados_nombre', 'N/A')}"
        except:
            drive_config_info = "Error cargando configuración"
        
        # Información de magnitudes
        magnitudes_info = ""
        for magnitud_key, magnitud_nombre in self.magnitude_manager.MAGNITUDES.items():
            folder_id = self.magnitude_manager.get_folder_id_magnitud(magnitud_key)
            if folder_id != self.magnitude_manager.folder_certificados:
                magnitudes_info += f"  • {magnitud_nombre}: ✅ Configurada\n"
            else:
                magnitudes_info += f"  • {magnitud_nombre}: ⚠️ Por configurar\n"
        
        info = f"""
Información del Sistema:

• ID de Instalación: {creds.get('install_id', 'N/A')}
• Usuario Configurado: {creds['user']['username']}
• Fecha de Creación: {datetime.fromtimestamp(creds.get('created_at', 0)).strftime('%Y-%m-%d %H:%M:%S')}

Configuración de Google Drive:
{drive_config_info}

Magnitudes Configuradas:
{magnitudes_info}
Archivos de Configuración:
• Credenciales de Usuario: {self.security_manager.CREDS_USER_FILE}
• Configuración Drive: {self.magnitude_manager.CONFIG_FILE}
• Log de Vinculación: {self.pdf_processor.log_file}
• Log de Errores: {self.pdf_processor.log_error_file}
"""
        messagebox.showinfo("Información del Sistema", info.strip())
    
    def center_window(self, window):
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry('{}x{}+{}+{}'.format(width, height, x, y))

# ======================================================
# FUNCIONES DE INICIALIZACIÓN Y LOGIN
# ======================================================

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