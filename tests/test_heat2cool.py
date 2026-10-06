"""Tests: balance con equipos genéricos, conservación de energía, tendencias físicas, Excel y paridad Python ↔ JavaScript."""
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from heat2cool import catalogo, entrada_xlsx, estudio, motor, salida_xlsx, web
from heat2cool import parametros as P

RAIZ = Path(__file__).resolve().parent.parent
GENERICOS = {"eq.bdc1": "Genérico BdC (COP 4 a 50→90)",
             "eq.abs": "Genérica absorción (COP 0,70 a 90/7/30)",
             "eq.r2": "Genérico BdC CO2 (COP 4 a 30→90)"}


SINTETICA = "Sintética 6 puntos (test)"


@pytest.fixture(scope="module")
def cat():
    c = dict(catalogo.cargar())
    # η con máximo a mitad de rango, como en las medidas de laboratorio
    c[SINTETICA] = {"tipo": "bdc", "origen": "medido", "puntos": [
        {"ts": 50.0, "tk": tk, "q": None, "cop": cop} for tk, cop in
        [(75, 4.84), (80, 4.61), (90, 4.14), (100, 3.68), (110, 3.25), (120, 2.82)]]}
    return c


@pytest.fixture
def caso():
    return P.caso_por_defecto()


def _punto(c, cat, carga=1.0, rec=False):
    return motor.punto(c, motor.dimensionar(c, motor.modelos(c, cat)), carga, rec)


def test_genericos_dan_el_balance_analitico(cat, caso):
    # COP 4 y 0,70 exactos en su punto: Q_gen = Q·4/3, W = Q/3, frío = 0,7·Q_gen, rechazo = Q_gen + frío
    c = {**caso, **GENERICOS, "cpd.q_kw": 120.0, "frio.demanda_kw": 500.0}
    p = _punto(c, cat)
    assert p["cop_bdc1"] == pytest.approx(4.0)
    assert p["cop_abs"] == pytest.approx(0.70)
    assert p["w_bdc1"] == pytest.approx(40.0)
    assert p["q_gen"] == pytest.approx(160.0)
    assert p["q_frio"] == pytest.approx(112.0)
    assert p["q_rej"] == pytest.approx(272.0)


@pytest.mark.parametrize("rec", [False, True])
@pytest.mark.parametrize("carga", [0.25, 0.75, 1.0])
def test_conservacion_de_energia(cat, caso, rec, carga):
    p = _punto(caso, cat, carga, rec)
    assert p["q_gen"] == pytest.approx(p["q_evap"] + p["w_bdc1"])
    assert p["q_rej"] == pytest.approx(p["q_gen"] + p["q_frio"])
    assert p["q_dis"] == pytest.approx(p["q_rej"] - p["q_r1"] - p["q_r2_ext"])
    assert p["q_torre"] + p["q_adiab"] == pytest.approx(p["q_dis"])
    assert p["q_frio"] + p["q_enf"] == pytest.approx(caso["frio.demanda_kw"])
    assert p["q_r2"] == pytest.approx(p["q_r2_ext"] + p["w_r2"])
    assert p["q_evap"] <= caso["cpd.q_kw"] * carga + 1e-9


def test_tendencias_fisicas(cat, caso):
    ms = motor.modelos(caso, cat)
    hp = lambda tk: motor.bdc_en(caso, ms["bdc1"], 50, tk)["cop"]
    ab = lambda tg, tc, tr=30: motor.abs_en(caso, ms["abs"], tg, tc, tr)["cop"]
    assert hp(75) > hp(85) > hp(95)            # más salto térmico → menos COP
    assert ab(90, 10) > ab(90, 7) > ab(90, 4)  # agua más fría → menos COP
    assert ab(90, 7, 27) > ab(90, 7, 33)       # rechazo más caliente → menos COP
    assert ab(38, 7) == 0.0                    # generador por debajo del rechazo + pinch: no hay ciclo
    cap = lambda tg: motor.abs_en(caso, ms["abs"], tg, 7, 30)["cap"]
    assert cap(60) < 0.4 * cap(88)             # a baja T de generador la máquina pierde casi toda su capacidad


