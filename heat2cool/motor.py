"""Motor de cálculo: modelos de equipo ajustados a curvas, balance de un punto, dimensionado y año completo.

Escrito a propósito con funciones puras sobre dicts y floats para que web/motor.js sea una traducción línea a línea
(el test de paridad compara ambos). Si cambias algo aquí, cámbialo también en web/motor.js.

Convenciones: potencias en kW, energías en kWh, temperaturas en °C. Un "caso" es el dict plano de parametros.py.
Catálogo: {equipo: {"tipo": "bdc"|"absorcion", "origen": str, "puntos": [{ts, tk, tg, tc, tr, q, cop}]}}.
"""
from __future__ import annotations

import math

K = 273.15
INF = float("inf")
KW_POR_M3H_K = 1.1611  # kW por (m3/h · K) de agua
G = 9.81

CALIDAD = {0: "genérico (un punto, capacidad libre)", 1: "dentro del rango del fabricante",
           2: "extrapolado (≤10 K fuera)", 3: "fuera de rango (>10 K)"}


def _dist(x, lo, hi):
    return lo - x if x < lo else (x - hi if x > hi else 0.0)


def _nivel(origen, d):
    if origen == "generico":
        return 0
    return 1 if d <= 2.0 else (2 if d <= 10.0 else 3)


def _media(xs):
    return sum(xs) / len(xs)


def _recta(xs, ys):
    """Mínimos cuadrados y = a + b·x. Con un solo x distinto devuelve (media, 0)."""
    mx, my = _media(xs), _media(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx < 1.0:
        return my, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def _ajuste_eta(xs, ys):
    """η(salto) = a + b·u + c·u², u = salto − centro. Parábola si hay ≥4 saltos distintos en ≥20 K
    (curvas medidas: η tiene un máximo); si no, recta (c = 0) o constante."""
    m = _media(xs)
    us = [x - m for x in xs]
    distintos = len({round(x) for x in xs})
    if distintos >= 4 and max(xs) - min(xs) >= 20.0:
        s = [sum(u ** k for u in us) for k in range(5)]
        t = [sum(y * u ** k for u, y in zip(us, ys)) for k in range(3)]
        A = [[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]]
        det = _det3(A)
        if abs(det) > 1e-9:
            sol = []
            for k in range(3):
                Ak = [fila[:] for fila in A]
                for i in range(3):
                    Ak[i][k] = t[i]
                sol.append(_det3(Ak) / det)
            return m, sol[0], sol[1], sol[2]
    a, b = _recta(us, ys)
    return m, a, b, 0.0


def _det3(A):
    return (A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1]) - A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0])
            + A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0]))


# ================================================================== bomba de calor
def _bdc_salto(c, ts, tk):
    return max((tk + c["bdc.ap_cond"]) - (ts - c["bdc.ap_evap"]), 5.0)


def _bdc_carnot(c, ts, tk):
    return (tk + c["bdc.ap_cond"] + K) / _bdc_salto(c, ts, tk)


def ajustar_bdc(c, eq):
    """η de Carnot (lineal en el salto si hay ≥2 saltos distintos) y capacidad ajustados a los puntos del equipo."""
    pts = eq["puntos"]
    saltos = [_bdc_salto(c, p["ts"], p["tk"]) for p in pts]
    etas = [p["cop"] / _bdc_carnot(c, p["ts"], p["tk"]) for p in pts]
    s_c, a, b, cc = _ajuste_eta(saltos, etas)
    pq = [(s, p["q"]) for s, p in zip(saltos, pts) if p.get("q")]
    if pq:
        qa, qb = _recta([x[0] for x in pq], [x[1] for x in pq])
        s_ref = _media([x[0] for x in pq])
        q_ref = qa + qb * s_ref
        k = qb / q_ref if qb != 0.0 else c["bdc.k_cap"]
        k = min(max(k, -0.03), 0.01)
    else:
        s_ref, q_ref, k = _media(saltos), INF, 0.0
    return {"tipo": "bdc", "origen": eq["origen"], "a": a, "b": b, "c": cc, "s_c": s_c,
            "s_min": min(saltos), "s_max": max(saltos),
            "ts_min": min(p["ts"] for p in pts), "ts_max": max(p["ts"] for p in pts),
            "tk_min": min(p["tk"] for p in pts), "tk_max": max(p["tk"] for p in pts),
            "q_ref": q_ref, "s_ref": s_ref, "k": k, "n_puntos": len(pts)}


