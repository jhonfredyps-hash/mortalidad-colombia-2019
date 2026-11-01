"""
Aplicación web interactiva - Análisis de mortalidad en Colombia (2019)
Datos: DANE - Estadísticas Vitales (defunciones no fetales 2019)
Tecnologías: Python, Pandas, Plotly y Dash
"""
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
PROC = DATA / "procesado"

# --------------------------------------------------------------------------------------
# 1. Carga de datos
# --------------------------------------------------------------------------------------
if not (PROC / "mortalidad_2019.csv.gz").exists():
    # Si los archivos procesados no existen, se generan desde los Excel originales
    from scripts.preparar_datos import main as preparar
    preparar()

df = pd.read_csv(PROC / "mortalidad_2019.csv.gz", dtype={"COD_DANE": str, "COD_DEPARTAMENTO": str})
causas = pd.read_csv(PROC / "causas_muerte.csv.gz", dtype=str)
DESC_CAUSA = dict(zip(causas["CODIGO"], causas["DESCRIPCION"]))

with open(DATA / "colombia_departamentos.geojson", encoding="utf-8") as f:
    GEOJSON = json.load(f)

SEXO = {1: "Hombre", 2: "Mujer", 3: "Indeterminado"}
df["SEXO_TXT"] = df["SEXO"].map(SEXO).fillna("Indeterminado")
# Nombres cortos y legibles para los gráficos
NOMBRE_CORTO = {"ARCHIPIÉLAGO DE SAN ANDRÉS, PROVIDENCIA Y SANTA CATALINA": "SAN ANDRÉS Y PROVIDENCIA",
                "BOGOTÁ, D.C.": "BOGOTÁ D.C."}
df["DEPARTAMENTO"] = df["DEPARTAMENTO"].replace(NOMBRE_CORTO)
df["MUNICIPIO"] = df["MUNICIPIO"].replace({"BOGOTÁ, D.C.": "BOGOTÁ D.C."})


def titulo(txt: str) -> str:
    """Convierte a formato título respetando conectores y siglas (p. ej. 'Bogotá D.C.')."""
    menores = {"de", "del", "la", "las", "los", "y", "el", "en"}
    palabras = [p.capitalize() if i == 0 or p.lower() not in menores else p.lower()
                for i, p in enumerate(str(txt).lower().split())]
    return " ".join(palabras).replace("D.c.", "D.C.")


df["DEPTO_TXT"] = df["DEPARTAMENTO"].map(titulo)
df["CIUDAD"] = df["MUNICIPIO"].map(titulo) + " (" + df["DEPTO_TXT"] + ")"

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES_LARGO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
               "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# Agrupación de GRUPO_EDAD1 según la tabla de referencia de la actividad
GRUPOS_EDAD = [
    ("Mortalidad neonatal", range(0, 5), "Menor de 1 mes"),
    ("Mortalidad infantil", range(5, 7), "1 a 11 meses"),
    ("Primera infancia", range(7, 9), "1 a 4 años"),
    ("Niñez", range(9, 11), "5 a 14 años"),
    ("Adolescencia", range(11, 12), "15 a 19 años"),
    ("Juventud", range(12, 14), "20 a 29 años"),
    ("Adultez temprana", range(14, 17), "30 a 44 años"),
    ("Adultez intermedia", range(17, 20), "45 a 59 años"),
    ("Vejez", range(20, 25), "60 a 84 años"),
    ("Longevidad / Centenarios", range(25, 29), "85 a 100+ años"),
    ("Edad desconocida", range(29, 30), "Sin información"),
]
MAPA_EDAD = {cod: cat for cat, rango, _ in GRUPOS_EDAD for cod in rango}
RANGO_EDAD = {cat: txt for cat, _, txt in GRUPOS_EDAD}
ORDEN_EDAD = [g[0] for g in GRUPOS_EDAD]
df["CATEGORIA_EDAD"] = df["GRUPO_EDAD1"].map(MAPA_EDAD).fillna("Edad desconocida")

# Homicidios con arma de fuego: CIE-10 X95 (X950-X959) - agresión con disparo de
# armas de fuego y casos no especificados
df["HOMICIDIO_X95"] = df["COD_MUERTE"].str.startswith("X95")

DEPARTAMENTOS = sorted(df["DEPARTAMENTO"].dropna().unique())

