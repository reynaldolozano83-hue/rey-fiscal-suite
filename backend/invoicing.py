import json
import xml.etree.ElementTree as ET
from datetime import datetime

def generate_invoice_xml(invoice_data: dict) -> tuple:
    """
    Simulates CFDI 4.0 XML generation, validation, and PAC stamping.
    """
    rfc_emisor = invoice_data.get('emisor_rfc', 'RFX010101AA1')
    rfc_receptor = invoice_data.get('receptor_rfc', 'EKU9003173C9')
    subtotal = float(invoice_data.get('subtotal', 100.0))
    iva = subtotal * 0.16
    total = subtotal + iva
    
    uuid = f"CFDI-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    
    # Structural CFDI 4.0 Mock XML
    root = ET.Element("cfdi:Comprobante", {
        "Version": "4.0",
        "Fecha": datetime.now().isoformat(),
        "SubTotal": f"{subtotal:.2f}",
        "Total": f"{total:.2f}",
        "TipoDeComprobante": "I",
        "MetodoPago": invoice_data.get('metodo_pago', 'PUE'),
        "FormaPago": invoice_data.get('forma_pago', '03'), # Transferencia
        "LugarExpedicion": "01000"
    })
    
    ET.SubElement(root, "cfdi:Emisor", {
        "Rfc": rfc_emisor,
        "Nombre": invoice_data.get('emisor_nombre', 'REY TECH LABS SA DE CV'),
        "RegimenFiscal": "601"
    })
    
    ET.SubElement(root, "cfdi:Receptor", {
        "Rfc": rfc_receptor,
        "Nombre": invoice_data.get('receptor_nombre', 'CLIENTE PRUEBAS'),
        "UsoCFDI": invoice_data.get('uso_cfdi', 'G03')
    })
    
    conceptos = ET.SubElement(root, "cfdi:Conceptos")
    for item in invoice_data.get('items', [{'descripcion': 'Servicios de Consultoría', 'cantidad': 1, 'valor_unitario': subtotal}]):
        ET.SubElement(conceptos, "cfdi:Concepto", {
            "ClaveProdServ": "84111500",
            "Cantidad": f"{item['cantidad']:.2f}",
            "Descripcion": item['descripcion'],
            "ValorUnitario": f"{item['valor_unitario']:.2f}",
            "Importe": f"{(item['cantidad'] * item['valor_unitario']):.2f}"
        })
        
    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    
    return uuid, xml_str

def generate_rep_xml(rep_data: dict) -> tuple:
    """
    Generates Complemento de Pago (REP 2.0) XML.
    """
    uuid = f"REP-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    root = ET.Element("cfdi:Comprobante", {
        "Version": "4.0",
        "TipoDeComprobante": "P",
        "SubTotal": "0",
        "Total": "0"
    })
    # Pagos Complemento
    pagos = ET.SubElement(root, "pago20:Pagos", {"Version": "2.0"})
    pago = ET.SubElement(pagos, "pago20:Pago", {
        "FechaPago": datetime.now().isoformat(),
        "FormaDePagoP": rep_data.get('forma_pago', '03'),
        "MonedaP": "MXN",
        "Monto": f"{rep_data.get('monto', 0.0):.2f}"
    })
    ET.SubElement(pago, "pago20:DoctoRelacionado", {
        "IdDocumento": rep_data.get('factura_uuid', 'MOCK-PREV-UUID'),
        "MonedaDR": "MXN",
        "MetodoDePagoDR": "PPD",
        "NumParcialidad": "1",
        "ImpSaldoAnt": f"{rep_data.get('monto', 0.0):.2f}",
        "ImpPagado": f"{rep_data.get('monto', 0.0):.2f}",
        "ImpSaldoInsoluto": "0.00"
    })
    
    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    return uuid, xml_str

def generate_carta_porte_xml(cp_data: dict) -> tuple:
    """
    Generates Carta Porte 3.0 Complemento XML.
    """
    uuid = f"CP-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    root = ET.Element("cfdi:Comprobante", {
        "Version": "4.0",
        "TipoDeComprobante": "T" # Traslado
    })
    cp = ET.SubElement(root, "cartaporte30:CartaPorte", {
        "Version": "3.0",
        "TranspInternac": "No",
        "TotalDistRec": f"{cp_data.get('distancia_km', 120.0):.2f}"
    })
    # Locations, Merchandises, etc.
    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    return uuid, xml_str