def bdc_en(c, m, ts, tk):
    """COP, capacidad por unidad (kW calor) y nivel de calidad a T fuente salida ts y T caliente salida tk."""
    s = _bdc_salto(c, ts, tk)
    u = min(max(s, m["s_min"]), m["s_max"]) - m["s_c"]
    eta = max(m["a"] + m["b"] * u + m["c"] * u * u, 0.05)
    cop = max(eta * _bdc_carnot(c, ts, tk), 1.05)
    cap = INF if m["q_ref"] == INF else m["q_ref"] * max(1.0 + m["k"] * (s - m["s_ref"]), 0.1)
    d = max(_dist(ts, m["ts_min"], m["ts_max"]), _dist(tk, m["tk_min"], m["tk_max"]))
    return {"cop": cop, "cap": cap, "q_nom": m["q_ref"], "nivel": _nivel(m["origen"], d), "dist": d}


# ================================================================== absorción
def _abs_ideal(c, tg, tc, tr):
    """COP ideal de tres focos (Gordon-Ng) con pinch en generador, evaporador y absorbedor."""
    t_g = tg - c["abs.ap_gen"] + K
    t_e = tc - c["abs.ap_evap"] + K
    t_a = tr + c["abs.ap_abs"] + K
    if t_g <= t_a + 1.0 or t_a <= t_e:
        return 0.0
    return (1.0 - t_a / t_g) * t_e / (t_a - t_e)


def ajustar_abs(c, eq):
    pts = eq["puntos"]
    etas = [p["cop"] / _abs_ideal(c, p["tg"], p["tc"], p["tr"]) for p in pts]
    pq = [p for p in pts if p.get("q")]
    m = {"tipo": "absorcion", "origen": eq["origen"], "eta": _media(etas), "n_puntos": len(pts),
         "tg_ref": _media([p["tg"] for p in pts]), "tc_ref": _media([p["tc"] for p in pts]),
         "tr_ref": _media([p["tr"] for p in pts]),
         "q_ref": _media([p["q"] for p in pq]) if pq else INF}
    for v in ("tg", "tc", "tr"):
        m[v + "_min"] = min(p[v] for p in pts)
        m[v + "_max"] = max(p[v] for p in pts)
    return m


def abs_factor_cap(c, m, tg, tc, tr):
    """Capacidad relativa a la del punto de referencia del equipo (lineal, con suelo 0)."""
    f = (1.0 + c["abs.k_gen"] * (tg - m["tg_ref"]) + c["abs.k_frio"] * (tc - m["tc_ref"])
         - c["abs.k_refrig"] * (tr - m["tr_ref"]))
    return max(f, 0.0)


def abs_en(c, m, tg, tc, tr):
    ideal = _abs_ideal(c, tg, tc, tr)
    cop = min(m["eta"] * ideal, 0.80)  # simple efecto LiBr: techo físico práctico ~0,8
    f = abs_factor_cap(c, m, tg, tc, tr) if ideal > 0 else 0.0
    cap = INF if m["q_ref"] == INF else m["q_ref"] * f
    d = max(_dist(tg, m["tg_min"], m["tg_max"]), _dist(tc, m["tc_min"], m["tc_max"]),
            _dist(tr, m["tr_min"], m["tr_max"]))
    return {"cop": cop, "cap": cap, "q_nom": m["q_ref"], "f_cap": f, "nivel": _nivel(m["origen"], d), "dist": d}


# ================================================================== enfriadora existente y agua
def _enf_carnot(c, t):
    t_e = t - 3.0 + K
    return t_e / (c["enf.t_cond"] + K - t_e)


def enf_eer(c, t):
    return c["enf.eer_ref"] * _enf_carnot(c, t) / _enf_carnot(c, c["enf.t_ref"])


def agua_torre_l_kwh(c):
    """Reposición de torre húmeda: evaporación (2430 kJ/kg) + purga por ciclos de concentración."""
    ciclos = c["rech.ciclos"]
    return 3600.0 / 2430.0 * ciclos / (ciclos - 1.0)


def caudal_m3h(q_kw, dt):
    return q_kw / (KW_POR_M3H_K * dt) if dt > 0 else 0.0


