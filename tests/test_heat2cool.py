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


@pytest.fixture(scope="module")
def cat():
    return catalogo.cargar()


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
              ({**caso, "bdc.pen_carga": 0.3, "abs.pen_carga": 0.2, "rec.cobertura": 0.6}, "con_recuperacion")]
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
