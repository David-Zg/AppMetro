"""
Módulo con funciones utilitarias comunes
"""

import tkinter as tk

def center_window(window):
    """
    Centra una ventana en la pantalla
    """
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry('{}x{}+{}+{}'.format(width, height, x, y))