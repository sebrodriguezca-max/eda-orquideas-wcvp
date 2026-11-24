"""
Análisis Exploratorio de Datos (EDA) - Familia Orchidaceae (WCVP / Kew)
Autor: Flujo reproducible sobre Orquideas.zip
"""

import os
import zipfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ==============================================================================
# 0. CONFIGURACIÓN GENERAL Y CARGA DIRECTA DESDE ZIP
# ==============================================================================
ZIP_PATH = "Orquideas.zip"
OUT_DIR = "figuras_eda"
os.makedirs(OUT_DIR, exist_ok=True)

sns.set_theme(style="whitegrid", context="notebook", font_scale=1.05)
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 300

if not os.path.exists(ZIP_PATH):
    raise FileNotFoundError(
        f"No se encontró '{ZIP_PATH}' en el directorio actual: {os.getcwd()}. "
        "Coloca Orquideas.zip junto al script o ajusta ZIP_PATH."
    )

with zipfile.ZipFile(ZIP_PATH, "r") as zf:
    print("Archivos dentro del ZIP:", zf.namelist())

    # Verificar hojas de metadatos en README_WCVP.xlsx
    with zf.open("README_WCVP.xlsx") as f_readme:
        hojas_readme = pd.ExcelFile(f_readme).sheet_names
        print("Hojas en README_WCVP.xlsx:", hojas_readme)

    # Evidencia del problema de delimitador: en crudo usan '|' y no ','
    with zf.open("wcvp_names.csv") as f_sample:
        primera_linea = f_sample.readline().decode("utf-8", errors="replace").strip()
        print("Muestra cabecera cruda (120 chars):", primera_linea[:120])

    # Carga completa con separador pipe '|'
    with zf.open("wcvp_names.csv") as f_names:
        df_names_all = pd.read_csv(f_names, sep="|", low_memory=False)

    with zf.open("wcvp_distribution.csv") as f_dist:
        df_dist_all = pd.read_csv(f_dist, sep="|", low_memory=False)

print(f"\nWCVP completo -> Nombres: {df_names_all.shape}, Distribución: {df_dist_all.shape}")

# Filtrado inicial a la familia Orchidaceae
df_names_raw = df_names_all[df_names_all["family"].astype(str).str.strip() == "Orchidaceae"].copy()
orchid_ids = set(df_names_raw["plant_name_id"].dropna())
df_dist_raw = df_dist_all[df_dist_all["plant_name_id"].isin(orchid_ids)].copy()

# Liberar tablas globales para ahorrar RAM
del df_names_all, df_dist_all

print(f"Orchidaceae CRUDO -> Nombres: {df_names_raw.shape}, Distribución: {df_dist_raw.shape}")


# ==============================================================================
# 1. DIAGNÓSTICO DE CALIDAD CON PANDAS
# ==============================================================================
def diagnosticar_df(df: pd.DataFrame, nombre: str) -> pd.DataFrame:
    print(f"\n{'='*75}")
    print(f"DIAGNÓSTICO: {nombre} ({df.shape[0]:,} filas x {df.shape[1]} columnas)")
    print(f"{'='*75}")
    print("Duplicados exactos de fila:", int(df.duplicated().sum()))

    resumen = pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "nulos": df.isna().sum(),
        "pct_nulos": (df.isna().mean() * 100).round(2),
        "unicos": df.nunique(dropna=True)
    })
    print("\nColumnas con valores faltantes (ordenadas por % faltante):")
    print(resumen[resumen["nulos"] > 0].sort_values("pct_nulos", ascending=False).to_string())
    return resumen


diagnosticar_df(df_names_raw, "wcvp_names (Orchidaceae)")
diagnosticar_df(df_dist_raw, "wcvp_distribution (Orchidaceae)")

