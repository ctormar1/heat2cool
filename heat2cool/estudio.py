"""Barrido de las variables que elijas, sensibilidad ±20 % y puntos de equilibrio."""
from __future__ import annotations

import itertools

from .motor import INF, con, evaluar
from .parametros import SENSIBILIDAD, SENSIBILIDAD_REC, etiqueta

# columnas escalares de evaluar() que van a la tabla del barrido
COLUMNAS = ["calor_revalorizado_mwh", "frac_revalorizado", "erf", "util_mwh", "coste_util", "valor_util", "cop_bdc1", "cop_abs", "cop_r2", "eer_enf", "cal_bdc1", "cal_abs", "cal_r2", "n_bdc1", "n_abs", "n_r2",
            "limitante", "frio_dis_kw", "cobertura_frio", "frio_mwh", "calor_rec_mwh", "elec_sis_mwh", "elec_enf_mwh",
            "elec_base_mwh", "ahorro_elec_mwh", "agua_m3", "agua_base_m3", "eer_sis", "capex_total", "c_elec",
            "c_agua", "c_mant", "capex_anual", "credito_calor", "J", "J_base", "ahorro_neto", "retorno_anos"]


def biseccion(f, lo, hi, it=60):
    """Raíz de f en [lo, hi] por bisección (misma implementación en motor.js). None si no cambia de signo."""
    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo
    if flo * fhi > 0:
        return None
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm < 0) == (flo < 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def equilibrios(c, cat, modo):
    """EER de la enfriadora existente y precio de la electricidad con los que el ahorro neto es 0."""
    def ah(ruta):
        return lambda x: evaluar(con(c, ruta, x), cat, modo)["ahorro_neto"]

    return {"eer_equilibrio": biseccion(ah("enf.eer_ref"), 0.5, 15.0),
            "elec_equilibrio": biseccion(ah("eco.elec"), 0.0, 2.0)}


def barrido(c, cat, modo, variables):
    """variables: [(ruta, [valores]), ...]. Devuelve una fila (dict) por combinación."""
    filas = []
    rutas = [v[0] for v in variables]
    for combo in itertools.product(*[v[1] for v in variables]):
        cc = dict(c)
        for r, x in zip(rutas, combo):
            cc[r] = float(x)
        res = evaluar(cc, cat, modo)
        fila = {r: x for r, x in zip(rutas, combo)}
        fila.update({k: res[k] for k in COLUMNAS})
        fila.update(equilibrios(cc, cat, modo))
        filas.append(fila)
    filas.sort(key=lambda f: (f["coste_util"], -f["calor_revalorizado_mwh"]))  # lo más barato de revalorizar primero
    for i, f in enumerate(filas, 1):
        f["ranking"] = i
    return filas


def sensibilidad(c, cat, modo, delta=0.20):
    rutas = SENSIBILIDAD + (SENSIBILIDAD_REC if modo == "con_recuperacion" else [])
    ref = evaluar(c, cat, modo)["ahorro_neto"]
    filas = []
    for r in rutas:
        v0 = c[r]
        lo = evaluar(con(c, r, v0 * (1 - delta)), cat, modo)["ahorro_neto"]
        hi = evaluar(con(c, r, v0 * (1 + delta)), cat, modo)["ahorro_neto"]
        filas.append({"parametro": etiqueta(r), "ruta": r, "valor": v0, "ahorro_menos": lo, "ahorro_mas": hi,
                      "ahorro_ref": ref, "rango": abs(hi - lo)})
    filas.sort(key=lambda f: -f["rango"])
    return filas


def fmt_retorno(x):
    return "no se recupera" if x == INF else f"{x:.1f} años"


# ================================================================== optimizador
# Situación del cliente = el caso (CPD, demanda del sitio, temperaturas, precios). El optimizador decide:
# BdC 1, absorción, modo (con/sin recuperación), BdC R2 y T del agua al generador. Misma lógica en web/motor.js.
OBJETIVOS = {
    "coste_util": ("Menor coste por MWh útil", False),
    "calor_revalorizado_mwh": ("Más calor del CPD revalorizado", True),
    "erf": ("Mayor ERF del CPD", True),
    "ahorro_neto": ("Mayor ahorro frente a la enfriadora", True),
}
T_GEN_OPT = [75.0, 80.0, 85.0, 90.0, 95.0]
CLAVES_OPT = ["calor_revalorizado_mwh", "frac_revalorizado", "erf", "util_mwh", "frio_mwh", "calor_rec_mwh",
              "coste_util", "valor_util", "capex_total", "ahorro_neto", "cop_bdc1", "cop_abs", "cop_r2",
              "cal_bdc1", "cal_abs", "cal_r2", "n_bdc1", "n_abs", "n_r2", "cobertura_frio", "limitante"]


def modos_opt(c):
    """Modos que prueba el optimizador según opt.recuperacion (0 no, 1 que decida, 2 siempre) y los interruptores R1/R2."""
    from .motor import demanda_r1, demanda_r2
    hay_rec = demanda_r1(c) > 0 or demanda_r2(c) > 0
    op = round(c.get("opt.recuperacion", 1.0))
    if op == 0 or not hay_rec:
        return ("sin_recuperacion",)
    return ("con_recuperacion",) if op == 2 else ("sin_recuperacion", "con_recuperacion")


def soluciones(c, cat, max_nivel=2, genericos=False, modos=None, t_gen=T_GEN_OPT):
    """Evalúa todas las combinaciones viables (equipos con calidad del dato ≤ max_nivel en sus condiciones)."""
    from .motor import abs_en, ajustar_abs, ajustar_bdc, bdc_en, demanda_r2
    modos = modos or modos_opt(c)

    def candidatos(tipo):
        # las máquinas ficticias de ejemplo solo entran si el catálogo no tiene equipos reales de ese tipo
        reales = any(e["tipo"] == tipo and e["origen"] not in ("generico", "ejemplo") for e in cat.values())
        return [n for n, e in cat.items() if e["tipo"] == tipo and (genericos or e["origen"] != "generico")
                and not (reales and e["origen"] == "ejemplo")]

    base = dict(c)
    base.update({"n.bdc1": 0, "n.abs": 0, "n.r2": 0})
    r2s = [n for n in candidatos("bdc")
           if bdc_en(base, ajustar_bdc(base, cat[n]), base["rech.t_ent"], base["rec.r2_t_sal"])["nivel"] <= max_nivel]
    con_r2 = demanda_r2(base) > 0  # sin R2 no hay BdC R2 que elegir
    sols = []
    for t in t_gen:
        ct = dict(base)
        ct["cal.t_ida"] = t
        b1 = [n for n in candidatos("bdc") if bdc_en(ct, ajustar_bdc(ct, cat[n]), ct["cpd.t_ret"], t)["nivel"] <= max_nivel]
        ab = []
        for n in candidatos("absorcion"):
            e = abs_en(ct, ajustar_abs(ct, cat[n]), t, ct["frio.t_imp"], ct["rech.t_ent"])
            if e["nivel"] <= max_nivel and e["cop"] > 0:
                ab.append(n)
        for modo in modos:
            rec = modo == "con_recuperacion"
            for b in b1:
                for a in ab:
                    for r2 in (r2s if rec and con_r2 else [c["eq.r2"]]):
                        cc = dict(ct)
                        cc.update({"eq.bdc1": b, "eq.abs": a, "eq.r2": r2})
                        r = evaluar(cc, cat, modo)
                        if r["util_mwh"] <= 0:
                            continue
                        s = {"modo": modo, "cal.t_ida": t, "eq.bdc1": b, "eq.abs": a, "eq.r2": r2 if rec and con_r2 else ""}
                        s.update({k: r[k] for k in CLAVES_OPT})
                        sols.append(s)
    return sols


def ordenar(sols, objetivo="coste_util"):
    """Mejor primero según el objetivo; desempate: más calor revalorizado y menor coste por MWh."""
    alto = OBJETIVOS[objetivo][1]
    return sorted(sols, key=lambda s: (-s[objetivo] if alto else s[objetivo], -s["calor_revalorizado_mwh"], s["coste_util"]))


def optimizar(c, cat, objetivo="coste_util", n=5, **kw):
    return ordenar(soluciones(c, cat, **kw), objetivo)[:n]
