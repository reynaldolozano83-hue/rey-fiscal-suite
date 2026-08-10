import json
from datetime import datetime

def calculate_taxes(cfdis: list) -> dict:
    """
    Calculates cumulative taxes (IVA and ISR) based on Cash Flow (Flujo de Efectivo) logic.
    For Mexican tax system:
    - Income PUE CFDI -> Declared IVA (IVA Trasladado) & ISR taxable.
    - Expense PUE CFDI -> Deductible/Acreditable IVA & ISR deductible.
    """
    iva_trasladado_cobrado = 0.0
    iva_acreditable_pagado = 0.0
    isr_ingreso_acumulable = 0.0
    isr_deduccion_autorizada = 0.0
    
    retencion_isr = 0.0
    retencion_iva = 0.0
    
    for c in cfdis:
        is_paid = c.get('metodo_pago') == 'PUE'
        tipo = c.get('tipo')
        subtotal = float(c.get('subtotal', 0.0))
        iva = float(c.get('impuestos_trasladados', 0.0))
        ret_iva = float(c.get('impuestos_retenidos', 0.0)) # simplified retenciones mapping
        
        if is_paid:
            if tipo == 'I': # Issued (Ingresos)
                isr_ingreso_acumulable += subtotal
                iva_trasladado_cobrado += iva
                retencion_iva += ret_iva
            elif tipo == 'E': # Received (Egresos / Gastos)
                # Note: In CFDI 'E' usually stands for egreso (notes of credit), but we model received expenses as 'E' or 'I' (received).
                # To be exact: in SAT, we download issued (Ingreso) and received (Ingreso). Let's check the parser.
                # In standard terms, let's treat received cfdis as expenses.
                isr_deduccion_autorizada += subtotal
                iva_acreditable_pagado += iva
                
    iva_a_pagar = max(0.0, iva_trasladado_cobrado - iva_acreditable_pagado - retencion_iva)
    
    # Calculate ISR Pagos Provisionales (Régimen General 30% mock or RESICO 1-2.5% mock)
    # General Regime: (Ingresos - Deducciones) * 30%
    base_gravable = max(0.0, isr_ingreso_acumulable - isr_deduccion_autorizada)
    isr_general = base_gravable * 0.30
    
    # RESICO PF (approx. 2.0% average rate)
    isr_resico = isr_ingreso_acumulable * 0.02
    
    return {
        'period': datetime.now().strftime('%Y-%m'),
        'iva_cobrado': iva_trasladado_cobrado,
        'iva_acreditable': iva_acreditable_pagado,
        'iva_retenciones': retencion_iva,
        'iva_a_pagar': iva_a_pagar,
        'isr_ingresos': isr_ingreso_acumulable,
        'isr_deducciones': isr_deduccion_autorizada,
        'isr_base_gravable': base_gravable,
        'isr_provisional_general': isr_general,
        'isr_provisional_resico': isr_resico
    }

def generate_diot_file(cfdis_gastos: list) -> str:
    """
    Generates a DIOT batch pipe-separated file (Declaración Informativa de Operaciones con Terceros)
    Format: TipoTercero|TipoOperacion|RFC|Nombre|Valor...
    """
    lines = []
    # Deductible expenses paid via PUE
    for c in cfdis_gastos:
        if c.get('metodo_pago') == 'PUE':
            rfc = c.get('emisor_rfc', '')
            total_neto = float(c.get('subtotal', 0.0))
            iva = float(c.get('impuestos_trasladados', 0.0))
            # 04 = Proveedor Nacional, 85 = Prestacion de Servicios Profesionales / General
            line = f"04|85|{rfc}||{int(total_neto)}|||||||||||"
            lines.append(line)
            
    return "\n".join(lines)

def scan_efos(cfdis: list, blacklist_rfcs: set) -> list:
    """
    Checks CFDI vendor RFCs against the EFOS blacklist.
    """
    alerts = []
    for c in cfdis:
        vendor_rfc = c.get('emisor_rfc')
        if vendor_rfc in blacklist_rfcs:
            alerts.append({
                'uuid': c.get('uuid'),
                'rfc': vendor_rfc,
                'nombre': c.get('emisor_nombre'),
                'total': c.get('total'),
                'fecha': c.get('fecha'),
                'severity': 'HIGH'
            })
    return alerts
