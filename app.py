import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import statsmodels.api as sm

# ==========================================================
# CONFIGURACIÓN DE PÁGINA Y DISEÑO GENERAL
# ==========================================================
st.set_page_config(
    page_title="Dynamic Pricing & Elasticity Analyzer",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados para tarjetas financieras y espaciado
st.markdown("""
<style>
    .kpi-container {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        border-left: 5px solid #007bff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .metric-label {
        font-size: 0.9rem;
        color: #6c757d;
        font-weight: bold;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: bold;
        color: #212529;
    }
</style>
""", unsafe_allow_html=True)

# Variables de configuración interna
MIN_OBSERVACIONES = 5
MIN_PRECIOS_DISTINTOS = 2
ELASTICIDAD_MIN_RAZONABLE = -5.0

ESCENARIOS_CAMBIO_PRECIO = [-0.15, -0.10, -0.05, 0.00, 0.05, 0.10, 0.15]
ESCENARIOS_PROMOCION = [
    {"Escenario_ID": "promo_2x1", "Nombre_Escenario": "Promoción 2x1", "Tipo_Escenario": "Promoción", "Cambio_Efectivo": -0.50, "Mecanica_Promocion": "2x1"},
    {"Escenario_ID": "promo_3x2", "Nombre_Escenario": "Promoción 3x2", "Tipo_Escenario": "Promoción", "Cambio_Efectivo": -0.3333, "Mecanica_Promocion": "3x2"},
    {"Escenario_ID": "promo_2do_50", "Nombre_Escenario": "Promoción 2do a 50%", "Tipo_Escenario": "Promoción", "Cambio_Efectivo": -0.25, "Mecanica_Promocion": "2do a 50%"},
]

ESCENARIOS_PRICING = pd.DataFrame(
    [{"Escenario_ID": f"precio_{int(round(c * 100)):+d}pct", "Nombre_Escenario": f"Cambio de precio {c * 100:+.0f}%", "Tipo_Escenario": "Cambio de precio", "Cambio_Efectivo": c, "Mecanica_Promocion": "No aplica"} for c in ESCENARIOS_CAMBIO_PRECIO] + ESCENARIOS_PROMOCION
)

# Initialize Session State for Custom SKUs
if "custom_skus" not in st.session_state:
    st.session_state.custom_skus = pd.DataFrame(columns=["SKU", "Precio_Base", "Costo_Unitario_Base", "Unidades_Base", "Elasticidad", "Diagnostico"])

# ==========================================================
# SIDEBAR - CARGA DE DATOS Y MENÚ PRINCIPAL
# ==========================================================
st.sidebar.title("🛠️ Configuración Core")
archivo_cargado = st.sidebar.file_uploader("1. Sube tu archivo de ventas (CSV o Excel):", type=["csv", "xlsx"])
archivo_promos = st.sidebar.file_uploader("2. Opcional: Sube tu archivo de promociones:", type=["csv", "xlsx"])

opciones_menu = [
    "📌 Introducción y Calidad", 
    "📈 Dashboard de Elasticidad", 
    "💰 Dashboard de Pricing & Simulación"
]
menu_sel = st.sidebar.radio("Navegar por las Secciones:", opciones_menu)

# ==========================================================
# FUNCIONES DATA PIPELINE 
# ==========================================================
@st.cache_data
def cargar_y_limpiar_datos(file):
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    
    df.columns = df.columns.str.strip()
    filas_originales = len(df)
    
    cols_req = ["tran_date", "qty", "net_sale", "prod_nbr", "costo2"]
    for c in cols_req:
        if c not in df.columns:
            if c == "costo2" and "costo" in df.columns:
                df["costo2"] = df["costo"]
            else:
                st.error(f"❌ La columna requerida '{c}' no está presente en el archivo.")
                return None, None
    
    if "dept_nm" not in df.columns:
        df["dept_nm"] = "General"
        
    df = df.drop_duplicates().copy()
    df["tran_date"] = pd.to_datetime(df["tran_date"], errors="coerce")
    
    for col in ["qty", "net_sale", "prod_nbr", "costo2"]:
        df[col] = df[col].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False).str.strip()
        df[col] = pd.to_numeric(df[col], errors="coerce")
        
    df = df.dropna(subset=["tran_date", "qty", "net_sale", "prod_nbr"]).copy()
    df = df[(df["qty"] > 0) & (df["net_sale"] >= 0)]
    
    df["precio_unitario"] = df["net_sale"] / df["qty"]
    df["costo_unitario"] = df["costo2"]
    df["periodo_mensual"] = df["tran_date"].dt.to_period("M").astype(str)
    
    resumen_calidad = {
        "Filas Iniciales": filas_originales,
        "Filas Limpias": len(df),
        "Removidos": filas_originales - len(df),
        "% Pérdida": round(((filas_originales - len(df)) / filas_originales) * 100, 2) if filas_originales > 0 else 0
    }
    
    return df, resumen_calidad

