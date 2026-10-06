"""Esquema único de parámetros de entrada (valores por defecto, unidades y etiqueta [BASE]/[SUPUESTO]).

De aquí salen la plantilla entrada.xlsx y los controles del dashboard HTML.
Un "caso" es un dict plano {ruta: valor}, p.ej. {"cpd.q_kw": 150.0, ...}.
"""
from __future__ import annotations

BASE, SUP = "BASE", "SUPUESTO"  # BASE = dato de diseño; SUPUESTO = provisional, a confirmar

# (bloque, ruta, etiqueta, valor, unidad, etiqueta_origen, nota)
PARAMS = [
    # ------------------------------------------------------------ fuente
    ("CPD (fuente de calor)", "cpd.q_kw", "Calor recuperable a plena carga", 150.0, "kW", BASE, ""),
    ("CPD (fuente de calor)", "cpd.t_sal", "T salida del CPD (ida a BdC 1)", 60.0, "°C", BASE, "circuito 50/60"),
    ("CPD (fuente de calor)", "cpd.t_ret", "T retorno al CPD (salida evaporador BdC 1)", 50.0, "°C", BASE, ""),
    ("CPD (fuente de calor)", "cpd.horas", "Horas de funcionamiento al año", 8760.0, "h", BASE, ""),
    ("CPD (fuente de calor)", "cpd.dry_cooler_kwe_kw", "Ventiladores dry cooler CPD ahorrados", 0.025, "kWe/kW", SUP,
     "electricidad que deja de gastar el dry cooler por kW recuperado"),
    # ------------------------------------------------------------ agua caliente
    ("Agua caliente (BdC 1 → generador)", "cal.t_ida", "T ida al generador", 90.0, "°C", BASE, ""),
    ("Agua caliente (BdC 1 → generador)", "cal.t_ret", "T retorno del generador", 85.0, "°C", SUP, "nominal típico de catálogo 88/83"),
    # ------------------------------------------------------------ frío
    ("Agua enfriada (demanda)", "frio.demanda_kw", "Demanda de frío", 150.0, "kW", BASE, "continua"),
    ("Agua enfriada (demanda)", "frio.t_imp", "T impulsión agua enfriada", 7.0, "°C", BASE, ""),
    ("Agua enfriada (demanda)", "frio.t_ret", "T retorno agua enfriada", 12.0, "°C", SUP, ""),
    # ------------------------------------------------------------ rechazo
    ("Rechazo (torre + adiabático)", "rech.t_ent", "T agua de refrigeración a máquinas", 30.0, "°C", BASE, "retorno de torre"),
    ("Rechazo (torre + adiabático)", "rech.t_sal", "T agua de refrigeración de vuelta a torre", 35.0, "°C", BASE, ""),
    ("Rechazo (torre + adiabático)", "rech.torre_kw", "Capacidad de la torre existente", 200.0, "kW", BASE, ""),
    ("Rechazo (torre + adiabático)", "rech.torre_kwe_kw", "Ventiladores torre", 0.010, "kWe/kW", SUP, ""),
    ("Rechazo (torre + adiabático)", "rech.adiab_kwe_kw", "Ventiladores adiabático", 0.025, "kWe/kW", SUP, ""),
    ("Rechazo (torre + adiabático)", "rech.ciclos", "Ciclos de concentración torre", 4.0, "-", SUP, ""),
    ("Rechazo (torre + adiabático)", "rech.adiab_l_kwh", "Agua del adiabático", 0.30, "L/kWh", SUP, ""),
    # ------------------------------------------------------------ bombeo
    ("Bombeo (circuitos nuevos)", "bomb.h_cpd", "Altura bomba circuito CPD", 10.0, "m", SUP, ""),
    ("Bombeo (circuitos nuevos)", "bomb.h_cal", "Altura bomba agua caliente", 10.0, "m", SUP, ""),
    ("Bombeo (circuitos nuevos)", "bomb.h_rech", "Altura bomba agua de refrigeración", 15.0, "m", SUP, ""),
    ("Bombeo (circuitos nuevos)", "bomb.rend", "Rendimiento de las bombas", 0.60, "-", SUP, ""),
    # ------------------------------------------------------------ modelos
    ("Modelo BdC", "bdc.ap_evap", "Pinch evaporador", 3.0, "K", SUP, "T evaporación = T fuente salida - pinch"),
    ("Modelo BdC", "bdc.ap_cond", "Pinch condensador", 3.0, "K", SUP, "T condensación = T caliente salida + pinch"),
    ("Modelo BdC", "bdc.k_cap", "Variación de capacidad por K de salto (si la curva no la da)", -0.005, "1/K", SUP, ""),
    ("Modelo BdC", "bdc.pen_carga", "Penalización de COP a carga parcial", 0.0, "-", SUP,
     "COP = COP_nom·(1 - pen·(1 - carga)); 0 = COP constante"),
    ("Modelo absorción", "abs.ap_gen", "Pinch generador", 5.0, "K", SUP, ""),
    ("Modelo absorción", "abs.ap_evap", "Pinch evaporador", 3.0, "K", SUP, ""),
    ("Modelo absorción", "abs.ap_abs", "Pinch absorbedor/condensador", 3.0, "K", SUP, ""),
    ("Modelo absorción", "abs.aux_kwe_kw", "Auxiliares (bomba de solución, control)", 0.010, "kWe/kW frío", SUP, ""),
    ("Modelo absorción", "abs.k_gen", "Capacidad: ganancia por K de T generador", 0.025, "1/K", SUP, ""),
    ("Modelo absorción", "abs.k_frio", "Capacidad: ganancia por K de T agua enfriada", 0.030, "1/K", SUP, ""),
    ("Modelo absorción", "abs.k_refrig", "Capacidad: pérdida por K de T agua refrigeración", 0.030, "1/K", SUP, ""),
    ("Modelo absorción", "abs.pen_carga", "Penalización de COP a carga parcial", 0.0, "-", SUP, ""),
    # ------------------------------------------------------------ enfriadora existente
    ("Enfriadora existente", "enf.eer_ref", "EER de la enfriadora existente", 4.5, "-", SUP, "a la T de referencia"),
    ("Enfriadora existente", "enf.t_ref", "T agua enfriada de referencia del EER", 7.0, "°C", SUP, ""),
    ("Enfriadora existente", "enf.t_cond", "T condensación equivalente", 38.0, "°C", SUP, "rechazo 35 + 3 K"),
    # ------------------------------------------------------------ recuperación
    ("Recuperación (solo modo con recuperación)", "rec.r1_kw", "R1: demanda precalentamiento red", 60.0, "kW", BASE, "15→30 °C"),
    ("Recuperación (solo modo con recuperación)", "rec.r2_kw", "R2: demanda de calor a alta T", 240.0, "kW", BASE, ""),
    ("Recuperación (solo modo con recuperación)", "rec.r2_t_sal", "R2: T de entrega", 90.0, "°C", BASE, ""),
    ("Recuperación (solo modo con recuperación)", "rec.cobertura", "Fracción de horas con consumo de calor", 1.0, "-", SUP,
     "1 = siempre hay consumo (cota superior)"),
    ("Recuperación (solo modo con recuperación)", "rec.precio_calor", "Coste del calor desplazado (combustible)", 0.05, "€/kWh", SUP, ""),
    ("Recuperación (solo modo con recuperación)", "rec.rend_caldera", "Rendimiento de la caldera desplazada", 0.90, "-", SUP, ""),
    # ------------------------------------------------------------ economía
    ("Economía", "eco.elec", "Precio medio electricidad", 0.12, "€/kWh", SUP, ""),
    ("Economía", "eco.agua", "Precio agua + vertido", 2.0, "€/m3", SUP, ""),
    ("Economía", "eco.mant", "Mantenimiento anual", 0.03, "frac. CAPEX", SUP, ""),
    ("Economía", "eco.tasa", "Tasa de descuento", 0.06, "-", SUP, ""),
    ("Economía", "eco.vida", "Vida útil", 15.0, "años", SUP, ""),
    ("Economía", "eco.bop", "BoP (obra, tuberías, control) sobre equipos", 0.25, "frac.", SUP, ""),
    ("Economía", "eco.capex_abs", "CAPEX absorción", 600.0, "€/kW frío nominal", SUP, ""),
    ("Economía", "eco.capex_bdc", "CAPEX BdC 1", 450.0, "€/kW calor nominal", SUP, ""),
    ("Economía", "eco.capex_adiab", "CAPEX adiabático", 300.0, "€/kW real", SUP, ""),
    ("Economía", "eco.capex_r1", "CAPEX R1 (intercambiador)", 100.0, "€/kW", SUP, ""),
    ("Economía", "eco.capex_r2", "CAPEX BdC R2", 700.0, "€/kW calor nominal", SUP, ""),
]

