"""
Módulo de análisis de firmas digitales en PDF
"""

import re
from asn1crypto import cms, x509

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