@st.cache_data
def cargar_promociones(file):
    if file is None:
        return None
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    
    # Estandarización básica según Notebook
    for col in ["Fecha_Inicio", "Fecha_Fin", "SKU"]:
        if col in df.columns:
            if "Fecha" in col:
                df[col] = pd.to_datetime(df[col], errors="coerce")
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    if "Porcentaje" in df.columns:
        df["Porcentaje"] = pd.to_numeric(df["Porcentaje"], errors="coerce").fillna(0)
    else:
        df["Porcentaje"] = 0.0
    return df.dropna(subset=["Fecha_Inicio", "Fecha_Fin", "SKU"])

@st.cache_data
def procesar_modelos_y_simulacion(df_limpio, df_promos=None):
    # Cruzar promociones con ventas si existe el archivo
    if df_promos is not None:
        df_limpio = df_limpio.copy()
        df_limpio["promo_activa"] = 0
        df_limpio["porcentaje_promo"] = 0.0
        
        # Mapeo rápido de rango de fechas promocionales por SKU
        for _, promo in df_promos.iterrows():
            mask = (df_limpio["prod_nbr"] == promo["SKU"]) & \
                   (df_limpio["tran_date"] >= promo["Fecha_Inicio"]) & \
                   (df_limpio["tran_date"] <= promo["Fecha_Fin"])
            df_limpio.loc[mask, "promo_activa"] = 1
            if "Porcentaje" in promo:
                df_limpio.loc[mask, "porcentaje_promo"] = promo["Porcentaje"]

    resultados_elasticidad = []
    for sku, datos_sku in df_limpio.groupby("prod_nbr"):
        n_obs = len(datos_sku)
        n_precios = datos_sku["precio_unitario"].nunique()
        
        if n_obs < MIN_OBSERVACIONES or n_precios < MIN_PRECIOS_DISTINTOS:
            resultados_elasticidad.append({"SKU": sku, "Beta": np.nan, "Elasticidad": np.nan, "R2": np.nan, "P_Value": np.nan, "Diagnostico": "Datos insuficientes"})
            continue
            
        d_log = datos_sku.copy()
        d_log["log_qty"] = np.log(d_log["qty"])
        d_log["log_precio"] = np.log(d_log["precio_unitario"])
        d_log = d_log.replace([np.inf, -np.inf], np.nan).dropna(subset=["log_qty", "log_precio"])
        
        if d_log["log_precio"].nunique() < MIN_PRECIOS_DISTINTOS:
            resultados_elasticidad.append({"SKU": sku, "Beta": np.nan, "Elasticidad": np.nan, "R2": np.nan, "P_Value": np.nan, "Diagnostico": "Datos insuficientes"})
            continue
            
        # Regresión OLS Multivariable o Simple según disponibilidad
        if df_promos is not None and "promo_activa" in d_log.columns and d_log["promo_activa"].nunique() > 1:
            X = d_log[["log_precio", "promo_activa", "porcentaje_promo"]]
            X = X.loc[:, X.nunique() > 1] # Eliminar features sin variación
            if "log_precio" not in X.columns:
                X["log_precio"] = d_log["log_precio"]
            X = sm.add_constant(X)
        else:
            X = sm.add_constant(d_log["log_precio"])
            
        try:
            model = sm.OLS(d_log["log_qty"], X).fit()
            beta = model.params.get("log_precio", np.nan)
            p_val = model.pvalues.get("log_precio", np.nan)
            r2 = model.rsquared
            
            diag = "Elástica" if beta < -1 else ("Inelástica" if -1 <= beta < 0 else "Mantener precio: positiva")
            resultados_elasticidad.append({"SKU": sku, "Beta": beta, "Elasticidad": beta, "R2": r2, "P_Value": p_val, "Diagnostico": diag})
        except:
            resultados_elasticidad.append({"SKU": sku, "Beta": np.nan, "Elasticidad": np.nan, "R2": np.nan, "P_Value": np.nan, "Diagnostico": "Error en cálculo"})
            
    df_el = pd.DataFrame(resultados_elasticidad)
    
    df_limpio["costo_total_linea"] = df_limpio["costo_unitario"] * df_limpio["qty"]
    base_fin = df_limpio.groupby("prod_nbr").agg(
        Venta_Neta_Total=("net_sale", "sum"),
        Unidades_Totales=("qty", "sum"),
        Costo_Total=("costo_total_linea", "sum")
    ).reset_index()
    
    base_fin["Precio_Base"] = base_fin["Venta_Neta_Total"] / base_fin["Unidades_Totales"]
    base_fin["Costo_Unitario_Base"] = base_fin["Costo_Total"] / base_fin["Unidades_Totales"]
    base_fin["Margen_Base"] = base_fin["Venta_Neta_Total"] - base_fin["Costo_Total"]
    
    demanda_mensual = df_limpio.groupby(["prod_nbr", "periodo_mensual"]).agg(Unidades_Mensuales=("qty", "sum")).reset_index()
    demanda_base = demanda_mensual.groupby("prod_nbr").agg(Unidades_Base=("Unidades_Mensuales", "mean")).reset_index()
    
    base_pricing = base_fin.merge(demanda_base, on="prod_nbr").merge(df_el, left_on="prod_nbr", right_on="SKU")
    base_pricing["Ingreso_Base"] = base_pricing["Precio_Base"] * base_pricing["Unidades_Base"]
    base_pricing["Margen_Base_Mensual"] = (base_pricing["Precio_Base"] - base_pricing["Costo_Unitario_Base"]) * base_pricing["Unidades_Base"]
    
    return base_pricing.drop(columns=["SKU"])

