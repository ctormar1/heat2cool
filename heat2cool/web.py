"""Genera el dashboard: un único HTML autónomo (motor JS + catálogo + Plotly) que funciona sin Python ni internet.

Para incrustarlo en otra web: <iframe src="heat2cool_dashboard.html" style="width:100%;height:900px;border:0"></iframe>
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import parametros as P

WEB = Path(__file__).resolve().parent.parent / "web"


def _json_seguro(obj) -> str:
    def limpio(x):
        if isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
            return None
        if isinstance(x, dict):
            return {k: limpio(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [limpio(v) for v in x]
        return x
    return json.dumps(limpio(obj), ensure_ascii=False).replace("</", "<\\/")


def datos(cat: dict, caso: dict) -> dict:
    return {"catalogo": {n: {"tipo": e["tipo"], "origen": e["origen"], "puntos": e["puntos"]} for n, e in cat.items()},
            "params": [list(p) for p in P.PARAMS], "equipos": [list(e) for e in P.EQUIPOS],
            "unidades": [list(u) for u in P.UNIDADES], "barrido": [[r, v] for r, v in P.BARRIDO],
            "modos": P.MODOS, "sens": P.SENSIBILIDAD, "sens_rec": P.SENSIBILIDAD_REC, "caso": caso}


def construir(ruta: str | Path, cat: dict, caso: dict, plotly_en_linea: bool = True) -> Path:
    html = (WEB / "plantilla.html").read_text(encoding="utf-8")
    motor = (WEB / "motor.js").read_text(encoding="utf-8")
    if plotly_en_linea:
        from plotly.offline import get_plotlyjs
        plotly = get_plotlyjs()
    else:
        plotly = ""
        html = html.replace("<script>/*__PLOTLY__*/</script>",
                            '<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>')
    html = (html.replace("/*__PLOTLY__*/", plotly)
                .replace("/*__MOTOR__*/", motor)
                .replace("/*__DATOS__*/", _json_seguro(datos(cat, caso))))
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(html, encoding="utf-8")
    return ruta.resolve()
