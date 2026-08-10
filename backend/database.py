import sqlite3
import os
import json
from datetime import datetime, timedelta

DB_NAME = 'rey_fiscal.db'

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('PRAGMA foreign_keys = ON')
    
    # 1. Organizations (RFCs)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfc TEXT UNIQUE NOT NULL,
            razon_social TEXT NOT NULL,
            ciec TEXT,
            fiel_cert TEXT,
            fiel_key TEXT,
            plan_type TEXT DEFAULT 'FREE', -- FREE, PREMIUM
            subscription_status TEXT DEFAULT 'Inactive', -- Active, Inactive
            stripe_customer_id TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    
    # 2. Users (RBAC with Accountant Subscription)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT CHECK(role IN ('admin', 'accountant', 'client')) NOT NULL,
            plan_type TEXT DEFAULT 'FREE_TRIAL', -- FREE_TRIAL, PAID
            subscription_status TEXT DEFAULT 'Active', -- Active, Inactive
            trial_expires_at TEXT,
            expires_at TEXT,
            stripe_customer_id TEXT
        )
    ''')
    
    # 3. Accountant-Organization mapping table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accountant_organization_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            organization_id INTEGER NOT NULL,
            permission_level TEXT DEFAULT 'Full', -- ReadOnly, Full
            linked_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
            UNIQUE(user_id, organization_id)
        )
    ''')
    
    # 4. CFDIs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cfdis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            uuid TEXT UNIQUE NOT NULL,
            emisor_rfc TEXT NOT NULL,
            emisor_nombre TEXT NOT NULL,
            receptor_rfc TEXT NOT NULL,
            receptor_nombre TEXT NOT NULL,
            tipo TEXT CHECK(tipo IN ('I', 'E', 'N', 'P', 'T')) NOT NULL,
            fecha TEXT NOT NULL,
            subtotal REAL NOT NULL,
            descuento REAL DEFAULT 0.0,
            impuestos_trasladados REAL DEFAULT 0.0,
            impuestos_retenidos REAL DEFAULT 0.0,
            total REAL NOT NULL,
            metodo_pago TEXT,
            forma_pago TEXT,
            uso_cfdi TEXT,
            xml_content TEXT,
            estado_sat TEXT DEFAULT 'Vigente',
            efos_status TEXT DEFAULT 'Limpio',
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    ''')

    # 5. Catalogo de Cuentas (Anexo 24)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS catalogo_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            codigo_agrupador TEXT NOT NULL,
            num_cuenta TEXT NOT NULL,
            desc_cuenta TEXT NOT NULL,
            nivel INTEGER NOT NULL,
            tipo_cuenta TEXT CHECK(tipo_cuenta IN ('Activo', 'Pasivo', 'Capital', 'Ingresos', 'Costos', 'Gastos')) NOT NULL,
            parent_id INTEGER,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_id) REFERENCES catalogo_cuentas(id) ON DELETE SET NULL,
            UNIQUE(organization_id, num_cuenta)
        )
    ''')

    # 6. Polizas (Journal Entries)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS polizas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            tipo TEXT CHECK(tipo IN ('Diario', 'Ingreso', 'Egreso')) NOT NULL,
            numero INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            concepto TEXT NOT NULL,
            cargos_abonos_json TEXT NOT NULL,
            xml_uuid TEXT,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
            FOREIGN KEY (xml_uuid) REFERENCES cfdis(uuid) ON DELETE SET NULL
        )
    ''')

    # 7. Empleados (Payroll)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            rfc TEXT NOT NULL,
            curp TEXT NOT NULL,
            nss TEXT NOT NULL,
            fecha_ingreso TEXT NOT NULL,
            salario_diario REAL NOT NULL,
            dias_aguinaldo INTEGER DEFAULT 15,
            pct_fondo_ahorro REAL DEFAULT 10.0,
            pct_prima_vacacional REAL DEFAULT 25.0,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    ''')

    # 8. Inventarios (Inventory & Warehousing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            nombre TEXT NOT NULL,
            cantidad REAL DEFAULT 0.0,
            unidad TEXT DEFAULT 'Pza',
            fecha_actualizacion TEXT,
            FOREIGN KEY(organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    ''')

    # 8. Historial Calculos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_calculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            empleado_id INTEGER NOT NULL,
            tipo_calculo TEXT CHECK(tipo_calculo IN ('Nomina', 'Aguinaldo', 'Finiquito', 'Liquidacion')) NOT NULL,
            fecha_registro TEXT NOT NULL,
            total_neto REAL NOT NULL,
            desglose_json TEXT NOT NULL,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
            FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE
        )
    ''')

    # 9. EFOS Blacklist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efos_blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfc TEXT UNIQUE NOT NULL,
            razon_social TEXT NOT NULL,
            situacion TEXT NOT NULL,
            publicacion_sat TEXT
        )
    ''')

    conn.commit()
    seed_initial_data(cursor)
    # Safety migration: Ensure expires_at exists in users table
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN expires_at TEXT")
        conn.commit()
    except Exception:
        # Column already exists, safe to ignore
        pass

    conn.commit()
    conn.close()

def seed_initial_data(cursor):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("SELECT COUNT(*) FROM organizations")
    if cursor.fetchone()[0] == 0:
        # User 1: Master Accountant
        trial_expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO users (username, password_hash, email, role, plan_type, subscription_status, trial_expires_at)
            VALUES ('admin', 'admin123', 'admin@reytech.mx', 'admin', 'FREE_TRIAL', 'Active', ?)
        """, (trial_expiry,))
        user1_id = cursor.lastrowid
        
        # User 2: PyME user
        cursor.execute("INSERT INTO users (username, password_hash, email, role) VALUES ('pyme_owner', 'pass123', 'owner@acme.mx', 'client')")
        
        # Org 1: Free
        cursor.execute("""
            INSERT INTO organizations (rfc, razon_social, plan_type, subscription_status, created_at)
            VALUES ('RFX010101AA1', 'DESPACHO MOCK FREE SA DE CV', 'FREE', 'Inactive', ?)
        """, (now_str,))
        org1_id = cursor.lastrowid
        
        # Org 2: Premium (Paid)
        cursor.execute("""
            INSERT INTO organizations (rfc, razon_social, plan_type, subscription_status, expires_at, created_at)
            VALUES ('EKU9003173C9', 'PYME ACME DE MEXICO SA DE CV', 'PREMIUM', 'Active', ?, ?)
        """, (expiry_date, now_str))
        org2_id = cursor.lastrowid
        
        # Link Accountant (User 1) to BOTH organizations
        cursor.execute("""
            INSERT INTO accountant_organization_links (user_id, organization_id, permission_level, linked_at)
            VALUES (?, ?, 'Full', ?)
        """, (user1_id, org1_id, now_str))
        
        cursor.execute("""
            INSERT INTO accountant_organization_links (user_id, organization_id, permission_level, linked_at)
            VALUES (?, ?, 'Full', ?)
        """, (user1_id, org2_id, now_str))
        
        # EFOS samples
        efos_samples = [
            ('MSO1205047A1', 'MOCK SIMULACIONES OPERATIVAS SA DE CV', 'Definitivo', '2025-01-15'),
            ('FAS1508219B2', 'FACTURAS APOCRIFAS DEL SURESTE', 'Presunto', '2025-03-10'),
            ('MEL991122AA1', 'MOCK EFOS LOGISTICS SA DE CV', 'Definitivo', '2026-02-28')
        ]
        for rfc, name, sit, pub in efos_samples:
            cursor.execute("INSERT OR IGNORE INTO efos_blacklist (rfc, razon_social, situacion, publicacion_sat) VALUES (?, ?, ?, ?)", (rfc, name, sit, pub))
            
        # Accounts
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
            cursor.execute("INSERT OR IGNORE INTO catalogo_cuentas (organization_id, codigo_agrupador, num_cuenta, desc_cuenta, nivel, tipo_cuenta) VALUES (?, ?, ?, ?, ?, ?)", (org1_id, cod, num, desc, niv, tipo))
            cursor.execute("INSERT OR IGNORE INTO catalogo_cuentas (organization_id, codigo_agrupador, num_cuenta, desc_cuenta, nivel, tipo_cuenta) VALUES (?, ?, ?, ?, ?, ?)", (org2_id, cod, num, desc, niv, tipo))
            
        # Sample Employees
        cursor.execute("INSERT INTO empleados (organization_id, nombre, rfc, curp, nss, fecha_ingreso, salario_diario) VALUES (?, 'Juan Perez Lopez (FREE)', 'PELJ800101ABC', 'PELJ800101HMRLPR01', '12345678901', '2020-01-01', 500.0)", (org1_id,))
        cursor.execute("INSERT INTO empleados (organization_id, nombre, rfc, curp, nss, fecha_ingreso, salario_diario) VALUES (?, 'Maria Gomez Ruiz (PAID)', 'GORM900202XYZ', 'GORM900202HMRLPR02', '98765432102', '2022-05-15', 650.0)", (org2_id,))
            
        # Seed Inventarios
        cursor.execute("SELECT COUNT(*) FROM inventarios")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO inventarios (organization_id, nombre, cantidad, unidad, fecha_actualizacion) VALUES (?, 'Arroz', 120.0, 'Kg', '2026-08-10 12:00:00')", (org2_id,))
            cursor.execute("INSERT INTO inventarios (organization_id, nombre, cantidad, unidad, fecha_actualizacion) VALUES (?, 'Frijol', 85.0, 'Kg', '2026-08-10 12:00:00')", (org2_id,))
            cursor.execute("INSERT INTO inventarios (organization_id, nombre, cantidad, unidad, fecha_actualizacion) VALUES (?, 'Leche Entera', 45.0, 'Litros', '2026-08-10 12:00:00')", (org2_id,))
            cursor.execute("INSERT INTO inventarios (organization_id, nombre, cantidad, unidad, fecha_actualizacion) VALUES (?, 'Aceite Vegetal', 20.0, 'Litros', '2026-08-10 12:00:00')", (org2_id,))

if __name__ == '__main__':
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
    init_db()
    print("Database initialised with multi-company mapping.")
