"""Genera catalogo/curvas.csv (formato único y editable) a partir de los datos brutos de data/.

Uso: python tools/construir_catalogo.py      (sobrescribe catalogo/curvas.csv y catalogo/curvas_ejemplo.csv)
Si no tienes data/, el programa usa catalogo/curvas_ejemplo.csv (genéricos y máquinas ficticias).

Después de generarlo, el fichero a editar es catalogo/curvas.csv: añade filas con curvas de fabricante
cuando las tengas. Columnas:
  tipo            bdc | absorcion
  equipo          nombre del modelo (una fila por punto de funcionamiento)
  t_fuente_sal    BdC: °C del agua de fuente a la salida del evaporador
  t_caliente_sal  BdC: °C del agua caliente a la salida del condensador
  t_gen_ent       absorción: °C del agua caliente a la entrada del generador
  t_frio_sal      absorción: °C del agua enfriada a la salida del evaporador
  t_refrig_ent    absorción: °C del agua de refrigeración a la entrada del absorbedor
  q_kw            BdC: calor útil; absorción: frío (vacío = capacidad libre, equipo genérico)
  cop             COP de calefacción (BdC) o COP térmico frío/calor de generador (absorción)
  origen          fabricante | calculado | generico
  usar            1 = entra en el ajuste; 0 = se guarda pero no se usa
  fuente          enlace o nota
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COLS = ["tipo", "equipo", "t_fuente_sal", "t_caliente_sal", "t_gen_ent", "t_frio_sal", "t_refrig_ent",
        "q_kw", "cop", "origen", "usar", "fuente"]

rows = []

# ---------------------------------------------------------------- genéricos y ejemplos (también en curvas_ejemplo.csv)
# Genéricos: un punto, capacidad libre. Ejemplos: máquinas ficticias con valores típicos, para probar el programa
# sin datos reales (son las que trae por defecto el repositorio público).
EJEMPLO = "ficticio, valores típicos de catálogo"
rows += [
    dict(tipo="bdc", equipo="Genérico BdC (COP 4 a 50→90)", t_fuente_sal=50, t_caliente_sal=90,
         cop=4.0, origen="generico", usar=1, fuente="genérico"),
    dict(tipo="bdc", equipo="Genérico BdC CO2 (COP 4 a 30→90)", t_fuente_sal=30, t_caliente_sal=90,
         cop=4.0, origen="generico", usar=1, fuente="genérico"),
    dict(tipo="absorcion", equipo="Genérica absorción (COP 0,70 a 90/7/30)", t_gen_ent=90, t_frio_sal=7,
         t_refrig_ent=30, cop=0.70, origen="generico", usar=1, fuente="genérico"),
    dict(tipo="bdc", equipo="Ejemplo BdC alta T 200 kW", t_fuente_sal=40, t_caliente_sal=80, q_kw=215, cop=4.3,
         origen="ejemplo", usar=1, fuente=EJEMPLO),
    dict(tipo="bdc", equipo="Ejemplo BdC alta T 200 kW", t_fuente_sal=40, t_caliente_sal=90, q_kw=200, cop=3.6,
         origen="ejemplo", usar=1, fuente=EJEMPLO),
    dict(tipo="bdc", equipo="Ejemplo BdC alta T 200 kW", t_fuente_sal=50, t_caliente_sal=90, q_kw=225, cop=4.4,
         origen="ejemplo", usar=1, fuente=EJEMPLO),
    dict(tipo="bdc", equipo="Ejemplo BdC CO2 250 kW", t_fuente_sal=25, t_caliente_sal=80, q_kw=260, cop=3.6,
         origen="ejemplo", usar=1, fuente=EJEMPLO),
    dict(tipo="bdc", equipo="Ejemplo BdC CO2 250 kW", t_fuente_sal=30, t_caliente_sal=90, q_kw=250, cop=3.3,
         origen="ejemplo", usar=1, fuente=EJEMPLO),
    dict(tipo="absorcion", equipo="Ejemplo absorción 150 kW", t_gen_ent=88, t_frio_sal=7, t_refrig_ent=31,
         q_kw=150, cop=0.70, origen="ejemplo", usar=1, fuente=EJEMPLO),
    dict(tipo="absorcion", equipo="Ejemplo absorción 150 kW", t_gen_ent=80, t_frio_sal=7, t_refrig_ent=31,
         q_kw=115, cop=0.67, origen="ejemplo", usar=1, fuente=EJEMPLO),
    dict(tipo="absorcion", equipo="Ejemplo absorción 150 kW", t_gen_ent=95, t_frio_sal=9, t_refrig_ent=29,
         q_kw=180, cop=0.74, origen="ejemplo", usar=1, fuente=EJEMPLO),
    dict(tipo="absorcion", equipo="Ejemplo absorción 50 kW", t_gen_ent=88, t_frio_sal=7, t_refrig_ent=31,
         q_kw=52, cop=0.70, origen="ejemplo", usar=1, fuente=EJEMPLO),
]
n_ejemplo = len(rows)

# ---------------------------------------------------------------- bombas de calor
bdc = pd.read_csv(ROOT / "data" / "curvas_bdc_raw.csv")
for _, r in bdc.iterrows():
    if pd.isna(r.cop) or pd.isna(r.t_sink_out) or pd.isna(r.t_source_in):
        continue  # sin COP o sin temperaturas no sirve para ajustar
    t_src_out = r.t_source_out if pd.notna(r.t_source_out) else r.t_source_in - 5.0  # salto típico 5 K si no se publica
    nota = "" if pd.notna(r.t_source_out) else " | t_fuente_sal supuesta = entrada - 5 K"
    rows.append(dict(tipo="bdc", equipo=r.equipo.strip(), t_fuente_sal=t_src_out, t_caliente_sal=r.t_sink_out,
                     q_kw=r.capacidad_kw if pd.notna(r.capacidad_kw) else None, cop=r.cop,
                     origen=r.tipo_dato if isinstance(r.tipo_dato, str) else "fabricante",
                     usar=1 if r.tipo_dato != "calculado" else 0, fuente=str(r.fuente) + nota))

# ---------------------------------------------------------------- absorción
ab = pd.read_csv(ROOT / "data" / "curvas_absorcion_raw.csv")
for _, r in ab.iterrows():
    rows.append(dict(tipo="absorcion", equipo=r.equipo.strip(), t_gen_ent=r.t_gen, t_frio_sal=r.t_chw,
                     t_refrig_ent=r.t_rej, q_kw=r.capacidad_kw, cop=r.cop, origen=r.tipo_dato,
                     # los puntos "calculado" de Thermax son medidas de campo a carga parcial: no son curva de máquina
                     usar=1 if r.tipo_dato == "fabricante" else 0, fuente=r.fuente))

# ---------------------------------------------------------------- medidas de laboratorio (si existe el Excel)
# Prototipo HTHP R1233zd(E) ~37 kW, Universidad de Bayreuth. DOI 10.17632/56m3dd55zf.1
# Sin capacidad (q vacío): el prototipo no se escala a una máquina comercial; se usa solo para la forma del COP.
MED = ROOT / "data" / "mediciones_bdc.xlsx"
if MED.exists():
    from openpyxl import load_workbook
    filas = list(load_workbook(MED, data_only=True, read_only=True)["Datos"].iter_rows(values_only=True))
    cab = next(i for i, f in enumerate(filas) if f and f[0] == "ID")
    med = pd.DataFrame([f[:14] for f in filas[cab + 1:] if f and f[0]], columns=filas[cab][:14])
    FUENTE_MED = "Medido (Bayreuth, DOI 10.17632/56m3dd55zf.1), serie {}; retorno caliente {:.0f} °C"
    grupos = [
        # plena carga: series de carga parcial a 70 Hz (salida 90/100/110/120 °C, fuente 60→50)
        ("Prototipo R1233zd(E) · medido 70 Hz (plena carga)",
         med[med.Serie.isin(["S04", "S05", "S06", "S07"]) & (med["Frecuencia Hz"] == 70)]),
        # 50 Hz: salida 75-140 °C (S03), fuente 35-43 °C (S01) y retorno 50-60 °C de S02
        ("Prototipo R1233zd(E) · medido 50 Hz",
         med[med.Serie.isin(["S01", "S03"]) | ((med.Serie == "S02") & med["Caliente retorno °C"].between(45, 65))]),
    ]
    for nombre, g in grupos:
        for _, r in g.iterrows():
            rows.append(dict(tipo="bdc", equipo=nombre, t_fuente_sal=round(r["Fuente salida °C"], 2),
                             t_caliente_sal=round(r["Caliente salida °C"], 2), cop=round(r["COP registrado"], 4),
                             origen="medido", usar=1,
                             fuente=FUENTE_MED.format(r["Serie"], r["Caliente retorno °C"])))
    print(f"Medidas de laboratorio añadidas: {sum(len(g) for _, g in grupos)} puntos en {len(grupos)} equipos")

out = ROOT / "catalogo" / "curvas.csv"
out.parent.mkdir(exist_ok=True)
pd.DataFrame(rows[:n_ejemplo], columns=COLS).to_csv(out.with_name("curvas_ejemplo.csv"), index=False, encoding="utf-8")
df = pd.DataFrame(rows, columns=COLS).drop_duplicates(subset=COLS[:9])
df.to_csv(out, index=False, encoding="utf-8")
print(f"{len(df)} puntos, {df.equipo.nunique()} equipos -> {out}")
print(df[df.usar == 1].groupby("tipo").equipo.nunique().to_string())