def test_calidad_del_dato(cat, caso):
    ms = motor.modelos({**caso, "eq.bdc1": "Ejemplo BdC alta T 200 kW"}, cat)  # puntos a 80-90 °C
    assert motor.bdc_en(caso, ms["bdc1"], 45, 85)["nivel"] == 1   # dentro del rango publicado
    assert motor.bdc_en(caso, ms["bdc1"], 45, 95)["nivel"] == 2   # 5 K por encima
    assert motor.bdc_en(caso, ms["bdc1"], 45, 105)["nivel"] == 3  # 15 K por encima
    gen = motor.modelos({**caso, **GENERICOS}, cat)
    assert motor.bdc_en(caso, gen["bdc1"], 45, 105)["nivel"] == 0


def test_ajuste_parabolico_reproduce_medidas(cat, caso):
    ms = motor.modelos({**caso, "eq.bdc1": SINTETICA}, cat)
    assert ms["bdc1"]["c"] != 0.0                       # con 6 saltos en 45 K usa parábola
    for p in cat[SINTETICA]["puntos"]:
        assert motor.bdc_en(caso, ms["bdc1"], p["ts"], p["tk"])["cop"] == pytest.approx(p["cop"], rel=0.03)
    pocos = motor.ajustar_bdc(caso, {"origen": "x", "puntos": cat[SINTETICA]["puntos"][:3]})
    assert pocos["c"] == 0.0                            # con 3 puntos sigue siendo recta


def test_dimensiona_unidades_y_limita_por_capacidad(cat, caso):
    c = {**caso, "eq.abs": "Ejemplo absorción 50 kW"}
    r = motor.evaluar(c, cat, "sin_recuperacion")
    assert (r["n_abs"] - 1) * r["cap_abs_kw"] < r["frio_dis_kw"] <= r["n_abs"] * r["cap_abs_kw"] + 1e-9
    assert r["n_abs"] >= 2
    r1 = motor.evaluar({**c, "n.abs": 1}, cat, "sin_recuperacion")
    assert r1["limitante"] == "Capacidad de la absorción"
    assert r1["frio_dis_kw"] < r["frio_dis_kw"]


def test_desglose_de_costes_suma_J(cat, caso):
    for modo in P.MODOS:
        r = motor.evaluar(caso, cat, modo)
        assert r["J"] == pytest.approx(r["c_elec"] + r["c_agua"] + r["c_mant"] + r["capex_anual"] - r["credito_calor"])
        assert r["capex_total"] == pytest.approx(sum(r[k] for k in ("capex_bdc1", "capex_abs", "capex_adiab",
                                                                    "capex_r1", "capex_r2", "capex_bop")))
    assert motor.evaluar(caso, cat, "sin_recuperacion")["credito_calor"] == 0.0


def test_equilibrio_anula_el_ahorro(cat, caso):
    eq = estudio.equilibrios(caso, cat, "sin_recuperacion")
    r = motor.evaluar({**caso, "enf.eer_ref": eq["eer_equilibrio"]}, cat, "sin_recuperacion")
    assert abs(r["ahorro_neto"]) < 1.0


def test_barrido_completo(cat, caso):
    filas = estudio.barrido(caso, cat, "sin_recuperacion", P.BARRIDO)
    assert len(filas) == 5 * 7
    assert [f["ranking"] for f in filas] == list(range(1, 36))
    assert all(math.isfinite(f["ahorro_neto"]) for f in filas)


