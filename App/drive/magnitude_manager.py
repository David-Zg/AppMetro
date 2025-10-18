"""
Módulo de gestión de magnitudes para Google Drive
"""

import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

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