def simular_matriz_completa(base_pricing_df):
    # Unificar SKUs reales con SKUs introducidos manualmente por el usuario
    df_union = base_pricing_df[["prod_nbr", "Precio_Base", "Costo_Unitario_Base", "Unidades_Base", "Elasticidad", "Diagnostico"]].copy()
    df_union.columns = ["SKU", "Precio_Base", "Costo_Unitario_Base", "Unidades_Base", "Elasticidad", "Diagnostico"]
    
    if not st.session_state.custom_skus.empty:
        df_union = pd.concat([df_union, st.session_state.custom_skus], ignore_index=True)
        df_union = df_union.drop_duplicates(subset=["SKU"], keep="last")

    simulaciones = []
    for _, row in df_union.iterrows():
        sku = row["SKU"]
        p_base = row["Precio_Base"]
        c_base = row["Costo_Unitario_Base"]
        u_base = row["Unidades_Base"]
        elas = row["Elasticidad"]
        
        for _, esc in ESCENARIOS_PRICING.iterrows():
            chg = esc["Cambio_Efectivo"]
            
            if pd.isna(elas) or pd.isna(p_base) or u_base <= 0 or chg <= -1:
                p_new, u_sim, i_sim, m_sim = np.nan, np.nan, np.nan, np.nan
            else:
                elas_usada = max(min(elas, 0.0), ELASTICIDAD_MIN_RAZONABLE)
                p_new = p_base * (1 + chg)
                u_sim = u_base * (1 + (elas_usada * chg))
                u_sim = max(0, u_sim)
                i_sim = p_new * u_sim
                m_sim = (p_new - c_base) * u_sim
                
            simulaciones.append({
                "SKU": sku, "Escenario_ID": esc["Escenario_ID"], "Nombre_Escenario": esc["Nombre_Escenario"],
                "Tipo_Escenario": esc["Tipo_Escenario"], "Mecanica_Promocion": esc["Mecanica_Promocion"],
                "Precio_Nuevo": p_new, "Unidades_Base": u_base, "Unidades_Simuladas": u_sim,
                "Ingreso_Base": p_base * u_base, "Ingreso_Simulados": i_sim,
                "Margen_Base": (p_base - c_base) * u_base, "Margen_Simulados": m_sim,
                "Cambio_Precio_Pct": chg * 100
            })
            
    df_sim_detalles = pd.DataFrame(simulaciones)
    
    # Calcular Estrategias y Escenario Ideal por Margen Máximo
    recomendaciones = []
    for sku, datos_sim in df_sim_detalles.groupby("SKU"):
        info_sku = df_union[df_union["SKU"] == sku].iloc[0]
        elas = info_sku["Elasticidad"]
        
        if pd.isna(elas) or info_sku["Diagnostico"] == "Datos insuficientes":
            cat = "No recomendar"
            motivo = "Registros históricos insuficientes para trazar curva OLS estable."
        elif elas >= 0:
            cat = "Mantener precio"
            motivo = "Elasticidad positiva o cero. El volumen no decrece ante variaciones de precio."
        elif -1 <= elas < 0:
            cat = "Subir precio"
            motivo = "Demanda Inelástica. Una subida de precio incrementa los márgenes totales."
        else:
            cat = "Bajar precio / promover"
            motivo = "Demanda Altamente Elástica. Sensible al descuento, ideal para campañas/promos."
        
        valid_sims = datos_sim.dropna(subset=["Margen_Simulados"])
        if not valid_sims.empty:
            best_row = valid_sims.loc[valid_sims["Margen_Simulados"].idxmax()]
            esc_ideal = best_row["Nombre_Escenario"]
        else:
            esc_ideal = "Mantener precio 0%"
            
        recomendaciones.append({
            "SKU": sku, 
            "Categoria_Recomendacion": cat, 
            "Motivo_Recomendacion": motivo, 
            "Elasticidad": elas,
            "Escenario ideal": esc_ideal
        })
        
    return df_sim_detalles, pd.DataFrame(recomendaciones)

