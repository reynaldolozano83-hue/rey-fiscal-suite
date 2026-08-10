import json
import xml.etree.ElementTree as ET
from datetime import datetime

def generate_auto_poliza(cfdi_data: dict) -> dict:
    """
    Rule-based engine to generate balanced Polizas (Journal Entries) from parsed CFDI.
    """
    total = cfdi_data['total']
    subtotal = cfdi_data['subtotal']
    iva = cfdi_data['impuestos_trasladados']
    uuid = cfdi_data['uuid']
    tipo = cfdi_data['tipo'] # I = Ingreso, E = Egreso (Expense/Credit note)
    
    cargos_abonos = []
    
    # Simple double-entry mapping
    if tipo == 'I': # We issued an invoice -> Client owes us (Cargo 105.01), Income increases (Abono 401.01), IVA (Abono 209.01)
        # Check if Metodo de Pago is PUE (Paid immediately) or PPD (To be paid later)
        is_paid = cfdi_data.get('metodo_pago') == 'PUE'
        
        if is_paid:
            # Cargo to Cash/Bank (102.01)
            cargos_abonos.append({'cuenta': '10201', 'cargo': total, 'abono': 0.0, 'concepto': f'Cobro factura {uuid[:8]}'})
            # Abono to Revenues (401.01)
            cargos_abonos.append({'cuenta': '40101', 'cargo': 0.0, 'abono': subtotal, 'concepto': f'Ingreso por venta {uuid[:8]}'})
            # Abono to IVA Trasladado Cobrado (208.01)
            if iva > 0:
                cargos_abonos.append({'cuenta': '20801', 'cargo': 0.0, 'abono': iva, 'concepto': f'IVA Trasladado Cobrado'})
        else:
            # Cargo to Accounts Receivable / Clientes (105.01)
            cargos_abonos.append({'cuenta': '10501', 'cargo': total, 'abono': 0.0, 'concepto': f'Venta a crédito {uuid[:8]}'})
            # Abono to Revenues (401.01)
            cargos_abonos.append({'cuenta': '40101', 'cargo': 0.0, 'abono': subtotal, 'concepto': f'Ingreso por venta {uuid[:8]}'})
            # Abono to IVA Pendiente de Trasladar (209.01)
            if iva > 0:
                cargos_abonos.append({'cuenta': '20901', 'cargo': 0.0, 'abono': iva, 'concepto': f'IVA Pendiente de Trasladar'})
                
    elif tipo == 'E': # We received an expense / purchase
        is_paid = cfdi_data.get('metodo_pago') == 'PUE'
        
        # Categorize Gastos/Costos based on concept or default
        cuenta_gasto = '60101' # Gastos de Admin
        
        if is_paid:
            # Cargo to Expenses (601.01)
            cargos_abonos.append({'cuenta': cuenta_gasto, 'cargo': subtotal, 'abono': 0.0, 'concepto': f'Gasto {uuid[:8]}'})
            # Cargo to IVA Acreditable Pagado (118.01)
            if iva > 0:
                cargos_abonos.append({'cuenta': '11801', 'cargo': iva, 'abono': 0.0, 'concepto': f'IVA Acreditable Pagado'})
            # Abono to Bank (102.01)
            cargos_abonos.append({'cuenta': '10201', 'cargo': 0.0, 'abono': total, 'concepto': f'Pago de gasto {uuid[:8]}'})
        else:
            # Cargo to Expenses (601.01)
            cargos_abonos.append({'cuenta': cuenta_gasto, 'cargo': subtotal, 'abono': 0.0, 'concepto': f'Provisión Gasto {uuid[:8]}'})
            # Cargo to IVA Pendiente de Acreditar (119.01)
            if iva > 0:
                cargos_abonos.append({'cuenta': '11901', 'cargo': iva, 'abono': 0.0, 'concepto': f'IVA Pendiente de Acreditar'})
            # Abono to Proveedores (201.01)
            cargos_abonos.append({'cuenta': '20101', 'cargo': 0.0, 'abono': total, 'concepto': f'Adeudo a proveedor {uuid[:8]}'})
            
    # Fallback to make sure it exists
    if not cargos_abonos:
        cargos_abonos.append({'cuenta': '10101', 'cargo': total, 'abono': 0.0, 'concepto': 'Cuadre manual'})
        cargos_abonos.append({'cuenta': '30101', 'cargo': 0.0, 'abono': total, 'concepto': 'Cuadre manual'})
        
    return {
        'tipo': 'Diario' if tipo == 'E' else 'Ingreso',
        'fecha': cfdi_data['fecha'][:10] if cfdi_data['fecha'] else datetime.now().strftime('%Y-%m-%d'),
        'concepto': f"Registro automático CFDI {uuid[:8]} - {cfdi_data['emisor_nombre'] if tipo == 'E' else cfdi_data['receptor_nombre']}",
        'cargos_abonos': cargos_abonos,
        'xml_uuid': uuid
    }

def export_catalogo_xml(rfc: str, accounts: list) -> str:
    """
    Exports Chart of Accounts (Anexo 24) in SAT compliant XML format.
    """
    now = datetime.now()
    anio = now.year
    mes = f"{now.month:02d}"
    
    root = ET.Element("catalogocuentas:Catalogo", {
        "xmlns:catalogocuentas": "http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/CatalogoCuentas",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/CatalogoCuentas http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/CatalogoCuentas/CatalogoCuentas_1_3.xsd",
        "Version": "1.3",
        "RFC": rfc,
        "Mes": mes,
        "Anio": str(anio)
    })
    
    for acc in accounts:
        ET.SubElement(root, "catalogocuentas:Ctas", {
            "CodAgru": acc['codigo_agrupador'],
            "NumCta": acc['num_cuenta'],
            "Desc": acc['desc_cuenta'],
            "Nivel": str(acc['nivel']),
            "Natur": "A" if acc['tipo_cuenta'] in ['Pasivo', 'Capital', 'Ingresos'] else "D"
        })
        
    return ET.tostring(root, encoding="utf-8").decode("utf-8")

def export_balanza_xml(rfc: str, balances: list) -> str:
    """
    Exports Balanza de Comprobación (Anexo 24) XML.
    """
    now = datetime.now()
    root = ET.Element("balanzacomprobacion:Balanza", {
        "xmlns:balanzacomprobacion": "http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/BalanzaComprobacion",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/BalanzaComprobacion http://www.sat.gob.mx/esquemas/ContabilidadE/1_3/BalanzaComprobacion/BalanzaComprobacion_1_3.xsd",
        "Version": "1.3",
        "RFC": rfc,
        "Mes": f"{now.month:02d}",
        "Anio": str(now.year),
        "TipoEnvio": "N" # Normal
    })
    
    for b in balances:
        ET.SubElement(root, "balanzacomprobacion:Ctas", {
            "NumCta": b['num_cuenta'],
            "SaldoIni": f"{b['saldo_inicial']:.2f}",
            "Debe": f"{b['debe']:.2f}",
            "Haber": f"{b['haber']:.2f}",
            "SaldoFin": f"{b['saldo_final']:.2f}"
        })
        
    return ET.tostring(root, encoding="utf-8").decode("utf-8")
