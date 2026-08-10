import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unittest
import os
import sqlite3
import json
from datetime import datetime

# Import backend modules
import database
import parser
import accounting
import tax_engine
import payroll
import invoicing
import ai_agent

class TestReyFiscalSuite(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Override DB for tests
        database.DB_NAME = 'test_rey_fiscal.db'
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)

    def test_database_initialization(self):
        """Verify DB tables are created and seed data is present."""
        conn = database.get_connection()
        cursor = conn.cursor()
        
        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r['name'] for r in cursor.fetchall()]
        self.assertIn('organizations', tables)
        self.assertIn('users', tables)
        self.assertIn('cfdis', tables)
        self.assertIn('catalogo_cuentas', tables)
        self.assertIn('polizas', tables)
        self.assertIn('empleados', tables)
        self.assertIn('historial_calculos', tables)
        self.assertIn('efos_blacklist', tables)
        
        # Check seeds
        cursor.execute("SELECT COUNT(*) FROM organizations")
        self.assertGreater(cursor.fetchone()[0], 0)
        cursor.execute("SELECT COUNT(*) FROM efos_blacklist")
        self.assertGreater(cursor.fetchone()[0], 0)
        
        conn.close()

    def test_xml_parser(self):
        """Verify XML parsing extracts correct UUID, totals, and taxes."""
        xml_sample = """<?xml version="1.0" encoding="utf-8"?>
        <cfdi:Comprobante Version="4.0" Fecha="2026-08-09T12:00:00" TipoDeComprobante="I" SubTotal="10000.00" Total="11600.00" MetodoPago="PUE" FormaPago="03">
          <cfdi:Emisor Rfc="EKU9003173C9" Nombre="ESCUELA KEMPER URGATE SA"/>
          <cfdi:Receptor Rfc="RFX010101AA1" Nombre="REY TECH LABS SA DE CV" UsoCFDI="G03"/>
          <cfdi:Conceptos>
            <cfdi:Concepto ClaveProdServ="84111500" Cantidad="1.0" Descripcion="Licencia" ValorUnitario="10000.00" Importe="10000.00"/>
          </cfdi:Conceptos>
          <cfdi:Impuestos TotalImpuestosTrasladados="1600.00"/>
          <cfdi:Complemento>
            <tfd:TimbreFiscalDigital UUID="9F3B66D1-C91A-4FBA-B968-07DF0D79F172"/>
          </cfdi:Complemento>
        </cfdi:Comprobante>"""
        
        parsed = parser.parse_cfdi_xml(xml_sample)
        self.assertEqual(parsed['uuid'], '9F3B66D1-C91A-4FBA-B968-07DF0D79F172')
        self.assertEqual(parsed['emisor_rfc'], 'EKU9003173C9')
        self.assertEqual(parsed['subtotal'], 10000.00)
        self.assertEqual(parsed['total'], 11600.00)
        self.assertEqual(parsed['impuestos_trasladados'], 1600.00)
        self.assertEqual(parsed['metodo_pago'], 'PUE')

    def test_automatic_journal_entries(self):
        """Verify business rules map XML variables to balanced cargo/abono ledger entries."""
        cfdi_data = {
            'total': 116.00,
            'subtotal': 100.00,
            'impuestos_trasladados': 16.00,
            'uuid': 'TEST-UUID-1234',
            'tipo': 'I',
            'metodo_pago': 'PUE',
            'fecha': '2026-08-09T12:00:00',
            'emisor_nombre': 'EMISOR PRUEBA',
            'receptor_nombre': 'RECEPTOR PRUEBA'
        }
        
        poliza = accounting.generate_auto_poliza(cfdi_data)
        self.assertEqual(poliza['tipo'], 'Ingreso')
        
        # Verify double-entry balancing (sum of cargos = sum of abonos)
        sum_cargos = sum(item['cargo'] for item in poliza['cargos_abonos'])
        sum_abonos = sum(item['abono'] for item in poliza['cargos_abonos'])
        self.assertAlmostEqual(sum_cargos, sum_abonos, places=2)
        self.assertAlmostEqual(sum_cargos, 116.00, places=2)

    def test_tax_calculations(self):
        """Verify VAT flow and ISR projections are mathematically correct."""
        cfdis = [
            # Paid Income (PUE) -> taxable
            {'tipo': 'I', 'subtotal': 20000.00, 'impuestos_trasladados': 3200.00, 'total': 23200.00, 'metodo_pago': 'PUE'},
            # Paid Expense (PUE) -> deductible
            {'tipo': 'E', 'subtotal': 10000.00, 'impuestos_trasladados': 1600.00, 'total': 11600.00, 'metodo_pago': 'PUE'},
            # Unpaid Income (PPD) -> should be excluded from cash flow calculations
            {'tipo': 'I', 'subtotal': 50000.00, 'impuestos_trasladados': 8000.00, 'total': 58000.00, 'metodo_pago': 'PPD'}
        ]
        
        taxes = tax_engine.calculate_taxes(cfdis)
        self.assertEqual(taxes['iva_cobrado'], 3200.00)
        self.assertEqual(taxes['iva_acreditable'], 1600.00)
        self.assertEqual(taxes['iva_a_pagar'], 1600.00)
        self.assertEqual(taxes['isr_ingresos'], 20000.00)
        self.assertEqual(taxes['isr_deducciones'], 10000.00)
        self.assertEqual(taxes['isr_base_gravable'], 10000.00)
        self.assertEqual(taxes['isr_provisional_general'], 3000.00) # 30%
        self.assertEqual(taxes['isr_provisional_resico'], 400.00) # 2% of 20000

    def test_payroll_and_finiquito_lft(self):
        """Verify LFT quincenal, finiquitos, and liquidaciones formulas."""
        # 1. Standard Payroll
        pay = payroll.calculate_payroll_receipt(salario_diario=600.00, dias_trabajados=15)
        self.assertEqual(pay['sueldo_bruto'], 9000.00)
        self.assertGreater(pay['isr_retenido'], 0)
        self.assertGreater(pay['imss_obrero'], 0)
        self.assertEqual(pay['neto_pagar'], pay['total_percepciones'] - pay['total_deducciones'])

        # 2. Resignation (Finiquito)
        finiquito = payroll.calculate_finiquito_liquidacion(
            fecha_ingreso_str="2024-01-01",
            fecha_baja_str="2024-12-31",
            salario_diario=500.00,
            tipo_baja="renuncia",
            dias_aguinaldo=15,
            pct_prima_vacacional=25.0
        )
        self.assertAlmostEqual(finiquito['antiguedad_anos'], 1.0, delta=0.05)
        self.assertGreater(finiquito['aguinaldo'], 0)
        self.assertGreater(finiquito['vacaciones'], 0)
        # Resignation has NO indemnizaciones
        self.assertEqual(finiquito['indemnizacion_90'], 0)
        self.assertEqual(finiquito['indemnizacion_20'], 0)

        # 3. Layoff (Liquidación)
        liquidacion = payroll.calculate_finiquito_liquidacion(
            fecha_ingreso_str="2024-01-01",
            fecha_baja_str="2024-12-31",
            salario_diario=500.00,
            tipo_baja="despido_injustificado",
            dias_aguinaldo=15,
            pct_prima_vacacional=25.0
        )
        self.assertEqual(liquidacion['indemnizacion_90'], 45000.00) # 90 days * 500
        self.assertGreater(liquidacion['indemnizacion_20'], 0)
        self.assertGreater(liquidacion['prima_antiguedad'], 0)

    def test_efos_scanning(self):
        """Verify EFOS blacklist scanner warns on simulated billing."""
        cfdis = [
            {'emisor_rfc': 'MSO1205047A1', 'emisor_nombre': 'EFOS CORP', 'total': 1000.00, 'fecha': '2026-08-09', 'uuid': 'U1'},
            {'emisor_rfc': 'OK_RFC_123', 'emisor_nombre': 'CLEAN CORP', 'total': 2000.00, 'fecha': '2026-08-09', 'uuid': 'U2'}
        ]
        blacklist = {'MSO1205047A1'}
        alerts = tax_engine.scan_efos(cfdis, blacklist)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['rfc'], 'MSO1205047A1')
        self.assertEqual(alerts[0]['severity'], 'HIGH')

if __name__ == '__main__':
    unittest.main()