print("\n--- Inspección de categorías y anomalías antes de limpiar ---")
print("taxon_status:\n", df_names_raw["taxon_status"].value_counts(dropna=False).to_string())
print("\nTop 12 lifeform_description crudos:\n", df_names_raw["lifeform_description"].value_counts(dropna=False).head(12).to_string())
print("\nTop 12 climate_description crudos:\n", df_names_raw["climate_description"].value_counts(dropna=False).head(12).to_string())


# ==============================================================================
# 2. LIMPIEZA, CONVERSIÓN DE TIPOS Y VARIABLES DERIVADAS
# ==============================================================================
df_names = df_names_raw.copy()
df_dist = df_dist_raw.copy()

# Normalizar nombres de columnas
df_names.columns = [c.strip().lower().replace(" ", "_") for c in df_names.columns]
df_dist.columns = [c.strip().lower().replace(" ", "_") for c in df_dist.columns]

# Eliminar duplicados exactos y duplicados por clave primaria
n_dup_names_exact = int(df_names.duplicated().sum())
n_dup_names_id = int(df_names.duplicated(subset=["plant_name_id"]).sum())
df_names = df_names.drop_duplicates().drop_duplicates(subset=["plant_name_id"])

n_dup_dist_exact = int(df_dist.duplicated().sum())
n_dup_dist_id = int(df_dist.duplicated(subset=["plant_locality_id"]).sum())
df_dist = df_dist.drop_duplicates().drop_duplicates(subset=["plant_locality_id"])

print(f"\nDuplicados removidos en names (exactos/id): {n_dup_names_exact} / {n_dup_names_id}")
print(f"Duplicados removidos en dist  (exactos/id): {n_dup_dist_exact} / {n_dup_dist_id}")

# Extraer año de first_published y validar rango botánico [1753, 2026]
anio_str = df_names["first_published"].astype(str).str.extract(r"\((\d{4})")[0]
df_names["publication_year"] = pd.to_numeric(anio_str, errors="coerce").astype("Int64")

