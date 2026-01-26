# Firmador PDF (Streamlit + PyMuPDF)
# - Permite subir 1 o varios PDFs
# - Permite subir imagen de firma (PNG/JPG con fondo transparente ideal)
# - Inserta firma EXACTAMENTE encima del nombre "PEDRO ALEJANDRO NIÑO ROA" (o el que configures)
# - Descarga el PDF firmado o un ZIP si son varios
#
# Requisitos:
#   pip install streamlit pymupdf pillow numpy
#
# Ejecutar:
#   streamlit run app.py

import io
import zipfile
from datetime import datetime
from pathlib import Path
import base64

import streamlit as st
from PIL import Image
import numpy as np
import fitz  # PyMuPDF

# ---------------------- Conversión mm -> puntos PDF ----------------------
MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
PT_PER_MM = PT_PER_INCH / MM_PER_INCH

# ==== Archivos del footer (opcional) ====
# Si quieres logos en el pie, ponlos en una carpeta "images" al lado de app.py
IMAGES_DIR = Path(__file__).parent / "images"
LOGO_LEFT = IMAGES_DIR / "logo_colombia.png"
LOGO_RIGHT = IMAGES_DIR / "logo_sic.png"


# ============================ Utilidades ============================
def _img_to_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def pil_to_png_bytes(img: Image.Image) -> bytes:
    """Convierte PIL a PNG bytes (mantiene alpha si existe)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def ensure_rgba(img: Image.Image) -> Image.Image:
    """Asegura canal alfa."""
    if img.mode != "RGBA":
        return img.convert("RGBA")
    return img


def resize_keep_aspect(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Redimensiona manteniendo aspecto y encaja dentro de target_w x target_h."""
    img = ensure_rgba(img)
    w, h = img.size
    if w == 0 or h == 0:
        return img
    scale = min(target_w / w, target_h / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return img.resize((new_w, new_h), Image.LANCZOS)


def add_footer_logos(page: fitz.Page, margin_mm=8, logo_h_mm=8):
    """Inserta logos (si existen) en el pie de la página."""
    if not (LOGO_LEFT.exists() or LOGO_RIGHT.exists()):
        return

    margin = margin_mm * PT_PER_MM
    logo_h = logo_h_mm * PT_PER_MM

    rect = page.rect
    y1 = rect.y1 - margin
    y0 = y1 - logo_h

    if LOGO_LEFT.exists():
        img_bytes = LOGO_LEFT.read_bytes()
        # Ancho proporcional basado en la imagen real:
        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        if h > 0:
            logo_w = logo_h * (w / h)
        else:
            logo_w = logo_h * 2
        x0 = margin
        x1 = x0 + logo_w
        page.insert_image(fitz.Rect(x0, y0, x1, y1), stream=img_bytes, keep_proportion=True, overlay=True)

    if LOGO_RIGHT.exists():
        img_bytes = LOGO_RIGHT.read_bytes()
        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        if h > 0:
            logo_w = logo_h * (w / h)
        else:
            logo_w = logo_h * 2
        x1 = rect.x1 - margin
        x0 = x1 - logo_w
        page.insert_image(fitz.Rect(x0, y0, x1, y1), stream=img_bytes, keep_proportion=True, overlay=True)


def colocar_firma_sobre_nombre(
    doc: fitz.Document,
    firma_img_bytes: bytes,
    nombre_objetivo: str = "PEDRO ALEJANDRO NIÑO ROA",
    ancho_firma_mm: float = 45,
    alto_firma_mm: float = 18,
    desplazamiento_y_mm: float = 6,
    solo_primera_coincidencia: bool = False,
):
    """
    Busca el texto 'nombre_objetivo' en cada página y coloca la firma encima.
    - ancho_firma_mm / alto_firma_mm: tamaño de la firma en mm
    - desplazamiento_y_mm: cuánto sube adicionalmente (separa firma del texto)
    - solo_primera_coincidencia: si True, firma solo el primer match encontrado en todo el doc
    """
    ancho_firma_pt = ancho_firma_mm * PT_PER_MM
    alto_firma_pt = alto_firma_mm * PT_PER_MM
    desplazamiento_y_pt = desplazamiento_y_mm * PT_PER_MM

    firmado = False

    for page in doc:
        matches = page.search_for(nombre_objetivo)
        if not matches:
            continue

        # Normalmente es 1 match por página, pero si hay varios, firmamos todos
        for rect_nombre in matches:
            # Centrar firma sobre el texto
            x0 = rect_nombre.x0 + (rect_nombre.width - ancho_firma_pt) / 2
            y0 = rect_nombre.y0 - alto_firma_pt - desplazamiento_y_pt
            x1 = x0 + ancho_firma_pt
            y1 = y0 + alto_firma_pt

            rect_firma = fitz.Rect(x0, y0, x1, y1)

            # Inserta imagen
            page.insert_image(
                rect_firma,
                stream=firma_img_bytes,
                keep_proportion=True,
                overlay=True
            )
            firmado = True

            if solo_primera_coincidencia:
                return firmado

    return firmado


def firmar_pdf(
    pdf_bytes: bytes,
    firma_img_bytes: bytes,
    nombre_objetivo: str,
    ancho_firma_mm: float,
    alto_firma_mm: float,
    desplazamiento_y_mm: float,
    firmar_solo_una_vez: bool,
    agregar_logos_footer: bool,
):
    """Devuelve bytes del PDF firmado."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # (opcional) Logos en el footer
    if agregar_logos_footer:
        for p in doc:
            add_footer_logos(p)

    # Firma sobre el nombre
    ok = colocar_firma_sobre_nombre(
        doc=doc,
        firma_img_bytes=firma_img_bytes,
        nombre_objetivo=nombre_objetivo,
        ancho_firma_mm=ancho_firma_mm,
        alto_firma_mm=alto_firma_mm,
        desplazamiento_y_mm=desplazamiento_y_mm,
        solo_primera_coincidencia=firmar_solo_una_vez
    )

    # Si no encontró el nombre, igual devolvemos el PDF sin cambios, pero avisamos arriba
    out = doc.tobytes(deflate=True)
    doc.close()
    return out, ok


# ============================ UI Streamlit ============================
st.set_page_config(page_title="Firmador Juris PDF (Doble)", layout="centered")

st.title("✍️ Firmador PDF (Doble)")
st.caption("Sube uno o varios PDFs y una imagen de firma. La firma se ubicará encima del nombre indicado.")

with st.expander("⚙️ Configuración", expanded=True):
    nombre_objetivo = st.text_input("Texto exacto del nombre a buscar", value="PEDRO ALEJANDRO NIÑO ROA")

    col1, col2, col3 = st.columns(3)
    with col1:
        ancho_firma_mm = st.number_input("Ancho firma (mm)", min_value=10.0, max_value=120.0, value=45.0, step=1.0)
    with col2:
        alto_firma_mm = st.number_input("Alto firma (mm)", min_value=5.0, max_value=80.0, value=18.0, step=1.0)
    with col3:
        desplazamiento_y_mm = st.number_input("Subir firma sobre el texto (mm)", min_value=0.0, max_value=30.0, value=6.0, step=0.5)

    firmar_solo_una_vez = st.checkbox("Firmar solo la primera coincidencia (en todo el PDF)", value=False)
    agregar_logos_footer = st.checkbox("Agregar logos en el footer (si existen en /images)", value=False)

st.divider()

pdf_files = st.file_uploader("📄 Sube PDF(s)", type=["pdf"], accept_multiple_files=True)
firma_file = st.file_uploader("🖊️ Sube imagen de firma (PNG/JPG)", type=["png", "jpg", "jpeg"], accept_multiple_files=False)

# Vista previa firma
firma_img_bytes = None
if firma_file:
    try:
        img = Image.open(firma_file)
        img = ensure_rgba(img)
        st.write("Vista previa de la firma:")
        st.image(img, use_container_width=True)
        firma_img_bytes = pil_to_png_bytes(img)  # Convertimos a PNG para mejor alpha
    except Exception as e:
        st.error(f"No pude leer la imagen de firma: {e}")
        firma_img_bytes = None

st.divider()

if st.button("✅ Firmar", type="primary", disabled=(not pdf_files or not firma_img_bytes)):
    if not pdf_files:
        st.warning("Sube al menos un PDF.")
        st.stop()
    if not firma_img_bytes:
        st.warning("Sube una imagen de firma válida.")
        st.stop()

    resultados = []
    warnings_no_encontro = []

    for up in pdf_files:
        pdf_bytes = up.read()
        try:
            firmado_bytes, ok = firmar_pdf(
                pdf_bytes=pdf_bytes,
                firma_img_bytes=firma_img_bytes,
                nombre_objetivo=nombre_objetivo,
                ancho_firma_mm=ancho_firma_mm,
                alto_firma_mm=alto_firma_mm,
                desplazamiento_y_mm=desplazamiento_y_mm,
                firmar_solo_una_vez=firmar_solo_una_vez,
                agregar_logos_footer=agregar_logos_footer,
            )
            resultados.append((up.name, firmado_bytes, ok))
            if not ok:
                warnings_no_encontro.append(up.name)
        except Exception as e:
            st.error(f"Error firmando {up.name}: {e}")

    if warnings_no_encontro:
        st.warning(
            "En estos archivos NO encontré el texto exacto del nombre, así que no se insertó la firma: "
            + ", ".join(warnings_no_encontro)
            + "\n\nRevisa si el nombre tiene tildes/espacios diferentes o si el PDF es una imagen escaneada."
        )

    # Si solo es 1 PDF, descarga directo
    if len(resultados) == 1:
        nombre, data, ok = resultados[0]
        out_name = f"FIRMADO_{nombre}"
        st.success("Listo. Descarga tu PDF firmado:")
        st.download_button(
            "⬇️ Descargar PDF firmado",
            data=data,
            file_name=out_name,
            mime="application/pdf"
        )
    else:
        # Varios: zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for nombre, data, ok in resultados:
                out_name = f"FIRMADO_{nombre}"
                zf.writestr(out_name, data)

        zip_bytes = zip_buf.getvalue()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.success("Listo. Descarga el ZIP con todos los PDFs firmados:")
        st.download_button(
            "⬇️ Descargar ZIP",
            data=zip_bytes,
            file_name=f"PDFs_Firmados_{stamp}.zip",
            mime="application/zip"
        )

st.caption("Tip: Si el nombre no se encuentra, verifica que el PDF no sea escaneado como imagen; en ese caso toca OCR.")