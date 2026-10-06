"""Lee catalogo/curvas.csv y lo convierte al formato del motor: {equipo: {tipo, origen, puntos: [...]}}."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parent.parent / "catalogo"
RUTA = DIR / "curvas.csv"            # catálogo real (no se sube al repositorio)
EJEMPLO = DIR / "curvas_ejemplo.csv"  # genéricos y máquinas ficticias


def _f(v):
    return None if pd.isna(v) else float(v)


def cargar(ruta: str | Path | None = None) -> dict:
    ruta = Path(ruta) if ruta else (RUTA if RUTA.exists() else EJEMPLO)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}. Genéralo con: python tools/construir_catalogo.py")
    df = pd.read_csv(ruta)
    df = df[df["usar"] == 1]
    cat = {}
    for nombre, g in df.groupby("equipo", sort=False):
        tipo = g["tipo"].iloc[0]
        origen = "generico" if (g["origen"] == "generico").all() else (
            "fabricante" if (g["origen"] == "fabricante").any() else g["origen"].iloc[0])
        pts = []
        for _, r in g.iterrows():
            p = {"q": _f(r["q_kw"]), "cop": float(r["cop"])}
            if tipo == "bdc":
                p.update(ts=float(r["t_fuente_sal"]), tk=float(r["t_caliente_sal"]))
            else:
                p.update(tg=float(r["t_gen_ent"]), tc=float(r["t_frio_sal"]), tr=float(r["t_refrig_ent"]))
            pts.append(p)
        cat[nombre] = {"tipo": tipo, "origen": origen, "puntos": pts,
                       "fuente": str(g["fuente"].iloc[0]) if "fuente" in g else ""}
    return cat


def nombres(cat: dict, tipo: str) -> list[str]:
    return [n for n, e in cat.items() if e["tipo"] == tipo]
