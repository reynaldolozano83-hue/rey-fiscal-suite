import json
import re

# Mock vector DB matching queries to Mexican tax compliance articles
TAX_KNOWLEDGE_BASE = [
    {
        "keywords": ["horas extra", "tiempo extra", "extraordinario", "lft"],
        "answer": "De acuerdo con la LFT (Articulo 68), las primeras 9 horas extras a la semana se pagan al doble (100% de recargo). Las horas que excedan de 9 a la semana se deben pagar al triple (200% de recargo). El patron no puede obligar a laborar mas de 3 horas diarias ni mas de 3 veces a la semana de tiempo extra."
    },
    {
        "keywords": ["anexo 24", "contabilidad electronica", "xml"],
        "answer": "De acuerdo con el Anexo 24 de la RMF, la contabilidad electrónica consta del envío del Catálogo de Cuentas con código agrupador del SAT y la Balanza de Comprobación de forma mensual. Las pólizas se enviarán solo a requerimiento de la autoridad fiscal."
    },
    {
        "keywords": ["cfdi 4.0", "emisor", "receptor", "regimen", "codigo postal"],
        "answer": "En CFDI 4.0 es obligatorio validar el RFC, Nombre/Razón Social (sin régimen societario como SA de CV), Código Postal del domicilio fiscal y el Régimen Fiscal tanto del Emisor como del Receptor. Si estos no coinciden con la Constancia de Situación Fiscal actual, el PAC devolverá error de timbrado."
    },
    {
        "keywords": ["error 401", "timbrado", "401", "pac"],
        "answer": "El Error 401 del SAT/PAC indica problemas de autenticación o que los sellos digitales (CSD) son nuevos o están revocados (LCO - Lista de Contribuyentes Obligados). Recuerda que un CSD nuevo tarda de 24 a 72 horas en propagarse a los servidores del SAT."
    },
    {
        "keywords": ["efos", "blacklist", "69-b", "simuladas"],
        "answer": "Bajo el Artículo 69-B del CFF, si un proveedor aparece como Definitivo en el listado EFOS, las operaciones con él no producen efectos fiscales (deducciones/acreditamientos). El contribuyente tiene 30 días para corregir su situación fiscal o acreditar la materialidad."
    },
    {
        "keywords": ["resico", "tasa", "porcentaje", "pf"],
        "answer": "El Régimen Simplificado de Confianza (RESICO) para Personas Físicas cuenta con tasas progresivas de ISR que van desde el 1.0% (hasta 25k pesos mensuales) hasta el 2.5% (máximo 3.5 millones de pesos anuales), sin derecho a deducciones autorizadas."
    },
    {
        "keywords": ["rep", "complemento de pago", "ppd", "limite"],
        "answer": "El Complemento de Pago (REP 2.0) debe emitirse a más tardar el quinto día natural del mes siguiente a aquel en que se reciba el pago de facturas emitidas con método PPD (Pago en Parcialidades o Diferido)."
    }
]

def query_rey_ai(question: str) -> str:
    question_lower = question.lower()
    for entry in TAX_KNOWLEDGE_BASE:
        for kw in entry["keywords"]:
            if kw in question_lower:
                return entry["answer"]
                
    return (
        "Hola, soy el Asistente Fiscal Inteligente de Enlace Fiscal. "
        "No he localizado un artículo específico para tu consulta en el Anexo 24 / RMF, "
        "pero de acuerdo con las disposiciones generales del SAT, te recomiendo validar tu Constancia de "
        "Situación Fiscal o confirmar si la operación se realizó en PUE (Pago en una sola exhibición) o PPD."
    )
