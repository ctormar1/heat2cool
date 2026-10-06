"""Barrido de las variables que elijas, sensibilidad ±20 % y puntos de equilibrio."""
from __future__ import annotations

import itertools

from .motor import INF, con, evaluar
from .parametros import SENSIBILIDAD, SENSIBILIDAD_REC, etiqueta

# columnas escalares de evaluar() que van a la tabla del barrido
COLUMNAS = ["cop_bdc1", "cop_abs", "cop_r2", "eer_enf", "cal_bdc1", "cal_abs", "cal_r2", "n_bdc1", "n_abs", "n_r2",
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
    filas.sort(key=lambda f: -f["ahorro_neto"])
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
