"""
Módulo de procesamiento de PDFs (vinculación, QR, etc.)
Versión mejorada con búsqueda directa de patrones desde carpeta
✅ OPTIMIZADO: Logs únicos sin repeticiones
"""

import os
import json
import threading
import shutil
import re
from glob import glob
from datetime import datetime

import fitz
import qrcode
import pytesseract
from PIL import Image
import io

class PDFProcessor:
    """Procesa documentos PDF - BÚSQUEDA DIRECTA DE PATRONES EN CARPETA"""
    
    def __init__(self, magnitude_manager, signature_analyzer):
        self.magnitude_manager = magnitude_manager
        self.signature_analyzer = signature_analyzer
        # 🔥 MODIFICACIÓN: Tamaño QR 2.1 cm x 2.1 cm (convertido a puntos PDF)
        # 1 cm = 28.35 puntos, 2.1 cm = 59.535 puntos ≈ 60 puntos
        self.qr_size = 60  # 🔥 CAMBIO: De 40 a 60 puntos (2.1 cm)
        self.temp_pdf = "temp_output.pdf"
        self.log_file = "vinculados.json"
        self.log_error_file = "errores_qr_log.txt"
    
    def _extraer_texto_con_ocr(self, page):
        """
        Extrae texto de una página PDF usando OCR (Tesseract).
        Devuelve una lista de palabras en el formato compatible con fitz.get_text("words"):
        [x0, y0, x1, y1, 'palabra', ...]
        
        Args:
            page: Objeto fitz.Page
            
        Returns:
            list: Lista de palabras con coordenadas en formato fitz
        """
        try:
            # Generar imagen de la página con buena resolución
            mat = fitz.Matrix(2, 2)  # Escala 2x para mejor calidad OCR
            pix = page.get_pixmap(matrix=mat)
            
            # Convertir a imagen PIL
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            
            # Ejecutar OCR con tesseract en español e inglés
            ocr_data = pytesseract.image_to_data(img, lang='spa+eng', output_type=pytesseract.Output.DICT)
            
            # Convertir resultados OCR al formato de fitz
            palabras = []
            scale_factor = 0.5  # Compensar la escala 2x aplicada al pixmap
            
            for i in range(len(ocr_data['text'])):
                texto = ocr_data['text'][i].strip()
                conf = int(ocr_data['conf'][i])
                
                # Filtrar palabras vacías y con confianza muy baja
                if texto and conf > 30:
                    x0 = ocr_data['left'][i] * scale_factor
                    y0 = ocr_data['top'][i] * scale_factor
                    x1 = (ocr_data['left'][i] + ocr_data['width'][i]) * scale_factor
                    y1 = (ocr_data['top'][i] + ocr_data['height'][i]) * scale_factor
                    
                    # Formato compatible con fitz: (x0, y0, x1, y1, "palabra", block_no, line_no, word_no)
                    palabras.append((x0, y0, x1, y1, texto, 0, 0, 0))
            
            return palabras
            
        except ImportError:
            return []
        except Exception as e:
            return []
    
    def _obtener_nombres_patrones_desde_carpeta(self, app=None):
        """
        🔥 NUEVO: Obtiene los nombres de todos los archivos PDF desde Google Drive (carpeta Patrones)
        
        Returns:
            dict: Diccionario con {nombre_sin_extension: id_archivo_drive}
        """
        patrones = {}
        
        try:
            # Obtener ID de la carpeta de patrones desde magnitude_manager
            folder_patrones_id = self.magnitude_manager.folder_patrones
            
            if not folder_patrones_id:
                if app:
                    app._insertar_log(f"   ⚠️ No se ha configurado la carpeta de Patrones en Drive\n", "warning")
                return patrones
            
            # Buscar todos los PDFs en la carpeta de Patrones de Drive
            query = f"'{folder_patrones_id}' in parents and mimeType='application/pdf' and trashed=false"
            archivos_drive = self.magnitude_manager.drive.ListFile({'q': query}).GetList()
            
            for archivo in archivos_drive:
                nombre_con_extension = archivo['title']
                nombre_sin_extension = os.path.splitext(nombre_con_extension)[0]
                file_id = archivo['id']
                
                # Guardar tanto el nombre completo como sin espacios ni guiones para búsqueda flexible
                patrones[nombre_sin_extension] = file_id
                
                # También guardar versiones normalizadas para mejor coincidencia
                nombre_normalizado = nombre_sin_extension.replace(" ", "").replace("-", "").replace("_", "").upper()
                patrones[nombre_normalizado] = file_id
            
            # 🎯 SOLO mostrar log si app está disponible (no en modo silencioso)
            # if app:
            #     app._insertar_log(f"   📁 {len(archivos_drive)} patrones encontrados en Drive\n", "info")
            
            return patrones
            
        except Exception as e:
            if app:
                app._insertar_log(f"   ❌ Error obteniendo patrones de Drive: {str(e)}\n", "error")
            return patrones
    
    def _buscar_patron_en_texto(self, texto_completo, nombres_patrones):
        """
        🔥 NUEVO: Busca coincidencias de nombres de patrones en el texto
        
        Args:
            texto_completo: Texto completo de la página
            nombres_patrones: Diccionario con nombres de patrones
            
        Returns:
            list: Lista de nombres de patrones encontrados
        """
        coincidencias = []
        texto_normalizado = texto_completo.upper().replace(" ", "").replace("-", "").replace("_", "")
        
        for nombre_patron in nombres_patrones.keys():
            nombre_buscar = nombre_patron.upper().replace(" ", "").replace("-", "").replace("_", "")
            
            # Buscar el patrón en el texto
            if nombre_buscar in texto_normalizado:
                coincidencias.append(nombre_patron)
        
        return coincidencias
    
    def _buscar_coordenadas_patron_en_pagina(self, page, nombre_patron, app=None):
        """
        🔥 NUEVO: Busca las coordenadas exactas donde aparece el nombre del patrón en la página
        
        Args:
            page: Página de fitz
            nombre_patron: Nombre del patrón a buscar
            app: Instancia de la aplicación para logs
            
        Returns:
            list: Lista de rectángulos donde aparece el patrón
        """
        # Primero intentar con búsqueda directa de fitz
        texto_buscar = nombre_patron
        areas = page.search_for(texto_buscar)
        
        if areas:
            return areas
        
        # Si no encuentra, intentar con palabras individuales
        palabras = page.get_text("words")
        
        # Si no hay texto embebido, usar OCR
        if not palabras:
            if app:
                app._insertar_log(f"   🔍 Usando OCR para buscar '{nombre_patron}'\n", "info")
            palabras = self._extraer_texto_con_ocr(page)
        
        if not palabras:
            return []
        
        # Normalizar el patrón buscado
        patron_normalizado = nombre_patron.upper().replace(" ", "").replace("-", "").replace("_", "")
        
        # Buscar coincidencias en las palabras
        areas_encontradas = []
        for palabra in palabras:
            x0, y0, x1, y1, texto = palabra[:5]
            texto_normalizado = texto.upper().replace(" ", "").replace("-", "").replace("_", "")
            
            # Si la palabra contiene parte del patrón o viceversa
            if patron_normalizado in texto_normalizado or texto_normalizado in patron_normalizado:
                areas_encontradas.append(fitz.Rect(x0, y0, x1, y1))
        
        return areas_encontradas
    
    def procesar_vinculacion_pdf_sincrono(self, archivo, app):
        """
        🔥 VERSIÓN OPTIMIZADA: Busca nombres de patrones de la carpeta en la segunda página del PDF
        ✅ Solo muestra patrones únicos en el log (sin repeticiones)
        """
        temp_path = None
        try:
            nombre = os.path.basename(archivo)
            
            # 1. Obtener nombres de patrones desde la carpeta (SILENCIOSO)
            patrones_disponibles = self._obtener_nombres_patrones_desde_carpeta(app=None)
            
            if not patrones_disponibles:
                app._insertar_log(f"   ⚠️ No se encontraron patrones\n", "warning")
                return {'ruta_pdf_vinculado': archivo, 'vinculos': 0}
            
            # 2. Abrir el PDF a procesar
            temp_path = os.path.join(os.path.dirname(archivo), self.temp_pdf)
            shutil.copy2(archivo, temp_path)
            doc = fitz.open(temp_path)
            
            vinculos_creados = 0
            vinculos_unicos = set()  # 🎯 Set para patrones únicos
            
            # 3. Procesar la SEGUNDA página (índice 1) que es donde están los patrones
            if len(doc) < 2:
                app._insertar_log(f"   ⚠️ El PDF solo tiene {len(doc)} página(s)\n", "warning")
                doc.close()
                return {'ruta_pdf_vinculado': archivo, 'vinculos': 0}
            
            page = doc[1]  # Segunda página (índice 1)
            
            # 4. Extraer todo el texto de la página (SILENCIOSO)
            texto_completo = page.get_text()
            
            # Si no hay texto, usar OCR (SILENCIOSO)
            if not texto_completo.strip():
                palabras_ocr = self._extraer_texto_con_ocr(page)
                texto_completo = ' '.join([p[4] for p in palabras_ocr])
            
            # 5. Buscar qué patrones aparecen en el texto (SILENCIOSO)
            patrones_encontrados = self._buscar_patron_en_texto(texto_completo, patrones_disponibles)
            
            # 6. Para cada patrón encontrado, buscar sus coordenadas y crear el vínculo
            for nombre_patron in patrones_encontrados:
                # Buscar coordenadas exactas del patrón en la página
                areas = self._buscar_coordenadas_patron_en_pagina(page, nombre_patron, app)
                
                if not areas:
                    app._insertar_log(f"   ⚠️ No se encontraron coordenadas para '{nombre_patron}'\n", "warning")
                    continue
                
                # Obtener file_id del patrón desde el diccionario
                file_id_patron = patrones_disponibles[nombre_patron]
                
                # Generar enlace directo de Drive
                enlace = f"https://drive.google.com/file/d/{file_id_patron}/view"
                
                # 🎯 OPTIMIZACIÓN: Insertar vínculos SIN mostrar log repetitivo
                for area in areas:
                    try:
                        rect_expandido = fitz.Rect(
                            area.x0 - 2, area.y0 - 2, 
                            area.x1 + 2, area.y1 + 2
                        )
                        page.insert_link({
                            "kind": fitz.LINK_URI,
                            "from": rect_expandido,
                            "uri": enlace
                        })
                        vinculos_creados += 1
                        vinculos_unicos.add(nombre_patron)  # Solo agregamos al set
                        # ❌ NO imprimimos aquí para evitar repeticiones
                    except Exception as e:
                        app._insertar_log(f"   ❌ Error vinculando '{nombre_patron}': {str(e)}\n", "error")
            
            # 7. Guardar cambios
            doc.save(archivo, garbage=4, deflate=True)
            doc.close()
            
            # 8. 🎯 MOSTRAR SOLO RESUMEN COMPACTO
            if vinculos_creados > 0:
                patrones_texto = ", ".join(sorted(vinculos_unicos))
                app._insertar_log(f"   ✅ {vinculos_creados} vínculos creados: {patrones_texto}\n", "success")
                
                if hasattr(app, 'mostrar_vinculos_unicos'):
                    app.mostrar_vinculos_unicos([(p, "PATRÓN") for p in vinculos_unicos])
                
                return {'ruta_pdf_vinculado': archivo, 'vinculos': vinculos_creados}
            else:
                app._insertar_log(f"   ⚠️ No se crearon vínculos\n", "info")
                return {'ruta_pdf_vinculado': archivo, 'vinculos': 0}
                
        except Exception as e:
            app._insertar_log(f"   ❌ Error en vinculación: {str(e)}\n", "error")
            import traceback
            app._insertar_log(f"   {traceback.format_exc()}\n", "error")
            return None
        finally:
            # Limpiar temporal
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
    
    def procesar_pdf_con_qr_sincrono(self, archivo, app):
        """Versión sincrónica para procesamiento de QR - SIN BLOQUEOS"""
        try:
            nombre = os.path.basename(archivo)
            
            # Analizar firma (SILENCIOSO)
            estado_firma, subfilter, firmante, fecha_firma = self.signature_analyzer.analizar_pdf_firma(archivo)
            esta_firmado = "✅ Firmado" in estado_firma

            # Actualizar tabla de firmas
            app.actualizar_tabla_firmas(
                archivo, estado_firma, subfilter, firmante, fecha_firma,
                self.magnitude_manager.magnitud_seleccionada
            )

            magnitud_actual = self.magnitude_manager.magnitud_seleccionada or "otros"
            
            if esta_firmado:
                # 🔥 Intentar reemplazar PDF firmado (SILENCIOSO)
                resultado_reemplazo = self.magnitude_manager.reemplazar_pdf_por_certificado(archivo, app)
                
                if resultado_reemplazo:
                    return True
                else:
                    # No se encontró coincidencia, subir como nuevo
                    file_id, enlace, modo, magnitud = self.magnitude_manager.subir_pdf(archivo, magnitud_actual)
                    app._insertar_log(f"   ✅ PDF firmado subido\n", "success")
                    return True
            else:
                # Subir PDF primero (SILENCIOSO)
                file_id, enlace, modo, magnitud = self.magnitude_manager.subir_pdf(archivo, magnitud_actual)
                
                # Generar e insertar QR (SILENCIOSO)
                ruta_qr = self.generar_qr(enlace)
                ruta_con_qr, sobrescrito = self.insertar_qr_en_pdf(archivo, ruta_qr)
                
                # Re-subir con QR
                file = self.magnitude_manager.drive.CreateFile({'id': file_id})
                file.SetContentFile(ruta_con_qr)
                file.Upload()

                app._insertar_log(f"   ✅ QR insertado\n", "success")
                return True

        except Exception as e:
            app._insertar_log(f"   ❌ Error: {str(e)}\n", "error")
            return False
        finally:
            # Limpiar temporales
            self.limpiar_temporales_individual()

    # MÉTODOS ORIGINALES OPTIMIZADOS
    def procesar_vinculacion_pdf(self, ruta_pdf: str, log_widget, root, callback, progress, lbl_estado_global):
        """
        🔥 VERSIÓN OPTIMIZADA: Procesa vinculación para tablas complejas con múltiples filas
        ✅ Solo muestra patrones únicos en el log (sin repeticiones)
        """
        def _run():
            nombre = os.path.basename(ruta_pdf)
            magnitud_actual = self.magnitude_manager.magnitud_seleccionada or "otros"
            nombre_magnitud = self.magnitude_manager.MAGNITUDES[magnitud_actual]
            temp_path = None
            
            try:
                log_widget.insert('end', f"\n📋 PROCESANDO PATRONES: {nombre}\n", "proceso")
                
                # Obtener nombres de patrones desde la carpeta (SILENCIOSO)
                patrones_disponibles = self._obtener_nombres_patrones_desde_carpeta()
                
                if not patrones_disponibles:
                    root.after(0, lambda: log_widget.insert('end', f"   ⚠️ No se encontraron patrones\n", "warning"))
                    return
                
                temp_path = os.path.join(os.path.dirname(ruta_pdf), self.temp_pdf)
                shutil.copy2(ruta_pdf, temp_path)
                doc = fitz.open(temp_path)
                
                vinculos_creados = 0
                vinculos_unicos = set()  # 🎯 Set para patrones únicos
                
                # Procesar la segunda página
                if len(doc) < 2:
                    root.after(0, lambda: log_widget.insert('end', f"   ⚠️ El PDF solo tiene {len(doc)} página(s)\n", "warning"))
                    doc.close()
                    return
                
                page = doc[1]  # Segunda página
                
                # Extraer texto (SILENCIOSO)
                texto_completo = page.get_text()
                if not texto_completo.strip():
                    palabras_ocr = self._extraer_texto_con_ocr(page)
                    texto_completo = ' '.join([p[4] for p in palabras_ocr])
                
                # Buscar patrones (SILENCIOSO)
                patrones_encontrados = self._buscar_patron_en_texto(texto_completo, patrones_disponibles)
                
                # 🎯 OPTIMIZACIÓN: Vincular sin logs repetitivos
                for nombre_patron in patrones_encontrados:
                    areas = self._buscar_coordenadas_patron_en_pagina(page, nombre_patron)
                    
                    if not areas:
                        continue
                    
                    # Obtener file_id del patrón desde el diccionario
                    file_id_patron = patrones_disponibles[nombre_patron]
                    
                    # Generar enlace directo de Drive
                    enlace = f"https://drive.google.com/file/d/{file_id_patron}/view"
                    
                    for area in areas:
                        try:
                            rect_expandido = fitz.Rect(
                                area.x0 - 2, area.y0 - 2, 
                                area.x1 + 2, area.y1 + 2
                            )
                            page.insert_link({
                                "kind": fitz.LINK_URI,
                                "from": rect_expandido,
                                "uri": enlace
                            })
                            vinculos_creados += 1
                            vinculos_unicos.add(nombre_patron)  # Solo agregamos al set
                            # ❌ NO imprimimos aquí para evitar repeticiones
                        except Exception as e:
                            pass

                # Guardar cambios
                doc.save(ruta_pdf, garbage=4, deflate=True)
                doc.close()
                
                # Limpiar temporales
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                
                # Registrar en log JSON
                self._registrar_vinculacion(nombre, vinculos_creados, magnitud_actual)
                
                # 🎯 MOSTRAR SOLO RESUMEN COMPACTO
                patrones_texto = ", ".join(sorted(vinculos_unicos))
                root.after(0, lambda txt=patrones_texto, n=vinculos_creados: 
                    log_widget.insert('end', f"   ✅ {n} vínculos: {txt}\n", "success"))
                
                root.after(0, lambda: log_widget.insert('end', f"\n✅ COMPLETADO: {nombre}\n", "success"))
                lbl_estado_global.config(text=f"Vinculación completada: {vinculos_creados} vínculos", fg="#27ae60")
                
            except Exception as e:
                error_msg = str(e)
                root.after(0, lambda e=error_msg: 
                    log_widget.insert('end', f"\n❌ ERROR: {e}\n", "error"))
                with open(self.log_error_file, "a", encoding="utf-8") as ferr:
                    ferr.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | VINCULACIÓN | {nombre} | {error_msg}\n")
                lbl_estado_global.config(text=f"Error en vinculación: {nombre}", fg="#c0392b")
            
            finally:
                if progress:
                    progress.step()
                root.after(100, callback)

        threading.Thread(target=_run).start()

    def _registrar_vinculacion(self, nombre_archivo, vinculos_creados, magnitud):
        """Registra la vinculación en el archivo JSON"""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    registros = json.load(f)
            else:
                registros = []
            
            registro = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'archivo': nombre_archivo,
                'vinculos': vinculos_creados,
                'magnitud': magnitud
            }
            
            registros.append(registro)
            
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(registros, f, indent=2, ensure_ascii=False)
                
        except Exception:
            pass

    def procesar_pdf_con_qr(self, ruta_pdf: str, log_widget, root, callback, progress, lbl_estado_global, app_instance):
        """Procesa PDF completo"""
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
                    # 🔥 Intentar reemplazar PDF firmado (SILENCIOSO)
                    resultado_reemplazo = self.magnitude_manager.reemplazar_pdf_por_certificado_thread(
                        ruta_pdf, log_widget, root
                    )
                    
                    if not resultado_reemplazo:
                        # No se encontró coincidencia, subir como nuevo
                        file_id, enlace, modo, magnitud = self.magnitude_manager.subir_pdf(ruta_pdf, magnitud_actual)
                        log_widget.insert('end', f"   ✅ PDF firmado subido\n", "success")
                    
                else:
                    # Subir PDF y generar QR (SILENCIOSO)
                    file_id, enlace, modo, magnitud = self.magnitude_manager.subir_pdf(ruta_pdf, magnitud_actual)
                    ruta_qr = self.generar_qr(enlace)
                    ruta_con_qr, sobrescrito = self.insertar_qr_en_pdf(ruta_pdf, ruta_qr)
                    
                    if not sobrescrito:
                        ruta_para_subir_temporal = ruta_con_qr 

                    file = self.magnitude_manager.drive.CreateFile({'id': file_id})
                    file.SetContentFile(ruta_con_qr)
                    file.Upload()

                    log_widget.insert('end', f"   ✅ QR insertado\n", "success")

            except Exception as e:
                error_msg = str(e)
                log_widget.insert('end', f"   ❌ Error: {error_msg}\n", "error")
                with open(self.log_error_file, "a", encoding="utf-8") as ferr:
                    ferr.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | QR | {nombre} | {error_msg}\n")

            finally:
                self.limpiar_temporales_individual(ruta_para_subir_temporal)
                if progress:
                    progress.step()
                root.after(100, callback)
                lbl_estado_global.config(text=f"Completado: {nombre}", fg="#1a5276")

        threading.Thread(target=_run).start()

    def generar_qr(self, enlace, salida="qr_temp.png"):
        """Genera código QR"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=8,
                border=2,
            )
            qr.add_data(enlace)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(salida)
            return salida
        except Exception as e:
            raise RuntimeError(f"Error generando QR: {str(e)}")

    def buscar_palabra_coordenadas(self, ruta_pdf, palabra="QR"):
        """Busca coordenadas de una palabra en el PDF"""
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
        """Inserta imagen QR en el PDF - CORREGIDO"""
        doc = None
        try:
            doc = fitz.open(ruta_pdf)
            pagina = doc[0]

            # Buscar la palabra "QR" en el PDF
            rect_palabra = self.buscar_palabra_coordenadas(ruta_pdf, "QR")

            if rect_palabra:
                # Si encuentra "QR", insertar el código QR en esa posición
                x_centro = (rect_palabra.x0 + rect_palabra.x1) / 2
                y_centro = (rect_palabra.y0 + rect_palabra.y1) / 2
                # 🔥 MODIFICACIÓN: Usar self.qr_size (60 puntos = 2.1 cm)
                rect = fitz.Rect(
                    x_centro - self.qr_size / 2, 
                    y_centro - self.qr_size / 2, 
                    x_centro + self.qr_size / 2, 
                    y_centro + self.qr_size / 2
                )
            else:
                # Si no encuentra "QR", colocar en esquina inferior derecha
                # 🔥 MODIFICACIÓN: Usar self.qr_size (60 puntos = 2.1 cm)
                rect = fitz.Rect(
                    pagina.rect.width - self.qr_size - 30, 
                    pagina.rect.height - self.qr_size - 30, 
                    pagina.rect.width - 30, 
                    pagina.rect.height - 30
                )

            # Insertar la imagen QR
            pagina.insert_image(rect, filename=ruta_qr)
            
            # Guardar el PDF
            doc.save(ruta_pdf, garbage=4, deflate=True, clean=True)
            return ruta_pdf, True

        except Exception as e:
            try:
                if doc is not None:
                    # Si falla, guardar en archivo temporal
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
        """Limpia archivos temporales individuales"""
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
        """Limpia todos los archivos temporales del directorio"""
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