mask_imposible = (
    df_names["publication_year"].notna() &
    ((df_names["publication_year"] < 1753) | (df_names["publication_year"] > 2026))
)
print(f"Años de publicación imposibles (<1753 o >2026) convertidos a NA: {int(mask_imposible.sum())}")
df_names.loc[mask_imposible, "publication_year"] = pd.NA
df_names["publication_decade"] = (df_names["publication_year"] // 10) * 10

# Normalizar cadenas textuales relevantes
for col in ["taxon_status", "taxon_rank", "genus", "lifeform_description", "climate_description"]:
    df_names[col] = df_names[col].astype("string").str.strip()


def clasificar_habito(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return "No registrado"
    v = str(val).lower()
    es_epi = "epiphyte" in v
    es_ter = any(k in v for k in [
        "terrestrial", "geophyte", "hemicryptophyte", "therophyte",
        "chamaephyte", "helophyte", "hydrophyte", "mycotrophic"
    ])
    es_lit = "lithophyte" in v
    n_tipos = int(es_epi) + int(es_ter) + int(es_lit)
    if n_tipos > 1:
        return "Mixta / Facultativa"
    if es_epi:
        return "Epífita"
    if es_ter:
        return "Terrestre / Geófita"
    if es_lit:
        return "Litófita"
    return "Otras formas"


def clasificar_clima(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return "No registrado"
    v = str(val).lower()
    if "wet tropical" in v:
        return "Tropical húmedo"
    if "seasonally dry tropical" in v:
        return "Tropical estacional seco"
    if "subtropical" in v:
        return "Subtropical"
    if any(k in v for k in ["temperate", "subarctic", "alpine"]):
        return "Templado / Alpino"
    if any(k in v for k in ["desert", "dry shrubland"]):
        return "Árido / Matorral seco"
    return "Otros climas"


df_names["habit_group"] = df_names["lifeform_description"].apply(clasificar_habito)
df_names["climate_group"] = df_names["climate_description"].apply(clasificar_clima)

# Limpieza de distribución y exclusión de localidades dudosas
for flag in ["introduced", "extinct", "location_doubtful"]:
    df_dist[flag] = pd.to_numeric(df_dist[flag], errors="coerce").fillna(0).astype(int)

for col in ["continent", "region", "area", "area_code_l3"]:
    df_dist[col] = df_dist[col].astype("string").str.strip()

n_doubtful = int((df_dist["location_doubtful"] == 1).sum())
print(f"Registros de distribución con location_doubtful == 1 excluidos: {n_doubtful:,}")
df_dist_clean = df_dist[df_dist["location_doubtful"] == 0].copy()

# Agregación a nivel de taxón (1 fila por plant_name_id) para evitar duplicación 1-a-N
dist_nativa = df_dist_clean[df_dist_clean["introduced"] == 0]
areas_nativas_por_id = dist_nativa.groupby("plant_name_id")["area_code_l3"].nunique()
continentes_por_id = dist_nativa.groupby("plant_name_id")["continent"].nunique()
areas_totales_por_id = df_dist_clean.groupby("plant_name_id")["area_code_l3"].nunique()
introducidas_por_id = df_dist_clean.groupby("plant_name_id")["introduced"].sum()
extintas_por_id = df_dist_clean.groupby("plant_name_id")["extinct"].sum()

continente_principal = (
    dist_nativa.dropna(subset=["continent"])
    .groupby("plant_name_id")["continent"]
    .agg(lambda s: s.mode().iloc[0] if len(s.mode()) > 0 else pd.NA)
)

df_taxa = df_names.copy()
df_taxa["native_areas"] = df_taxa["plant_name_id"].map(areas_nativas_por_id).fillna(0).astype(int)
df_taxa["total_areas_tdwg"] = df_taxa["plant_name_id"].map(areas_totales_por_id).fillna(0).astype(int)
df_taxa["introduced_areas"] = df_taxa["plant_name_id"].map(introducidas_por_id).fillna(0).astype(int)
df_taxa["extinct_areas"] = df_taxa["plant_name_id"].map(extintas_por_id).fillna(0).astype(int)
df_taxa["n_continents"] = df_taxa["plant_name_id"].map(continentes_por_id).fillna(0).astype(int)
df_taxa["primary_continent"] = df_taxa["plant_name_id"].map(continente_principal)

df_taxa["endemism_type"] = np.where(
    df_taxa["native_areas"] == 1, "Endémica (1 área)",
    np.where(df_taxa["native_areas"] > 1, "No endémica (>1 área)", "Sin distribución nativa")
)

# Subconjunto analítico: especies aceptadas
df_accepted_sp = df_taxa[
    (df_taxa["taxon_status"] == "Accepted") &
    (df_taxa["taxon_rank"] == "Species")
].copy()

print("\n--- DIMENSIONES ANTES Y DESPUÉS DE LA LIMPIEZA ---")
print(f"wcvp_names crudo (Orchidaceae):        {df_names_raw.shape[0]:>8,} filas x {df_names_raw.shape[1]} cols")
print(f"df_taxa limpio (todos los taxones):    {df_taxa.shape[0]:>8,} filas x {df_taxa.shape[1]} cols")
print(f"df_accepted_sp (especies aceptadas):  {df_accepted_sp.shape[0]:>8,} filas x {df_accepted_sp.shape[1]} cols")
print(f"wcvp_distribution crudo (Orchidaceae): {df_dist_raw.shape[0]:>8,} filas x {df_dist_raw.shape[1]} cols")
print(f"df_dist_clean (localidades válidas):   {df_dist_clean.shape[0]:>8,} filas x {df_dist_clean.shape[1]} cols")


# ==============================================================================
# 3. ESTADÍSTICOS DESCRIPTIVOS, ATÍPICOS Y RELACIONES
# ==============================================================================
print(f"\n{'='*75}")
print("ESTADÍSTICOS DESCRIPTIVOS - ESPECIES ACEPTADAS")
print(f"{'='*75}")

num_cols = ["publication_year", "native_areas", "total_areas_tdwg", "introduced_areas", "n_continents"]
desc_num = pd.DataFrame({
    "n": df_accepted_sp[num_cols].count(),
    "media": df_accepted_sp[num_cols].mean().round(2),
    "sd": df_accepted_sp[num_cols].std().round(2),
    "min": df_accepted_sp[num_cols].min(),
    "q25": df_accepted_sp[num_cols].quantile(0.25).round(2),
    "mediana": df_accepted_sp[num_cols].median().round(2),
    "q75": df_accepted_sp[num_cols].quantile(0.75).round(2),
    "IQR": (df_accepted_sp[num_cols].quantile(0.75) - df_accepted_sp[num_cols].quantile(0.25)).round(2),
    "max": df_accepted_sp[num_cols].max(),
    "asimetria": df_accepted_sp[num_cols].astype(float).skew().round(2),
    "curtosis": df_accepted_sp[num_cols].astype(float).kurt().round(2),
})
print("\nVariables numéricas:\n", desc_num.to_string())

for cat_col in ["habit_group", "climate_group", "endemism_type", "primary_continent"]:
    vc = df_accepted_sp[cat_col].fillna("No registrado").value_counts()
    pct = (vc / len(df_accepted_sp) * 100).round(2)
    print(f"\nVariable categórica '{cat_col}':\n", pd.DataFrame({"n": vc, "pct": pct}).to_string())

# Valores atípicos en native_areas (regla de Tukey)
q1 = df_accepted_sp["native_areas"].quantile(0.25)
q3 = df_accepted_sp["native_areas"].quantile(0.75)
iqr = q3 - q1
lim_sup = q3 + 1.5 * iqr
outliers = df_accepted_sp[df_accepted_sp["native_areas"] > lim_sup].sort_values("native_areas", ascending=False)

print(f"\nAtípicos en native_areas (umbral Tukey > {lim_sup:.1f}): {len(outliers):,} especies "
      f"({len(outliers)/len(df_accepted_sp)*100:.2f} %)")
print("Top 10 especies de mayor amplitud geográfica nativa:")
cols_show = [c for c in ["taxon_name", "habit_group", "climate_group", "publication_year", "native_areas", "n_continents"] if c in outliers.columns]
print(outliers[cols_show].head(10).to_string(index=False))

# Correlación de Spearman
print("\nMatriz de correlación de Spearman (variables numéricas):\n",
      df_accepted_sp[num_cols].astype(float).corr(method="spearman").round(3).to_string())

# Comparación de native_areas entre hábitos
comp_hab = (
    df_accepted_sp.groupby("habit_group")["native_areas"]
    .agg(
        n="count",
        media="mean",
        mediana="median",
        iqr=lambda s: s.quantile(0.75) - s.quantile(0.25),
        pct_endemicas=lambda s: (s == 1).mean() * 100
    )
    .round(2)
    .sort_values("n", ascending=False)
)
print("\nAmplitud geográfica nativa por hábito:\n", comp_hab.to_string())

# Asociación entre hábito y clima (excluyendo 'No registrado')
df_eco_valid = df_accepted_sp[
    (df_accepted_sp["habit_group"] != "No registrado") &
    (df_accepted_sp["climate_group"] != "No registrado")
].copy()

ct_eco = pd.crosstab(df_eco_valid["habit_group"], df_eco_valid["climate_group"])
esp_eco = np.outer(ct_eco.sum(axis=1), ct_eco.sum(axis=0)) / ct_eco.values.sum()
chi2_eco = (((ct_eco.values - esp_eco) ** 2) / esp_eco).sum()
n_eco = ct_eco.values.sum()
v_cramer = np.sqrt(chi2_eco / (n_eco * (min(ct_eco.shape) - 1)))
print(f"\nAsociación Hábito x Clima (n = {n_eco:,}): chi2 = {chi2_eco:,.1f}, V de Cramér = {v_cramer:.3f}")


# ==============================================================================
# 4. GENERACIÓN DE LAS 6 FIGURAS
# ==============================================================================
print(f"\nGenerando figuras en '{OUT_DIR}/'...")

# --- FIGURA 1: Distribución (Histograma log10 + ECDF) ---
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
valid_native = df_accepted_sp[df_accepted_sp["native_areas"] >= 1]["native_areas"]
bins_log = np.logspace(0, np.log10(valid_native.max()), 22)

sns.histplot(valid_native, bins=bins_log, ax=axes[0], color="#2b5c8f", edgecolor="white", alpha=0.88)
axes[0].set_xscale("log")
axes[0].set_xticks([1, 2, 5, 10, 20, 50])
axes[0].get_xaxis().set_major_formatter(plt.ScalarFormatter())
axes[0].axvline(valid_native.median(), color="#d95f02", linestyle="--", linewidth=1.8,
                label=f"Mediana = {valid_native.median():.0f} área")
axes[0].set_title("A. Frecuencia de amplitud geográfica nativa", fontweight="bold")
axes[0].set_xlabel("Número de áreas botánicas TDWG Nivel 3 (escala log10)")
axes[0].set_ylabel("Número de especies aceptadas")
axes[0].legend(frameon=True)

sns.ecdfplot(valid_native, ax=axes[1], color="#1b9e77", linewidth=2.4)
axes[1].set_xscale("log")
axes[1].set_xticks([1, 2, 5, 10, 20, 50])
axes[1].get_xaxis().set_major_formatter(plt.ScalarFormatter())
pct_endem = (valid_native == 1).mean() * 100
axes[1].axhline(pct_endem / 100, color="#d95f02", linestyle=":", linewidth=1.5)
axes[1].annotate(f"{pct_endem:.1f} % endémicas\n(1 área TDWG)",
                 xy=(1, pct_endem / 100), xytext=(2.2, 0.52),
                 arrowprops=dict(arrowstyle="->", color="#d95f02"),
                 fontweight="bold", color="#d95f02")
axes[1].set_title("B. Distribución acumulada empírica (ECDF)", fontweight="bold")
axes[1].set_xlabel("Número de áreas botánicas TDWG Nivel 3 (escala log10)")
axes[1].set_ylabel("Proporción acumulada de especies")

plt.suptitle("Distribución del rango geográfico nativo en especies aceptadas de Orchidaceae",
             fontsize=13, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "fig1_distribucion_rango_geografico.png"), bbox_inches="tight")
plt.close()

# --- FIGURA 2: Comparación entre grupos (Top 15 regiones TDWG) ---
endem_map = df_accepted_sp.set_index("plant_name_id")["endemism_type"]
dist_nat_acc = df_dist_clean[
    (df_dist_clean["introduced"] == 0) &
    (df_dist_clean["plant_name_id"].isin(endem_map.index)) &
    (df_dist_clean["region"].notna())
].copy()
dist_nat_acc["es_endemica"] = dist_nat_acc["plant_name_id"].map(endem_map) == "Endémica (1 área)"

sp_region = (
    dist_nat_acc.groupby("region", as_index=False)
    .agg(
        especies_nativas=("plant_name_id", "nunique"),
        especies_endemicas=("plant_name_id", lambda s: s[dist_nat_acc.loc[s.index, "es_endemica"]].nunique())
    )
    .sort_values("especies_nativas", ascending=False)
    .head(15)
)

fig, ax = plt.subplots(figsize=(11, 6.5))
sns.barplot(data=sp_region, y="region", x="especies_nativas", color="#386cb0",
            label="Total especies nativas", ax=ax)
sns.barplot(data=sp_region, y="region", x="especies_endemicas", color="#f0027f",
            alpha=0.85, label="Endémicas estrictas (1 área)", ax=ax)

for idx, row in sp_region.reset_index(drop=True).iterrows():
    ax.text(row["especies_nativas"] + 120, idx, f"{row['especies_nativas']:,}", va="center", fontsize=9)

ax.set_xlim(0, sp_region["especies_nativas"].max() * 1.15)
ax.set_title("Top 15 regiones botánicas TDWG por riqueza nativa y endemismo de Orchidaceae", fontweight="bold")
ax.set_xlabel("Número de especies aceptadas (conteo desde cero)")
ax.set_ylabel("Región botánica (TDWG Nivel 2)")
ax.legend(loc="lower right", frameon=True)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "fig2_riqueza_regiones_tdwg.png"), bbox_inches="tight")
plt.close()

