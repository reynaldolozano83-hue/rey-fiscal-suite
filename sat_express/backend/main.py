import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uuid
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks
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

def process_sat_download(order_uuid: str, identifier: str, credentials: str, doc_type: str):
    conn = database.get_connection()
    cursor = conn.cursor()
    
    # Simulate federal server processing (4 seconds)
    import time
    time.sleep(4)
    
    # Mocking a valid PDF document byte stream
    dummy_pdf = b"%PDF-1.4 ... Real-Time Tramite Express Official Document ..."
    
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        UPDATE orders 
        SET download_status = 'success', pdf_data = ?, completed_at = ?
        WHERE order_uuid = ?
    """, (dummy_pdf, now_str, order_uuid))
    
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
