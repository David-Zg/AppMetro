"""
Módulo de procesamiento de PDFs (vinculación, QR, etc.)
"""

import os
import json
import threading
import shutil
from glob import glob
from datetime import datetime

import fitz
import qrcode

class PDFProcessor:
    """Procesa documentos PDF (vinculación, QR, etc.) - MEJORADA"""
    
    def __init__(self, magnitude_manager, signature_analyzer):
        self.magnitude_manager = magnitude_manager
        self.signature_analyzer = signature_analyzer
        self.qr_size = 40
        self.temp_pdf = "temp_output.pdf"
        self.log_file = "vinculados.json"
        self.log_error_file = "errores_qr_log.txt"
    
    def procesar_vinculacion_pdf(self, ruta_pdf: str, log_widget, root, callback, progress, lbl_estado_global):
        """Procesa vinculación de patrones en PDF"""
        def _run():
            nombre = os.path.basename(ruta_pdf)
            temp_path = os.path.join(os.path.dirname(ruta_pdf), self.temp_pdf)

            cambios_realizados = False
            total_vinculos = 0
            pares = []
            
            try:
                log_widget.insert('end', f"\n🔗 Procesando vinculación: {nombre}\n", "proceso")
                log_widget.see('end')
                
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
                    log_widget.insert('end', f"   ✅ VINCULACIÓN COMPLETA: {nombre} actualizado con {total_vinculos} vínculo(s).\n", "success")
                else:
                    log_widget.insert('end', f"   ℹ️ VINCULACIÓN INCOMPLETA: {nombre}. No se encontraron patrones válidos.\n", "info")

            except Exception as e:
                error_msg = str(e)
                log_widget.insert('end', f"   ❌ ERROR EN VINCULACIÓN: {error_msg}\n", "error")
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
    
    def procesar_pdf_con_qr(self, ruta_pdf: str, log_widget, root, callback, progress, lbl_estado_global, app_instance):
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
                    log_widget.insert('end', f"\n📄 PDF FIRMADO detectado: {nombre}\n", "proceso")
                    log_widget.see('end')

                    file_id, enlace, modo, magnitud = self.magnitude_manager.subir_pdf(ruta_pdf, magnitud_actual)
                    log_widget.insert('end', f"   ✅ REEMPLAZO EN DRIVE: {nombre} ({modo}).\n", "success")
                    log_widget.insert('end', f"   📁 Carpeta: {nombre_magnitud}\n", "magnitud")
                    log_widget.insert('end', f"   🔗 Enlace: {enlace}\n", "enlace")
                    
                else:
                    log_widget.insert('end', f"\n📱 Procesando PDF NO FIRMADO: {nombre}\n", "proceso")
                    log_widget.see('end')

                    file_id, enlace, modo, magnitud = self.magnitude_manager.subir_pdf(ruta_pdf, magnitud_actual)
                    ruta_qr = self.generar_qr(enlace)
                    ruta_con_qr, sobrescrito = self.insertar_qr_en_pdf(ruta_pdf, ruta_qr)
                    
                    if not sobrescrito:
                        ruta_para_subir_temporal = ruta_con_qr 

                    file = self.magnitude_manager.drive.CreateFile({'id': file_id})
                    file.SetContentFile(ruta_con_qr)
                    file.Upload()

                    log_widget.insert('end', f"   ✅ QR INSERTADO Y SUBIDO: {nombre} ({modo}).\n", "success")
                    log_widget.insert('end', f"   📁 Carpeta: {nombre_magnitud}\n", "magnitud")
                    log_widget.insert('end', f"   🔗 Enlace: {enlace}\n", "enlace")

            except Exception as e:
                error_msg = str(e)
                log_widget.insert('end', f"   ❌ Error en proceso: {error_msg}\n", "error")
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