# --- FIGURA 3: Relación entre dos numéricas (Dispersión + jitter + tendencia decadal) ---
df_rel = df_accepted_sp.dropna(subset=["publication_year"]).copy()
df_rel = df_rel[df_rel["native_areas"] >= 1]
rng = np.random.default_rng(42)
df_rel["native_areas_jitter"] = df_rel["native_areas"] * np.exp(rng.normal(0, 0.08, size=len(df_rel)))

fig, ax = plt.subplots(figsize=(10.5, 6))
ax.scatter(
    df_rel["publication_year"].astype(float),
    df_rel["native_areas_jitter"],
    alpha=0.08, s=12, color="#2c7fb8", rasterized=True, label="Especies individuales (con jitter)"
)

dec_summary = (
    df_rel.groupby("publication_decade", as_index=False)["native_areas"]
    .agg(mediana="median", q25=lambda s: s.quantile(0.25), q75=lambda s: s.quantile(0.75), n="count")
)
dec_summary = dec_summary[dec_summary["n"] >= 30]

ax.plot(dec_summary["publication_decade"] + 5, dec_summary["mediana"],
        color="#d95f02", linewidth=2.5, marker="o", label="Mediana decadal")
ax.fill_between(dec_summary["publication_decade"] + 5, dec_summary["q25"], dec_summary["q75"],
                color="#d95f02", alpha=0.22, label="Rango intercuartílico (Q25–Q75)")