def test_excel_ida_y_vuelta(tmp_path, cat, caso):
    ent = tmp_path / "entrada.xlsx"
    entrada_xlsx.escribir_plantilla(ent, cat)
    leido, barrido = entrada_xlsx.leer(ent)
    assert leido == caso
    assert barrido == [(r, [float(v) for v in vs]) for r, vs in P.BARRIDO]
    for modo in P.MODOS:
        res = motor.evaluar(leido, cat, modo)
        filas = estudio.barrido(leido, cat, modo, barrido[:1])
        salida_xlsx.escribir(tmp_path / f"{modo}.xlsx", modo, leido, res, barrido[:1], filas,
                             estudio.sensibilidad(leido, cat, modo), estudio.equilibrios(leido, cat, modo), cat)
        assert (tmp_path / f"{modo}.xlsx").stat().st_size > 10_000


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no instalado")
def test_paridad_python_javascript(tmp_path, cat, caso):
    casos = [(caso, m) for m in P.MODOS]
    casos += [({**caso, **GENERICOS}, "con_recuperacion"),
              ({**caso, "eq.abs": "Ejemplo absorción 50 kW", "cal.t_ida": 80.0, "frio.t_imp": 5.0}, "sin_recuperacion"),
              ({**caso, "bdc.pen_carga": 0.3, "abs.pen_carga": 0.2, "rec.cobertura": 0.6}, "con_recuperacion"),
              ({**caso, "eq.bdc1": SINTETICA, "cal.t_ida": 84.0}, "sin_recuperacion"),
              ({**caso, "rec.r2_on": 0.0}, "con_recuperacion"),
              ({**caso, "rec.r1_on": 0.0, "rec.r2_kw": 0.0}, "con_recuperacion")]
    entrada = {"cat": web.datos(cat, caso)["catalogo"], "casos": [[c, m] for c, m in casos]}
    f = tmp_path / "casos.json"
    f.write_text(web._json_seguro(entrada), encoding="utf-8")
    script = (f"const H=require({json.dumps(str(RAIZ / 'web' / 'motor.js'))});"
              f"const d=JSON.parse(require('fs').readFileSync({json.dumps(str(f))},'utf8'));"
              "const out=d.casos.map(([c,m])=>{const r=H.evaluar(c,d.cat,m);delete r.cargas;"
              "return Object.assign(r,H.equilibrios(c,d.cat,m));});"
              "console.log(JSON.stringify(out,(k,v)=>v===Infinity?'INF':v));")
    js = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True,
                                   encoding="utf-8").stdout)
    for (c, m), rj in zip(casos, js):
        rp = motor.evaluar(c, cat, m)
        rp.update(estudio.equilibrios(c, cat, m))
        for k, vp in rp.items():
            if k in ("cargas", "diseno"):
                continue
            vj = rj[k]
            if isinstance(vp, float) and math.isinf(vp):
                assert vj == "INF", k
            elif isinstance(vp, (int, float)) and vp is not None:
                assert vj == pytest.approx(vp, rel=1e-9, abs=1e-9), f"{m}: {k}"
            else:
                assert vj == vp, k
        for k, vp in rp["diseno"].items():
            if isinstance(vp, float):
                assert rj["diseno"][k] == pytest.approx(vp, rel=1e-9, abs=1e-9), f"diseño {k}"