# ==========================================================
# FLUJO LÓGICO DE LA APLICACIÓN
# ==========================================================
if archivo_cargado is not None:
    df_limpio, q_res = cargar_y_limpiar_datos(archivo_cargado)
    df_promos = cargar_promociones(archivo_promos) if archivo_promos else None
    
    if df_limpio is not None:
        df_pricing = procesar_modelos_y_simulacion(df_limpio, df_promos)
        df_sim, df_rec = simular_matriz_completa(df_pricing)
        
        # --- SECCIÓN 1: INTRODUCCIÓN Y CALIDAD ---
        if menu_sel == "📌 Introducción y Calidad":
            st.header("📌 Semáforo de Calidad y Limpieza de Datos")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📦 Registros Crudos", f"{q_res['Filas Iniciales']:,}")
            c2.metric("🟢 Registros Filtrados", f"{q_res['Filas Limpias']:,}")
            c3.metric("🗑️ Removidos", f"{q_res['Removidos']:,}")
            
            if df_promos is not None:
                st.sidebar.success(f"✅ Archivo de promociones activo: {len(df_promos)} registros cargados.")
            
            porcentaje_perdida = q_res['% Pérdida']
            if porcentaje_perdida < 5:
                c4.markdown(f"<div class='kpi-container' style='border-left-color:green'><span class='metric-label'>ESTADO DE BASE</span><br><span class='metric-value' style='color:green'>🟢 Saludable ({porcentaje_perdida}%)</span></div>", unsafe_allow_html=True)
            elif porcentaje_perdida < 15:
                c4.markdown(f"<div class='kpi-container' style='border-left-color:orange'><span class='metric-label'>ESTADO DE BASE</span><br><span class='metric-value' style='color:orange'>🟡 Tolerable ({porcentaje_perdida}%)</span></div>", unsafe_allow_html=True)
            else:
                c4.markdown(f"<div class='kpi-container' style='border-left-color:red'><span class='metric-label'>ESTADO DE BASE</span><br><span class='metric-value' style='color:red'>🔴 Pérdida Alta ({porcentaje_perdida}%)</span></div>", unsafe_allow_html=True)

            st.write("### 📋 Vista Previa de Transacciones Sanadas")
            st.dataframe(df_limpio.head(100), use_container_width=True)

        # --- SECCIÓN 2: DASHBOARD DE ELASTICIDAD ---
        elif menu_sel == "📈 Dashboard de Elasticidad":
            st.header("📈 Centro de Control de Elasticidad Precio-Demanda")
            
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                deptos = sorted(df_limpio["dept_nm"].dropna().unique().tolist())
                depto_sel = st.selectbox("Filtrar por Departamento:", ["Todos"] + deptos)
                
            df_fil_dept = df_limpio.copy()
            if depto_sel != "Todos":
                df_fil_dept = df_fil_dept[df_fil_dept["dept_nm"] == depto_sel]
                
            skus_dispo = sorted(df_fil_dept["prod_nbr"].dropna().astype(int).unique().tolist())
            
            with col_f2:
                periodo_opc = st.selectbox("Agrupación Temporal (Periodo):", ["Mensual", "Trimestral", "Semestral"])
            with col_f3:
                tipo_sel = st.radio("Método de Selección de SKU:", ["Único", "Múltiple"], horizontal=True)

            if tipo_sel == "Único":
                sku_sel = st.selectbox("Selecciona el SKU a evaluar:", skus_dispo)
                skus_finales = [sku_sel] if sku_sel else []
            else:
                skus_finales = st.multiselect("Selecciona múltiples SKUs:", skus_dispo, default=skus_dispo[:3] if len(skus_dispo) >= 3 else skus_dispo)

            if len(skus_finales) > 0:
                df_analisis = df_fil_dept[df_fil_dept["prod_nbr"].isin(skus_finales)].copy()
                
                if periodo_opc == "Mensual":
                    df_analisis["Periodo"] = df_analisis["tran_date"].dt.to_period("M").astype(str)
                elif periodo_opc == "Trimestral":
                    df_analisis["Periodo"] = df_analisis["tran_date"].dt.to_period("Q").astype(str)
                else:
                    df_analisis["Periodo"] = df_analisis["tran_date"].apply(lambda x: f"{x.year}-S1" if x.month <= 6 else f"{x.year}-S2")

                df_g = df_analisis.groupby(["prod_nbr", "Periodo"]).agg(Unidades=("qty", "sum"), Ingresos=("net_sale", "sum")).reset_index()
                df_g["Precio_Promedio"] = df_g["Ingresos"] / df_g["Unidades"].replace(0, np.nan)
                df_g = df_g.dropna()

                st.subheader("📊 Diagnóstico y Tendencias del Comportamiento del Consumidor")
                cg1, cg2 = st.columns(2)
                with cg1:
                    fig_hist = px.histogram(df_analisis, x="precio_unitario", color="prod_nbr" if tipo_sel=="Múltiple" else None,
                                            title="Distribución Histórica de Precios Unitarios Cobrados",
                                            labels={"precio_unitario": "Precio Transaccionado ($)", "count": "Frecuencia"},
                                            barmode="overlay", template="plotly_white")
                    st.plotly_chart(fig_hist, use_container_width=True)
                with cg2:
                    fig_trend = px.line(df_g, x="Periodo", y="Unidades", color="prod_nbr" if tipo_sel=="Múltiple" else None,
                                        title=f"Volumen Temporal de Demanda ({periodo_opc})", markers=True, template="plotly_white")
                    st.plotly_chart(fig_trend, use_container_width=True)

                st.subheader("📉 Ajuste del Modelo Log-Log Realizado")
                fig_scat = px.scatter(df_g, x="Precio_Promedio", y="Unidades", color=df_g["prod_nbr"].astype(str),
                                      log_x=True, log_y=True, trendline="ols",
                                      title="Regresión Lineal en Espacio Logarítmico (Pendiente = Elasticidad)", template="plotly_white")
                st.plotly_chart(fig_scat, use_container_width=True)

        # --- SECCIÓN 3: DASHBOARD DE PRICING & SIMULACIÓN ---
        elif menu_sel == "💰 Dashboard de Pricing & Simulación":
            st.header("💰 Optimizador de Pricing Dinámico y Simulación")
            
            # ------------------------------------------------------
            # NUEVO FEATURE: INTRODUCCIÓN MANUAL DE SKU POR EL USUARIO
            # ------------------------------------------------------
            with st.expander("➕ Introducir e Inyectar un SKU y Elasticidad de Forma Manual", expanded=False):
                st.write("Agrega un producto ajeno a la base o fuerza métricas específicas para simular:")
                c_m1, c_m2, c_m3 = st.columns(3)
                with c_m1:
                    new_sku = st.number_input("Código SKU del Producto:", min_value=1, value=99999)
                    new_price = st.number_input("Precio Base Unitario ($):", min_value=0.1, value=100.0)
                with c_m2:
                    new_cost = st.number_input("Costo Unitario ($):", min_value=0.0, value=60.0)
                    new_qty = st.number_input("Demanda Promedio Mensual (Unidades):", min_value=1.0, value=50.0)
                with c_m3:
                    new_elas = st.number_input("Coeficiente de Elasticidad de Precio:", max_value=10.0, value=-1.8)
                    st.write("##")
                    if st.button("🚀 Inyectar Producto al Simulador", use_container_width=True):
                        new_row = pd.DataFrame([{
                            "SKU": int(new_sku), "Precio_Base": new_price, "Costo_Unitario_Base": new_cost,
                            "Unidades_Base": new_qty, "Elasticidad": new_elas, "Diagnostico": "Introducido por usuario"
                        }])
                        st.session_state.custom_skus = pd.concat([st.session_state.custom_skus, new_row], ignore_index=True).drop_duplicates(subset=["SKU"], keep="last")
                        st.success(f"✅ SKU {new_sku} listo para análisis. ¡Recalculando matrices!")
                        st.rerun()
                
                if not st.session_state.custom_skus.empty:
                    st.write("**Productos manuales activos:**")
                    st.dataframe(st.session_state.custom_skus, use_container_width=True)
                    if st.button("🗑️ Limpiar productos manuales"):
                        st.session_state.custom_skus = pd.DataFrame(columns=["SKU", "Precio_Base", "Costo_Unitario_Base", "Unidades_Base", "Elasticidad", "Diagnostico"])
                        st.rerun()

            # Flujo normal de simulación
            cp1, cp2 = st.columns(2)
            with cp1:
                cat_list = ["Todas"] + list(df_rec["Categoria_Recomendacion"].unique())
                cat_sel = st.selectbox("Filtrar por Categoría Recomendada (Regla de Negocio):", cat_list)
                
            df_rec_fil = df_rec.copy()
            if cat_sel != "Todas":
                df_rec_fil = df_rec_fil[df_rec_fil["Categoria_Recomendacion"] == cat_sel]
                
            skus_p_lista = sorted(df_rec_fil["SKU"].dropna().astype(int).unique().tolist())
            
            with cp2:
                sku_p_sel = st.selectbox("Selecciona SKU para Simular Escenarios de Impacto:", [str(x) for x in skus_p_lista])

            if sku_p_sel:
                sku_int = int(sku_p_sel)
                rec_sku = df_rec[df_rec["SKU"] == sku_int].iloc[0]
                df_sim_sku = df_sim[df_sim["SKU"] == sku_int].copy()
                
                st.markdown("### 🛠️ Parámetros del Simulador Matemático")
                lista_esc = df_sim_sku["Nombre_Escenario"].unique().tolist()
                esc_sel = st.selectbox("Selecciona la Acción Comercial o Mecánica Promocional a Evaluar:", lista_esc)
                
                fila_act = df_sim_sku[df_sim_sku["Nombre_Escenario"] == esc_sel].iloc[0]
                
                st.markdown("### 📊 Proyecciones Financieras Estimadas (Mensuales vs Escenario Base)")
                u_b, u_s = fila_act["Unidades_Base"], fila_act["Unidades_Simuladas"]
                i_b, i_s = fila_act["Ingreso_Base"], fila_act["Ingreso_Simulados"]
                m_b, m_s = fila_act["Margen_Base"], fila_act["Margen_Simulados"]
                
                pct_u = ((u_s / u_b) - 1) * 100 if u_b > 0 else 0
                pct_i = ((i_s / i_b) - 1) * 100 if i_b > 0 else 0
                pct_m = ((m_s / m_b) - 1) * 100 if m_b > 0 else 0
                
                kpi1, kpi2, kpi3 = st.columns(3)
                with kpi1:
                    st.metric(label="📦 Volumen de Demanda Proyectado", value=f"{u_s:,.1f} unidades", delta=f"{pct_u:+.2f}% vs Base")
                with kpi2:
                    st.metric(label="💵 Ingresos Brutos Estimados", value=f"${i_s:,.2f}", delta=f"{pct_i:+.2f}% vs Base")
                with kpi3:
                    st.metric(label="📈 Margen Comercial de Utilidad", value=f"${m_s:,.2f}", delta=f"{pct_m:+.2f}% vs Base")
                    
                st.markdown("---")
                st.subheader("💡 Conclusión Estratégica Automatizada")
                st.info(f"**Dictamen Analítico para SKU {sku_int}:** {rec_sku['Motivo_Recomendacion']} Se recomienda clasificar el portafolio en la estrategia de **{rec_sku['Categoria_Recomendacion'].upper()}**.")
                
                st.markdown("### 📉 Curvas de Sensibilidad Comercial")
                gp1, gp2 = st.columns(2)
                with gp1:
                    df_curva = df_sim_sku.sort_values("Precio_Nuevo")
                    fig_c = px.line(df_curva, x="Precio_Nuevo", y="Unidades_Simuladas", markers=True,
                                    title="Curva de Demanda Proyectada de Elasticidad", template="plotly_white", color_discrete_sequence=["#17a2b8"])
                    st.plotly_chart(fig_c, use_container_width=True)
                with gp2:
                    df_melt = df_sim_sku.melt(id_vars=["Nombre_Escenario"], value_vars=["Ingreso_Simulados", "Margen_Simulados"], var_name="Indicador", value_name="Monto")
                    fig_b = px.bar(df_melt, x="Nombre_Escenario", y="Monto", color="Indicador", barmode="group",
                                   title="Comparativa de Ingresos vs Márgenes de Ganancia", template="plotly_white", color_discrete_sequence=["#007bff", "#28a745"])
                    st.plotly_chart(fig_b, use_container_width=True)

                # ==========================================================
                # EXPORTADORES CSV CON FILTRADO DE COLUMNAS SOLICITADO
                # ==========================================================
                st.markdown("---")
                st.subheader("📥 Exportar Reportes Masivos")
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.write("**1. Reporte Resumen por SKU (Estructura Solicitada)**")
                    
                    # Cruzar matriz con la recomendación/escenario ideal para tener las columnas exactas
                    df_resumen_final = df_sim.merge(
                        df_rec[["SKU", "Escenario ideal"]], 
                        on="SKU", 
                        how="left"
                    )
                    
                    # Mapeo exacto solicitado por el usuario
                    columnas_solicitadas = [
                        "SKU", "Escenario ideal", "Nombre_Escenario", "Tipo_Escenario", 
                        "Mecanica_Promocion", "Precio_Nuevo", "Unidades_Base", 
                        "Unidades_Simuladas", "Ingreso_Base", "Ingreso_Simulados", 
                        "Margen_Base", "Margen_Simulados", "Cambio_Precio_Pct"
                    ]
                    
                    # Filtrar de forma segura sólo las existentes para evitar KeyErrors
                    columnas_existentes = [c for c in columnas_solicitadas if c in df_resumen_final.columns]
                    df_resumen_exportable = df_resumen_final[columnas_existentes]
                    
                    csv_resumen = df_resumen_exportable.to_csv(index=False, encoding="utf-8-sig")
                    st.download_button(
                        label="💾 Descargar Resumen por SKU (CSV)",
                        data=csv_resumen,
                        file_name="resumen_recomendacion_sku_export.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                with col_d2:
                    st.write("**2. Reporte Completo de Experimentos (Matriz Cruda)**")
                    csv_experimentos = df_sim.to_csv(index=False, encoding="utf-8-sig")
                    st.download_button(
                        label="💾 Descargar Todos los Experimentos (CSV)",
                        data=csv_experimentos,
                        file_name="resultados_elasticidad_pricing_skus.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
else:
    st.info("👋 Por favor, sube los archivos requeridos en el panel lateral izquierdo para inicializar el motor analítico de precios.")
