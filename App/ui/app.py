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
        
        # PESTAÑA 4: Análisis Estadístico (NUEVA)
        tab_analisis = tk.Frame(notebook, bg="#e9eef7")
        notebook.add(tab_analisis, text="📊 Análisis Estadístico")
        self.setup_tab_analisis_estadistico(tab_analisis)
        
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
        log_frame = tk.LabelFrame(main_frame, text="📋 Registro de actividades", 
                                 bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=8, 
                                                    font=("Consolas", 8), wrap=tk.WORD, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.log_widget.tag_config("info", foreground="#1f618d")
        self.log_widget.tag_config("success", foreground="#27ae60")
        self.log_widget.tag_config("error", foreground="#e74c3c")
        
        # Buttons frame
        buttons_frame = tk.Frame(main_frame, bg="#e9eef7")
        buttons_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.btn_procesar = tk.Button(buttons_frame, text="▶️ PROCESAR ARCHIVOS", 
                                       command=self.iniciar_procesamiento_simple,
                                       bg="#27ae60", fg="white", font=("Segoe UI", 11, "bold"),
                                       relief=tk.FLAT, padx=20, pady=10, state=tk.DISABLED)
        self.btn_procesar.pack(side=tk.LEFT, padx=8, expand=True, fill=tk.X)
        
        tk.Button(buttons_frame, text="⚙️ CONFIGURACIÓN", command=self.mostrar_configuracion,
                 bg="#9b59b6", fg="white", font=("Segoe UI", 11, "bold"),
                 relief=tk.FLAT, padx=20, pady=10).pack(side=tk.LEFT, padx=8)
    
    def setup_tab_carga_patrones(self, parent):
        """Tab de Carga de Patrones"""
        main_frame = tk.Frame(parent, bg="#e9eef7")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        
        # Header explicativo
        info_frame = tk.Frame(main_frame, bg="#d6eaf8", relief=tk.RIDGE, bd=2)
        info_frame.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(info_frame, text="📦 CARGA DE PATRONES A GOOGLE DRIVE", 
                bg="#d6eaf8", fg="#1f618d", font=("Segoe UI", 11, "bold")).pack(pady=8)
        
        tk.Label(info_frame, 
                text="Selecciona archivos PDF escaneados de calibraciones/ensayos para subirlos como patrones.\n"
                     "El sistema detectará automáticamente si ya existen en Drive y evitará duplicados.",
                bg="#d6eaf8", fg="#2c3e50", font=("Segoe UI", 8), justify=tk.LEFT).pack(padx=12, pady=(0, 8))
        
        # File frame
        file_frame = tk.LabelFrame(main_frame, text="📄 Archivos PDF a cargar como patrones", 
                                  bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        file_frame.pack(fill=tk.X, pady=(0, 8))
        
        btn_frame = tk.Frame(file_frame, bg="#e9eef7")
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        
        tk.Button(btn_frame, text="📂 Seleccionar PDFs", command=self.seleccionar_patrones,
                 bg="#3498db", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        tk.Button(btn_frame, text="🗑️ Limpiar Lista", command=self.limpiar_lista_patrones,
                 bg="#e74c3c", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        self.lista_patrones = tk.Listbox(file_frame, height=5, font=("Segoe UI", 8))
        self.lista_patrones.pack(fill=tk.X, padx=8, pady=(0, 8))
        
        # Progress frame
        progress_frame = tk.LabelFrame(main_frame, text="📊 Progreso de Carga", 
                                      bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        progress_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.progress_patrones = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_patrones.pack(fill=tk.X, padx=8, pady=8)
        
        self.lbl_estado_patrones = tk.Label(progress_frame, text="Esperando archivos...", 
                                           bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 9, "bold"))
        self.lbl_estado_patrones.pack(pady=(0, 8))
        
        # Log frame
        log_frame = tk.LabelFrame(main_frame, text="📋 Registro de carga", 
                                 bg="#e9eef7", fg="#1f618d", font=("Segoe UI", 10, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        self.log_patrones = scrolledtext.ScrolledText(log_frame, height=6, 
                                                     font=("Consolas", 8), wrap=tk.WORD, state=tk.DISABLED)
        self.log_patrones.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.log_patrones.tag_config("info", foreground="#1f618d")
        self.log_patrones.tag_config("success", foreground="#27ae60")
        self.log_patrones.tag_config("error", foreground="#e74c3c")
        self.log_patrones.tag_config("warning", foreground="#e67e22")
        
        # Buttons frame
        buttons_frame = tk.Frame(main_frame, bg="#e9eef7")
        buttons_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.btn_cargar_patrones = tk.Button(buttons_frame, text="📤 CARGAR PATRONES A DRIVE", 
                                             command=self.iniciar_carga_patrones,
                                             bg="#f39c12", fg="white", font=("Segoe UI", 11, "bold"),
                                             relief=tk.FLAT, padx=20, pady=10, state=tk.DISABLED)
        self.btn_cargar_patrones.pack(expand=True, fill=tk.X, padx=8)
    
    def setup_tab_firmas(self, parent):
        """Tab de información de firmas"""
        main_frame = tk.Frame(parent, bg="#e9eef7")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        
        # Header
        header_frame = tk.Frame(main_frame, bg="#d6eaf8", relief=tk.RIDGE, bd=2)
        header_frame.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(header_frame, text="📋 INFORMACIÓN DE FIRMAS DIGITALES", 
                bg="#d6eaf8", fg="#1f618d", font=("Segoe UI", 11, "bold")).pack(pady=8)
        
        tk.Label(header_frame, 
                text="Consulta información detallada de las firmas de los PDFs procesados",
                bg="#d6eaf8", fg="#2c3e50", font=("Segoe UI", 8)).pack(pady=(0, 8))
        
        # Frame de botones
        btn_frame = tk.Frame(main_frame, bg="#e9eef7")
        btn_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Button(btn_frame, text="🔄 Actualizar datos", 
                 command=self.actualizar_tabla_firmas,
                 bg="#3498db", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        tk.Button(btn_frame, text="📄 Exportar a CSV", 
                 command=self.exportar_firmas_csv,
                 bg="#27ae60", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        tk.Button(btn_frame, text="🗑️ Limpiar", 
                 command=self.limpiar_tabla_firmas,
                 bg="#e74c3c", fg="white", font=("Segoe UI", 9, "bold"),
                 relief=tk.FLAT, padx=12, pady=6).pack(side=tk.LEFT, padx=4)
        
        # Tree frame
        tree_frame = tk.Frame(main_frame, bg="#e9eef7")
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview
        self.tree_firmas = ttk.Treeview(tree_frame, 
                                       columns=("archivo", "firmante", "fecha", "certificado"),
                                       show="headings",
                                       yscrollcommand=vsb.set,
                                       xscrollcommand=hsb.set)
        
        vsb.config(command=self.tree_firmas.yview)
        hsb.config(command=self.tree_firmas.xview)
        
        # Columnas
        self.tree_firmas.heading("archivo", text="Archivo")
        self.tree_firmas.heading("firmante", text="Firmante")
        self.tree_firmas.heading("fecha", text="Fecha de Firma")
        self.tree_firmas.heading("certificado", text="Emisor del Certificado")
        
        self.tree_firmas.column("archivo", width=180)
        self.tree_firmas.column("firmante", width=150)
        self.tree_firmas.column("fecha", width=130)
        self.tree_firmas.column("certificado", width=150)
        
        # Grid
        self.tree_firmas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
    
    def setup_tab_analisis_estadistico(self, parent):
        """Tab de Análisis Estadístico - Módulo en construcción"""
        main_frame = tk.Frame(parent, bg="#e9eef7")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        
        # Header principal con gradiente visual
        header_frame = tk.Frame(main_frame, bg="#2c3e50", relief=tk.RIDGE, bd=2)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(header_frame, text="📊 ANÁLISIS ESTADÍSTICO", 
                bg="#2c3e50", fg="white", font=("Segoe UI", 13, "bold")).pack(pady=12)
        
        # Subtítulo con estado
        estado_frame = tk.Frame(header_frame, bg="#34495e")
        estado_frame.pack(fill=tk.X, pady=(0, 12))
        
        tk.Label(estado_frame, text="🔧 Módulo de Análisis Estadístico - En proceso de creación", 
                bg="#34495e", fg="#f39c12", font=("Segoe UI", 10, "bold")).pack(pady=8)
        
        # Container principal con scroll
        canvas = tk.Canvas(main_frame, bg="#e9eef7", highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#e9eef7")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Frame de pruebas estadísticas
        pruebas_frame = tk.LabelFrame(scrollable_frame, text="🧮 Pruebas estadísticas previstas", 
                                     bg="#ffffff", fg="#1f618d", font=("Segoe UI", 11, "bold"),
                                     relief=tk.GROOVE, bd=3, padx=20, pady=15)
        pruebas_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 12), padx=20)
        
        # Sección 1: Pruebas de Normalidad
        seccion1 = tk.Frame(pruebas_frame, bg="#ffffff")
        seccion1.pack(fill=tk.X, pady=8)
        
        tk.Label(seccion1, text="🔍", bg="#ffffff", font=("Segoe UI", 14)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(seccion1, text="Pruebas de normalidad:", 
                bg="#ffffff", fg="#2c3e50", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        
        tk.Label(pruebas_frame, text="   • Shapiro-Wilk\n   • Kolmogorov-Smirnov", 
                bg="#ffffff", fg="#34495e", font=("Segoe UI", 9), justify=tk.LEFT).pack(anchor="w", padx=30)
        
        # Separador
        tk.Frame(pruebas_frame, height=2, bg="#bdc3c7").pack(fill=tk.X, pady=10)
        
        # Sección 2: Pruebas No Paramétricas
        seccion2 = tk.Frame(pruebas_frame, bg="#ffffff")
        seccion2.pack(fill=tk.X, pady=8)
        
        tk.Label(seccion2, text="📊", bg="#ffffff", font=("Segoe UI", 14)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(seccion2, text="Pruebas no paramétricas:", 
                bg="#ffffff", fg="#2c3e50", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        
        tk.Label(pruebas_frame, text="   • Mann-Whitney U\n   • Wilcoxon", 
                bg="#ffffff", fg="#34495e", font=("Segoe UI", 9), justify=tk.LEFT).pack(anchor="w", padx=30)
        
        # Separador
        tk.Frame(pruebas_frame, height=2, bg="#bdc3c7").pack(fill=tk.X, pady=10)
        
        # Sección 3: Comparación de Medias
        seccion3 = tk.Frame(pruebas_frame, bg="#ffffff")
        seccion3.pack(fill=tk.X, pady=8)
        
        tk.Label(seccion3, text="📈", bg="#ffffff", font=("Segoe UI", 14)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(seccion3, text="Pruebas de comparación de medias:", 
                bg="#ffffff", fg="#2c3e50", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        
        tk.Label(pruebas_frame, text="   • t-test (Student)\n   • ANOVA (Análisis de Varianza)", 
                bg="#ffffff", fg="#34495e", font=("Segoe UI", 9), justify=tk.LEFT).pack(anchor="w", padx=30)
        
        # Separador
        tk.Frame(pruebas_frame, height=2, bg="#bdc3c7").pack(fill=tk.X, pady=10)
        
        # Sección 4: Incertidumbre (NUEVO)
        seccion4 = tk.Frame(pruebas_frame, bg="#ffffff")
        seccion4.pack(fill=tk.X, pady=8)
        
        tk.Label(seccion4, text="🎯", bg="#ffffff", font=("Segoe UI", 14)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(seccion4, text="Estimación de incertidumbre y varianza combinada", 
                bg="#ffffff", fg="#2c3e50", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        
        tk.Label(pruebas_frame, text="   • Cálculo de incertidumbre tipo A y tipo B\n   • Varianza combinada y expandida\n   • Factor de cobertura k", 
                bg="#ffffff", fg="#34495e", font=("Segoe UI", 9), justify=tk.LEFT).pack(anchor="w", padx=30)
        
        # Separador
        tk.Frame(pruebas_frame, height=2, bg="#bdc3c7").pack(fill=tk.X, pady=10)
        
        # Sección 5: Gráficos
        seccion5 = tk.Frame(pruebas_frame, bg="#ffffff")
        seccion5.pack(fill=tk.X, pady=8)
        
        tk.Label(seccion5, text="📉", bg="#ffffff", font=("Segoe UI", 14)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(seccion5, text="Gráficos estadísticos:", 
                bg="#ffffff", fg="#2c3e50", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        
        tk.Label(pruebas_frame, text="   • Histogramas de distribución\n   • Boxplot (Diagramas de caja)\n   • QQ-Plot (Gráficos cuantil-cuantil)\n   • Gráficos de control", 
                bg="#ffffff", fg="#34495e", font=("Segoe UI", 9), justify=tk.LEFT).pack(anchor="w", padx=30)
        
        # Frame de tecnologías
        tech_frame = tk.LabelFrame(scrollable_frame, text="🔧 Tecnologías de implementación", 
                                  bg="#ffffff", fg="#1f618d", font=("Segoe UI", 11, "bold"),
                                  relief=tk.GROOVE, bd=3, padx=20, pady=15)
        tech_frame.pack(fill=tk.X, pady=(0, 12), padx=20)
        
        # Iconos y tecnologías
        tech_items = [
            ("🐍", "SciPy", "Análisis estadístico científico"),
            ("🐼", "Pandas", "Manipulación y análisis de datos"),
            ("📊", "Matplotlib", "Visualización de gráficos"),
            ("📉", "Seaborn", "Gráficos estadísticos avanzados"),
            ("🔢", "NumPy", "Computación numérica")
        ]
        
        for emoji, tech, desc in tech_items:
            item_frame = tk.Frame(tech_frame, bg="#ffffff")
            item_frame.pack(fill=tk.X, pady=4)
            
            tk.Label(item_frame, text=emoji, bg="#ffffff", font=("Segoe UI", 12)).pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(item_frame, text=f"{tech}:", bg="#ffffff", fg="#2c3e50", 
                    font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 5))
            tk.Label(item_frame, text=desc, bg="#ffffff", fg="#7f8c8d", 
                    font=("Segoe UI", 8)).pack(side=tk.LEFT)
        
        # Banner de estado final
        footer_frame = tk.Frame(scrollable_frame, bg="#27ae60", relief=tk.RAISED, bd=2)
        footer_frame.pack(fill=tk.X, pady=(0, 15), padx=20)
        
        tk.Label(footer_frame, text="✨ Próximamente disponible", 
                bg="#27ae60", fg="white", font=("Segoe UI", 11, "bold")).pack(pady=10)
        
        tk.Label(footer_frame, 
                text="Este módulo se integrará con las funcionalidades de procesamiento\n"
                     "para ofrecer análisis estadístico completo de los datos de certificación",
                bg="#27ae60", fg="white", font=("Segoe UI", 8), justify=tk.CENTER).pack(pady=(0, 10))
        
        # Empaquetar canvas y scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    # ==================== MÉTODOS DE GESTIÓN DE ARCHIVOS ====================
    
    def seleccionar_archivos(self):
        archivos = filedialog.askopenfilenames(
            title="Seleccionar archivos PDF",
            filetypes=[("Archivos PDF", "*.pdf")]
        )
        if archivos:
            self.archivos_pendientes.extend(archivos)
            self.actualizar_lista_archivos()
            self.btn_procesar.config(state=tk.NORMAL)
            self._insertar_log(f"✅ {len(archivos)} archivo(s) agregado(s).\n", "success")
    
    def seleccionar_patrones(self):
        """Seleccionar archivos PDF para cargar como patrones"""
        archivos = filedialog.askopenfilenames(
            title="Seleccionar patrones PDF",
            filetypes=[("Archivos PDF", "*.pdf")]
        )
        if archivos:
            self.patrones_pendientes.extend(archivos)
            self.actualizar_lista_patrones()
            self.btn_cargar_patrones.config(state=tk.NORMAL)
            self._insertar_log_patrones(f"✅ {len(archivos)} patrón(es) agregado(s).\n", "success")
    
    def actualizar_lista_archivos(self):
        self.lista_archivos.delete(0, tk.END)
        for archivo in self.archivos_pendientes:
            self.lista_archivos.insert(tk.END, os.path.basename(archivo))
    
    def actualizar_lista_patrones(self):
        """Actualizar lista de patrones pendientes"""
        self.lista_patrones.delete(0, tk.END)
        for archivo in self.patrones_pendientes:
            self.lista_patrones.insert(tk.END, os.path.basename(archivo))
    
    def limpiar_todo(self):
        if messagebox.askyesno("Confirmar", "¿Desea limpiar todos los archivos y reiniciar?"):
            self.archivos_pendientes.clear()
            self.actualizar_lista_archivos()
            self.btn_procesar.config(state=tk.DISABLED)
            self.progress["value"] = 0
            self.archivos_procesados = 0
            self.total_archivos = 0
            self.lbl_estado_global.config(text="Esperando archivos...", fg="#1f618d")
            self.log_widget.config(state=tk.NORMAL)
            self.log_widget.delete(1.0, tk.END)
            self.log_widget.config(state=tk.DISABLED)
            self.ultimo_mensaje_log = ""
            self.vinculos_unicos.clear()
            self._insertar_log("🔄 Sistema reiniciado.\n", "info")
    
    def limpiar_lista_patrones(self):
        """Limpiar lista de patrones"""
        if messagebox.askyesno("Confirmar", "¿Desea limpiar la lista de patrones?"):
            self.patrones_pendientes.clear()
            self.actualizar_lista_patrones()
            self.btn_cargar_patrones.config(state=tk.DISABLED)
            self.progress_patrones["value"] = 0
            self.patrones_procesados = 0
            self.total_patrones = 0
            self.lbl_estado_patrones.config(text="Esperando archivos...", fg="#1f618d")
            self.log_patrones.config(state=tk.NORMAL)
            self.log_patrones.delete(1.0, tk.END)
            self.log_patrones.config(state=tk.DISABLED)
            self.ultimo_mensaje_log_patrones = ""
            self._insertar_log_patrones("🔄 Lista de patrones limpiada.\n", "info")
    
    # ==================== MÉTODOS DE LOG ====================
    
    def _insertar_log(self, mensaje, tipo="info"):
        """Insertar mensaje en el log de procesamiento (evita duplicados)"""
        if mensaje != self.ultimo_mensaje_log:
            self.cola_log.put(("log_procesamiento", mensaje, tipo))
            self.ultimo_mensaje_log = mensaje
    
    def _insertar_log_patrones(self, mensaje, tipo="info"):
        """Insertar mensaje en el log de patrones (evita duplicados)"""
        if mensaje != self.ultimo_mensaje_log_patrones:
            self.cola_log_patrones.put((mensaje, tipo))
            self.ultimo_mensaje_log_patrones = mensaje
    
    def procesar_cola_log(self):
        """Procesar mensajes del log de procesamiento"""
        try:
            while True:
                tipo_log, mensaje, tag = self.cola_log.get_nowait()
                if tipo_log == "log_procesamiento":
                    self.log_widget.config(state=tk.NORMAL)
                    self.log_widget.insert(tk.END, mensaje, tag)
                    self.log_widget.see(tk.END)
                    self.log_widget.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self.procesar_cola_log)
    
    def procesar_cola_log_patrones(self):
        """Procesar mensajes del log de patrones"""
        try:
            while True:
                mensaje, tag = self.cola_log_patrones.get_nowait()
                self.log_patrones.config(state=tk.NORMAL)
                self.log_patrones.insert(tk.END, mensaje, tag)
                self.log_patrones.see(tk.END)
                self.log_patrones.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self.procesar_cola_log_patrones)
    
    def procesar_cola_comandos(self):
        """Procesar comandos desde otros hilos"""
        try:
            while True:
                comando, datos = self.cola_comandos.get_nowait()
                if comando == "actualizar_tabla_firmas":
                    self._actualizar_tabla_firmas_ui(datos)
        except queue.Empty:
            pass
        self.root.after(100, self.procesar_cola_comandos)
    
    # ==================== MÉTODOS DE FIRMAS ====================
    
    def actualizar_tabla_firmas(self):
        """Actualizar tabla de firmas con datos recientes"""
        if not self.datos_firmas:
            messagebox.showinfo("Info", "No hay datos de firmas para mostrar")
            return
        self._actualizar_tabla_firmas_ui(self.datos_firmas)
    
    def _actualizar_tabla_firmas_ui(self, datos):
        """Actualizar UI de tabla de firmas"""
        for item in self.tree_firmas.get_children():
            self.tree_firmas.delete(item)
        
        for dato in datos:
            self.tree_firmas.insert("", tk.END, values=(
                dato.get("archivo", ""),
                dato.get("firmante", ""),
                dato.get("fecha", ""),
                dato.get("certificado", "")
            ))
    
    def limpiar_tabla_firmas(self):
        """Limpiar tabla de firmas"""
        if messagebox.askyesno("Confirmar", "¿Desea limpiar los datos de firmas?"):
            for item in self.tree_firmas.get_children():
                self.tree_firmas.delete(item)
            self.datos_firmas.clear()
    
    def exportar_firmas_csv(self):
        """Exportar datos de firmas a CSV"""
        if not self.datos_firmas:
            messagebox.showinfo("Info", "No hay datos para exportar")
            return
        
        archivo = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            title="Guardar datos de firmas"
        )
        
        if archivo:
            try:
                import csv
                with open(archivo, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=["archivo", "firmante", "fecha", "certificado"])
                    writer.writeheader()
                    writer.writerows(self.datos_firmas)
                messagebox.showinfo("Éxito", "Datos exportados correctamente")
            except Exception as e:
                messagebox.showerror("Error", f"Error al exportar: {str(e)}")
    
    # ==================== MÉTODOS DE DRIVE ====================
    
    def inicializar_drive(self):
        """Inicializar conexión con Drive"""
        try:
            if not self.magnitude_manager.verificar_autenticacion():
                messagebox.showwarning("Advertencia", 
                    "No se pudo autenticar con Google Drive.\n"
                    "Algunas funciones pueden no estar disponibles.")
                return
            
            if not self.magnitude_manager.verificar_configuracion():
                messagebox.showinfo("Configuración requerida",
                    "Es necesario configurar las carpetas de Drive.\n"
                    "Por favor, vaya a Configuración > Configurar carpetas Drive")
                return
            
            # Cargar lista de patrones existentes
            self.actualizar_lista_patrones_drive()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al inicializar Drive: {str(e)}")
    
    def actualizar_lista_patrones_drive(self):
        """Actualizar lista de patrones existentes en Drive"""
        try:
            folder_id = self.magnitude_manager.folder_patrones
            if folder_id:
                archivos = self.magnitude_manager.listar_archivos_drive(folder_id)
                self.patrones_existentes_drive = {archivo['name'] for archivo in archivos}
                self._insertar_log_patrones(
                    f"📂 {len(self.patrones_existentes_drive)} patrones encontrados en Drive.\n", 
                    "info"
                )
        except Exception as e:
            self._insertar_log_patrones(f"⚠️ Error al listar patrones: {str(e)}\n", "error")
    
    def cambiar_magnitud(self):
        """Abrir selector de magnitud"""
        selector = MagnitudeSelector(self.root, self.magnitude_manager)
        magnitud_seleccionada = selector.get_selection()
        
        if magnitud_seleccionada:
            self.magnitude_manager.set_magnitud_actual(magnitud_seleccionada)
            self.actualizar_display_magnitud()
            messagebox.showinfo("Éxito", 
                f"Magnitud cambiada a: {self.magnitude_manager.get_nombre_magnitud()}")
    
    def actualizar_display_magnitud(self):
        """Actualizar display de magnitud actual"""
        nombre_magnitud = self.magnitude_manager.get_nombre_magnitud()
        emoji = self.magnitude_manager.get_emoji_magnitud()
        
        self.lbl_magnitud_actual.config(
            text=f"{emoji} Magnitud actual: {nombre_magnitud}"
        )
        
        if hasattr(self, 'lbl_magnitud_archivos'):
            self.lbl_magnitud_archivos.config(
                text=f"Los archivos se guardarán en: {emoji} {nombre_magnitud}"
            )
    
    # ==================== MÉTODOS DE PROCESAMIENTO ====================
    
    def iniciar_procesamiento_simple(self):
        """Iniciar procesamiento simplificado"""
        if not self.archivos_pendientes:
            messagebox.showwarning("Advertencia", "No hay archivos para procesar")
            return
        
        if self.procesando:
            messagebox.showwarning("Advertencia", "Ya hay un procesamiento en curso")
            return
        
        self.procesando = True
        self.btn_procesar.config(state=tk.DISABLED, bg="#95a5a6")
        self.archivos_procesados = 0
        self.total_archivos = len(self.archivos_pendientes)
        self.progress["maximum"] = self.total_archivos
        self.progress["value"] = 0
        
        self._insertar_log(f"\n{'='*60}\n", "info")
        self._insertar_log(f"🚀 INICIANDO PROCESAMIENTO - {self.total_archivos} archivo(s)\n", "info")
        self._insertar_log(f"{'='*60}\n\n", "info")
        
        # Procesar en hilo separado
        thread = threading.Thread(target=self.procesar_archivos_secuencial, daemon=True)
        thread.start()
    
    def iniciar_carga_patrones(self):
        """Iniciar carga de patrones a Drive"""
        if not self.patrones_pendientes:
            messagebox.showwarning("Advertencia", "No hay patrones para cargar")
            return
        
        if self.cargando_patrones:
            messagebox.showwarning("Advertencia", "Ya hay una carga en curso")
            return
        
        # Actualizar lista de patrones existentes antes de cargar
        self.actualizar_lista_patrones_drive()
        
        self.cargando_patrones = True
        self.btn_cargar_patrones.config(state=tk.DISABLED, bg="#95a5a6")
        self.patrones_procesados = 0
        self.total_patrones = len(self.patrones_pendientes)
        self.progress_patrones["maximum"] = self.total_patrones
        self.progress_patrones["value"] = 0
        
        self._insertar_log_patrones(f"\n{'='*60}\n", "info")
        self._insertar_log_patrones(f"🚀 INICIANDO CARGA DE PATRONES - {self.total_patrones} archivo(s)\n", "info")
        self._insertar_log_patrones(f"{'='*60}\n\n", "info")
        
        # Procesar en hilo separado
        thread = threading.Thread(target=self.cargar_patrones_secuencial, daemon=True)
        thread.start()
    
    def cargar_patrones_secuencial(self):
        """Cargar patrones secuencialmente"""
        folder_id = self.magnitude_manager.folder_patrones
        
        if not folder_id:
            self._insertar_log_patrones("❌ Error: Carpeta de patrones no configurada\n", "error")
            self._ejecutar_en_principal(self.carga_patrones_completada)
            return
        
        archivos_a_cargar = list(self.patrones_pendientes)
        
        for archivo in archivos_a_cargar:
            nombre_archivo = os.path.basename(archivo)
            
            # Verificar si ya existe
            if nombre_archivo in self.patrones_existentes_drive:
                self._insertar_log_patrones(f"⚠️ {nombre_archivo} - Ya existe en Drive (omitido)\n", "warning")
            else:
                self._insertar_log_patrones(f"📤 Subiendo: {nombre_archivo}\n", "info")
                
                try:
                    result = self.magnitude_manager.subir_archivo_drive(archivo, folder_id)
                    if result:
                        self._insertar_log_patrones(f"   ✅ Subido correctamente\n", "success")
                        self.patrones_existentes_drive.add(nombre_archivo)
                    else:
                        self._insertar_log_patrones(f"   ❌ Error al subir\n", "error")
                except Exception as e:
                    self._insertar_log_patrones(f"   ❌ Error: {str(e)}\n", "error")
            
            self.patrones_procesados += 1
            self._ejecutar_en_principal(self.actualizar_progreso_patrones)
            
            if archivo in self.patrones_pendientes:
                self.patrones_pendientes.remove(archivo)
        
        self._ejecutar_en_principal(self.carga_patrones_completada)
    
    def actualizar_progreso_patrones(self):
        """Actualizar progreso de carga de patrones"""
        self.progress_patrones["value"] = self.patrones_procesados
        self.lbl_estado_patrones.config(
            text=f"Procesados: {self.patrones_procesados}/{self.total_patrones}"
        )
    
    def carga_patrones_completada(self):
        """Finalizar carga de patrones"""
        self.cargando_patrones = False
        self.btn_cargar_patrones.config(state=tk.NORMAL, bg="#f39c12")
        self.lbl_estado_patrones.config(
            text=f"Carga completada: {self.patrones_procesados}/{self.total_patrones} archivos", 
            fg="#27ae60"
        )
        self._insertar_log_patrones(
            f"\n✅ CARGA COMPLETADA: {self.patrones_procesados} de {self.total_patrones} archivos procesados.\n", 
            "success"
        )
    
    def _ejecutar_en_principal(self, funcion):
        """Ejecutar función en el hilo principal"""
        self.root.after(0, funcion)
    
    def procesar_archivos_secuencial(self):
        """Procesar archivos de manera secuencial"""
        archivos_a_procesar = list(self.archivos_pendientes)
        
        for archivo in archivos_a_procesar:
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