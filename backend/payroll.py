import json



from datetime import datetime, date







def calculate_payroll_receipt(salario_diario: float, dias_trabajados: int, pct_fondo: float = 10.0, horas_dobles: int = 0, horas_triples: int = 0) -> dict:



    """



    Computes standard payroll with Mexican law deductions (ISR, IMSS, Fondo de Ahorro) and LFT overtime.



    """



    sueldo_base = salario_diario * dias_trabajados



    



    # Calculate overtime payouts (Art. 67-68 LFT)



    cuota_hora = salario_diario / 8.0



    pago_dobles = cuota_hora * 2.0 * horas_dobles



    pago_triples = cuota_hora * 3.0 * horas_triples



    total_horas_extra = pago_dobles + pago_triples



    



    sueldo_bruto = sueldo_base + total_horas_extra



    



    # 1. Fondo de Ahorro (usually tax exempt up to limits)



    fondo_ahorro_patron = sueldo_bruto * (pct_fondo / 100.0)



    fondo_ahorro_obrero = sueldo_bruto * (pct_fondo / 100.0)



    



    # 2. Mock IMSS Obrero calculation (roughly 2.5% of gross wage depending on SBC)



    imss_obrero = sueldo_bruto * 0.025



    imss_patronal = sueldo_bruto * 0.115 # Mock employer share



    



    # 3. Mock ISR Retenido (approximate tax bracket mapping)



    # Progressive rate mock:



    if sueldo_bruto < 5000:



        isr_retenido = sueldo_bruto * 0.0192



    elif sueldo_bruto < 15000:



        isr_retenido = 95 + (sueldo_bruto - 5000) * 0.064



    elif sueldo_bruto < 30000:



        isr_retenido = 735 + (sueldo_bruto - 15000) * 0.108



    else:



        isr_retenido = 2355 + (sueldo_bruto - 30000) * 0.20



        



    percepciones = sueldo_bruto



    deducciones = isr_retenido + imss_obrero + fondo_ahorro_obrero



    neto_pagar = percepciones - deducciones



    



    return {



        'sueldo_bruto': sueldo_bruto,



        'fondo_ahorro_patron': fondo_ahorro_patron,



        'fondo_ahorro_obrero': fondo_ahorro_obrero,



        'imss_obrero': imss_obrero,



        'imss_patronal': imss_patronal,



        'isr_retenido': isr_retenido,



        'total_percepciones': percepciones,



        'total_deducciones': deducciones,



        'neto_pagar': neto_pagar



    }







def calculate_finiquito_liquidacion(fecha_ingreso_str: str, fecha_baja_str: str, salario_diario: float, tipo_baja: str = 'renuncia', dias_aguinaldo: int = 15, pct_prima_vacacional: float = 25.0) -> dict:



    """



    LFT (Ley Federal del Trabajo) compliant calculations for resignation (finiquito) or layoff (liquidacion).



    """



    fmt = "%Y-%m-%d"



    f_ingreso = datetime.strptime(fecha_ingreso_str, fmt).date()



    f_baja = datetime.strptime(fecha_baja_str, fmt).date()



    



    dias_totales = (f_baja - f_ingreso).days



    antiguedad_anos = dias_totales / 365.0



    



    # Year progression metrics



    anio_actual = f_baja.year



    f_inicio_ano = date(anio_actual, 1, 1)



    dias_trabajados_ano_actual = (f_baja - max(f_ingreso, f_inicio_ano)).days + 1



    



    # Vacaciones (Article 76 LFT - updated values since 2023 Dignas Vacations)



    # Years to Vacation days mapping



    v_days_map = {1: 12, 2: 14, 3: 16, 4: 18, 5: 20, 6: 22, 11: 24, 16: 26, 21: 28, 26: 30, 31: 32}



    v_days = 12



    for k, v in sorted(v_days_map.items()):



        if antiguedad_anos >= k:



            v_days = v



            



    # Proporcional Aguinaldo



    prop_aguinaldo = (dias_trabajados_ano_actual / 365.0) * dias_aguinaldo * salario_diario



    



    # Proporcional Vacaciones (dias transcurridos desde aniversario)



    # Find last anniversary



    try:



        ultimo_aniversario = date(anio_actual, f_ingreso.month, f_ingreso.day)



        if ultimo_aniversario > f_baja:



            ultimo_aniversario = date(anio_actual - 1, f_ingreso.month, f_ingreso.day)



    except ValueError:



        # handle leap years



        ultimo_aniversario = date(anio_actual, 2, 28)



        



    dias_desde_aniversario = (f_baja - ultimo_aniversario).days + 1



    prop_vacaciones = (dias_desde_aniversario / 365.0) * v_days * salario_diario



    prop_prima_vacacional = prop_vacaciones * (pct_prima_vacacional / 100.0)



    



    finiquito_subtotal = prop_aguinaldo + prop_vacaciones + prop_prima_vacacional



    



    # Indemnización (Layoff only)



    indemnizacion_90 = 0.0



    indemnizacion_20 = 0.0



    prima_antiguedad = 0.0



    



    if tipo_baja == 'despido_injustificado':



        # 3 months salary (90 days)



        indemnizacion_90 = 90 * salario_diario



        # 20 days per year worked



        indemnizacion_20 = 20 * antiguedad_anos * salario_diario



        # Prima de antigüedad (12 days per year worked capped at 2x minimum wage)



        # Cap wage roughly at 497.86 (2x current general minimum wage average)



        salario_tope = min(salario_diario, 497.86)



        prima_antiguedad = 12 * antiguedad_anos * salario_tope



        



    total_neto = finiquito_subtotal + indemnizacion_90 + indemnizacion_20 + prima_antiguedad



    



    return {



        'antiguedad_anos': round(antiguedad_anos, 2),



        'dias_trabajados_ano': dias_trabajados_ano_actual,



        'aguinaldo': round(prop_aguinaldo, 2),



        'vacaciones': round(prop_vacaciones, 2),



        'prima_vacacional': round(prop_prima_vacacional, 2),



        'indemnizacion_90': round(indemnizacion_90, 2),



        'indemnizacion_20': round(indemnizacion_20, 2),



        'prima_antiguedad': round(prima_antiguedad, 2),



        'total_neto': round(total_neto, 2)



    }







def stamp_payroll_bulk(receipts: list) -> list:



    """



    Mock integration for bulk CFDI 4.0 payroll stamping with PAC.



    """



    stamped = []



    for r in receipts:



        stamped.append({



            'empleado_id': r.get('empleado_id'),



            'uuid': f"PAY-UUID-{datetime.now().strftime('%M%S%f')}",



            'status': 'Stamped',



            'neto': r.get('neto_pagar')



        })



    return stamped



