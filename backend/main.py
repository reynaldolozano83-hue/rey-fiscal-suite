import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from datetime import datetime, timedelta

import database
import parser
import accounting
import tax_engine
import payroll
import invoicing
import ai_agent

app = FastAPI(title="Rey Fiscal & ERP Suite Backend", version="1.0.0")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.on_event("startup")
def startup_event():
    database.init_db()

def verify_premium_plan(org_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plan_type, subscription_status FROM organizations WHERE id = ?", (org_id,))
    org = cursor.fetchone()
    conn.close()
    
    if not org or org['plan_type'] != 'PREMIUM' or org['subscription_status'] != 'Active':
        raise HTTPException(
            status_code=403,
            detail="ACCESO DENEGADO: El modulo Premium (Invoicing/Payroll/Inventory) requiere suscripcion activa de PyME Total ($399/mes)."
        )

@app.get("/api/status")
def get_status(org_id: int = 1):
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM cfdis WHERE organization_id = ?", (org_id,))
    cfdis_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM polizas WHERE organization_id = ?", (org_id,))
    polizas_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM empleados WHERE organization_id = ?", (org_id,))
    empleados_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM efos_blacklist")
    efos_count = c.fetchone()[0]
    
    c.execute("SELECT * FROM organizations WHERE id = ?", (org_id,))
    org = dict(c.fetchone())
    conn.close()
    
    return {
        "status": "healthy",
        "cfdis_count": cfdis_count,
        "polizas_count": polizas_count,
        "empleados_count": empleados_count,
        "efos_count": efos_count,
        "organization": org
    }

# ----------------- MULTI-TENANT LINKING APIs -----------------

class AddOrgRequest(BaseModel):
    rfc: str
    razon_social: str
    ciec: Optional[str] = None

@app.post("/api/v1/organizations/add")
def add_organization(req: AddOrgRequest, user_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    
    try:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Insert Organization
        cursor.execute("""
            INSERT INTO organizations (rfc, razon_social, ciec, plan_type, subscription_status, created_at)
            VALUES (?, ?, ?, 'FREE', 'Inactive', ?)
        """, (req.rfc.upper(), req.razon_social, req.ciec, now_str))
        org_id = cursor.lastrowid
        
        # Link to Master Accountant (user_id = 1)
        cursor.execute("""
            INSERT INTO accountant_organization_links (user_id, organization_id, permission_level, linked_at)
            VALUES (?, ?, 'Full', ?)
        """, (user_id, org_id, now_str))
        
        # Add default chart accounts for the new organization
        accounts = [
            ('101.01', '10101', 'Caja General', 1, 'Activo'),
            ('102.01', '10201', 'Bancos Nacionales', 1, 'Activo'),
            ('105.01', '10501', 'Clientes Nacionales', 1, 'Activo'),
            ('115.01', '11501', 'Almacén / Inventario', 1, 'Activo'),
            ('118.01', '11801', 'IVA Acreditable Pagado', 1, 'Activo'),
            ('119.01', '11901', 'IVA Pendiente de Acreditar', 1, 'Activo'),
            ('201.01', '20101', 'Proveedores Nacionales', 1, 'Pasivo'),
            ('208.01', '20801', 'IVA Trasladado Cobrado', 1, 'Pasivo'),
            ('209.01', '20901', 'IVA Pendiente de Trasladar', 1, 'Pasivo'),
            ('301.01', '30101', 'Capital Social', 1, 'Capital'),
            ('401.01', '40101', 'Ventas Gravadas Tasa 16%', 1, 'Ingresos'),
            ('501.01', '50101', 'Costo de Ventas', 1, 'Costos'),
            ('601.01', '60101', 'Gastos de Administración', 1, 'Gastos'),
            ('602.01', '60201', 'Sueldos y Salarios', 1, 'Gastos')
        ]
        for cod, num, desc, niv, tipo in accounts:
            cursor.execute("""
                INSERT OR IGNORE INTO catalogo_cuentas (organization_id, codigo_agrupador, num_cuenta, desc_cuenta, nivel, tipo_cuenta)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (org_id, cod, num, desc, niv, tipo))
            
        conn.commit()
        conn.close()
        return {"status": "success", "organization_id": org_id, "rfc": req.rfc.upper()}
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error al agregar RFC: {str(e)}")

class LinkAccountantRequest(BaseModel):
    organization_id: int
    accountant_email: str

@app.post("/api/v1/organizations/link-accountant")
def link_accountant(req: LinkAccountantRequest):
    conn = database.get_connection()
    cursor = conn.cursor()
    
    # Find accountant user
    cursor.execute("SELECT id FROM users WHERE email = ? AND role = 'admin'", (req.accountant_email,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Contador no encontrado en el sistema.")
        
    try:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT OR IGNORE INTO accountant_organization_links (user_id, organization_id, permission_level, linked_at)
            VALUES (?, ?, 'Full', ?)
        """, (user['id'], req.organization_id, now_str))
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Enlace exitoso."}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error de vinculación: {str(e)}")

@app.get("/api/v1/accountant/dashboard")
def get_accountant_dashboard(user_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    
    # Get all linked organizations for this accountant
    cursor.execute("""
        SELECT o.* FROM organizations o
        JOIN accountant_organization_links l ON o.id = l.organization_id
        WHERE l.user_id = ?
    """, (user_id,))
    orgs = [dict(r) for r in cursor.fetchall()]
    
    dashboard_data = []
    for o in orgs:
        # Calculate counts
        cursor.execute("SELECT COUNT(*) FROM cfdis WHERE organization_id = ?", (o['id'],))
        cfdis_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM polizas WHERE organization_id = ?", (o['id'],))
        polizas_count = cursor.fetchone()[0]
        
        dashboard_data.append({
            "id": o['id'],
            "rfc": o['rfc'],
            "razon_social": o['razon_social'],
            "plan_type": o['plan_type'],
            "subscription_status": o['subscription_status'],
            "cfdis_count": cfdis_count,
            "polizas_count": polizas_count
        })
        
    conn.close()
    return dashboard_data

# ----------------- OLD ENDPOINTS (ADAPTED) -----------------

@app.get("/api/organizations")
def get_organizations(user_id: int = 1):
    # Retrieve only linked organizations for the dropdown switcher
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.* FROM organizations o
        JOIN accountant_organization_links l ON o.id = l.organization_id
        WHERE l.user_id = ?
    """, (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/organizations/{org_id}/subscribe")
def subscribe_org(org_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        UPDATE organizations 
        SET plan_type = 'PREMIUM', subscription_status = 'Active', expires_at = ?
        WHERE id = ?
    """, (expiry_date, org_id))
    conn.commit()
    conn.close()
    return {"status": "success", "plan_type": "PREMIUM", "subscription_status": "Active"}

@app.post("/api/organizations/{org_id}/unsubscribe")
def unsubscribe_org(org_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE organizations 
        SET plan_type = 'FREE', subscription_status = 'Inactive', expires_at = NULL
        WHERE id = ?
    """, (org_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "plan_type": "FREE", "subscription_status": "Inactive"}

# CFDIs Endpoints
@app.get("/api/cfdis")
def get_cfdis(org_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cfdis WHERE organization_id = ? ORDER BY fecha DESC", (org_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/cfdis/upload")
async def upload_cfdi(file: UploadFile = File(...), org_id: int = Form(1)):
    try:
        xml_content = await file.read()
        xml_str = xml_content.decode("utf-8")
        parsed = parser.parse_cfdi_xml(xml_str)
        
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM efos_blacklist WHERE rfc = ?", (parsed['emisor_rfc'],))
        is_efos = cursor.fetchone()[0] > 0
        efos_status = "Alerta (EFOS)" if is_efos else "Limpio"
        
        cursor.execute("""
            INSERT OR REPLACE INTO cfdis (
                organization_id, uuid, emisor_rfc, emisor_nombre, receptor_rfc, receptor_nombre,
                tipo, fecha, subtotal, descuento, impuestos_trasladados, impuestos_retenidos,
                total, metodo_pago, forma_pago, uso_cfdi, xml_content, efos_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            org_id, parsed['uuid'], parsed['emisor_rfc'], parsed['emisor_nombre'],
            parsed['receptor_rfc'], parsed['receptor_nombre'], parsed['tipo'], parsed['fecha'],
            parsed['subtotal'], parsed['descuento'], parsed['impuestos_trasladados'], parsed['impuestos_retenidos'],
            parsed['total'], parsed['metodo_pago'], parsed['forma_pago'], parsed['uso_cfdi'], xml_str, efos_status
        ))
        
        poliza_data = accounting.generate_auto_poliza(parsed)
        cursor.execute("SELECT COUNT(*) FROM polizas WHERE organization_id = ? AND xml_uuid = ?", (org_id, parsed['uuid']))
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO polizas (organization_id, tipo, numero, fecha, concepto, cargos_abonos_json, xml_uuid)
                VALUES (?, ?, (SELECT COALESCE(MAX(numero), 0) + 1 FROM polizas WHERE organization_id = ?), ?, ?, ?, ?)
            """, (
                org_id, poliza_data['tipo'], org_id, poliza_data['fecha'], poliza_data['concepto'],
                json.dumps(poliza_data['cargos_abonos']), parsed['uuid']
            ))
            
        conn.commit()
        conn.close()
        await manager.broadcast({"event": "cfdi_uploaded", "uuid": parsed['uuid'], "total": parsed['total']})
        return {"status": "success", "uuid": parsed['uuid'], "efos_status": efos_status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al subir CFDI: {str(e)}")

# Pólizas
@app.get("/api/polizas")
def get_polizas(org_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM polizas WHERE organization_id = ? ORDER BY fecha DESC", (org_id,))
    rows = []
    for r in cursor.fetchall():
        row_dict = dict(r)
        row_dict['cargos_abonos'] = json.loads(row_dict['cargos_abonos_json'])
        rows.append(row_dict)
    conn.close()
    return rows

# Chart of Accounts
@app.get("/api/accounts")
def get_accounts(org_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM catalogo_cuentas WHERE organization_id = ? ORDER BY num_cuenta ASC", (org_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# Tax Determinations
@app.get("/api/taxes")
def get_taxes(org_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cfdis WHERE organization_id = ?", (org_id,))
    cfdis = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return tax_engine.calculate_taxes(cfdis)

# Employees List
@app.get("/api/employees")
def get_employees(org_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM empleados WHERE organization_id = ?", (org_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

class PayrollCalcRequest(BaseModel):
    empleado_id: int
    fecha_baja: Optional[str] = None
    tipo_baja: str = "renuncia"
    dias_trabajados: int = 15


class EmployeeCreateRequest(BaseModel):
    nombre: str
    rfc: str
    salario_diario: float

@app.post("/api/employees")
def add_employee(req: EmployeeCreateRequest, org_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    # Insert with mock CURP/NSS/date for test ease
    cursor.execute("""
        INSERT INTO empleados (organization_id, nombre, rfc, curp, nss, fecha_ingreso, salario_diario)
        VALUES (?, ?, ?, 'MOCKCURP1234567', '12345678901', '2026-01-01', ?)
    """, (org_id, req.nombre, req.rfc, req.salario_diario))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/payroll/calculate")
def calculate_payroll(req: PayrollCalcRequest, org_id: int = 1):
    verify_premium_plan(org_id)
    
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM empleados WHERE id = ? AND organization_id = ?", (req.empleado_id, org_id))
    emp = cursor.fetchone()
    if not emp:
        conn.close()
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    emp = dict(emp)
    
    if req.fecha_baja:
        desglose = payroll.calculate_finiquito_liquidacion(
            fecha_ingreso_str=emp['fecha_ingreso'],
            fecha_baja_str=req.fecha_baja,
            salario_diario=emp['salario_diario'],
            tipo_baja=req.tipo_baja,
            dias_aguinaldo=emp['dias_aguinaldo'],
            pct_prima_vacacional=emp['pct_prima_vacacional']
        )
        total_neto = desglose['total_neto']
        tipo_calc = 'Finiquito' if req.tipo_baja == 'renuncia' else 'Liquidacion'
    else:
        calc = payroll.calculate_payroll_receipt(
            salario_diario=emp['salario_diario'],
            dias_trabajados=req.dias_trabajados,
            pct_fondo=emp['pct_fondo_ahorro']
        )
        desglose = calc
        total_neto = calc['neto_pagar']
        tipo_calc = 'Nomina'
        
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        INSERT INTO historial_calculos (organization_id, empleado_id, tipo_calculo, fecha_registro, total_neto, desglose_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (org_id, req.empleado_id, tipo_calc, now_str, total_neto, json.dumps(desglose)))
    
    conn.commit()
    conn.close()
    return {
        "empleado": emp['nombre'],
        "tipo_calculo": tipo_calc,
        "fecha": now_str,
        "total_neto": total_neto,
        "desglose": desglose
    }

# EFOS List
@app.get("/api/efos")
def get_efos():
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM efos_blacklist ORDER BY rfc ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    reply = ai_agent.query_rey_ai(req.message)
    return {"reply": reply}

@app.websocket("/ws/sync")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"event": "pong", "payload": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Mount frontend static files

# Auth Models
class SignupRequest(BaseModel):
    username: str
    password: str
    email: str
    rfc: str
    razon_social: str

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/v1/auth/signup")
def signup(req: SignupRequest):
    conn = database.get_connection()
    cursor = conn.cursor()
    
    try:
        # Create default organization for user
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO organizations (rfc, razon_social, plan_type, subscription_status, created_at)
            VALUES (?, ?, 'FREE', 'Inactive', ?)
        """, (req.rfc.upper(), req.razon_social, now_str))
        org_id = cursor.lastrowid
        
        # Create user linked to organization with 30-day Free Trial
        trial_expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO users (username, password_hash, email, role, plan_type, subscription_status, trial_expires_at)
            VALUES (?, ?, ?, 'admin', 'FREE_TRIAL', 'Active', ?)
        """, (req.username, req.password, req.email, trial_expiry))
        user_id = cursor.lastrowid
        
        # Link accountant user to organization
        cursor.execute("""
            INSERT INTO accountant_organization_links (user_id, organization_id, permission_level, linked_at)
            VALUES (?, ?, 'Full', ?)
        """, (user_id, org_id, now_str))
        
        # Initial chart of accounts
        accounts = [
            ('101.01', '10101', 'Caja General', 1, 'Activo'),
            ('102.01', '10201', 'Bancos Nacionales', 1, 'Activo'),
            ('105.01', '10501', 'Clientes Nacionales', 1, 'Activo'),
            ('115.01', '11501', 'Almacén / Inventario', 1, 'Activo'),
            ('118.01', '11801', 'IVA Acreditable Pagado', 1, 'Activo'),
            ('119.01', '11901', 'IVA Pendiente de Acreditar', 1, 'Activo'),
            ('201.01', '20101', 'Proveedores Nacionales', 1, 'Pasivo'),
            ('208.01', '20801', 'IVA Trasladado Cobrado', 1, 'Pasivo'),
            ('209.01', '20901', 'IVA Pendiente de Trasladar', 1, 'Pasivo'),
            ('301.01', '30101', 'Capital Social', 1, 'Capital'),
            ('401.01', '40101', 'Ventas Gravadas Tasa 16%', 1, 'Ingresos'),
            ('501.01', '50101', 'Costo de Ventas', 1, 'Costos'),
            ('601.01', '60101', 'Gastos de Administración', 1, 'Gastos'),
            ('602.01', '60201', 'Sueldos y Salarios', 1, 'Gastos')
        ]
        for cod, num, desc, niv, tipo in accounts:
            cursor.execute("""
                INSERT OR IGNORE INTO catalogo_cuentas (organization_id, codigo_agrupador, num_cuenta, desc_cuenta, nivel, tipo_cuenta)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (org_id, cod, num, desc, niv, tipo))
            
        conn.commit()
        conn.close()
        return {"status": "success", "user_id": user_id, "organization_id": org_id, "username": req.username}
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Error al registrar usuario: {str(e)}")