def p_bomba_kw(c, m3h, h):
    return m3h / 3600.0 * 1000.0 * G * h / c["bomb.rend"] / 1000.0


# ================================================================== modelos de los equipos elegidos
def modelos(c, cat):
    def get(ruta, tipo):
        nombre = c[ruta]
        if nombre not in cat:
            raise KeyError(f"Equipo '{nombre}' ({ruta}) no está en el catálogo")
        eq = cat[nombre]
        if eq["tipo"] != tipo:
            raise ValueError(f"'{nombre}' es de tipo {eq['tipo']}, se esperaba {tipo}")
        return ajustar_bdc(c, eq) if tipo == "bdc" else ajustar_abs(c, eq)

    return {"bdc1": get("eq.bdc1", "bdc"), "abs": get("eq.abs", "absorcion"), "r2": get("eq.r2", "bdc")}


def demanda_r1(c):
    """kW de R1 si está activado (casos antiguos sin el interruptor: activado)."""
    return c["rec.r1_kw"] if c.get("rec.r1_on", 1.0) >= 0.5 else 0.0


def demanda_r2(c):
    return c["rec.r2_kw"] if c.get("rec.r2_on", 1.0) >= 0.5 else 0.0


def _n_auto(fijo, requerido, cap):
    if fijo and fijo > 0:
        return int(fijo)
    if cap == INF or requerido <= 0:
        return 1
    return max(1, math.ceil(requerido / cap - 1e-6))


def dimensionar(c, ms):
    """Condiciones de diseño (plena carga, sin recuperación): COP, capacidades y nº de unidades."""
    hp = bdc_en(c, ms["bdc1"], c["cpd.t_ret"], c["cal.t_ida"])
    ab = abs_en(c, ms["abs"], c["cal.t_ida"], c["frio.t_imp"], c["rech.t_ent"])
    r2 = bdc_en(c, ms["r2"], c["rech.t_ent"], c["rec.r2_t_sal"])
    q_gen0 = c["cpd.q_kw"] * hp["cop"] / (hp["cop"] - 1.0)
    q_frio_req = min(c["frio.demanda_kw"], ab["cop"] * q_gen0)
    q_gen_req = q_frio_req / ab["cop"] if ab["cop"] > 0 else 0.0
    n_hp = _n_auto(c["n.bdc1"], q_gen_req, hp["cap"])
    n_ab = _n_auto(c["n.abs"], q_frio_req, ab["cap"])
    n_r2 = _n_auto(c["n.r2"], demanda_r2(c), r2["cap"]) if demanda_r2(c) > 0 else 0
    return {"hp": hp, "ab": ab, "r2": r2, "n_hp": n_hp, "n_ab": n_ab, "n_r2": n_r2,
            "q_gen_req": q_gen_req, "q_frio_req": q_frio_req}


def _plr(q, n, cap):
    return 1.0 if cap == INF else (q / (n * cap) if cap > 0 else 0.0)


