import xmltodict
import json
import re

def parse_cfdi_xml(xml_content_str: str) -> dict:
    """
    Parses CFDI 4.0/3.3 XML and returns a structured dictionary with details.
    """
    try:
        # Remove XML declaration or encoding issues
        clean_xml = re.sub(r'<\?xml.*?\?>', '', xml_content_str, flags=re.DOTALL).strip()
        data = xmltodict.parse(clean_xml)
        
        # Check standard root namespaces (Comprobante)
        comprobante_key = None
        for key in data.keys():
            if 'Comprobante' in key:
                comprobante_key = key
                break
                
        if not comprobante_key:
            raise ValueError("No Comprobante root element found in XML")
            
        comp = data[comprobante_key]
        
        # Extract basic info
        fecha = comp.get('@Fecha', '')
        tipo = comp.get('@TipoDeComprobante', 'I')
        subtotal = float(comp.get('@SubTotal', 0.0))
        descuento = float(comp.get('@Descuento', 0.0))
        total = float(comp.get('@Total', 0.0))
        metodo_pago = comp.get('@MetodoPago', '')
        forma_pago = comp.get('@FormaPago', '')
        uso_cfdi = ''
        
        # Emisor / Receptor
        emisor_raw = comp.get('cfdi:Emisor', comp.get('Emisor', {}))
        emisor_rfc = emisor_raw.get('@Rfc', 'RFC_DESCONOCIDO')
        emisor_nombre = emisor_raw.get('@Nombre', 'EMISOR DESCONOCIDO')
        
        receptor_raw = comp.get('cfdi:Receptor', comp.get('Receptor', {}))
        receptor_rfc = receptor_raw.get('@Rfc', 'RFC_DESCONOCIDO')
        receptor_nombre = receptor_raw.get('@Nombre', 'RECEPTOR DESCONOCIDO')
        uso_cfdi = receptor_raw.get('@UsoCFDI', '')
        
        # UUID from TimbreFiscalDigital
        uuid = "MOCK-UUID-" + str(hash(xml_content_str))[:10]
        complemento = comp.get('cfdi:Complemento', comp.get('Complemento', {}))
        if complemento:
            tfd = complemento.get('tfd:TimbreFiscalDigital', {})
            if not tfd and isinstance(complemento, list):
                for c in complemento:
                    if 'tfd:TimbreFiscalDigital' in c:
                        tfd = c['tfd:TimbreFiscalDigital']
                        break
            if tfd:
                uuid = tfd.get('@UUID', uuid)
                
        # Impuestos (Taxes)
        impuestos_raw = comp.get('cfdi:Impuestos', comp.get('Impuestos', {}))
        impuestos_trasladados = 0.0
        impuestos_retenidos = 0.0
        
        if impuestos_raw:
            impuestos_trasladados = float(impuestos_raw.get('@TotalImpuestosTrasladados', 0.0))
            impuestos_retenidos = float(impuestos_raw.get('@TotalImpuestosRetenidos', 0.0))
            
        # Conceptos
        conceptos_list = []
        conceptos_raw = comp.get('cfdi:Conceptos', comp.get('Conceptos', {}))
        if conceptos_raw:
            conceptos = conceptos_raw.get('cfdi:Concepto', conceptos_raw.get('Concepto', []))
            if not isinstance(conceptos, list):
                conceptos = [conceptos]
            for c in conceptos:
                conceptos_list.append({
                    'clave': c.get('@ClaveProdServ', ''),
                    'cantidad': float(c.get('@Cantidad', 1)),
                    'descripcion': c.get('@Descripcion', ''),
                    'valor_unitario': float(c.get('@ValorUnitario', 0.0)),
                    'importe': float(c.get('@Importe', 0.0))
                })

        return {
            'uuid': uuid,
            'emisor_rfc': emisor_rfc,
            'emisor_nombre': emisor_nombre,
            'receptor_rfc': receptor_rfc,
            'receptor_nombre': receptor_nombre,
            'tipo': tipo,
            'fecha': fecha,
            'subtotal': subtotal,
            'descuento': descuento,
            'impuestos_trasladados': impuestos_trasladados,
            'impuestos_retenidos': impuestos_retenidos,
            'total': total,
            'metodo_pago': metodo_pago,
            'forma_pago': forma_pago,
            'uso_cfdi': uso_cfdi,
            'conceptos': conceptos_list
        }
    except Exception as e:
        print(f"Error parsing XML: {e}")
        raise e
