from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from datetime import datetime
import uuid
import os


def generar_boletin_pdf(alumno, notas):
    # ================= RUTA ABSOLUTA BASE =================
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # ================= RUTA LOGO (STATIC) =================
    logo_path = os.path.join(BASE_DIR, "static", "logo.jpg")

    # ================= CARPETAS PDF =================
    carpeta_base = os.path.join(BASE_DIR, "pdfs")
    carpeta_grado = os.path.join(carpeta_base, alumno.grado)

    os.makedirs(carpeta_grado, exist_ok=True)

    nombre_archivo = f"{alumno.nombre.replace(' ', '_')}_2026.pdf"
    ruta_pdf = os.path.join(carpeta_grado, nombre_archivo)

    # ================= DOCUMENTO =================
    doc = SimpleDocTemplate(
        ruta_pdf,
        pagesize=letter,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm
    )

    styles = getSampleStyleSheet()
    elementos = []

    # ================= LOGO =================
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=4 * cm, height=4 * cm)
        logo.hAlign = "CENTER"
        elementos.append(logo)
        elementos.append(Paragraph("<br/>", styles["Normal"]))

    # ================= ENCABEZADO =================
    elementos.append(Paragraph(
        "<b>LICEO PREUNIVERSITARIO SANTINY</b><br/>"
        "BOLETA OFICIAL DE CALIFICACIONES<br/><br/>",
        styles["Title"]
    ))

    # ================= DATOS DEL ALUMNO =================
    elementos.append(Paragraph(
        f"<b>Alumno:</b> {alumno.nombre}<br/>"
        f"<b>Grado:</b> {alumno.grado}<br/>"
        f"<b>Ciclo Escolar:</b> 2026<br/><br/>",
        styles["Normal"]
    ))

    # ================= ORGANIZAR NOTAS =================
    materias = {}

    for nota in notas:
        if nota.materia not in materias:
            materias[nota.materia] = {1: 0, 2: 0, 3: 0, 4: 0}
        materias[nota.materia][nota.bloque] = nota.puntaje

    # ================= TABLA =================
    data = [["Materia", "Bloque 1", "Bloque 2", "Bloque 3", "Bloque 4", "Promedio Final"]]

    for materia, bloques in materias.items():
        b1 = bloques[1]
        b2 = bloques[2]
        b3 = bloques[3]
        b4 = bloques[4]

        promedio = round((b1 + b2 + b3 + b4) / 4, 2)

        data.append([
            materia,
            b1 if b1 else "",
            b2 if b2 else "",
            b3 if b3 else "",
            b4 if b4 else "",
            promedio
        ])

    tabla = Table(data, colWidths=[5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 3*cm])
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]))

    elementos.append(tabla)

    # ================= FIRMA DIGITAL =================
    codigo = str(uuid.uuid4())[:10].upper()
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    elementos.append(Paragraph(
        "<br/><br/><b>VALIDACIÓN DIGITAL</b><br/>"
        f"Documento generado automáticamente el {fecha}.<br/>"
        f"Código único de verificación: <b>{codigo}</b><br/>"
        "Este documento es oficial y válido sin firma manuscrita.",
        styles["Normal"]
    ))

    doc.build(elementos)

    return ruta_pdf