def punto(c, d, carga, rec_on):
    """Balance de un punto de operación (potencias medias en kW)."""
    hp, ab, r2 = d["hp"], d["ab"], d["r2"]
    dem = c["frio.demanda_kw"]
    q_src = c["cpd.q_kw"] * carga
    cop_hp, cop_ab = hp["cop"], ab["cop"]
    cap_hp, cap_ab = d["n_hp"] * hp["cap"], d["n_ab"] * ab["cap"]
    q_gen = q_frio = 0.0
    limitante = "Absorción sin ciclo (T generador demasiado baja)"
    plr_hp = plr_ab = 0.0
    for _ in range(4):  # la penalización a carga parcial cambia el COP: punto fijo
        q_gen0 = q_src * cop_hp / (cop_hp - 1.0)
        q_frio0 = cop_ab * q_gen0
        if q_frio0 <= 0:
            q_gen = q_frio = 0.0
            break
        lims = [("Calor disponible del CPD", 1.0), ("Demanda de frío", dem / q_frio0),
                ("Capacidad de la absorción", cap_ab / q_frio0), ("Capacidad de la BdC 1", cap_hp / q_gen0)]
        limitante, s = lims[0]
        for nombre, v in lims[1:]:
            if v < s - 1e-12:
                limitante, s = nombre, v
        q_gen, q_frio = q_gen0 * s, q_frio0 * s
        plr_hp, plr_ab = _plr(q_gen, d["n_hp"], hp["cap"]), _plr(q_frio, d["n_ab"], ab["cap"])
        cop_hp = max(hp["cop"] * (1.0 - c["bdc.pen_carga"] * (1.0 - plr_hp)), 1.05)
        cop_ab = ab["cop"] * (1.0 - c["abs.pen_carga"] * (1.0 - plr_ab))
    w_hp = q_gen / cop_hp
    q_evap = q_gen - w_hp
    q_rej = q_gen + q_frio

    q_r1 = q_r2 = q_r2_ext = w_r2 = 0.0
    if rec_on:
        q_r1 = min(demanda_r1(c), q_rej)
        q_r2 = min(demanda_r2(c), (q_rej - q_r1) * r2["cop"] / (r2["cop"] - 1.0), d["n_r2"] * r2["cap"])
        w_r2 = q_r2 / r2["cop"]
        q_r2_ext = q_r2 - w_r2
    q_dis = q_rej - q_r1 - q_r2_ext
    q_torre = min(q_dis, c["rech.torre_kw"])
    q_adiab = max(0.0, q_dis - c["rech.torre_kw"])

    f_cpd = caudal_m3h(q_evap, c["cpd.t_sal"] - c["cpd.t_ret"])
    f_cal = caudal_m3h(q_gen, c["cal.t_ida"] - c["cal.t_ret"])
    f_frio = caudal_m3h(q_frio, c["frio.t_ret"] - c["frio.t_imp"])
    f_rech = caudal_m3h(q_rej, c["rech.t_sal"] - c["rech.t_ent"])
    p_bombas = (p_bomba_kw(c, f_cpd, c["bomb.h_cpd"]) + p_bomba_kw(c, f_cal, c["bomb.h_cal"])
                + p_bomba_kw(c, f_rech, c["bomb.h_rech"]))
    p_aux = c["abs.aux_kwe_kw"] * q_frio
    p_vent = c["rech.torre_kwe_kw"] * q_torre + c["rech.adiab_kwe_kw"] * q_adiab
    p_dc = c["cpd.dry_cooler_kwe_kw"] * q_evap
    p_sis = w_hp + w_r2 + p_aux + p_vent + p_bombas - p_dc

    eer = enf_eer(c, c["frio.t_imp"])
    q_res = max(dem - q_frio, 0.0)
    p_enf = q_res / eer
    agua_sis_l_h = agua_torre_l_kwh(c) * q_torre + c["rech.adiab_l_kwh"] * q_adiab
    agua_l_h = agua_sis_l_h + agua_torre_l_kwh(c) * (q_res + p_enf)
    return {"carga": carga, "rec": rec_on, "limitante": limitante, "cop_bdc1": cop_hp, "cop_abs": cop_ab,
            "cop_r2": r2["cop"], "eer_enf": eer, "plr_bdc1": plr_hp, "plr_abs": plr_ab,
            "q_cpd_disp": q_src, "q_evap": q_evap, "w_bdc1": w_hp, "q_gen": q_gen, "q_frio": q_frio, "q_rej": q_rej,
            "q_r1": q_r1, "q_r2": q_r2, "q_r2_ext": q_r2_ext, "w_r2": w_r2, "q_dis": q_dis, "q_torre": q_torre,
            "q_adiab": q_adiab, "q_enf": q_res, "p_enf": p_enf, "p_bombas": p_bombas, "p_aux_abs": p_aux,
            "p_vent": p_vent, "p_dc_ahorro": p_dc, "p_sis": p_sis, "agua_l_h": agua_l_h, "agua_sis_l_h": agua_sis_l_h,
            "f_cpd": f_cpd, "f_cal": f_cal, "f_frio": f_frio, "f_rech": f_rech}


def crf(i, n):
    return i * (1 + i) ** n / ((1 + i) ** n - 1)