def test_optimizador_ordena_y_respeta_filtros(cat, caso):
    sols = estudio.soluciones(caso, cat)
    assert sols
    top = estudio.ordenar(sols, "coste_util")
    assert [x["coste_util"] for x in top] == sorted(x["coste_util"] for x in top)
    assert all(max(x["cal_bdc1"], x["cal_abs"], x["cal_r2"]) <= 2 for x in sols)     # nada fuera de rango
    assert not any(cat[x["eq.bdc1"]]["origen"] == "generico" for x in sols)           # sin genéricos por defecto
    mejor = top[0]
    r = motor.evaluar({**caso, "eq.bdc1": mejor["eq.bdc1"], "eq.abs": mejor["eq.abs"], "eq.r2": mejor["eq.r2"] or caso["eq.r2"],
                       "cal.t_ida": mejor["cal.t_ida"], "n.bdc1": 0, "n.abs": 0, "n.r2": 0}, cat, mejor["modo"])
    assert r["coste_util"] == pytest.approx(mejor["coste_util"])                      # la solución se puede reproducir


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no instalado")
def test_paridad_optimizador(tmp_path, cat, caso):
    f = tmp_path / "opt.json"
    caso = {**caso, "opt.recuperacion": 2.0, "rec.r2_on": 0.0}   # también la opción de recuperación del optimizador
    f.write_text(web._json_seguro({"cat": web.datos(cat, caso)["catalogo"], "caso": caso}), encoding="utf-8")
    script = (f"const H=require({json.dumps(str(RAIZ / 'web' / 'motor.js'))});"
              f"const d=JSON.parse(require('fs').readFileSync({json.dumps(str(f))},'utf8'));"
              "const s=H.soluciones(d.caso,d.cat);const o={n:s.length};"
              "for(const k of Object.keys(H.OBJETIVOS)) o[k]=H.ordenar(s,k).slice(0,5).map(x=>[x.modo,x['cal.t_ida'],x['eq.bdc1'],x['eq.abs'],x['eq.r2'],x[k]]);"
              "console.log(JSON.stringify(o));")
    js = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, encoding="utf-8").stdout)
    sols = estudio.soluciones(caso, cat)
    assert js["n"] == len(sols)
    for k in estudio.OBJETIVOS:
        py = [[x["modo"], x["cal.t_ida"], x["eq.bdc1"], x["eq.abs"], x["eq.r2"], x[k]] for x in estudio.ordenar(sols, k)[:5]]
        for a, b in zip(py, js[k]):
            assert a[:5] == b[:5], k
            assert a[5] == pytest.approx(b[5], rel=1e-9)


def test_interruptores_de_recuperacion(cat, caso):
    sin = motor.evaluar(caso, cat, "sin_recuperacion")
    apagada = motor.evaluar({**caso, "rec.r1_on": 0.0, "rec.r2_on": 0.0}, cat, "con_recuperacion")
    for k in ("ahorro_neto", "capex_total", "coste_util", "calor_rec_mwh", "elec_sis_mwh"):
        assert apagada[k] == pytest.approx(sin[k]), k                    # con todo apagado = sin recuperación
    solo_r1 = motor.evaluar({**caso, "rec.r2_on": 0.0}, cat, "con_recuperacion")
    assert solo_r1["capex_r2"] == 0.0 and solo_r1["n_r2"] == 0 and solo_r1["e_r2_mwh"] == 0.0
    assert solo_r1["calor_rec_mwh"] > 0                                  # R1 sigue entregando calor
    sin_demanda = motor.evaluar({**caso, "rec.r2_kw": 0.0}, cat, "con_recuperacion")
    assert sin_demanda["capex_r2"] == 0.0                                # sin demanda de R2 no se compra la BdC R2


def test_optimizador_respeta_la_opcion_de_recuperacion(cat, caso):
    assert estudio.modos_opt({**caso, "opt.recuperacion": 0.0}) == ("sin_recuperacion",)
    assert estudio.modos_opt({**caso, "opt.recuperacion": 2.0}) == ("con_recuperacion",)
    assert estudio.modos_opt({**caso, "opt.recuperacion": 1.0}) == ("sin_recuperacion", "con_recuperacion")
    assert estudio.modos_opt({**caso, "rec.r1_on": 0.0, "rec.r2_on": 0.0}) == ("sin_recuperacion",)
    sols = estudio.soluciones({**caso, "opt.recuperacion": 0.0}, cat)
    assert sols and all(s["modo"] == "sin_recuperacion" for s in sols)
    sols = estudio.soluciones({**caso, "opt.recuperacion": 2.0, "rec.r2_on": 0.0}, cat)
    assert sols and all(s["modo"] == "con_recuperacion" and s["eq.r2"] == "" for s in sols)
