"""
Módulo principal de la interfaz de usuario
"""

import os
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
from datetime import datetime

from security.security_manager import SecurityManager
from drive.magnitude_manager import MagnitudeManager
from drive.magnitude_selector import MagnitudeSelector
from pdf.signature_analyzer import SignatureAnalyzer
from pdf.pdf_processor import PDFProcessor

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_ACTIVO = True
except ImportError:
    TkinterDnD = tk
    DND_ACTIVO = False

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