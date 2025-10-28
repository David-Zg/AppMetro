"""
Módulo de gestión de magnitudes para Google Drive
"""

import os
import json
import re
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
        self.folder_patrones = "1uj_n8M8ymeLJp2H7clfsno7cSqKgbN8a"
        self.folder_certificados = "1xHUXnymGCFHr58ptJTNhIHH8NhL3A9cr"
        self.folder_patrones_nombre = "Patrones"
        self.folder_certificados_nombre = "Certificado"
        self.magnitudes_config = {}
        self.magnitud_seleccionada = None
        
        # 🔥 NUEVO: Caché de archivos de patrones para búsqueda rápida
        self.cache_patrones = {}
        self.cache_actualizado = False
        
        self.load_config()
        
    def load_config(self):
        """Carga la configuración de carpetas desde archivo"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                
                self.folder_patrones = config_data.get("folder_patrones", self.folder_patrones)
                self.folder_certificados = config_data.get("folder_certificados", self.folder_certificados)
                self.folder_patrones_nombre = config_data.get("folder_patrones_nombre", "Patrones")
                self.folder_certificados_nombre = config_data.get("folder_certificados_nombre", "Certificado")
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
        
        # 🔥 NUEVO: Actualizar caché de patrones al autenticar
        self.actualizar_cache_patrones()
        
        return self.drive
    
    def actualizar_cache_patrones(self):
        """
        🔥 NUEVO: Actualiza el caché de archivos de patrones desde Drive
        """
        try:
            if not self.drive:
                return
            
            # Buscar todos los PDFs en la carpeta de patrones
            query = f"'{self.folder_patrones}' in parents and mimeType='application/pdf' and trashed=false"
            archivos = self.drive.ListFile({'q': query}).GetList()
            
            self.cache_patrones = {}
            for archivo in archivos:
                nombre_original = archivo['title']
                nombre_sin_ext = os.path.splitext(nombre_original)[0]
                
                # Guardar con múltiples claves para búsqueda flexible
                self.cache_patrones[nombre_sin_ext] = {
                    'id': archivo['id'],
                    'title': nombre_original,
                    'modified': archivo.get('modifiedDate', '')
                }
                
                # También guardar versión normalizada
                nombre_normalizado = nombre_sin_ext.upper().replace(" ", "").replace("-", "").replace("_", "")
                self.cache_patrones[nombre_normalizado] = {
                    'id': archivo['id'],
                    'title': nombre_original,
                    'modified': archivo.get('modifiedDate', '')
                }
            
            self.cache_actualizado = True
            print(f"✓ Caché de patrones actualizado: {len(archivos)} archivos")
            
        except Exception as e:
            print(f"Error actualizando caché de patrones: {e}")
            self.cache_actualizado = False
    
    def buscar_patron_por_nombre(self, nombre_patron):
        """
        🔥 NUEVO: Busca un patrón en Google Drive por su nombre
        Primero busca en caché (rápido), luego consulta Drive si es necesario
        
        Args:
            nombre_patron: Nombre del patrón a buscar (sin extensión)
            
        Returns:
            str: Enlace de Drive del patrón, o None si no se encuentra
        """
        try:
            # 1. Intentar búsqueda en caché primero (más rápido)
            if self.cache_actualizado and self.cache_patrones:
                # Buscar por nombre exacto
                if nombre_patron in self.cache_patrones:
                    file_id = self.cache_patrones[nombre_patron]['id']
                    return f"https://drive.google.com/file/d/{file_id}/view"
                
                # Buscar por nombre normalizado
                nombre_normalizado = nombre_patron.upper().replace(" ", "").replace("-", "").replace("_", "")
                if nombre_normalizado in self.cache_patrones:
                    file_id = self.cache_patrones[nombre_normalizado]['id']
                    return f"https://drive.google.com/file/d/{file_id}/view"
                
                # Búsqueda flexible: si alguna clave contiene el patrón o viceversa
                for clave, info in self.cache_patrones.items():
                    clave_normalizada = clave.upper().replace(" ", "").replace("-", "").replace("_", "")
                    if nombre_normalizado in clave_normalizada or clave_normalizada in nombre_normalizado:
                        file_id = info['id']
                        return f"https://drive.google.com/file/d/{file_id}/view"
            
            # 2. Si no está en caché, buscar directamente en Drive
            if not self.drive:
                return None
            
            # Buscar por nombre que contenga el patrón
            query = f"'{self.folder_patrones}' in parents and title contains '{nombre_patron}' and mimeType='application/pdf' and trashed=false"
            file_list = self.drive.ListFile({'q': query}).GetList()
            
            if file_list:
                # Tomar el primer resultado (o el más reciente)
                archivo = sorted(file_list, key=lambda x: x.get('modifiedDate', ''), reverse=True)[0]
                file_id = archivo['id']
                
                # Actualizar caché con este archivo
                nombre_sin_ext = os.path.splitext(archivo['title'])[0]
                self.cache_patrones[nombre_sin_ext] = {
                    'id': file_id,
                    'title': archivo['title'],
                    'modified': archivo.get('modifiedDate', '')
                }
                
                return f"https://drive.google.com/file/d/{file_id}/view"
            
            # 3. No se encontró
            return None
            
        except Exception as e:
            print(f"Error buscando patrón '{nombre_patron}': {str(e)}")
            return None
    
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
            
            # Actualizar caché de patrones
            self.actualizar_cache_patrones()
            
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
        
        # Título principal
        title_frame = tk.Frame(config_window, bg="#e9eef7", pady=10)
        title_frame.pack(fill=tk.X)
        
        title_label = tk.Label(
            title_frame,
            text="⚙️ Configuración de Google Drive",
            font=("Segoe UI", 14, "bold"),
            bg="#e9eef7",
            fg="#2c3e50"
        )
        title_label.pack()
        
        # Frame de búsqueda
        search_frame = tk.Frame(config_window, bg="#e9eef7", pady=10)
        search_frame.pack(fill=tk.X, padx=20)
        
        btn_buscar = tk.Button(
            search_frame,
            text="🔍 Buscar Carpetas en Drive",
            command=buscar_carpetas,
            bg="#3498db",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            padx=15,
            pady=5
        )
        btn_buscar.pack()
        
        # Lista de carpetas
        list_frame = tk.Frame(config_window, bg="#e9eef7")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        lista_carpetas = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Segoe UI", 9),
            bg="white",
            fg="#2c3e50",
            selectbackground="#3498db",
            relief=tk.FLAT,
            borderwidth=2
        )
        lista_carpetas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=lista_carpetas.yview)
        
        # Frame de botones de selección
        button_frame = tk.Frame(config_window, bg="#e9eef7", pady=10)
        button_frame.pack(fill=tk.X, padx=20)
        
        btn_sel_patrones = tk.Button(
            button_frame,
            text="📁 Seleccionar como PATRONES",
            command=lambda: seleccionar_carpeta("patrones"),
            bg="#27ae60",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=5
        )
        btn_sel_patrones.pack(side=tk.LEFT, padx=5)
        
        btn_sel_certificados = tk.Button(
            button_frame,
            text="📋 Seleccionar como CERTIFICADOS",
            command=lambda: seleccionar_carpeta("certificados"),
            bg="#e67e22",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=5
        )
        btn_sel_certificados.pack(side=tk.LEFT, padx=5)
        
        # Labels de carpetas seleccionadas
        status_frame = tk.Frame(config_window, bg="#e9eef7", pady=10)
        status_frame.pack(fill=tk.X, padx=20)
        
        lbl_patrones = tk.Label(
            status_frame,
            text=f"Patrones: {self.folder_patrones_nombre}",
            font=("Segoe UI", 9),
            bg="#e9eef7",
            fg="#27ae60"
        )
        lbl_patrones.pack()
        
        lbl_certificados = tk.Label(
            status_frame,
            text=f"Certificados: {self.folder_certificados_nombre}",
            font=("Segoe UI", 9),
            bg="#e9eef7",
            fg="#e67e22"
        )
        lbl_certificados.pack()
        
        # Botón guardar
        save_frame = tk.Frame(config_window, bg="#e9eef7", pady=10)
        save_frame.pack(fill=tk.X, padx=20)
        
        btn_guardar = tk.Button(
            save_frame,
            text="💾 Guardar Configuración",
            command=guardar_configuracion,
            bg="#2ecc71",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=8
        )
        btn_guardar.pack()
        
        self.center_window(config_window)
    
    def crear_subcarpetas_magnitudes(self):
        """Crea subcarpetas de magnitudes en la carpeta de certificados"""
        if not self.drive or not self.folder_certificados:
            return
        
        for magnitud_key, magnitud_nombre in self.MAGNITUDES.items():
            try:
                # Verificar si ya existe
                nombre_subcarpeta = magnitud_key
                query = f"'{self.folder_certificados}' in parents and title = '{nombre_subcarpeta}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                existing = self.drive.ListFile({'q': query}).GetList()
                
                if existing:
                    # Ya existe, guardar su ID
                    self.magnitudes_config[magnitud_key] = existing[0]['id']
                else:
                    # Crear nueva subcarpeta
                    folder_metadata = {
                        'title': nombre_subcarpeta,
                        'parents': [{'id': self.folder_certificados}],
                        'mimeType': 'application/vnd.google-apps.folder'
                    }
                    folder = self.drive.CreateFile(folder_metadata)
                    folder.Upload()
                    self.magnitudes_config[magnitud_key] = folder['id']
                    
            except Exception as e:
                print(f"Error creando subcarpeta {magnitud_key}: {e}")
    
    def get_folder_id_magnitud(self, magnitud_key: str) -> str:
        """Obtiene el ID de carpeta para una magnitud específica"""
        if magnitud_key in self.magnitudes_config:
            return self.magnitudes_config[magnitud_key]
        
        # Si no existe en config, intentar crearla
        self.crear_subcarpetas_magnitudes()
        return self.magnitudes_config.get(magnitud_key, self.folder_certificados)
    
    def extraer_codigo_certificado(self, nombre_archivo: str) -> str | None:
        """Extrae el código del certificado del nombre del archivo"""
        # Patrón: DDMMMAAAA donde DDD = día, MMM = mes en texto, AAAA = año
        match = re.search(r'(\d{2}[A-Z]{3}\d{4})', nombre_archivo.upper())
        if match:
            return match.group(1)
        return None
    
    def reemplazar_pdf_por_certificado(self, ruta_pdf, app):
        """
        Busca y reemplaza un PDF existente en Drive basándose en el código de certificado
        Versión sincrónica para uso con app._insertar_log
        """
        try:
            nombre_archivo = os.path.basename(ruta_pdf)
            
            # Extraer código de certificado del nombre
            codigo_certificado = self.extraer_codigo_certificado(nombre_archivo)
            
            if not codigo_certificado:
                app._insertar_log(f"   ⚠️ No se pudo identificar código de certificado en: {nombre_archivo}\n", "warning")
                return False
            
            app._insertar_log(f"   🔍 Buscando archivo con código: {codigo_certificado}\n", "info")
            
            # Obtener carpeta de la magnitud actual
            magnitud_key = self.magnitud_seleccionada or "otros"
            folder_id = self.get_folder_id_magnitud(magnitud_key)
            
            # Buscar archivo por código usando 'title contains'
            query = f"'{folder_id}' in parents and title contains '{codigo_certificado}' and trashed=false"
            archivos_encontrados = self.drive.ListFile({'q': query}).GetList()
            
            if archivos_encontrados:
                # Tomar el primer archivo encontrado
                archivo_drive = archivos_encontrados[0]
                file_id = archivo_drive['id']
                nombre_existente = archivo_drive['title']
                
                app._insertar_log(f"   ✅ Archivo encontrado: {nombre_existente}\n", "success")
                app._insertar_log(f"   🔄 Reemplazando contenido del archivo\n", "info")
                
                # Actualizar contenido del archivo existente
                archivo_drive.SetContentFile(ruta_pdf)
                archivo_drive.Upload()
                
                # Asegurar permisos de lectura
                try:
                    archivo_drive.InsertPermission({
                        'type': 'anyone',
                        'role': 'reader',
                        'withLink': True
                    })
                except:
                    pass  # Si ya tiene permisos, ignorar error
                
                app._insertar_log(f"   ✅ PDF firmado reemplazado exitosamente\n", "success")
                app._insertar_log(f"   📎 Enlace: https://drive.google.com/file/d/{file_id}/view\n", "info")
                
                return True
            else:
                app._insertar_log(f"   ℹ️ No se encontró archivo previo con código {codigo_certificado}\n", "info")
                return False
                
        except Exception as e:
            app._insertar_log(f"   ❌ Error en reemplazo: {str(e)}\n", "error")
            return False
    
    def reemplazar_pdf_por_certificado_thread(self, ruta_pdf, log_widget, root):
        """Versión para usar con threads en la interfaz gráfica"""
        # 🔥 FUNCIÓN AUXILIAR: Para llamadas desde hilos con widgets
        
        try:
            nombre_archivo = os.path.basename(ruta_pdf)
            
            # Extraer código de certificado del nombre
            codigo_certificado = self.extraer_codigo_certificado(nombre_archivo)
            
            if not codigo_certificado:
                log_widget.insert('end', f"   ⚠️ No se pudo identificar código de certificado\n", "warning")
                return False
            
            log_widget.insert('end', f"   🔍 Buscando archivo con código: {codigo_certificado}\n", "info")
            
            # Obtener carpeta de la magnitud actual
            magnitud_key = self.magnitud_seleccionada or "otros"
            folder_id = self.get_folder_id_magnitud(magnitud_key)
            
            # Buscar archivo por código usando 'title contains'
            query = f"'{folder_id}' in parents and title contains '{codigo_certificado}' and trashed=false"
            archivos_encontrados = self.drive.ListFile({'q': query}).GetList()
            
            if archivos_encontrados:
                # Tomar el primer archivo encontrado
                archivo_drive = archivos_encontrados[0]
                file_id = archivo_drive['id']
                nombre_existente = archivo_drive['title']
                
                log_widget.insert('end', f"   ✅ Archivo encontrado: {nombre_existente}\n", "success")
                log_widget.insert('end', f"   🔄 Reemplazando contenido del archivo\n", "info")
                
                # Actualizar contenido del archivo existente
                archivo_drive.SetContentFile(ruta_pdf)
                archivo_drive.Upload()
                
                # Asegurar permisos de lectura
                try:
                    archivo_drive.InsertPermission({
                        'type': 'anyone',
                        'role': 'reader',
                        'withLink': True
                    })
                except:
                    pass
                
                log_widget.insert('end', f"   ✅ PDF REEMPLAZADO EN DRIVE\n", "success")
                log_widget.insert('end', f"   📎 https://drive.google.com/file/d/{file_id}/view\n", "info_detalle")
                
                return True
            else:
                return False
                
        except Exception as e:
            log_widget.insert('end', f"   ❌ Error en reemplazo: {str(e)}\n", "error")
            return False
    
    def subir_pdf(self, ruta_pdf: str, magnitud_key: str = None) -> tuple[str, str, str, str]:
        """Sube un PDF a la carpeta de magnitud específica CON PERMISOS RESTRINGIDOS"""
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
            # 🔥 ENLACE CORREGIDO - Abre en navegador con opción de descargar
            enlace = f"https://drive.google.com/file/d/{file_id}/view"
            
            # ACTUALIZAR el archivo existente
            file.SetContentFile(ruta_pdf)
            file.Upload()
            
            # 🔥 CONFIGURAR PERMISOS RESTRINGIDOS para archivo existente
            file.InsertPermission({
                'type': 'anyone',       # Cualquiera con el enlace
                'role': 'reader',       # Solo lectura (puede ver y descargar)
                'withLink': True        # Requiere enlace para acceder
            })
            
            return file_id, enlace, "reemplazado 🔁", magnitud_key
        else:
            # Crear nuevo archivo
            file = self.drive.CreateFile({
                'title': nombre, 
                'parents': [{'id': folder_id}]
            })
            file.SetContentFile(ruta_pdf)
            file.Upload()
            
            # 🔥 CONFIGURAR PERMISOS RESTRINGIDOS para archivo nuevo
            file.InsertPermission({
                'type': 'anyone',       # Cualquiera con el enlace
                'role': 'reader',       # Solo lectura (puede ver y descargar)
                'withLink': True        # Requiere enlace para acceder
            })
            
            file_id = file['id']
            # 🔥 ENLACE CORREGIDO - Abre en navegador con opción de descargar
            enlace = f"https://drive.google.com/file/d/{file_id}/view"
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
            # 🔥 ENLACE CORREGIDO - Abre en navegador con opción de descargar
            return f"https://drive.google.com/file/d/{file['id']}/view"
        except Exception as e:
            raise RuntimeError(f"Error buscando en Drive: {e}")

    def center_window(self, window):
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry('{}x{}+{}+{}'.format(width, height, x, y))