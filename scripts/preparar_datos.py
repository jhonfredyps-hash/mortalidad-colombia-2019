"""
Preparación de datos - Mortalidad en Colombia 2019.

Lee los tres archivos originales del DANE (Excel) y genera archivos livianos
en formato CSV comprimido que la aplicación carga en segundos:

    data/procesado/mortalidad_2019.csv.gz   -> una fila por defunción (columnas útiles + nombres)
    data/procesado/causas_muerte.csv.gz     -> catálogo CIE-10 (código y descripción)

Uso:
    python scripts/preparar_datos.py
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
OUT = DATA / "procesado"


def cargar_mortalidad() -> pd.DataFrame:
    cols = ["COD_DANE", "COD_DEPARTAMENTO", "COD_MUNICIPIO", "MES",
            "SEXO", "GRUPO_EDAD1", "MANERA_MUERTE", "COD_MUERTE"]
    df = pd.read_excel(DATA / "NoFetal2019.xlsx", sheet_name=0, dtype=str, usecols=cols)
    df["COD_DANE"] = df["COD_DANE"].str.strip().str.zfill(5)
    df["COD_DEPARTAMENTO"] = df["COD_DEPARTAMENTO"].str.strip().str.zfill(2)
    df["COD_MUERTE"] = df["COD_MUERTE"].str.strip().str.upper()
    for c in ["MES", "SEXO", "GRUPO_EDAD1"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


def cargar_divipola() -> pd.DataFrame:
    dv = pd.read_excel(DATA / "Divipola.xlsx", sheet_name=0, dtype=str)
    dv = dv[["COD_DANE", "COD_DEPARTAMENTO", "DEPARTAMENTO", "MUNICIPIO"]].copy()
    dv["COD_DANE"] = dv["COD_DANE"].str.strip().str.zfill(5)
    dv["COD_DEPARTAMENTO"] = dv["COD_DEPARTAMENTO"].str.strip().str.zfill(2)
    dv["DEPARTAMENTO"] = dv["DEPARTAMENTO"].str.strip()
    dv["MUNICIPIO"] = dv["MUNICIPIO"].str.strip()
    return dv.drop_duplicates("COD_DANE")


def cargar_causas() -> pd.DataFrame:
    raw = pd.read_excel(DATA / "CodigosDeMuerte.xlsx", sheet_name=0, header=None, dtype=str)
    # La fila de encabezado es la que contiene "Capítulo" en la primera columna
    fila = raw.index[raw[0].astype(str).str.strip().str.startswith("Cap")][0]
    raw = raw.iloc[fila + 1:, :6]
    raw.columns = ["CAPITULO", "NOMBRE_CAPITULO", "COD3", "DESC3", "COD4", "DESC4"]
    raw = raw.dropna(subset=["COD3"])
    for c in raw.columns:
        raw[c] = raw[c].astype(str).str.strip()
    c4 = raw[["COD4", "DESC4"]].rename(columns={"COD4": "CODIGO", "DESC4": "DESCRIPCION"})
    c3 = raw[["COD3", "DESC3"]].rename(columns={"COD3": "CODIGO", "DESC3": "DESCRIPCION"})
    cat = pd.concat([c4, c3]).drop_duplicates("CODIGO")
    cat["CODIGO"] = cat["CODIGO"].str.upper()
    return cat


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Leyendo NoFetal2019.xlsx (puede tardar ~1 minuto)...")
    df = cargar_mortalidad()
    dv = cargar_divipola()
    causas = cargar_causas()

    df = df.merge(dv[["COD_DANE", "MUNICIPIO"]], on="COD_DANE", how="left")
    deptos = dv[["COD_DEPARTAMENTO", "DEPARTAMENTO"]].drop_duplicates("COD_DEPARTAMENTO")
    df = df.merge(deptos, on="COD_DEPARTAMENTO", how="left")
    df.drop(columns=["COD_MUNICIPIO"], inplace=True)

    sin_mpio = df["MUNICIPIO"].isna().sum()
    print(f"Registros: {len(df):,} | sin municipio en Divipola: {sin_mpio:,}")

    df.to_csv(OUT / "mortalidad_2019.csv.gz", index=False, compression="gzip")
    causas.to_csv(OUT / "causas_muerte.csv.gz", index=False, compression="gzip")
    print("Archivos generados en", OUT)


if __name__ == "__main__":
    main()
