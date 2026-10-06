"""heat2cool · simulador de recuperación de calor del CPD → BdC → absorción.

    python simular.py                    lee entrada.xlsx (la crea si no existe) y calcula los dos modos
    python simular.py --modo sin         solo el modo sin recuperación (o: con | ambos)
    python simular.py --plantilla        regenera entrada.xlsx con los valores por defecto y sale
    python simular.py --sin-barrido      solo el caso de la hoja Entradas (más rápido)

Salidas en salidas/: heat2cool_sin_recuperacion.xlsx, heat2cool_con_recuperacion.xlsx y heat2cool_dashboard.html.
"""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from pathlib import Path

from heat2cool import catalogo, entrada_xlsx, estudio, salida_xlsx, web
from heat2cool.motor import CALIDAD, evaluar
from heat2cool.parametros import MODOS

RAIZ = Path(__file__).resolve().parent
ALIAS = {"sin": ["sin_recuperacion"], "con": ["con_recuperacion"], "ambos": list(MODOS)}


def _eur(x):
    return f"{x:>12,.0f} €".replace(",", ".")


def main():
    ap = argparse.ArgumentParser(description="heat2cool · simulador")
    ap.add_argument("--entrada", default=str(RAIZ / "entrada.xlsx"))
    ap.add_argument("--salida", default=str(RAIZ / "salidas"))
    ap.add_argument("--modo", choices=list(ALIAS), default="ambos")
    ap.add_argument("--plantilla", action="store_true", help="regenera el Excel de entrada y sale")
    ap.add_argument("--sin-barrido", action="store_true")
    ap.add_argument("--no-abrir", action="store_true", help="no abre el dashboard al terminar")
    a = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cat = catalogo.cargar()
    entrada = Path(a.entrada)
    if a.plantilla or not entrada.exists():
        entrada_xlsx.escribir_plantilla(entrada, cat)
        print(f"Plantilla de entrada creada: {entrada}")
        if a.plantilla:
            return
        print("Calculo con los valores por defecto. Edita el Excel y vuelve a ejecutar.\n")

    caso, barrido_vars = entrada_xlsx.leer(entrada)
    if a.sin_barrido:
        barrido_vars = []
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    for modo in ALIAS[a.modo]:
        res = evaluar(caso, cat, modo)
        filas = estudio.barrido(caso, cat, modo, barrido_vars) if barrido_vars else []
        sens = estudio.sensibilidad(caso, cat, modo)
        equil = estudio.equilibrios(caso, cat, modo)
        ruta = salida / f"heat2cool_{modo}.xlsx"
        try:
            salida_xlsx.escribir(ruta, modo, caso, res, barrido_vars, filas, sens, equil, cat)
        except PermissionError:
            sys.exit(f"\n✖ No puedo escribir {ruta}: ciérralo en Excel y vuelve a ejecutar.")

        print(f"━━━ {MODOS[modo]} ━━━")
        print(f"  Ahorro neto   {_eur(res['ahorro_neto'])}/año    CAPEX {_eur(res['capex_total'])}    "
              f"retorno {estudio.fmt_retorno(res['retorno_anos'])}")
        print(f"  COP BdC 1 {res['cop_bdc1']:.2f} ({CALIDAD[res['cal_bdc1']]}) · "
              f"COP absorción {res['cop_abs']:.3f} ({CALIDAD[res['cal_abs']]})")
        print(f"  Limita a plena carga: {res['limitante']} · cubre el {res['cobertura_frio']:.0%} del frío")
        if equil["eer_equilibrio"]:
            print(f"  Empata si la enfriadora existente tuviera EER {equil['eer_equilibrio']:.2f} "
                  f"(supuesto {caso['enf.eer_ref']})")
        if filas:
            pos = sum(f["ahorro_neto"] > 0 for f in filas)
            m, p = filas[0], filas[-1]
            vs = lambda f: ", ".join(f"{r}={f[r]:g}" for r, _ in barrido_vars)
            print(f"  Barrido: {len(filas)} escenarios, {pos} con ahorro positivo")
            print(f"    mejor: {vs(m)} → {_eur(m['ahorro_neto'])}/año")
            print(f"    peor:  {vs(p)} → {_eur(p['ahorro_neto'])}/año")
        print(f"  → {ruta}\n")

    html = web.construir(salida / "heat2cool_dashboard.html", cat, caso)
    print(f"Dashboard: {html}")
    print(f"Listo en {time.time() - t0:.1f} s.")
    if not a.no_abrir:
        webbrowser.open(html.as_uri())


if __name__ == "__main__":
    main()
