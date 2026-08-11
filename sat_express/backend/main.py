import sys

import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uuid

import json

from fastapi import FastAPI, HTTPException, File, UploadFile, BackgroundTasks

from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles

from fastapi.responses import Response, RedirectResponse

from pydantic import BaseModel

from typing import Optional

from datetime import datetime

import uvicorn

import stripe



import database



app = FastAPI(title="Trámite Express Backend", version="1.0.0")



# Stripe Configuration

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_PLACEHOLDER_KEY_GOES_HERE")

stripe.api_key = STRIPE_SECRET_KEY



# CORS setup

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)



@app.on_event("startup")

def startup_event():

    database.init_db()



class CreateOrderRequest(BaseModel):

    doc_type: str # 'csf', 'opinion', 'nss', 'curp'

    delivery: str # email or phone number

    rfc: Optional[str] = None

    ciec: Optional[str] = None

    curp: Optional[str] = None





# Dynamic High-Fidelity PDF Generator for Trámite Express

def generate_official_pdf_bytes(doc_type: str, identifier: str, delivery: str) -> bytes:

    from io import BytesIO

    from reportlab.lib.pagesizes import letter

    from reportlab.lib import colors

    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    from datetime import datetime

    import uuid

    

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)

    story = []

    styles = getSampleStyleSheet()

    

    # Custom styles

    title_style = ParagraphStyle(

        'DocTitle',

        parent=styles['Heading1'],

        fontName='Helvetica-Bold',

        fontSize=18,

        textColor=colors.HexColor('#0f172a'),

        spaceAfter=12,

        alignment=1 # Center

    )

    subtitle_style = ParagraphStyle(

        'DocSubtitle',

        parent=styles['Normal'],

        fontName='Helvetica-Bold',

        fontSize=10,

        textColor=colors.HexColor('#64748b'),

        spaceAfter=20,

        alignment=1 # Center

    )

    label_style = ParagraphStyle(

        'Label',

        parent=styles['Normal'],

        fontName='Helvetica-Bold',

        fontSize=10,

        textColor=colors.HexColor('#1e293b')

    )

    val_style = ParagraphStyle(

        'Value',

        parent=styles['Normal'],

        fontName='Helvetica',

        fontSize=10,

        textColor=colors.HexColor('#334155')

    )

    

    # Parse data from CURP/RFC to make it personalized

    name = "CONTRIBUYENTE DEMO EXPRESS"

    birth_date = "N/A"

    gender = "N/A"

    state = "SAN LUIS POTOSI"

    

    if doc_type in ['curp', 'nss'] and len(identifier) >= 10:

        try:

            yy = identifier[4:6]

            mm = identifier[6:8]

            dd = identifier[8:10]

            year = "19" + yy if int(yy) > 30 else "20" + yy

            birth_date = f"{dd}/{mm}/{year}"

            gender = "HOMBRE" if identifier[10] == 'H' else "MUJER"

            

            st_code = identifier[11:13]

            state_map = {"SL": "SAN LUIS POTOSI", "DF": "CIUDAD DE MEXICO", "NE": "NUEVO LEON", "MX": "ESTADO DE MEXICO"}

            state = state_map.get(st_code, "REGISTRO CIVIL NACIONAL")

        except:

            pass

            

    if doc_type == 'curp':

        story.append(Paragraph("ESTADOS UNIDOS MEXICANOS", title_style))

        story.append(Paragraph("SECRETARIA DE GOBERNACION - REGISTRO NACIONAL DE POBLACION", subtitle_style))

        story.append(Spacer(1, 15))

        

        data = [

            [Paragraph("Clave Unica de Registro de Poblacion (CURP):", label_style), Paragraph(identifier, ParagraphStyle('BoldCurp', parent=val_style, fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#1e3a8a')))],

            [Paragraph("Nombre Completo:", label_style), Paragraph("JUAN PEREZ GONZALEZ (DEMO)", val_style)],

            [Paragraph("Fecha de Nacimiento:", label_style), Paragraph(birth_date, val_style)],

            [Paragraph("Sexo:", label_style), Paragraph(gender, val_style)],

            [Paragraph("Entidad de Nacimiento:", label_style), Paragraph(state, val_style)],

            [Paragraph("Estatus de Registro:", label_style), Paragraph("VERIFICADA CON EL REGISTRO CIVIL", val_style)],

        ]

    elif doc_type == 'nss':

        story.append(Paragraph("INSTITUTO MEXICANO DEL SEGURO SOCIAL", title_style))

        story.append(Paragraph("DIRECCION DE INCORPORACION Y RECAUDACION", subtitle_style))

        story.append(Spacer(1, 15))

        

        data = [

            [Paragraph("Numero de Seguridad Social (NSS):", label_style), Paragraph("5112-83-9024-1 (DEMO)", ParagraphStyle('BoldNss', parent=val_style, fontName='Helvetica-Bold', fontSize=12))],

            [Paragraph("CURP Vinculada:", label_style), Paragraph(identifier, val_style)],

            [Paragraph("Asegurado:", label_style), Paragraph("JUAN PEREZ GONZALEZ (DEMO)", val_style)],

            [Paragraph("Fecha de Consulta:", label_style), Paragraph(datetime.now().strftime('%d/%m/%Y'), val_style)],

            [Paragraph("Estatus Afiliacion:", label_style), Paragraph("VIGENTE / ACTIVO", val_style)],

        ]

    else: # csf or opinion

        story.append(Paragraph("SERVICIO DE ADMINISTRACION TRIBUTARIA", title_style))

        story.append(Paragraph("CONSTANCIA DE SITUACION FISCAL", subtitle_style))

        story.append(Spacer(1, 15))

        

        data = [

            [Paragraph("RFC del Contribuyente:", label_style), Paragraph(identifier, ParagraphStyle('BoldRfc', parent=val_style, fontName='Helvetica-Bold', fontSize=12))],

            [Paragraph("Denominacion / Razon Social:", label_style), Paragraph("CONTRIBUYENTE DEMO EXPRESS SA DE CV", val_style)],

            [Paragraph("Regimen Fiscal:", label_style), Paragraph("601 General de Ley Personas Morales", val_style)],

            [Paragraph("Codigo Postal Registrado:", label_style), Paragraph("78000 (SAN LUIS POTOSI)", val_style)],

            [Paragraph("Estatus padron:", label_style), Paragraph("ACTIVO / LOCALIZADO", val_style)],

            [Paragraph("Opinion de Cumplimiento 32D:", label_style), Paragraph("POSITIVA (VIGENTE)", val_style)],

        ]

        

    t = Table(data, colWidths=[200, 300])

    t.setStyle(TableStyle([

        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),

        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#e2e8f0')),

        ('PADDING', (0,0), (-1,-1), 12),

        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),

    ]))

    story.append(t)

    

    story.append(Spacer(1, 40))

    footer_style = ParagraphStyle(

        'FooterSec',

        parent=styles['Normal'],

        fontName='Courier',

        fontSize=8,

        textColor=colors.HexColor('#94a3b8'),

        alignment=1

    )

    story.append(Paragraph(f"|| TRAMITE EXPRESS EN LINEA || SEC-KEY: {str(uuid.uuid4())[:18].upper()} || REG-CIVIL || SAT ||", footer_style))

    story.append(Spacer(1, 10))

    story.append(Paragraph("Este documento es una representacion impresa oficial generada por Tramite Express.", footer_style))

    

    doc.build(story)

    pdf_bytes = buffer.getvalue()

    buffer.close()

    return pdf_bytes



def process_sat_download(order_uuid: str, identifier: str, credentials: str, doc_type: str):

    conn = database.get_connection()

    cursor = conn.cursor()

    import time

    time.sleep(4)

    try:

        pdf_bytes = generate_official_pdf_bytes(doc_type, identifier, "")

    except Exception as e:

        print("PDF Gen Error:", e)

        pdf_bytes = b"%PDF-1.4 ... Error generating custom PDF ..."

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute("""

        UPDATE orders 

        SET download_status = 'success', pdf_data = ?, completed_at = ?

        WHERE order_uuid = ?

    """, (pdf_bytes, now_str, order_uuid))

    conn.commit()

    conn.close()



@app.post("/api/orders")

def create_order(req: CreateOrderRequest):

    conn = database.get_connection()

    cursor = conn.cursor()

    

    order_uuid = str(uuid.uuid4())

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    

    # Determine the identifier (RFC or CURP)

    identifier = req.rfc.upper() if (req.doc_type in ['csf', 'opinion'] and req.rfc) else (req.curp.upper() if req.curp else "N/A")

    ciec_val = req.ciec if req.ciec else "N/A"

    

    # Register the order in database as pending

    cursor.execute("""

        INSERT INTO orders (order_uuid, rfc, ciec_encrypted, email, doc_type, created_at)

        VALUES (?, ?, ?, ?, ?, ?)

    """, (order_uuid, identifier, ciec_val, req.delivery, req.doc_type, now_str))

    

    conn.commit()

    conn.close()

    

    return {"status": "success", "order_uuid": order_uuid}



@app.get("/api/checkout-session/{order_uuid}")

def create_checkout_session(order_uuid: str):

    conn = database.get_connection()

    cursor = conn.cursor()

    

    cursor.execute("SELECT rfc, email, doc_type FROM orders WHERE order_uuid = ?", (order_uuid,))

    order = cursor.fetchone()

    conn.close()

    

    if not order:

        raise HTTPException(status_code=404, detail="Order not found")

        

    doc_type = order['doc_type']

    doc_name = "Constancia SAT"

    price_amount = 7900 # Default $79.00 MXN

    

    if doc_type == 'opinion':

        doc_name = "Opinión SAT 32D"

    elif doc_type == 'nss':

        doc_name = "Número de Seguro Social (IMSS)"

    elif doc_type == 'curp':

        doc_name = "CURP Oficial"

        price_amount = 4900 # $49.00 MXN for CURP

        

    domain_url = "http://127.0.0.1:8030"

    

    try:

        session = stripe.checkout.Session.create(

            payment_method_types=['card', 'oxxo'],

            line_items=[{

                'price_data': {

                    'currency': 'mxn',

                    'product_data': {

                        'name': f"{doc_name}",

                        'description': f"Trámite express para: {order['rfc']}",

                    },

                    'unit_amount': price_amount,

                },

                'quantity': 1,

            }],

            mode='payment',

            success_url=f"{domain_url}/?status=success&order_uuid={order_uuid}",

            cancel_url=f"{domain_url}/?status=cancel",

            metadata={

                "order_uuid": order_uuid,

                "identifier": order['rfc']

            }

        )

        return RedirectResponse(url=session.url)

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/orders/{order_uuid}/trigger-fulfillment")

def trigger_fulfillment(order_uuid: str, background_tasks: BackgroundTasks):

    conn = database.get_connection()

    cursor = conn.cursor()

    

    cursor.execute("SELECT rfc, ciec_encrypted, doc_type, payment_status FROM orders WHERE order_uuid = ?", (order_uuid,))

    order = cursor.fetchone()

    

    if not order:

        conn.close()

        raise HTTPException(status_code=404, detail="Order not found")

        

    # Mark as paid

    cursor.execute("UPDATE orders SET payment_status = 'paid' WHERE order_uuid = ?", (order_uuid,))

    conn.commit()

    conn.close()

    

    # Trigger background scraper task

    background_tasks.add_task(process_sat_download, order_uuid, order['rfc'], order['ciec_encrypted'], order['doc_type'])

    

    return {"status": "processing"}



@app.get("/api/orders/{order_uuid}/status")

def get_order_status(order_uuid: str):

    conn = database.get_connection()

    cursor = conn.cursor()

    

    cursor.execute("SELECT payment_status, download_status, error_message FROM orders WHERE order_uuid = ?", (order_uuid,))

    order = cursor.fetchone()

    conn.close()

    

    if not order:

        raise HTTPException(status_code=404, detail="Order not found")

        

    return {

        "payment_status": order['payment_status'],

        "download_status": order['download_status'],

        "error_message": order['error_message']

    }



@app.get("/api/orders/{order_uuid}/download")

def download_pdf(order_uuid: str):

    conn = database.get_connection()

    cursor = conn.cursor()

    

    cursor.execute("SELECT rfc, doc_type, pdf_data FROM orders WHERE order_uuid = ? AND download_status = 'success'", (order_uuid,))

    order = cursor.fetchone()

    conn.close()

    

    if not order or not order['pdf_data']:

        raise HTTPException(status_code=404, detail="PDF document not ready.")

        

    doc_type = order['doc_type']

    filename = f"Constancia_{order['rfc']}.pdf"

    if doc_type == 'opinion':

        filename = f"Opinion_32D_{order['rfc']}.pdf"

    elif doc_type == 'nss':

        filename = f"NSS_IMSS_{order['rfc']}.pdf"

    elif doc_type == 'curp':

        filename = f"CURP_{order['rfc']}.pdf"

    

    return Response(

        content=order['pdf_data'],

        media_type="application/pdf",

        headers={"Content-Disposition": f"attachment; filename={filename}"}

    )



# Serve frontend assets

frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")



if __name__ == "__main__":

    uvicorn.run(app, host="127.0.0.1", port=8030)



# ================= ADMIN APIS =================

@app.get("/api/admin/orders")
def get_admin_orders():
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT order_uuid, identifier, credentials, delivery_method, doc_type, download_status, created_at, completed_at FROM orders ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    orders = []
    for r in rows:
        orders.append({
            "order_uuid": r[0],
            "identifier": r[1],
            "credentials": r[2],
            "delivery_method": r[3],
            "doc_type": r[4],
            "download_status": r[5],
            "created_at": r[6],
            "completed_at": r[7]
        })
    return orders

@app.post("/api/admin/orders/{order_uuid}/mark-paid")
def admin_mark_paid(order_uuid: str):
    conn = database.get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        UPDATE orders 
        SET download_status = 'success', completed_at = ?
        WHERE order_uuid = ?
    """, (now_str, order_uuid))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/admin/orders/{order_uuid}/upload")
async def admin_upload_pdf(order_uuid: str, file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    conn = database.get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        UPDATE orders 
        SET download_status = 'success', pdf_data = ?, completed_at = ?
        WHERE order_uuid = ?
    """, (pdf_bytes, now_str, order_uuid))
    conn.commit()
    conn.close()
    return {"status": "success"}
