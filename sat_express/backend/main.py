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
from datetime import datetime
import uvicorn
import stripe

import database

app = FastAPI(title="SAT Express Backend", version="1.0.0")

# Stripe Configuration
# Default to a standard Stripe test key (sk_test_51M3vJpJq5fVjW0...) or read from environment variables
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
    rfc: str
    ciec: str
    email: str
    doc_type: str # 'csf' or 'opinion'

def process_sat_download(order_uuid: str, rfc: str, ciec: str, doc_type: str):
    conn = database.get_connection()
    cursor = conn.cursor()
    
    # Simulate SAT scraping (4 seconds)
    import time
    time.sleep(4)
    
    # Mocking a valid PDF document byte stream
    dummy_pdf = b"%PDF-1.4 ... Real-Time SAT Express Document ..."
    
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
    
    # Register the order in database as pending
    cursor.execute("""
        INSERT INTO orders (order_uuid, rfc, ciec_encrypted, email, doc_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (order_uuid, req.rfc.upper(), req.ciec, req.email, req.doc_type, now_str))
    
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
        
    doc_name = "Constancia de Situación Fiscal" if order['doc_type'] == 'csf' else "Opinión de Cumplimiento 32-D"
    
    # Base URL of the application
    # In production, we read the host header or environment variable
    domain_url = "http://127.0.0.1:8030"
    
    try:
        # Create Stripe Checkout Session (charges $49.00 MXN)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'], # Can add 'oxxo' if test keys allow
            line_items=[{
                'price_data': {
                    'currency': 'mxn',
                    'product_data': {
                        'name': f"{doc_name} (SAT)",
                        'description': f"Trámite express para el RFC: {order['rfc']}",
                    },
                    'unit_amount': 7900, # $49.00 MXN in cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{domain_url}/?status=success&order_uuid={order_uuid}",
            cancel_url=f"{domain_url}/?status=cancel",
            customer_email=order['email'],
            metadata={
                "order_uuid": order_uuid,
                "rfc": order['rfc']
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
        
    # Mark as paid (since they returned via success URL)
    cursor.execute("UPDATE orders SET payment_status = 'paid' WHERE order_uuid = ?", (order_uuid,))
    conn.commit()
    conn.close()
    
    # Trigger background SAT scraper download
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
        raise HTTPException(status_code=404, detail="PDF document not ready or order unpaid.")
        
    filename = f"Constancia_{order['rfc']}.pdf" if order['doc_type'] == 'csf' else f"Opinion_32D_{order['rfc']}.pdf"
    
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
