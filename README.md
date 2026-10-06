# heat2cool · simulador CPD → bomba de calor → absorción

Tú das las condiciones de entrada y salida de cada circuito (temperaturas, potencias, demanda, equipos) y el
programa, con las curvas de fabricante por detrás, calcula todo lo demás: COP, capacidades, nº de unidades,
caudales, bombeo, rechazo a torre/adiabático, electricidad, agua, CAPEX, coste anual y ahorro frente a la línea base.

## Uso rápido

```bash
pip install -r requirements.txt
python simular.py            # 1ª vez: crea entrada.xlsx y calcula con los valores por defecto
```

1. Abre **`entrada.xlsx`** y cambia las celdas azules:
   - **Entradas**: CPD, agua caliente, agua enfriada, rechazo, bombeo, modelos, recuperación, economía.
     Columna *Origen*: `BASE` = dato de diseño, `SUPUESTO` = provisional (a confirmar).
   - **Equipos**: elige BdC 1, absorción y BdC R2 en el desplegable; nº de unidades (0 = lo dimensiona el programa).
   - **Perfil**: horas al año a cada carga del CPD.
   - **Barrido**: las variables que quieras barrer y sus valores (`75; 80; 85`). Se calculan todas las combinaciones.
2. `python simular.py` (o **F5** en VS Code → *heat2cool: calcular los dos modos*).
3. Resultados en `salidas/`:

| Fichero | Contenido |
|---|---|
| `heat2cool_sin_recuperacion.xlsx` | Solo frío |
| `heat2cool_con_recuperacion.xlsx` | Frío + R1 (precalentar red) + R2 (BdC a 90 °C) |
| `heat2cool_optimizacion.xlsx` | Top 5 de soluciones para la situación del cliente según cada objetivo, y todas las soluciones viables |
| `heat2cool_dashboard.html` | Dashboard **sencillo**: 8 deslizadores, veredicto en una frase, flujos de energía y costes |
| `heat2cool_dashboard_avanzado.html` | Dashboard **avanzado**: todos los parámetros, mapa de escenarios, sensibilidad, tablas |

Cada Excel tiene las hojas Resumen, Balance, Equipos, Barrido (**todos** los escenarios con ranking y filtros),
Mapas, Anual, Costes, Sensibilidad (tornado), Avisos y Entradas (copia exacta de lo que metiste), con gráficos de Excel.

Opciones: `--modo sin|con|ambos`, `--sin-barrido`, `--plantilla` (regenera el Excel de entrada), `--no-abrir`.

## Qué mide

El objetivo es **revalorizar el calor residual del CPD** en frío y calor para el sitio que lo acoge. Indicadores principales:

- **Calor del CPD revalorizado** (MWh/año y % del calor residual).
- **Coste por MWh útil** = (CAPEX anualizado + mantenimiento + electricidad + agua del sistema nuevo) / (frío + calor
  entregados al sitio), comparado con lo que le cuesta hoy al sitio ese MWh (frío con su enfriadora, calor con caldera).
- **ERF del CPD** (Energy Reuse Factor, EN 50600-4-6) = calor reutilizado / energía total del CPD (calor × PUE).

El ahorro frente a seguir con la enfriadora se mantiene como dato secundario.

## Optimizador

Con la situación del cliente fija (calor y temperaturas del CPD, demanda de frío y calor del sitio, temperaturas, precios)
prueba todas las combinaciones de BdC 1, absorción, con/sin recuperación, BdC R2 y T al generador (75-95 °C), descartando
equipos fuera de rango (>10 K de sus datos) y genéricos. Da el top 5 para cada objetivo: menor coste por MWh útil, más
calor revalorizado, mayor ERF y mayor ahorro. Sale en `salidas/heat2cool_optimizacion.xlsx` y en la tarjeta
*Optimizar para este sitio* del dashboard (botón *Usar* para cargar una solución).

## Dashboard HTML

Los dos dashboards son el mismo fichero con distinta vista inicial (se cambia con el botón *Sencillo / Avanzado* o con `?vista=avanzada` en la URL). Cada uno es un único fichero (≈4,5 MB) con el motor de cálculo en JavaScript, el catálogo y
Plotly dentro. Se abre con doble clic y recalcula al instante al cambiar cualquier entrada. Para integrarlo en otra web:

```html
<iframe src="heat2cool_dashboard.html" style="width:100%;height:900px;border:0"></iframe>
```

Incluye: indicadores, diagrama de flujos de energía, costes, mapa de escenarios con las variables que elijas
(pulsando una celda se aplica al caso), tornado, equipos con la calidad del dato, circuitos, detalle por carga y avisos.
*Exportar / Importar caso* guarda y carga el caso como JSON.

El motor JS (`web/motor.js`) es una traducción línea a línea de `heat2cool/motor.py`; `tests/test_heat2cool.py` comprueba
con Node que ambos dan los mismos números.

## Cómo calcula

- **Catálogo** (`catalogo/curvas.csv`): una fila por punto de funcionamiento publicado de cada equipo.
  Se genera con `python tools/construir_catalogo.py` a partir de `data/`, y puedes añadir filas a mano.
- **Bomba de calor**: rendimiento de Carnot η ajustado a los puntos del equipo (lineal en el salto térmico si hay
  varios) con pinch en evaporador y condensador; capacidad ajustada igual.
- **Absorción**: COP ideal de tres focos (Gordon-Ng) × η ajustado a los puntos del equipo, con techo 0,80;
  capacidad corregida linealmente con T generador, T agua enfriada y T refrigeración.
- **Calidad del dato** en cada resultado: ◆ genérico · ● dentro del rango del fabricante · ▲ extrapolado ≤10 K ·
  ✖ fuera de rango >10 K.
- **Sistema**: el CPD da calor a la BdC 1, que alimenta el generador. Lo que limita (calor del CPD, demanda,
  capacidad de absorción o de BdC) fija el punto. El frío que falta lo pone la enfriadora existente. El rechazo
  va a la torre existente y el exceso al adiabático nuevo; R1/R2 recuperan parte del rechazo.
- **Año**: ponderado por el perfil de carga (y por la fracción de horas con consumo de calor en el modo con recuperación).
- **Línea base**: toda la demanda de frío con la enfriadora existente. Ahorro neto = J_base − J, con
  J = electricidad + agua + mantenimiento + CRF·CAPEX − crédito por calor.

## Límites conocidos

- Con 1-2 puntos por máquina, el COP fuera de las condiciones publicadas es una estimación (por eso la calidad del dato).
- Clima fijo (sin rechazo horario), sin pérdidas en tuberías, penalización a carga parcial configurable pero 0 por defecto.
- Los importes dependen de los parámetros `SUPUESTO`.

## Estructura

```
simular.py              punto de entrada
heat2cool/parametros.py     esquema único de entradas (valores, unidades, BASE/SUPUESTO)
heat2cool/catalogo.py       lee catalogo/curvas.csv
heat2cool/motor.py          modelos de equipo, balance, dimensionado, año, economía
heat2cool/estudio.py        barrido, sensibilidad, puntos de equilibrio
heat2cool/entrada_xlsx.py   plantilla de entrada
heat2cool/salida_xlsx.py    Excel de resultados con gráficos
heat2cool/web.py            genera el dashboard
web/motor.js            el mismo motor en JavaScript
web/plantilla.html      interfaz del dashboard
tests/                  pytest (incluye paridad Python ↔ JS)
tools/                  construcción del catálogo y utilidades
```