def capex(c, d, ms, rec_on, p_dis):
    hp, ab, r2 = d["hp"], d["ab"], d["r2"]
    # potencia nominal comprada: n × nominal de catálogo; genéricos: lo requerido (absorción corregida por derrateo)
    nom_hp = d["q_gen_req"] if hp["q_nom"] == INF else d["n_hp"] * hp["q_nom"]
    if ab["q_nom"] == INF:
        f = ab["f_cap"] if ab["f_cap"] > 0 else 1.0
        nom_ab = d["q_frio_req"] / max(f, 0.3)
    else:
        nom_ab = d["n_ab"] * ab["q_nom"]
    nom_r2 = demanda_r2(c) if r2["q_nom"] == INF else d["n_r2"] * r2["q_nom"]
    c_hp = c["eco.capex_bdc"] * nom_hp
    c_ab = c["eco.capex_abs"] * nom_ab
    c_adiab = c["eco.capex_adiab"] * p_dis["q_adiab"]
    c_r1 = c["eco.capex_r1"] * demanda_r1(c) if rec_on else 0.0
    c_r2 = c["eco.capex_r2"] * nom_r2 if rec_on else 0.0
    equipos = c_hp + c_ab + c_adiab + c_r1 + c_r2
    return {"capex_bdc1": c_hp, "capex_abs": c_ab, "capex_adiab": c_adiab, "capex_r1": c_r1, "capex_r2": c_r2,
            "capex_bop": equipos * c["eco.bop"], "capex_total": equipos * (1 + c["eco.bop"]),
            "nom_bdc1_kw": nom_hp, "nom_abs_kw": nom_ab, "nom_r2_kw": nom_r2 if rec_on else 0.0,
            "nom_adiab_kw": p_dis["q_adiab"]}


