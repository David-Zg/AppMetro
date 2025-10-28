"""
Módulo principal de la interfaz de usuario
"""

import os
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
from datetime import datetime
import threading
import queue
import time

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
        self.root.geometry("750x600")
        self.root.configure(bg="#e9eef7")
        
        # Inicializar managers
        self.security_manager = SecurityManager()
        self.magnitude_manager = MagnitudeManager()
        self.signature_analyzer = SignatureAnalyzer()
        self.pdf_processor = PDFProcessor(self.magnitude_manager, self.signature_analyzer)
        
        # Variables de estado - CERTIFICADOS
        self.archivos_pendientes = []
        self.procesando = False
        self.archivos_procesados = 0
        self.total_archivos = 0
        self.datos_firmas = []
        self.ultimo_mensaje_log = ""
        self.vinculos_unicos = set()
        
        # Variables de estado - PATRONES (NUEVO)
        self.patrones_pendientes = []
        self.cargando_patrones = False
        self.patrones_procesados = 0
        self.total_patrones = 0
        self.patrones_existentes_drive = set()
        self.ultimo_mensaje_log_patrones = ""  # NUEVO: Para evitar duplicados en log de patrones
        
        # Cola para comunicación entre hilos
        self.cola_log = queue.Queue()
        self.cola_comandos = queue.Queue()
        self.cola_log_patrones = queue.Queue()
        
        # Elementos de UI - CERTIFICADOS
        self.progress = None
        self.lbl_estado_global = None
        self.log_widget = None
        self.btn_procesar = None
        self.tree_firmas = None
        self.lista_archivos = None
        self.lbl_magnitud_actual = None
        self.lbl_magnitud_archivos = None
        
        # Elementos de UI - PATRONES (NUEVO)
        self.lista_patrones = None
        self.progress_patrones = None
        self.lbl_estado_patrones = None
        self.log_patrones = None
        self.btn_cargar_patrones = None
        
        self.setup_ui()
        self.inicializar_drive()
        
        # Iniciar procesadores de cola
        self.procesar_cola_log()
        self.procesar_cola_comandos()
        self.procesar_cola_log_patrones()
    
    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg="#1f618d")
        header_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(header_frame, text="SISTEMA INTEGRAL DE CERTIFICADOS CON QR", 
                bg="#1f618d", fg="white", font=("Segoe UI", 14, "bold")).pack(pady=8)
        
        # Barra de información de magnitud actual
        info_frame = tk.Frame(header_frame, bg="#1a5276")
        info_frame.pack(fill=tk.X, padx=15, pady=(0, 8))
        
        self.lbl_magnitud_actual = tk.Label(info_frame, 
                                          text="🌡️ Magnitud actual: Temperatura", 
                                          bg="#1a5276", fg="white", 
                                          font=("Segoe UI", 9, "bold"))
        self.lbl_magnitud_actual.pack(side=tk.LEFT)
        
        tk.Button(info_frame, text="📁 Cambiar Magnitud", 
                 command=self.cambiar_magnitud,
                 bg="#3498db", fg="white", font=("Segoe UI", 8),
                 relief=tk.FLAT, padx=8, pady=1).pack(side=tk.RIGHT)
        
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=8)
        
        # PESTAÑA 1: Procesamiento (EXISTENTE)
        tab_procesamiento = tk.Frame(notebook, bg="#e9eef7")
        notebook.add(tab_procesamiento, text="🔄 Procesamiento")
        self.setup_tab_procesamiento(tab_procesamiento)
        
        # PESTAÑA 2: Carga de Patrones (NUEVA)
        tab_patrones = tk.Frame(notebook, bg="#e9eef7")
        notebook.add(tab_patrones, text="📦 Carga de Patrones")
        self.setup_tab_carga_patrones(tab_patrones)
        
        # PESTAÑA 3: Información de Firmas (EXISTENTE)
        tab_firmas = tk.Frame(notebook, bg="#e9eef7")
        notebook.add(tab_firmas, text="📋 Información de Firmas")
        self.setup_tab_firmas(tab_firmas)
        
        self.actualizar_display_magnitud()
    
    def setup_tab_procesamiento(self, parent):
        main_frame = tk.Frame(parent, bg="#e9eef7")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        
        # File frame
        file_frame = tk.LabelFrame(main_frame, text="📁 Archivos PDF a procesar", 
                                  bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        file_frame.pack(fill=tk.X, pady=(0, 8))
        
        btn_frame = tk.Frame(file_frame, bg="#e9eef7")
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        
        tk.Button(btn_frame, text="📂 Seleccionar archivos PDF", command=self.seleccionar_archivos,
                 bg="#3498db", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        tk.Button(btn_frame, text="🗑️ Limpiar TODO", command=self.limpiar_todo,
                 bg="#e74c3c", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        self.lista_archivos = tk.Listbox(file_frame, height=4, font=("Segoe UI", 8))
        self.lista_archivos.pack(fill=tk.X, padx=8, pady=(0, 8))
        
        # Información de magnitud
        magnitud_info = tk.Frame(file_frame, bg="#e9eef7")
        magnitud_info.pack(fill=tk.X, padx=8, pady=(0, 8))
        
        self.lbl_magnitud_archivos = tk.Label(magnitud_info, 
                                            text="Los archivos se guardarán en: 🌡️ Temperatura",
                                            bg="#e9eef7", fg="#e67e22", font=("Segoe UI", 8, "bold"))
        self.lbl_magnitud_archivos.pack(anchor="w")
        
        # Progress frame
        progress_frame = tk.LabelFrame(main_frame, text="📊 Progreso", 
                                      bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        progress_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill=tk.X, padx=8, pady=8)
        
        self.lbl_estado_global = tk.Label(progress_frame, text="Esperando archivos...", 
                                         bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 9, "bold"))
        self.lbl_estado_global.pack(pady=(0, 8))
        
        # Log frame
        log_frame = tk.LabelFrame(main_frame, text="📝 Log de Procesamiento", 
                                 bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 8))
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # Configurar tags para el log
        for tag, color in [("proceso", "#1f618d"), ("success", "#27ae60"), 
                          ("error", "#e74c3c"), ("info", "#f39c12"), 
                          ("enlace", "#3498db"), ("magnitud", "#9b59b6")]:
            self.log_widget.tag_config(tag, foreground=color, font=("Consolas", 8, "bold"))
        
        # Action frame
        action_frame = tk.Frame(main_frame, bg="#e9eef7")
        action_frame.pack(fill=tk.X, pady=8)
        
        center_frame = tk.Frame(action_frame, bg="#e9eef7")
        center_frame.pack(expand=True)
        
        self.btn_procesar = tk.Button(center_frame, text="🚀 INICIAR PROCESAMIENTO", 
                                    command=self.iniciar_procesamiento,
                                    bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"),
                                    relief=tk.FLAT, padx=15, pady=8)
        self.btn_procesar.pack(side=tk.LEFT, padx=4)
        
        tk.Button(center_frame, text="⚙️ Configuración", command=self.mostrar_configuracion,
                 bg="#95a5a6", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        if DND_ACTIVO:
            self.lista_archivos.drop_target_register(DND_FILES)
            self.lista_archivos.dnd_bind('<<Drop>>', self.archivos_arrastrados)
    
    def setup_tab_carga_patrones(self, parent):
        """NUEVA PESTAÑA: Carga de patrones a Drive"""
        main_frame = tk.Frame(parent, bg="#e9eef7")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        
        # File frame
        file_frame = tk.LabelFrame(main_frame, text="📦 Patrones PDF a cargar en Drive", 
                                  bg="#e9eef7", fg="#9b59b6", font=("Segoe UI", 10, "bold"))
        file_frame.pack(fill=tk.X, pady=(0, 8))
        
        btn_frame = tk.Frame(file_frame, bg="#e9eef7")
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        
        tk.Button(btn_frame, text="📂 Seleccionar archivos PDF", command=self.seleccionar_patrones,
                 bg="#9b59b6", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        tk.Button(btn_frame, text="🗑️ Limpiar TODO", command=self.limpiar_todo_patrones,  # CORREGIDO
                 bg="#e74c3c", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        self.lista_patrones = tk.Listbox(file_frame, height=4, font=("Segoe UI", 8))
        self.lista_patrones.pack(fill=tk.X, padx=8, pady=(0, 8))
        
        # Información de destino
        destino_info = tk.Frame(file_frame, bg="#e9eef7")
        destino_info.pack(fill=tk.X, padx=8, pady=(0, 8))
        
        tk.Label(destino_info, 
                text="📁 Carpeta destino: Patrones (Drive)",
                bg="#e9eef7", fg="#9b59b6", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        
        tk.Label(destino_info,
                text="🔗 Permisos: Cualquiera con el enlace (Lector)",
                bg="#e9eef7", fg="#e67e22", font=("Segoe UI", 7, "italic")).pack(anchor="w", pady=(2, 0))
        
        # Progress frame
        progress_frame = tk.LabelFrame(main_frame, text="📊 Progreso de Carga", 
                                      bg="#e9eef7", fg="#9b59b6", font=("Segoe UI", 10, "bold"))
        progress_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.progress_patrones = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_patrones.pack(fill=tk.X, padx=8, pady=8)
        
        self.lbl_estado_patrones = tk.Label(progress_frame, text="Esperando archivos...", 
                                           bg="#e9eef7", fg="#9b59b6", font=("Segoe UI", 9, "bold"))
        self.lbl_estado_patrones.pack(pady=(0, 8))
        
        # Log frame
        log_frame = tk.LabelFrame(main_frame, text="📝 Log de Carga de Patrones", 
                                 bg="#e9eef7", fg="#9b59b6", font=("Segoe UI", 10, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        self.log_patrones = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 8))
        self.log_patrones.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # Configurar tags
        for tag, color in [("success", "#27ae60"), ("error", "#e74c3c"), 
                          ("info", "#9b59b6"), ("enlace", "#3498db"), 
                          ("warning", "#f39c12"), ("duplicado", "#e67e22")]:
            self.log_patrones.tag_config(tag, foreground=color, font=("Consolas", 8, "bold"))
        
        # Mensaje inicial
        self._insertar_log_patrones("✨ Sistema de carga de patrones listo.\n", "info")
        self._insertar_log_patrones("📦 Seleccione o arrastre archivos PDF de patrones.\n\n", "info")
        
        # Action frame
        action_frame = tk.Frame(main_frame, bg="#e9eef7")
        action_frame.pack(fill=tk.X, pady=8)
        
        center_frame = tk.Frame(action_frame, bg="#e9eef7")
        center_frame.pack(expand=True)
        
        self.btn_cargar_patrones = tk.Button(center_frame, text="⬆️ SUBIR PATRONES A DRIVE", 
                                            command=self.iniciar_carga_patrones,
                                            bg="#9b59b6", fg="white", font=("Segoe UI", 10, "bold"),
                                            relief=tk.FLAT, padx=15, pady=8)
        self.btn_cargar_patrones.pack(side=tk.LEFT, padx=4)
        
        if DND_ACTIVO:
            self.lista_patrones.drop_target_register(DND_FILES)
            self.lista_patrones.dnd_bind('<<Drop>>', self.patrones_arrastrados)
    
    def setup_tab_firmas(self, parent):
        info_frame = tk.LabelFrame(parent, text="ℹ️ Información", 
                                  bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        info_frame.pack(fill=tk.X, pady=(0, 8), padx=8)
        
        info_text = tk.Label(info_frame, 
                            text="La información de firmas se genera automáticamente durante el procesamiento.",
                            bg="#e9eef7", fg="#7f8c8d", font=("Segoe UI", 8), justify=tk.LEFT)
        info_text.pack(padx=8, pady=8)
        
        results_frame = tk.LabelFrame(parent, text="📊 Resultados de Firmas Digitales", 
                                     bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        results_frame.pack(fill=tk.BOTH, expand=True, pady=8, padx=8)
        
        columns = ("Archivo", "Estado", "Firmante", "Fecha", "Tipo", "Magnitud")
        self.tree_firmas = ttk.Treeview(results_frame, columns=columns, show="headings", height=10)
        
        for col in columns:
            self.tree_firmas.heading(col, text=col)
        
        self.tree_firmas.column("Archivo", width=120)
        self.tree_firmas.column("Estado", width=70)
        self.tree_firmas.column("Firmante", width=120)
        self.tree_firmas.column("Fecha", width=80)
        self.tree_firmas.column("Tipo", width=100)
        self.tree_firmas.column("Magnitud", width=80)
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree_firmas.yview)
        self.tree_firmas.configure(yscrollcommand=scrollbar.set)
        
        self.tree_firmas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=8)
    
    # =========================================================================
    # MÉTODOS PARA CARGA DE PATRONES - CORREGIDOS
    # =========================================================================
    
    def seleccionar_patrones(self):
        archivos = filedialog.askopenfilenames(
            title="Seleccionar Patrones PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        
        if archivos:
            agregados = 0
            for archivo in archivos:
                if archivo not in self.patrones_pendientes:
                    self.patrones_pendientes.append(archivo)
                    self.lista_patrones.insert(tk.END, os.path.basename(archivo))
                    agregados += 1
            
            if agregados > 0:
                self._insertar_log_patrones(f"✅ {agregados} patrón(es) agregado(s).\n", "success")
                self._actualizar_estado_patrones()
    
    def patrones_arrastrados(self, event):
        try:
            archivos = self.root.tk.splitlist(event.data)
            archivos_pdf = [f for f in archivos if f.lower().endswith('.pdf')]
            
            if archivos_pdf:
                agregados = 0
                for archivo in archivos_pdf:
                    if archivo not in self.patrones_pendientes:
                        self.patrones_pendientes.append(archivo)
                        self.lista_patrones.insert(tk.END, os.path.basename(archivo))
                        agregados += 1
                
                if agregados > 0:
                    self._insertar_log_patrones(f"✅ {agregados} patrón(es) arrastrado(s).\n", "success")
                    self._actualizar_estado_patrones()
        except Exception as e:
            self._insertar_log_patrones(f"❌ Error al arrastrar: {e}\n", "error")
    
    def limpiar_todo_patrones(self):  # NUEVO MÉTODO CORREGIDO
        """Limpia completamente la pestaña de patrones"""
        self.cargando_patrones = False
        self.patrones_pendientes.clear()
        self.lista_patrones.delete(0, tk.END)
        self.patrones_procesados = 0
        self.total_patrones = 0
        self.progress_patrones["value"] = 0
        self.progress_patrones["maximum"] = 100
        self.ultimo_mensaje_log_patrones = ""
        
        # Limpiar el log de patrones
        if self.log_patrones:
            self.log_patrones.config(state=tk.NORMAL)
            self.log_patrones.delete("1.0", tk.END)
        
        self.lbl_estado_patrones.config(text="Esperando archivos...", fg="#9b59b6")
        self.btn_cargar_patrones.config(state=tk.NORMAL, bg="#9b59b6")
        self._insertar_log_patrones("🧹 TODO ha sido limpiado correctamente.\n", "success")
    
    def _actualizar_estado_patrones(self):
        """Actualiza el estado de la interfaz de patrones"""
        total = len(self.patrones_pendientes)
        self.lbl_estado_patrones.config(text=f"Patrones listos: {total}")
        self.btn_cargar_patrones.config(state=tk.NORMAL if total > 0 else tk.DISABLED, 
                                      bg="#9b59b6" if total > 0 else "#95a5a6")
    
    def iniciar_carga_patrones(self):
        if not self.patrones_pendientes:
            messagebox.showwarning("Sin Patrones", "No hay patrones para subir.", parent=self.root)
            return
        
        if self.cargando_patrones:
            messagebox.showwarning("Procesando", "Ya hay una carga en proceso.", parent=self.root)
            return
        
        if not self.magnitude_manager.drive:
            messagebox.showerror("Error Drive", "No hay conexión con Google Drive.", parent=self.root)
            return
        
        respuesta = messagebox.askyesno(
            "Confirmar Subida",
            f"¿Subir {len(self.patrones_pendientes)} patrón(es) a Drive?\n\n"
            "• Carpeta: Patrones\n"
            "• Permisos: Cualquiera con el enlace (Lector)",
            parent=self.root
        )
        
        if not respuesta:
            return
        
        self.cargando_patrones = True
        self.patrones_procesados = 0
        self.total_patrones = len(self.patrones_pendientes)
        
        self.progress_patrones["maximum"] = self.total_patrones
        self.progress_patrones["value"] = 0
        
        self.btn_cargar_patrones.config(state=tk.DISABLED, bg="#7f8c8d")
        self.lbl_estado_patrones.config(text="Subiendo patrones...", fg="#9b59b6")
        
        # Limpiar log antes de empezar
        self.log_patrones.delete(1.0, tk.END)
        self.ultimo_mensaje_log_patrones = ""
        
        self._insertar_log_patrones(f"\n{'='*60}\n", "info")
        self._insertar_log_patrones(f"🚀 CARGA DE {self.total_patrones} PATRONES\n", "info")
        self._insertar_log_patrones(f"{'='*60}\n\n", "info")
        
        self._cargar_patrones_existentes_drive()
        
        thread = threading.Thread(target=self._procesar_carga_patrones_thread, daemon=True)
        thread.start()
    
    def _cargar_patrones_existentes_drive(self):
        try:
            self._insertar_log_patrones("🔍 Verificando patrones en Drive...\n", "info")
            
            folder_id = self.magnitude_manager.folder_patrones
            query = f"'{folder_id}' in parents and trashed=false"
            results = self.magnitude_manager.drive.ListFile({'q': query}).GetList()
            
            self.patrones_existentes_drive = {r['title'] for r in results}
            
            if self.patrones_existentes_drive:
                self._insertar_log_patrones(f"📋 {len(self.patrones_existentes_drive)} patrón(es) existente(s).\n", "info")
            else:
                self._insertar_log_patrones("📋 No hay patrones previos.\n", "info")
            
        except Exception as e:
            self._insertar_log_patrones(f"⚠️ Error verificando: {e}\n", "warning")
            self.patrones_existentes_drive = set()
    
    def _procesar_carga_patrones_thread(self):
        for patron in self.patrones_pendientes[:]:
            try:
                self._subir_patron_individual(patron)
                self.patrones_procesados += 1
                self._ejecutar_en_principal(self._actualizar_progreso_patrones)
                
                if patron in self.patrones_pendientes:
                    self.patrones_pendientes.remove(patron)
                    
            except Exception as e:
                self._insertar_log_patrones(f"❌ Error: {str(e)}\n", "error")
                self.patrones_procesados += 1
                self._ejecutar_en_principal(self._actualizar_progreso_patrones)
        
        self._ejecutar_en_principal(self._carga_patrones_completada)
    
    def _subir_patron_individual(self, archivo_path):
        nombre_archivo = os.path.basename(archivo_path)
        self._insertar_log_patrones(f"\n{'─'*60}\n", "info")
        self._insertar_log_patrones(f"📄 {nombre_archivo}\n", "info")
        
        # Verificar duplicados
        if nombre_archivo in self.patrones_existentes_drive:
            self._insertar_log_patrones(f"   ⚠️ YA EXISTE en Drive\n", "duplicado")
            self._insertar_log_patrones(f"   ❌ SUBIDA CANCELADA\n", "error")
            return
        
        # Verificar firma
        self._insertar_log_patrones("   🔍 Verificando firma...\n", "info")
        try:
            firmado = self.signature_analyzer.verificar_si_pdf_firmado(archivo_path)
            if firmado:
                self._insertar_log_patrones("   ✅ PDF FIRMADO\n", "success")
            else:
                self._insertar_log_patrones("   ⚠️ PDF NO FIRMADO\n", "warning")
        except Exception as e:
            self._insertar_log_patrones(f"   ⚠️ Error firma: {e}\n", "warning")
            firmado = False
        
        # Subir a Drive
        self._insertar_log_patrones("   ⬆️ Subiendo a Drive...\n", "info")
        
        try:
            folder_id = self.magnitude_manager.folder_patrones
            
            file = self.magnitude_manager.drive.CreateFile({
                'title': nombre_archivo,
                'parents': [{'id': folder_id}]
            })
            file.SetContentFile(archivo_path)
            file.Upload()
            
            # Configurar permisos
            file.InsertPermission({
                'type': 'anyone',
                'role': 'reader',
                'withLink': True
            })
            
            file_id = file['id']
            enlace = f"https://drive.google.com/file/d/{file_id}/view"
            
            self._insertar_log_patrones("   ✅ Subido exitosamente\n", "success")
            self._insertar_log_patrones("   🔗 Enlace:\n", "enlace")
            self._insertar_log_patrones(f"      {enlace}\n", "enlace")
            
            self.patrones_existentes_drive.add(nombre_archivo)
            
        except Exception as e:
            self._insertar_log_patrones(f"   ❌ ERROR: {str(e)}\n", "error")
            raise
    
    def _actualizar_progreso_patrones(self):
        self.progress_patrones["value"] = self.patrones_procesados
        self.lbl_estado_patrones.config(
            text=f"Procesados: {self.patrones_procesados}/{self.total_patrones}"
        )
    
    def _carga_patrones_completada(self):
        self.cargando_patrones = False
        self.btn_cargar_patrones.config(state=tk.NORMAL, bg="#9b59b6")
        
        self.lbl_estado_patrones.config(
            text=f"✅ Completado: {self.patrones_procesados}/{self.total_patrones}",
            fg="#27ae60"
        )
        
        self._insertar_log_patrones(f"\n{'='*60}\n", "success")
        self._insertar_log_patrones(
            f"✅ COMPLETADO: {self.patrones_procesados}/{self.total_patrones}\n",
            "success"
        )
        self._insertar_log_patrones(f"{'='*60}\n\n", "success")
        
        # Limpiar la lista de archivos procesados
        self.lista_patrones.delete(0, tk.END)
        
        messagebox.showinfo(
            "Carga Completada",
            f"✅ {self.patrones_procesados}/{self.total_patrones} patrones procesados",
            parent=self.root
        )
    
    def _insertar_log_patrones(self, texto, tag="info"):
        self.cola_log_patrones.put((texto, tag))
    
    def procesar_cola_log_patrones(self):
        """Procesa los mensajes de la cola de logs de patrones"""
        try:
            while True:
                mensaje, tag = self.cola_log_patrones.get_nowait()
                self._insertar_log_patrones_directo(mensaje, tag)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.procesar_cola_log_patrones)
    
    def _insertar_log_patrones_directo(self, mensaje, tag=None):
        """Inserta directamente en el log de patrones (solo en hilo principal)"""
        if not self.log_patrones:
            return
            
        current_state = self.log_patrones.cget('state')
        if current_state == tk.DISABLED:
            self.log_patrones.config(state=tk.NORMAL)
        
        mensaje_limpio = mensaje.strip()
        if mensaje_limpio and mensaje_limpio != self.ultimo_mensaje_log_patrones:
            if tag:
                self.log_patrones.insert(tk.END, mensaje, tag)
            else:
                self.log_patrones.insert(tk.END, mensaje)
            self.log_patrones.see(tk.END)
            self.ultimo_mensaje_log_patrones = mensaje_limpio
    
    # =========================================================================
    # MÉTODOS EXISTENTES MEJORADOS
    # =========================================================================
    
    def cambiar_magnitud(self):
        selector = MagnitudeSelector(self.root, self.magnitude_manager)
        nueva_magnitud = selector.show_selector()
        
        if nueva_magnitud:
            self.magnitude_manager.magnitud_seleccionada = nueva_magnitud
            self.actualizar_display_magnitud()
            self._insertar_log(f"📁 Magnitud cambiada a: {self.magnitude_manager.MAGNITUDES[nueva_magnitud]}\n", "magnitud")
    
    def actualizar_display_magnitud(self):
        magnitud_actual = self.magnitude_manager.magnitud_seleccionada or "temperatura"
        nombre_magnitud = self.magnitude_manager.MAGNITUDES[magnitud_actual]
        
        self.lbl_magnitud_actual.config(text=f"📁 Magnitud actual: {nombre_magnitud}")
        self.lbl_magnitud_archivos.config(text=f"Los archivos se guardarán en: {nombre_magnitud}")
    
    def inicializar_drive(self):
        try:
            self.magnitude_manager.autenticar()
            self._insertar_log("✅ Autenticación con Google Drive exitosa.\n", "success")
            self.magnitude_manager.crear_subcarpetas_magnitudes()
            self._insertar_log("✅ Subcarpetas de magnitudes configuradas.\n", "success")
        except Exception as e:
            self._insertar_log(f"❌ Error autenticando con Google Drive: {e}\n", "error")
            messagebox.showerror("Error de Autenticación", f"No se pudo autenticar con Google Drive:\n{e}")
    
    def procesar_cola_log(self):
        """Procesa los mensajes de la cola de logs"""
        try:
            while True:
                mensaje, tag = self.cola_log.get_nowait()
                self._insertar_log_directo(mensaje, tag)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.procesar_cola_log)
    
    def procesar_cola_comandos(self):
        """Procesa comandos para ejecutar en el hilo principal"""
        try:
            while True:
                comando, args = self.cola_comandos.get_nowait()
                comando(*args)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.procesar_cola_comandos)
    
    def _insertar_log_directo(self, mensaje, tag=None):
        """Inserta directamente en el log (solo en hilo principal)"""
        current_state = self.log_widget.cget('state')
        if current_state == tk.DISABLED:
            self.log_widget.config(state=tk.NORMAL)
        
        mensaje_limpio = mensaje.strip()
        if mensaje_limpio and mensaje_limpio != self.ultimo_mensaje_log:
            if tag:
                self.log_widget.insert(tk.END, mensaje, tag)
            else:
                self.log_widget.insert(tk.END, mensaje)
            self.log_widget.see(tk.END)
            self.ultimo_mensaje_log = mensaje_limpio
    
    def _insertar_log(self, mensaje, tag=None):
        """Método seguro para insertar logs desde cualquier hilo"""
        self.cola_log.put((mensaje, tag))
    
    def _ejecutar_en_principal(self, comando, *args):
        """Ejecuta un comando en el hilo principal"""
        self.cola_comandos.put((comando, args))
    
    def mostrar_vinculos_unicos(self, vinculos_unicos):
        """Muestra los vínculos únicos encontrados en formato compacto"""
        if not vinculos_unicos:
            return
        
        # Convertir a lista y ordenar
        vinculos_lista = sorted(list(vinculos_unicos), key=lambda x: x[0])  # Ordenar por certificado
        
        self._insertar_log("🔍 Vínculos únicos encontrados:\n", "enlace")
        
        # Para pocos vínculos (hasta 6), mostrar en líneas compactas
        if len(vinculos_lista) <= 6:
            # Dividir en 2 líneas si hay más de 3 vínculos
            if len(vinculos_lista) > 3:
                mitad = len(vinculos_lista) // 2
                linea1 = "   "
                for i, (certificado, patron) in enumerate(vinculos_lista[:mitad]):
                    if i > 0:
                        linea1 += " / "
                    linea1 += f"📋 {certificado} → {patron}"
                
                linea2 = "   "
                for i, (certificado, patron) in enumerate(vinculos_lista[mitad:]):
                    if i > 0:
                        linea2 += " / "
                    linea2 += f"📋 {certificado} → {patron}"
                
                self._insertar_log(linea1 + "\n", "info")
                self._insertar_log(linea2 + "\n\n", "info")
            else:
                # Todos en una línea
                linea = "   "
                for i, (certificado, patron) in enumerate(vinculos_lista):
                    if i > 0:
                        linea += " / "
                    linea += f"📋 {certificado} → {patron}"
                self._insertar_log(linea + "\n\n", "info")
        else:
            # Para muchos vínculos, mostrar en formato de lista compacta
            for i, (certificado, patron) in enumerate(vinculos_lista):
                if i < 8:  # Mostrar máximo 8
                    self._insertar_log(f"   📋 {certificado} → {patron}\n", "info")
                else:
                    self._insertar_log(f"   ... y {len(vinculos_lista) - 8} más\n", "info")
                    break
            self._insertar_log("\n", "info")
    
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
        self.ultimo_mensaje_log = ""
        self.vinculos_unicos.clear()
        
        self.log_widget.config(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        
        self.limpiar_tabla_firmas()
        self.lbl_estado_global.config(text="Esperando archivos...", fg="#1f618d")
        self.btn_procesar.config(state=tk.NORMAL, bg="#27ae60")
        self.pdf_processor.limpiar_directorio_temporal_global()
        self._insertar_log("🧹 TODO ha sido limpiado correctamente.\n", "success")
    
    def limpiar_tabla_firmas(self):
        for item in self.tree_firmas.get_children():
            self.tree_firmas.delete(item)
        self.datos_firmas.clear()
    
    def actualizar_tabla_firmas(self, ruta_pdf, estado, tipo, firmante, fecha, magnitud):
        nombre_archivo = os.path.basename(ruta_pdf)
        nombre_magnitud = self.magnitude_manager.MAGNITUDES.get(magnitud, magnitud)
        
        self.datos_firmas.append({
            "archivo": nombre_archivo,
            "estado": estado,
            "tipo": tipo,
            "firmante": firmante,
            "fecha": fecha,
            "magnitud": nombre_magnitud
        })
        
        def _actualizar_tabla():
            self.tree_firmas.insert("", "end", values=(
                nombre_archivo, estado, firmante, fecha, tipo, nombre_magnitud
            ))
        
        self._ejecutar_en_principal(_actualizar_tabla)
    
    def iniciar_procesamiento(self):
        if not self.archivos_pendientes or self.procesando:
            return
        
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
        
        self.log_widget.delete(1.0, tk.END)
        self.ultimo_mensaje_log = ""
        self.vinculos_unicos.clear()
        
        magnitud_nombre = self.magnitude_manager.MAGNITUDES[self.magnitude_manager.magnitud_seleccionada]
        self._insertar_log(f"🚀 INICIANDO PROCESAMIENTO DE {self.total_archivos} ARCHIVO(S)\n", "proceso")
        self._insertar_log(f"📁 Magnitud seleccionada: {magnitud_nombre}\n\n", "magnitud")
        
        # Ejecutar en hilo separado
        threading.Thread(target=self._procesar_lote, daemon=True).start()
    
    def _procesar_lote(self):
        """Procesa el lote completo en hilo separado"""
        archivos_a_procesar = self.archivos_pendientes.copy()
        
        for archivo in archivos_a_procesar:
            if not self.procesando:
                break
                
            self._procesar_archivo_simple(archivo)
            self.archivos_procesados += 1
            
            # Actualizar progreso
            self._ejecutar_en_principal(self.actualizar_progreso)
            
            if archivo in self.archivos_pendientes:
                self.archivos_pendientes.remove(archivo)
        
        self._ejecutar_en_principal(self.procesamiento_completado)
    
    def _procesar_archivo_simple(self, archivo):
        """Procesa un archivo de manera simplificada"""
        try:
            nombre_archivo = os.path.basename(archivo)
            self._insertar_log(f"📄 Procesando: {nombre_archivo}\n", "info")
            
            # Verificar si está firmado
            if self.signature_analyzer.verificar_si_pdf_firmado(archivo):
                self._insertar_log("   📱 PDF FIRMADO - Insertando QR\n", "info")
                # Procesar directamente en el hilo actual
                resultado = self.pdf_processor.procesar_pdf_con_qr_sincrono(archivo, self)
                if resultado:
                    self._insertar_log("   ✅ QR insertado correctamente\n\n", "success")
                else:
                    self._insertar_log("   ❌ Error insertando QR\n\n", "error")
            else:
                self._insertar_log("   🔗 PDF NO FIRMADO - Procesando vinculación\n", "info")
                # Procesar vinculación
                resultado_vinculacion = self.pdf_processor.procesar_vinculacion_pdf_sincrono(archivo, self)
                if resultado_vinculacion and 'ruta_pdf_vinculado' in resultado_vinculacion:
                    self._insertar_log("   ✅ Vinculación completada - Insertando QR\n", "success")
                    # Procesar QR en el PDF vinculado
                    resultado_qr = self.pdf_processor.procesar_pdf_con_qr_sincrono(
                        resultado_vinculacion['ruta_pdf_vinculado'], self
                    )
                    if resultado_qr:
                        self._insertar_log("   ✅ QR insertado correctamente\n\n", "success")
                    else:
                        self._insertar_log("   ❌ Error insertando QR\n\n", "error")
                else:
                    self._insertar_log("   ❌ Error en la vinculación\n\n", "error")
                    
        except Exception as e:
            self._insertar_log(f"   ❌ Error procesando {os.path.basename(archivo)}: {str(e)}\n\n", "error")
    
    def actualizar_progreso(self):
        self.progress["value"] = self.archivos_procesados
        self.lbl_estado_global.config(
            text=f"Procesados: {self.archivos_procesados}/{self.total_archivos}"
        )
    
    def procesamiento_completado(self):
        self.procesando = False
        self.btn_procesar.config(state=tk.NORMAL, bg="#27ae60")
        self.lbl_estado_global.config(
            text=f"Procesamiento completado: {self.archivos_procesados}/{self.total_archivos} archivos", 
            fg="#27ae60"
        )
        self._insertar_log(f"\n✅ PROCESAMIENTO COMPLETADO: {self.archivos_procesados} de {self.total_archivos} archivos procesados.\n", "success")
        self.pdf_processor.limpiar_directorio_temporal_global()

    def mostrar_configuracion(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configuración del Sistema")
        config_window.geometry("380x380")
        config_window.configure(bg="#e9eef7")
        config_window.resizable(False, False)
        config_window.transient(self.root)
        config_window.grab_set()
        
        self.center_window(config_window)
        
        header = tk.Frame(config_window, bg="#1f618d")
        header.pack(fill=tk.X, pady=(0, 15))
        tk.Label(header, text="Configuración del Sistema", bg="#1f618d", fg="white",
                font=("Segoe UI", 12, "bold")).pack(pady=12)
        
        btn_frame = tk.Frame(config_window, bg="#e9eef7")
        btn_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=15)
        
        tk.Button(btn_frame, text="👤 Cambiar credenciales de usuario", 
                 command=lambda: self.verificar_master_y_ejecutar(self.security_manager.change_credentials_dialog, config_window),
                 bg="#3498db", fg="white", font=("Segoe UI", 10),
                 relief=tk.FLAT, pady=8, cursor="hand2").pack(fill=tk.X, pady=6)
        
        tk.Button(btn_frame, text="🔐 Cambiar contraseña maestra", 
                 command=lambda: self.verificar_master_y_ejecutar(self.security_manager.change_master_password_dialog, config_window),
                 bg="#9b59b6", fg="white", font=("Segoe UI", 10),
                 relief=tk.FLAT, pady=8, cursor="hand2").pack(fill=tk.X, pady=6)
        
        tk.Button(btn_frame, text="📁 Configurar carpetas Google Drive", 
                 command=lambda: self.verificar_master_y_ejecutar(self.magnitude_manager.configurar_carpetas_drive, config_window),
                 bg="#e67e22", fg="white", font=("Segoe UI", 10),
                 relief=tk.FLAT, pady=8, cursor="hand2").pack(fill=tk.X, pady=6)
        
        tk.Button(btn_frame, text="ℹ️ Información del sistema", 
                 command=self.mostrar_info_sistema,
                 bg="#2ecc71", fg="white", font=("Segoe UI", 10),
                 relief=tk.FLAT, pady=8, cursor="hand2").pack(fill=tk.X, pady=6)
        
        tk.Button(btn_frame, text="❌ Cerrar", 
                 command=config_window.destroy,
                 bg="#e74c3c", fg="white", font=("Segoe UI", 10),
                 relief=tk.FLAT, pady=8, cursor="hand2").pack(fill=tk.X, pady=6)
    
    def verificar_master_y_ejecutar(self, funcion, parent_window):
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
        
        funcion(parent_window)
    
    def mostrar_info_sistema(self):
        creds = self.security_manager.load_credentials()
        
        drive_config_info = "No configurado"
        try:
            if os.path.exists("drive_config.json"):
                with open("drive_config.json", "r", encoding="utf-8") as f:
                    drive_config = json.load(f)
                drive_config_info = f"Patrones: {drive_config.get('folder_patrones_nombre', 'N/A')}\nCertificados: {drive_config.get('folder_certificados_nombre', 'N/A')}"
        except:
            drive_config_info = "Error cargando configuración"
        
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