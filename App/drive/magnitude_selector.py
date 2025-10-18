"""
Módulo de selección de magnitud
"""

import tkinter as tk
from tkinter import ttk, messagebox

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