# equipos: (ruta, etiqueta, tipo de catálogo, valor por defecto)
EQUIPOS = [
    ("eq.bdc1", "Bomba de calor 1 (CPD → generador)", "bdc", "Ejemplo BdC alta T 200 kW"),
    ("eq.abs", "Máquina de absorción", "absorcion", "Ejemplo absorción 150 kW"),
    ("eq.r2", "Bomba de calor R2 (rechazo → 90 °C)", "bdc", "Ejemplo BdC CO2 250 kW"),
]
# nº de unidades: 0 = automático (lo dimensiona el programa)
UNIDADES = [("n.bdc1", "Nº unidades BdC 1", 0), ("n.abs", "Nº unidades absorción", 0), ("n.r2", "Nº unidades BdC R2", 0)]

# perfil anual de carga del CPD: fracción de carga -> fracción de horas
PERFIL = [(0.25, 0.10), (0.50, 0.20), (0.75, 0.30), (1.00, 0.40)]

# barrido por defecto: T generador × T agua enfriada
BARRIDO = [("cal.t_ida", [75, 80, 85, 90, 95]), ("frio.t_imp", [4, 5, 6, 7, 8, 9, 10])]

MODOS = {"sin_recuperacion": "Solo frío (sin recuperación)", "con_recuperacion": "Frío + recuperación R1/R2"}

# parámetros del tornado de sensibilidad
SENSIBILIDAD = ["eco.elec", "eco.capex_abs", "eco.capex_bdc", "eco.capex_adiab", "eco.bop", "eco.tasa", "eco.agua",
                "enf.eer_ref", "frio.demanda_kw", "cpd.q_kw", "rech.torre_kw", "abs.ap_gen", "bdc.ap_cond"]
SENSIBILIDAD_REC = ["rec.cobertura", "rec.precio_calor", "eco.capex_r2", "rec.r2_kw"]


def caso_por_defecto() -> dict:
    c = {p[1]: p[3] for p in PARAMS}
    c.update({e[0]: e[3] for e in EQUIPOS})
    c.update({u[0]: u[2] for u in UNIDADES})
    c["perfil"] = [list(x) for x in PERFIL]
    return c


def etiqueta(ruta: str) -> str:
    for p in PARAMS:
        if p[1] == ruta:
            return p[2]
    return ruta


def unidad(ruta: str) -> str:
    for p in PARAMS:
        if p[1] == ruta:
            return p[4]
    return ""