ax.set_yscale("log")
ax.set_yticks([1, 2, 5, 10, 20, 50])
ax.get_yaxis().set_major_formatter(plt.ScalarFormatter())
ax.set_title("Relación entre año de descripción taxonómica y amplitud geográfica nativa", fontweight="bold")
ax.set_xlabel("Año de primera publicación científica (1753–2026)")
ax.set_ylabel("Áreas botánicas TDWG nativas (escala log10)")
ax.legend(loc="upper right", frameon=True)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "fig3_relacion_anio_rango.png"), bbox_inches="tight")
plt.close()

# --- FIGURA 4: Evolución en el tiempo (Serie anual + promedio móvil + acumulado) ---
yearly = (
    df_rel[df_rel["publication_year"] <= 2026]
    .groupby("publication_year", as_index=False)
    .size()
    .rename(columns={"size": "nuevas_especies"})
    .sort_values("publication_year")
)
full_years = pd.DataFrame({"publication_year": range(1753, 2027)})
yearly = full_years.merge(yearly, on="publication_year", how="left").fillna({"nuevas_especies": 0})
yearly["media_movil_10a"] = yearly["nuevas_especies"].rolling(10, center=True, min_periods=1).mean()
yearly["acumulado"] = yearly["nuevas_especies"].cumsum()