# --------------------------------------------------------------------------------------
# 2. Estilo de gráficos (paleta validada y apta para daltonismo)
# --------------------------------------------------------------------------------------
AZUL, NARANJA, GRIS = "#2a78d6", "#eb6834", "#8a8984"
TINTA, TINTA_2 = "#0b0b0b", "#52514e"
ESCALA_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
COLOR_SEXO = {"Hombre": AZUL, "Mujer": NARANJA, "Indeterminado": GRIS}
FUENTE = "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"


def estilo(fig: go.Figure, alto: int = 420) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=alto, font=dict(family=FUENTE, size=13, color=TINTA_2),
        margin=dict(l=10, r=20, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="white", font=dict(family=FUENTE, color=TINTA), bordercolor="#d8d7d2"),
        separators=",.",
    )
    fig.update_xaxes(gridcolor="#ecebe7", linecolor="#d8d7d2", zeroline=False)
    fig.update_yaxes(gridcolor="#ecebe7", linecolor="#d8d7d2", zeroline=False)
    return fig


def fmt(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def filtrar(depto, sexo):
    d = df
    if depto and depto != "TODOS":
        d = d[d["DEPARTAMENTO"] == depto]
    if sexo and sexo != "TODOS":
        d = d[d["SEXO_TXT"] == sexo]
    return d


# --------------------------------------------------------------------------------------
# 3. Funciones que construyen cada visualización
# --------------------------------------------------------------------------------------
def fig_mapa(d):
    t = d.groupby(["COD_DEPARTAMENTO", "DEPTO_TXT"]).size().reset_index(name="Muertes")
    fig = px.choropleth(
        t, geojson=GEOJSON, locations="COD_DEPARTAMENTO", featureidkey="properties.DPTO_CCDGO",
        color="Muertes", color_continuous_scale=ESCALA_AZUL, hover_name="DEPTO_TXT",
        hover_data={"COD_DEPARTAMENTO": False, "Muertes": ":,"},
    )
    fig.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
    fig.update_traces(marker_line_color="white", marker_line_width=0.8)
    fig.update_layout(coloraxis_colorbar=dict(title="Muertes", thickness=12, len=0.7))
    return estilo(fig, 560)


def fig_lineas(d):
    t = d.groupby("MES").size().reindex(range(1, 13), fill_value=0).reset_index(name="Muertes")
    t["Mes"] = [MESES[m - 1] for m in t["MES"]]
    t["MesLargo"] = [MESES_LARGO[m - 1] for m in t["MES"]]
    fig = go.Figure(go.Scatter(
        x=t["Mes"], y=t["Muertes"], mode="lines+markers", line=dict(color=AZUL, width=2.5),
        marker=dict(size=8, color=AZUL, line=dict(color="white", width=2)),
        customdata=t["MesLargo"], hovertemplate="<b>%{customdata}</b><br>%{y:,} muertes<extra></extra>",
    ))
    mx = t.loc[t["Muertes"].idxmax()]
    mn = t.loc[t["Muertes"].idxmin()]
    for fila, txt in ((mx, "Máximo"), (mn, "Mínimo")):
        fig.add_annotation(x=fila["Mes"], y=fila["Muertes"], text=f"{txt}: {fmt(fila['Muertes'])}",
                           showarrow=False, yshift=16 if txt == "Máximo" else -16,
                           font=dict(size=12, color=TINTA))
    fig.update_layout(hovermode="x unified", yaxis_title="Número de muertes", xaxis_title=None)
    fig.update_yaxes(rangemode="tozero")
    return estilo(fig, 380)


def fig_violentas(d):
    t = (d[d["HOMICIDIO_X95"]].groupby("CIUDAD").size().nlargest(5)
         .reset_index(name="Homicidios").sort_values("Homicidios"))
    fig = px.bar(t, x="Homicidios", y="CIUDAD", orientation="h", text="Homicidios")
    fig.update_traces(marker_color=AZUL, texttemplate="%{text:,}", textposition="outside",
                      cliponaxis=False, hovertemplate="<b>%{y}</b><br>%{x:,} homicidios (X95)<extra></extra>")
    fig.update_layout(yaxis_title=None, xaxis_title="Homicidios por arma de fuego (X95)", bargap=0.35)
    return estilo(fig, 360)


def fig_menor_mortalidad(d):
    t = d.groupby("CIUDAD").size().reset_index(name="Muertes")
    t = t.sort_values(["Muertes", "CIUDAD"]).head(10)
    fig = go.Figure(go.Pie(
        labels=t["CIUDAD"], values=t["Muertes"], hole=0.45, sort=False,
        marker=dict(colors=(ESCALA_AZUL + ["#86b6ef", "#5598e7", "#1c5cab"])[:len(t)],
                    line=dict(color="white", width=2)),
        textinfo="value", hovertemplate="<b>%{label}</b><br>%{value} muerte(s)<extra></extra>",
    ))
    fig.update_layout(legend=dict(font=dict(size=11), orientation="v", x=1.02, y=0.5))
    return estilo(fig, 380)


def tabla_causas(d):
    t = d.groupby("COD_MUERTE").size().nlargest(10).reset_index(name="Total")
    t["Causa"] = t["COD_MUERTE"].map(DESC_CAUSA).fillna("Sin descripción")
    t.insert(0, "#", range(1, len(t) + 1))
    t = t.rename(columns={"COD_MUERTE": "Código CIE-10"})[["#", "Código CIE-10", "Causa", "Total"]]
    t["Total"] = t["Total"].map(fmt)
    return t.to_dict("records")


def fig_sexo(d):
    t = d.groupby(["DEPTO_TXT", "SEXO_TXT"]).size().reset_index(name="Muertes")
    orden = t.groupby("DEPTO_TXT")["Muertes"].sum().sort_values().index.tolist()
    fig = px.bar(t, x="Muertes", y="DEPTO_TXT", color="SEXO_TXT", orientation="h",
                 color_discrete_map=COLOR_SEXO,
                 category_orders={"DEPTO_TXT": orden, "SEXO_TXT": ["Hombre", "Mujer", "Indeterminado"]})
    fig.update_traces(marker_line_color="white", marker_line_width=1,
                      hovertemplate="<b>%{y}</b><br>%{fullData.name}: %{x:,}<extra></extra>")
    fig.update_layout(barmode="stack", yaxis_title=None, xaxis_title="Número de muertes",
                      legend=dict(title=None, orientation="h", y=1.03, x=0, yanchor="bottom"), bargap=0.25)
    return estilo(fig, max(420, 24 * len(orden) + 80))


def fig_edad(d):
    t = d.groupby("CATEGORIA_EDAD").size().reindex(ORDEN_EDAD, fill_value=0).reset_index(name="Muertes")
    t["Rango"] = t["CATEGORIA_EDAD"].map(RANGO_EDAD)
    t["Pct"] = t["Muertes"] / max(t["Muertes"].sum(), 1) * 100
    fig = go.Figure(go.Bar(
        x=t["CATEGORIA_EDAD"], y=t["Muertes"], marker_color=AZUL,
        customdata=t[["Rango", "Pct"]], text=t["Muertes"], texttemplate="%{text:,}", textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{x}</b> (%{customdata[0]})<br>%{y:,} muertes · %{customdata[1]:.1f}%<extra></extra>",
    ))
    fig.update_layout(bargap=0.08, xaxis_title=None, yaxis_title="Número de muertes")
    fig.update_xaxes(tickangle=-30)
    return estilo(fig, 420)


# --------------------------------------------------------------------------------------
# 4. Layout
# --------------------------------------------------------------------------------------
def tarjeta(titulo, subtitulo, contenido, clase=""):
    return html.Div(className=f"card {clase}", children=[
        html.H3(titulo), html.P(subtitulo, className="sub"), contenido])


def kpi(id_, etiqueta):
    return html.Div(className="kpi", children=[html.Div(id=id_, className="kpi-valor"),
                                               html.Div(etiqueta, className="kpi-etq")])


app = Dash(__name__, title="Mortalidad en Colombia 2019")
server = app.server  # usado por gunicorn en el despliegue

app.layout = html.Div(className="contenedor", children=[
    html.Header(children=[
        html.H1("Mortalidad en Colombia · 2019"),
        html.P("Análisis interactivo de las defunciones no fetales registradas por el DANE "
               "(Estadísticas Vitales). Use los filtros para explorar por departamento y sexo."),
    ]),
    html.Div(className="filtros", children=[
        html.Div([html.Label("Departamento"), dcc.Dropdown(
            id="f-depto", value="TODOS", clearable=False,
            options=[{"label": "Todos los departamentos", "value": "TODOS"}] +
                    [{"label": titulo(d), "value": d} for d in DEPARTAMENTOS])]),
        html.Div([html.Label("Sexo"), dcc.RadioItems(
            id="f-sexo", value="TODOS", inline=True, className="radio",
            options=[{"label": "Todos", "value": "TODOS"}, {"label": "Hombres", "value": "Hombre"},
                     {"label": "Mujeres", "value": "Mujer"}])]),
    ]),
    html.Div(className="kpis", children=[
        kpi("k-total", "Muertes registradas"), kpi("k-hom", "Homicidios con arma de fuego (X95)"),
        kpi("k-mes", "Mes con más muertes"), kpi("k-causa", "Principal causa (CIE-10)"),
    ]),
    html.Div(className="grid", children=[
        tarjeta("Distribución de muertes por departamento",
                "Total de defunciones 2019 por departamento. El mapa responde solo al filtro de sexo.",
                dcc.Graph(id="g-mapa", config={"displaylogo": False, "topojsonURL": "/assets/topojson/"}), "ancho"),
        tarjeta("Muertes por mes", "Total de defunciones en cada mes de 2019.",
                dcc.Graph(id="g-lineas", config={"displaylogo": False}), "ancho"),
        tarjeta("Las 5 ciudades más violentas",
                "Municipios con más homicidios por disparo de arma de fuego (CIE-10 X950–X959).",
                dcc.Graph(id="g-violentas", config={"displaylogo": False})),
        tarjeta("Las 10 ciudades con menor mortalidad",
                "Municipios con menos defunciones registradas en 2019 (empates en orden alfabético).",
                dcc.Graph(id="g-menor", config={"displaylogo": False})),
        tarjeta("Las 10 principales causas de muerte",
                "Códigos CIE-10 a cuatro caracteres, ordenados de mayor a menor número de casos.",
                dash_table.DataTable(
                    id="t-causas", columns=[{"name": c, "id": c} for c in ["#", "Código CIE-10", "Causa", "Total"]],
                    style_as_list_view=True, sort_action="native",
                    style_header={"fontWeight": "600", "backgroundColor": "#f4f3ef", "color": TINTA,
                                  "borderBottom": "1px solid #d8d7d2"},
                    style_cell={"fontFamily": FUENTE, "fontSize": 14, "padding": "10px 12px",
                                "textAlign": "left", "whiteSpace": "normal", "height": "auto",
                                "color": TINTA_2, "border": "none", "borderBottom": "1px solid #ecebe7"},
                    style_cell_conditional=[{"if": {"column_id": "Total"}, "textAlign": "right",
                                             "fontVariantNumeric": "tabular-nums", "color": TINTA},
                                            {"if": {"column_id": "#"}, "width": "40px"},
                                            {"if": {"column_id": "Código CIE-10"}, "width": "120px"}],
                ), "ancho"),
        tarjeta("Muertes por sexo en cada departamento",
                "Barras apiladas: hombres, mujeres e indeterminado. Responde solo al filtro de sexo.",
                dcc.Graph(id="g-sexo", config={"displaylogo": False}), "ancho"),
        tarjeta("Distribución de muertes por ciclo de vida",
                "GRUPO_EDAD1 agrupado según la tabla de referencia del DANE. Pase el cursor para ver el rango de edad.",
                dcc.Graph(id="g-edad", config={"displaylogo": False}), "ancho"),
    ]),
    html.Footer("Fuente: DANE – Estadísticas Vitales 2019 (defunciones no fetales), Clasificación CIE-10 y DIVIPOLA. "
                "Mapa: Marco Geoestadístico Nacional (MGN) DANE."),
])


# --------------------------------------------------------------------------------------
# 5. Callbacks (interactividad)
# --------------------------------------------------------------------------------------
@app.callback(
    Output("k-total", "children"), Output("k-hom", "children"), Output("k-mes", "children"),
    Output("k-causa", "children"),
    Output("g-mapa", "figure"), Output("g-lineas", "figure"), Output("g-violentas", "figure"),
    Output("g-menor", "figure"), Output("t-causas", "data"), Output("g-sexo", "figure"),
    Output("g-edad", "figure"),
    Input("f-depto", "value"), Input("f-sexo", "value"),
)
def actualizar(depto, sexo):
    d = filtrar(depto, sexo)
    solo_sexo = filtrar("TODOS", sexo)
    mes = d.groupby("MES").size()
    causa = d["COD_MUERTE"].value_counts()
    return (
        fmt(len(d)),
        fmt(d["HOMICIDIO_X95"].sum()),
        MESES_LARGO[int(mes.idxmax()) - 1] if len(mes) else "–",
        causa.index[0] if len(causa) else "–",
        fig_mapa(solo_sexo), fig_lineas(d), fig_violentas(d), fig_menor_mortalidad(d),
        tabla_causas(d), fig_sexo(solo_sexo), fig_edad(d),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