@app.post("/api/v1/auth/login")
def login(req: LoginRequest):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", (req.username, req.password))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
        
    # Get linked organizations
    cursor.execute("""
        SELECT o.* FROM organizations o
        JOIN accountant_organization_links l ON o.id = l.organization_id
        WHERE l.user_id = ?
    """, (user['id'],))
    orgs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    return {
        "status": "success",
        "user": {
            "id": user['id'],
            "username": user['username'],
            "email": user['email'],
            "role": user['role'],
            "plan_type": user['plan_type'],
            "subscription_status": user['subscription_status'],
            "trial_expires_at": user['trial_expires_at']
        },
        "organizations": orgs
    }

# Pricing Information
PRICING_PLANS = {
    "STARTER": {"price": 499, "desc": "Nómina hasta 10 empleados + Facturación"},
    "CRECIMIENTO": {"price": 799, "desc": "Nómina hasta 35 empleados + Inventarios"},
    "ESCALA": {"price": 1299, "desc": "Nómina hasta 100 empleados + CxC/CxP"}
}

@app.get("/api/v1/subscription/pricing")
def get_pricing():
    return PRICING_PLANS

class UpgradePlanRequest(BaseModel):
    plan_tier: str # STARTER, CRECIMIENTO, ESCALA

@app.post("/api/organizations/{org_id}/upgrade")
def upgrade_organization_plan(org_id: int, req: UpgradePlanRequest):
    tier = req.plan_tier.upper()
    if tier not in PRICING_PLANS:
        raise HTTPException(status_code=400, detail="Plan seleccionado invalido")
        
    conn = database.get_connection()
    cursor = conn.cursor()
    expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        UPDATE organizations 
        SET plan_type = ?, subscription_status = 'Active', expires_at = ?
        WHERE id = ?
    """, (tier, expiry_date, org_id))
    
    conn.commit()
    conn.close()
    return {"status": "success", "plan_type": tier, "subscription_status": "Active"}

@app.get("/api/v1/users/{user_id}/status")
def get_user_status(user_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, role, plan_type, subscription_status, trial_expires_at, expires_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return dict(user)

@app.post("/api/v1/users/{user_id}/upgrade")
def upgrade_user(user_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        UPDATE users 
        SET plan_type = 'PAID', subscription_status = 'Active', trial_expires_at = NULL, expires_at = ?
        WHERE id = ?
    """, (expiry_date, user_id))
    conn.commit()
    conn.close()
    return {"status": "success", "plan_type": "PAID", "subscription_status": "Active"}
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8020)