fig, ax1 = plt.subplots(figsize=(11.5, 5.5))
ax1.plot(yearly["publication_year"], yearly["nuevas_especies"],
         color="#9ecae1", linewidth=1.0, alpha=0.85, label="Descripciones anuales")
ax1.plot(yearly["publication_year"], yearly["media_movil_10a"],
         color="#08519c", linewidth=2.3, label="Promedio móvil (10 años)")
ax1.axvspan(1914, 1918, color="#bdbdbd", alpha=0.35, label="Guerras Mundiales (1914–18 / 1939–45)")
ax1.axvspan(1939, 1945, color="#bdbdbd", alpha=0.35)

ax1.set_xlabel("Año de publicación (1753–2026)")
ax1.set_ylabel("Especies aceptadas descritas por año", color="#08519c")
ax1.tick_params(axis="y", labelcolor="#08519c")

ax2 = ax1.twinx()
ax2.plot(yearly["publication_year"], yearly["acumulado"],
         color="#d95f02", linestyle="--", linewidth=2.0, label="Riqueza acumulada")
ax2.set_ylabel("Especies aceptadas acumuladas", color="#d95f02")
ax2.tick_params(axis="y", labelcolor="#d95f02")
ax2.grid(False)

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", frameon=True)
ax1.set_title("Evolución histórica de la descripción de especies aceptadas de Orchidaceae (1753–2026)",
              fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "fig4_evolucion_temporal_descripciones.png"), bbox_inches="tight")