def evaluar(c, cat, modo):
    """Año completo de un caso en un modo ('sin_recuperacion' | 'con_recuperacion')."""
    rec_modo = modo == "con_recuperacion"
    ms = modelos(c, cat)
    d = dimensionar(c, ms)
    p_dis = punto(c, d, 1.0, False)
    cov = c["rec.cobertura"] if rec_modo else 0.0
    subs = [(1.0 - cov, False), (cov, True)] if rec_modo else [(1.0, False)]
    h = c["cpd.horas"]

    acc = {k: 0.0 for k in ("e_sis", "e_enf", "agua", "frio", "calor", "rej", "adiab", "w_bdc1", "w_r2",
                            "bombas", "vent", "aux", "dc", "cpd", "evap", "agua_sis")}
    cargas = []
    for carga, peso in c["perfil"]:
        for w_sub, on in subs:
            if w_sub <= 0:
                continue
            w = peso * w_sub
            p = punto(c, d, carga, on)
            p["peso"] = w
            cargas.append(p)
            acc["e_sis"] += w * p["p_sis"] * h
            acc["e_enf"] += w * p["p_enf"] * h
            acc["agua"] += w * p["agua_l_h"] * h / 1000.0
            acc["frio"] += w * p["q_frio"] * h
            acc["calor"] += w * (p["q_r1"] + p["q_r2"]) * h
            acc["rej"] += w * p["q_rej"] * h
            acc["adiab"] += w * p["q_adiab"] * h
            acc["w_bdc1"] += w * p["w_bdc1"] * h
            acc["w_r2"] += w * p["w_r2"] * h
            acc["bombas"] += w * p["p_bombas"] * h
            acc["vent"] += w * p["p_vent"] * h
            acc["aux"] += w * p["p_aux_abs"] * h
            acc["dc"] += w * p["p_dc_ahorro"] * h
            acc["cpd"] += w * p["q_cpd_disp"] * h
            acc["evap"] += w * p["q_evap"] * h
            acc["agua_sis"] += w * p["agua_sis_l_h"] * h / 1000.0

    cx = capex(c, d, ms, rec_modo, p_dis)
    c_elec = (acc["e_sis"] + acc["e_enf"]) * c["eco.elec"]
    c_agua = acc["agua"] * c["eco.agua"]
    c_mant = c["eco.mant"] * cx["capex_total"]
    credito = acc["calor"] * c["rec.precio_calor"] / c["rec.rend_caldera"]
    capex_anual = crf(c["eco.tasa"], c["eco.vida"]) * cx["capex_total"]
    j = c_elec + c_agua + c_mant + capex_anual - credito

    dem = c["frio.demanda_kw"]
    eer = enf_eer(c, c["frio.t_imp"])
    e_base = dem / eer * h
    agua_base = agua_torre_l_kwh(c) * (dem + dem / eer) * h / 1000.0
    c_elec_base = e_base * c["eco.elec"]
    c_agua_base = agua_base * c["eco.agua"]
    j_base = c_elec_base + c_agua_base
    ahorro_op = j_base - (c_elec + c_agua + c_mant - credito)
    e_tot = acc["e_sis"] + acc["e_enf"]

    # ---- revalorización del calor del CPD (lo que importa al sitio que lo acoge)
    util = acc["frio"] + acc["calor"]                      # kWh útiles entregados al sitio
    coste_sis = capex_anual + c_mant + acc["e_sis"] * c["eco.elec"] + acc["agua_sis"] * c["eco.agua"]
    valor_frio = (c["eco.elec"] / eer + agua_torre_l_kwh(c) * (1 + 1 / eer) / 1000.0 * c["eco.agua"]) * 1000.0
    valor_calor = c["rec.precio_calor"] / c["rec.rend_caldera"] * 1000.0
    rev = {"calor_residual_mwh": acc["cpd"] / 1e3, "calor_revalorizado_mwh": acc["evap"] / 1e3,
           "frac_revalorizado": acc["evap"] / acc["cpd"] if acc["cpd"] > 0 else 0.0,
           "erf": acc["evap"] / (acc["cpd"] * c["cpd.pue"]) if acc["cpd"] > 0 else 0.0,
           "util_mwh": util / 1e3, "coste_sis": coste_sis,
           "coste_util": coste_sis / util * 1000.0 if util > 0 else INF,      # €/MWh útil
           "valor_frio": valor_frio, "valor_calor": valor_calor,             # €/MWh que le cuesta hoy al sitio
           "valor_util": (acc["frio"] * valor_frio + acc["calor"] * valor_calor) / util if util > 0 else 0.0,
           "agua_sis_m3": acc["agua_sis"]}

    r = {"modo": modo,
         "cop_bdc1": d["hp"]["cop"], "cop_abs": d["ab"]["cop"], "cop_r2": d["r2"]["cop"], "eer_enf": eer,
         "cal_bdc1": d["hp"]["nivel"], "cal_abs": d["ab"]["nivel"], "cal_r2": d["r2"]["nivel"] if rec_modo and d["n_r2"] > 0 else 0,
         "n_bdc1": d["n_hp"], "n_abs": d["n_ab"], "n_r2": d["n_r2"] if rec_modo else 0,
         "cap_bdc1_kw": d["hp"]["cap"], "cap_abs_kw": d["ab"]["cap"], "cap_r2_kw": d["r2"]["cap"],
         "limitante": p_dis["limitante"], "frio_dis_kw": p_dis["q_frio"], "cobertura_frio": p_dis["q_frio"] / dem,
         "frio_mwh": acc["frio"] / 1e3, "calor_rec_mwh": acc["calor"] / 1e3, "rechazo_mwh": acc["rej"] / 1e3,
         "elec_sis_mwh": acc["e_sis"] / 1e3, "elec_enf_mwh": acc["e_enf"] / 1e3, "elec_base_mwh": e_base / 1e3,
         "ahorro_elec_mwh": (e_base - e_tot) / 1e3,
         "e_bdc1_mwh": acc["w_bdc1"] / 1e3, "e_r2_mwh": acc["w_r2"] / 1e3, "e_bombas_mwh": acc["bombas"] / 1e3,
         "e_vent_mwh": acc["vent"] / 1e3, "e_aux_mwh": acc["aux"] / 1e3, "e_dc_ahorro_mwh": acc["dc"] / 1e3,
         "agua_m3": acc["agua"], "agua_base_m3": agua_base,
         "eer_sis": acc["frio"] / acc["e_sis"] if acc["e_sis"] > 0 else 0.0,
         "c_elec": c_elec, "c_agua": c_agua, "c_mant": c_mant, "capex_anual": capex_anual, "credito_calor": credito,
         "c_elec_base": c_elec_base, "c_agua_base": c_agua_base,
         "J": j, "J_base": j_base, "ahorro_neto": j_base - j, "ahorro_operacion": ahorro_op,
         "retorno_anos": cx["capex_total"] / ahorro_op if ahorro_op > 0 else INF}
    r.update(cx)
    r.update(rev)
    r["diseno"] = p_dis
    r["cargas"] = cargas
    return r


def con(c, ruta, valor):
    d = dict(c)
    d[ruta] = valor
    return d
