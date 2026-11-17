import math
import os
import re
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO
from urllib.parse import quote

from flask import Flask, render_template, request, send_file
import requests
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

app = Flask(__name__)
BACKEND_URL = os.getenv(
    'BACKEND_API_URL',
    os.getenv('BACKEND_URL', 'http://backend:8000')
).rstrip('/')


def _required_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"El campo {field_name} no es válido")
    return escape(value.strip()).replace('\n', '<br/>')


def _format_money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Un valor monetario no es válido") from None
    if not amount.is_finite():
        raise ValueError("Un valor monetario no es válido")

    whole, _, cents = format(amount, ',.2f').rpartition('.')
    return f"{whole.replace(',', '.')},{cents} €"


def _invoice_pdf(factura):
    if not isinstance(factura, dict):
        raise ValueError("La respuesta del API no es válida")

    empresa = factura.get('empresa')
    cliente = factura.get('cliente')
    detalle = factura.get('detalle')
    if not isinstance(empresa, dict) or not isinstance(cliente, dict):
        raise ValueError("La respuesta del API no contiene empresa y cliente válidos")
    if not isinstance(detalle, list) or not detalle:
        raise ValueError("La respuesta del API no contiene detalles válidos")

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    normal_style = styles['BodyText']
    elements = [
        Paragraph(
            f"Factura {_required_text(factura.get('numero_factura'), 'numero_factura')}",
            title_style
        ),
        Paragraph(
            f"Fecha de emisión: {_required_text(factura.get('fecha_emision'), 'fecha_emision')}",
            normal_style
        ),
        Spacer(1, 8 * mm)
    ]

    company = [
        Paragraph("<b>Empresa</b>", normal_style),
        Paragraph(_required_text(empresa.get('nombre'), 'empresa.nombre'), normal_style),
        Paragraph(_required_text(empresa.get('direccion'), 'empresa.direccion'), normal_style),
        Paragraph(_required_text(empresa.get('telefono'), 'empresa.telefono'), normal_style),
        Paragraph(_required_text(empresa.get('email'), 'empresa.email'), normal_style)
    ]
    customer = [
        Paragraph("<b>Cliente</b>", normal_style),
        Paragraph(_required_text(cliente.get('nombre'), 'cliente.nombre'), normal_style),
        Paragraph(_required_text(cliente.get('direccion'), 'cliente.direccion'), normal_style),
        Paragraph(_required_text(cliente.get('telefono'), 'cliente.telefono'), normal_style)
    ]
    parties = Table([[company, customer]], colWidths=[87 * mm, 87 * mm])
    parties.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8)
    ]))
    elements.extend([parties, Spacer(1, 8 * mm)])

    rows = [[
        "Cantidad", "Descripción", "Precio unitario", "Total"
    ]]
    for item in detalle:
        if not isinstance(item, dict):
            raise ValueError("Un detalle de la factura no es válido")
        try:
            quantity = item['cantidad']
            if isinstance(quantity, bool) or not math.isfinite(float(quantity)):
                raise ValueError
            description = _required_text(item.get('descripcion'), 'detalle.descripcion')
            unit_price = _format_money(item.get('precio_unitario'))
            line_total = _format_money(item.get('total'))
        except (KeyError, OverflowError, TypeError, ValueError):
            raise ValueError("Un detalle de la factura no es válido") from None
        rows.append([
            str(quantity),
            Paragraph(description, normal_style),
            unit_price,
            line_total
        ])

    items_table = Table(
        rows,
        colWidths=[22 * mm, 78 * mm, 37 * mm, 37 * mm],
        repeatRows=1
    )
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#245b4a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6)
    ]))
    elements.extend([items_table, Spacer(1, 6 * mm)])

    totals = Table([
        ["Subtotal", _format_money(factura.get('subtotal'))],
        ["Impuesto", _format_money(factura.get('impuesto'))],
        ["Total", _format_money(factura.get('total'))]
    ], colWidths=[40 * mm, 40 * mm], hAlign='RIGHT')
    totals.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.HexColor('#245b4a')),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5)
    ]))
    elements.append(totals)

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm
    )
    document.build(elements)
    buffer.seek(0)
    return buffer


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generar-pdf', methods=['POST'])
def generar_pdf():
    id_factura = request.form.get('id_factura', '').strip()
    if not id_factura or len(id_factura) > 100:
        return render_template(
            'index.html',
            error="Ingresa un número de factura de hasta 100 caracteres."
        ), 400

    url = f"{BACKEND_URL}/facturas/v1/{quote(id_factura, safe='')}"
    try:
        response = requests.get(url, timeout=(3, 10))
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return render_template(
            'index.html',
            error="El servidor de facturas tardó demasiado en responder. Inténtalo de nuevo."
        ), 504
    except requests.exceptions.ConnectionError:
        return render_template(
            'index.html',
            error="No se pudo conectar con el servidor de facturas."
        ), 503
    except requests.exceptions.HTTPError:
        return render_template(
            'index.html',
            error="El servidor no pudo generar la factura solicitada."
        ), 502
    except requests.exceptions.RequestException:
        return render_template(
            'index.html',
            error="Ocurrió un error al consultar el servidor de facturas."
        ), 502

    try:
        factura = response.json()
        buffer = _invoice_pdf(factura)
    except ValueError:
        return render_template(
            'index.html',
            error="El servidor devolvió datos de factura incompletos o inválidos."
        ), 502

    safe_id = re.sub(r'[^A-Za-z0-9._-]+', '-', id_factura).strip('-') or 'factura'
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=f'factura-{safe_id}.pdf'
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