plt.close()

# --- FIGURA 5: Heatmap divergente centrado en cero (Residuos Hábito x Clima) ---
ct = ct_eco.loc[ct_eco.sum(axis=1).sort_values(ascending=False).index,
                ct_eco.sum(axis=0).sort_values(ascending=False).index]
expected = np.outer(ct.sum(axis=1), ct.sum(axis=0)) / ct.values.sum()
std_residuals = pd.DataFrame((ct.values - expected) / np.sqrt(expected), index=ct.index, columns=ct.columns)
annot_matrix = std_residuals.round(1).astype(str) + "\n(n=" + ct.astype(str) + ")"

fig, ax = plt.subplots(figsize=(10.5, 5.8))
vmax = float(np.abs(std_residuals.values).max())
sns.heatmap(
    std_residuals, annot=annot_matrix, fmt="", cmap="RdBu_r", center=0,
    vmin=-vmax, vmax=vmax,
    cbar_kws={"label": "Residuo estandarizado de Pearson"},
    linewidths=0.8, ax=ax
)
ax.set_title("Asociación ecológica entre hábito de crecimiento y zona climática en Orchidaceae", fontweight="bold")
ax.set_xlabel("Zona climática (WCVP)")
ax.set_ylabel("Hábito de crecimiento agrupado")
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "fig5_heatmap_habito_clima.png"), bbox_inches="tight")
plt.close()

# --- FIGURA 6: Composición 100 % en pequeños múltiplos (Endemismo x Continente) ---
df_facet = df_accepted_sp[
    (df_accepted_sp["habit_group"] != "No registrado") &
    (df_accepted_sp["endemism_type"].isin(["Endémica (1 área)", "No endémica (>1 área)"])) &
    (df_accepted_sp["primary_continent"].notna())
].copy()

top_conts = df_facet["primary_continent"].value_counts().head(6).index
df_facet = df_facet[df_facet["primary_continent"].isin(top_conts)]

prop_df = (
    df_facet.groupby(["endemism_type", "primary_continent", "habit_group"])
    .size()
    .unstack(fill_value=0)
)
prop_pct = prop_df.div(prop_df.sum(axis=1), axis=0) * 100

fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharey=True)
hab_order = [h for h in ["Epífita", "Terrestre / Geófita", "Litófita", "Mixta / Facultativa", "Otras formas"]
             if h in prop_pct.columns]
colors = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e"]

for ax, endem_cat in zip(axes, ["Endémica (1 área)", "No endémica (>1 área)"]):
    sub = prop_pct.loc[endem_cat].reindex(top_conts)[hab_order]
    sub.plot(kind="barh", stacked=True, ax=ax, color=colors[:len(hab_order)], edgecolor="white", legend=False)
    ax.set_title(endem_cat, fontweight="bold")
    ax.set_xlabel("Composición porcentual (%)")
    ax.set_xlim(0, 100)
    ax.set_ylabel("Continente botánico (TDWG Nivel 1)" if ax == axes[0] else "")

handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.07), ncol=len(hab_order), frameon=True)
plt.suptitle("Composición de hábitos de crecimiento (100 %) por continente y condición de endemismo",
             fontweight="bold", y=1.13)
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "fig6_facetas_composicion_habitos.png"), bbox_inches="tight")
plt.close()

print(f"\n¡Listo! Revisa las tablas impresas arriba y las 6 imágenes en '{OUT_DIR}/'.")