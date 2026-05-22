import streamlit as st
import pandas as pd
import numpy as np
import statsmodels.api as sm
import plotly.express as px
import plotly.graph_objects as go

# Configuración de página de Streamlit de aspecto moderno y limpio
st.set_page_config(
    page_title="Simulador de Elasticidad & Pricing Dinámico",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos personalizados para mejorar la interfaz (colores corporativos atractivos)
st.markdown("""
    <style>
    .main-title { font-size:38px !important; font-weight: bold; color: #1E3A8A; margin-bottom: 5px; }
    .subtitle { font-size:18px !important; color: #4B5563; margin-bottom: 25px; }
    .section-holder { border-radius: 10px; background-color: #F3F4F6; padding: 20px; margin-bottom: 20px; }
    .metric-card { background-color: #FFFFFF; border-left: 5px solid #10B981; padding: 15px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📈 Simulador Avanzado de Elasticidad y Pricing Dinámico</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Sube tu histórico de transacciones para calcular elasticidades automáticas o asignar valores manuales por SKU.</div>', unsafe_allow_html=True)

# ==========================================
# SECCIÓN ANTES DE SUBIR LOS ARCHIVOS: EXPLICACIÓN DE COLUMNAS
# ==========================================
st.sidebar.header("📁 Carga de Datos")

# Mensaje informativo inicial sobre las columnas necesarias obligatorias y opcionales
st.info("""
### 📋 Guía de Columnas Requeridas para el Análisis

Antes de cargar tus bases de datos, asegúrate de que contengan exactamente los siguientes nombres de columna:

**1. Histórico de Ventas (Obligatorio):**
* `tran_date` : Fecha de la venta (formatos aceptados: AAAA-MM-DD o DD/MM/AAAA).
* `prod_nbr` : Identificador único del producto o SKU (Numérico).
* `qty` : Cantidad de unidades vendidas.
* `net_sale` : Venta neta total percibida (ingreso total por esa línea).
* *`costo2` (Opcional):* Costo del producto. Si no se incluye, se estimará automáticamente al 60% del precio.
* *`dept_nm` (Opcional):* Nombre del departamento o categoría para segmentar conclusiones.

**2. Base de Promociones (Opcional):**
* `SKU` : Código del producto (debe coincidir con `prod_nbr`).
* `Fecha_Inicio` : Fecha inicial de la vigencia de la promoción.
* `Fecha_Fin` : Fecha de término de la promoción.
* `Porcentaje` : Porcentaje de descuento aplicado (ej. 20 para 20% de descuento).
""")

# Uploaders de archivos mutables (Aceptan cualquier nombre de archivo CSV o Excel)
file_ventas = st.sidebar.file_uploader("1. Selecciona Histórico de Ventas (CSV o Excel)", type=["csv", "xlsx", "xls"])
file_promos = st.sidebar.file_uploader("2. Selecciona Base de Promociones Opcional (CSV o Excel)", type=["csv", "xlsx", "xls"])

# ==========================================
# FUNCIONES DE CARGA Y VALIDACIÓN DE DATOS
# ==========================================
def cargar_archivo(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        # Limpiar espacios en los nombres de las columnas
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None

# Cargar bases si existen
df_ventas = cargar_archivo(file_ventas)
df_promos = cargar_archivo(file_promos)

# Validar Columnas de Ventas
if df_ventas is not None:
    columnas_requeridas_ventas = ["tran_date", "qty", "net_sale", "prod_nbr"]
    faltantes_ventas = [col for col in columnas_requeridas_ventas if col not in df_ventas.columns]
    
    if len(faltantes_ventas) > 0:
        st.error(f"❌ **El archivo de ventas no sirve para el análisis.** Faltan las siguientes variables obligatorias: `{faltantes_ventas}`. Por favor, rectifica el nombre de las columnas e intenta de nuevo.")
        st.stop() # Detiene la ejecución para evitar fallas
    
    # Rellenar columnas opcionales si no existen
    if "dept_nm" not in df_ventas.columns:
        df_ventas["dept_nm"] = "General"
    if "costo2" not in df_ventas.columns:
        # Si no viene costo, se asume un margen por defecto referencial (Costo = 60% de la venta unitaria)
        df_ventas["costo2"] = df_ventas["net_sale"] * 0.60

# Validar Columnas de Promociones (Si se subió un archivo de promociones)
tiene_promos = False
if df_promos is not None:
    columnas_requeridas_promos = ["SKU", "Fecha_Inicio", "Fecha_Fin", "Porcentaje"]
    faltantes_promos = [col for col in columnas_requeridas_promos if col not in df_promos.columns]
    
    if len(faltantes_promos) > 0:
        st.warning(f"⚠️ El archivo de promociones cargado contiene nombres incorrectos. Faltan: `{faltantes_promos}`. El análisis continuará **SIN** considerar promociones.")
        tiene_promos = False
    else:
        tiene_promos = True

# ==========================================
# PROCESAMIENTO PRINCIPAL Y DOCK DE SOBREESCRITURA MANUAL
# ==========================================
if df_ventas is not None:
    # Formatear tipos de datos
    df_ventas["tran_date"] = pd.to_datetime(df_ventas["tran_date"], errors="coerce")
    df_ventas = df_ventas.dropna(subset=["tran_date", "prod_nbr", "qty", "net_sale"])
    df_ventas["prod_nbr"] = df_ventas["prod_nbr"].astype(int)
    
    # Calcular precio unitario base observado
    df_ventas = df_ventas[df_ventas["qty"] > 0]
    df_ventas["precio_unitario"] = df_ventas["net_sale"] / df_ventas["qty"]
    df_ventas["costo_unitario"] = df_ventas["costo2"] / df_ventas["qty"]
    
    # Procesar e integrar Promociones si están activas y validadas
    if tiene_promos:
        df_promos["Fecha_Inicio"] = pd.to_datetime(df_promos["Fecha_Inicio"], errors="coerce")
        df_promos["Fecha_Fin"] = pd.to_datetime(df_promos["Fecha_Fin"], errors="coerce")
        df_promos["SKU"] = df_promos["SKU"].astype(int)
        
        # Mapear promociones por fecha y SKU
        # Para simplificar la ejecución rápida en Streamlit, creamos flags agregados semanales
        df_ventas["semana"] = df_ventas["tran_date"].dt.to_period("W").dt.start_time
        
        # Agrupar ventas a nivel semanal por SKU para estabilizar regresión
        df_sku_weekly = df_ventas.groupby(["prod_nbr", "semana", "dept_nm"]).agg(
            qty=("qty", "sum"),
            net_sale=("net_sale", "sum"),
            costo_total=("costo2", "sum")
        ).reset_index()
        df_sku_weekly["precio_unitario"] = df_sku_weekly["net_sale"] / df_sku_weekly["qty"]
        df_sku_weekly["costo_unitario"] = df_sku_weekly["costo_total"] / df_sku_weekly["qty"]
        
        # Cruzar flag promocional sencillo
        df_sku_weekly["promo_activa"] = 0
        df_sku_weekly["porcentaje_promo"] = 0.0
        for idx, row in df_promos.dropna(subset=["Fecha_Inicio", "Fecha_Fin"]).iterrows():
            mask = (df_sku_weekly["prod_nbr"] == row["SKU"]) & \
                   (df_sku_weekly["semana"] >= row["Fecha_Inicio"]) & \
                   (df_sku_weekly["semana"] <= row["Fecha_Fin"])
            df_sku_weekly.loc[mask, "promo_activa"] = 1
            df_sku_weekly.loc[mask, "porcentaje_promo"] = float(row["Porcentaje"]) / 100.0
    else:
        # Agrupación estándar semanal sin promociones
        df_ventas["semana"] = df_ventas["tran_date"].dt.to_period("W").dt.start_time
        df_sku_weekly = df_ventas.groupby(["prod_nbr", "semana", "dept_nm"]).agg(
            qty=("qty", "sum"),
            net_sale=("net_sale", "sum"),
            costo_total=("costo2", "sum")
        ).reset_index()
        df_sku_weekly["precio_unitario"] = df_sku_weekly["net_sale"] / df_sku_weekly["qty"]
        df_sku_weekly["costo_unitario"] = df_sku_weekly["costo_total"] / df_sku_weekly["qty"]
        df_sku_weekly["promo_activa"] = 0
        df_sku_weekly["porcentaje_promo"] = 0.0

    # ------------------------------------------
    # CONFIGURACIÓN DE ELASTICIDAD MANUAL (SOLICITADO)
    # ------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.header("🛠️ Ajuste Manual de Elasticidad")
    st.sidebar.write("Puedes forzar una elasticidad personalizada para un SKU específico:")
    manual_sku_input = st.sidebar.text_input("Ingresa el SKU a modificar (ej. 50011837):", "")
    manual_elasticity_val = st.sidebar.number_input("Valor de Elasticidad Manual:", value=-1.5, step=0.1)

    # ------------------------------------------
    # CÁLCULO CIENTÍFICO DE ELASTICIDADES (LOG-LOG REGRESSION)
    # ------------------------------------------
    resultados_elasticidad = []
    skus_unicos = df_sku_weekly["prod_nbr"].unique()

    for sku in skus_unicos:
        df_sub = df_sku_weekly[df_sku_weekly["prod_nbr"] == sku].copy()
        
        # Requerir un mínimo de datos para estabilidad estadística
        if len(df_sub) < 3 or df_sub["precio_unitario"].nunique() < 2:
            # Obtener métricas base promedio del histórico
            p_base = df_sub["precio_unitario"].median()
            q_base = df_sub["qty"].mean()
            c_base = df_sub["costo_unitario"].median() if "costo_unitario" in df_sub.columns else p_base*0.6
            resultados_elasticidad.append({
                "SKU": sku, "Elasticidad": -1.0, "Alfa": 0, "R2": 0.0, "P_Value": 0.5, 
                "Precio_Base": p_base, "Unidades_Base": q_base, "Costo_Base": c_base, "Metodo": "Default por Datos Insuficientes"
            })
            continue
            
        df_sub["log_qty"] = np.log(df_sub["qty"])
        df_sub["log_p"] = np.log(df_sub["precio_unitario"])
        df_sub = df_sub.replace([np.inf, -np.inf], np.nan).dropna(subset=["log_qty", "log_p"])
        
        # Determinar si incluimos variables promocionales en la regresión
        if tiene_promos and df_sub["promo_activa"].nunique() > 1:
            X = df_sub[["log_p", "promo_activa", "porcentaje_promo"]]
        else:
            X = df_sub[["log_p"]]
            
        X = sm.add_constant(X)
        y = df_sub["log_qty"]
        
        try:
            model = sm.OLS(y, X).fit()
            elasticidad_calc = model.params.get("log_p", -1.0)
            alfa_calc = model.params.get("const", 0.0)
            r2_calc = model.rsquared
            p_val_calc = model.pvalues.get("log_p", 0.5)
        except:
            elasticidad_calc = -1.0
            alfa_calc = 0
            r2_calc = 0.0
            p_val_calc = 0.5
            
        p_base = df_sub["precio_unitario"].median()
        q_base = df_sub["qty"].mean()
        c_base = df_sub["costo_unitario"].median()
        
        resultados_elasticidad.append({
            "SKU": sku, "Elasticidad": elasticidad_calc, "Alfa": alfa_calc, "R2": r2_calc, "P_Value": p_val_calc,
            "Precio_Base": p_base, "Unidades_Base": q_base, "Costo_Base": c_base, "Metodo": "Regresión Log-Log"
        })

    df_elasticidades_resumen = pd.DataFrame(resultados_elasticidad)

    # APLICAR SOBREESCRITURA MANUAL DEL USUARIO SI APLICA
    if manual_sku_input.strip().isdigit():
        target_sku = int(manual_sku_input.strip())
        if target_sku in df_elasticidades_resumen["SKU"].values:
            df_elasticidades_resumen.loc[df_elasticidades_resumen["SKU"] == target_sku, "Elasticidad"] = manual_elasticity_val
            df_elasticidades_resumen.loc[df_elasticidades_resumen["SKU"] == target_sku, "Metodo"] = "Asignada Manualmente por Usuario"
            st.sidebar.success(f"✅ ¡SKU {target_sku} forzado exitosamente a Elasticidad {manual_elasticity_val}!")

    # Mapear de regreso los departamentos a la matriz resumen
    dept_map = df_sku_weekly.groupby("prod_nbr")["dept_nm"].first().to_dict()
    df_elasticidades_resumen["Departamento"] = df_elasticidades_resumen["SKU"].map(dept_map)

    # ==========================================
    # CREACIÓN DE PANELES (TABS SOLICITADOS)
    # ==========================================
    tab1, tab2 = st.tabs(["📈 Dashboard de Elasticidad", "💰 Dashboard de Pricing Dinámico"])

    # ------------------------------------------
    # TAB 1: DASHBOARD DE ELASTICIDAD
    # ------------------------------------------
    with tab1:
        st.subheader("Análisis General de Elasticidades Calculadas")
        
        # KPIs Principales
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total SKUs Evaluados", f"{len(df_elasticidades_resumen)}")
        col2.metric("Elasticidad Promedio", f"{df_elasticidades_resumen['Elasticidad'].mean():.2f}")
        col3.metric("R² Promedio Modelos", f"{df_elasticidades_resumen['R2'].mean():.2f}")
        elasticos_count = len(df_elasticidades_resumen[df_elasticidades_resumen["Elasticidad"] < -1])
        col4.metric("SKUs Altamente Elásticos (< -1)", f"{elasticos_count}")
        
        # Gráfica de Distribución de Elasticidad (Colores Bonitos)
        fig_hist = px.histogram(
            df_elasticidades_resumen, 
            x="Elasticidad", 
            title="Distribución Global de la Elasticidad Arco/Regresión",
            labels={"Elasticidad": "Coeficiente de Elasticidad Precio"},
            color_discrete_sequence=["#1E3A8A"], # Azul Marino Elegante
            nbins=30,
            template="plotly_white"
        )
        fig_hist.add_vline(x=-1.0, line_dash="dash", line_color="#EF4444", annotation_text="Límite Elasticidad")
        st.plotly_chart(fig_hist, use_container_width=True)
        
        # Tabla completa interactiva
        st.markdown("### 📋 Matriz Resumen de Elasticidades")
        st.dataframe(df_elasticidades_resumen[["SKU", "Departamento", "Elasticidad", "R2", "P_Value", "Precio_Base", "Metodo"]].style.format({
            "Elasticidad": "{:.3f}", "R2": "{:.2f}", "P_Value": "{:.4f}", "Precio_Base": "${:.2f}"
        }), use_container_width=True)

    # ------------------------------------------
    # TAB 2: DASHBOARD DE PRICING DINÁMICO
    # ------------------------------------------
    with tab2:
        st.subheader("Simulador de Escenarios de Precios y Recomendaciones Óptimas")
        
        # Selector de SKU para análisis dinámico profundo
        selected_sku = st.selectbox("Selecciona un SKU para simular estrategias:", sorted(df_elasticidades_resumen["SKU"].unique()))
        
        sku_row = df_elasticidades_resumen[df_elasticidades_resumen["SKU"] == selected_sku].iloc[0]
        e = sku_row["Elasticidad"]
        p_base = sku_row["Precio_Base"]
        q_base = sku_row["Unidades_Base"]
        c_base = sku_row["Costo_Base"]
        
        st.markdown(f"""
        <div class='metric-card'>
            <strong>SKU seleccionado:</strong> {selected_sku} | 
            <strong>Departamento:</strong> {sku_row['Departamento']} | 
            <strong>Elasticidad Aplicada:</strong> <span style='color:#1E3A8A; font-weight:bold;'>{e:.3f}</span> ({sku_row['Metodo']})
        </div>
        <br>
        """, unsafe_allow_html=True)
        
        # Generación de Escenarios de Cambio Porcentual de Precio (-15% a +15%)
        cambios_pct = [-0.15, -0.10, -0.05, 0.00, 0.05, 0.10, 0.15]
        sim_rows = []
        
        for chg in cambios_pct:
            p_nuevo = p_base * (1 + chg)
            # Modelo log-log: Q_nuevo = Q_base * (P_nuevo/P_base)^Elasticidad
            if p_base > 0 and q_base > 0:
                q_sim = q_base * ((p_nuevo / p_base) ** e)
            else:
                q_sim = max(0.0, q_base * (1 + (e * chg)))
                
            q_sim = max(0.0, q_sim) # Evitar cantidades negativas
            ingreso_sim = q_sim * p_nuevo
            costo_total_sim = q_sim * c_base
            margen_sim = ingreso_sim - costo_total_sim
            
            sim_rows.append({
                "Escenario": f"{chg*100:+.0f}%",
                "Precio_Nuevo": p_nuevo,
                "Unidades_Simuladas": q_sim,
                "Ingreso_Simulado": ingreso_sim,
                "Margen_Simulado": margen_sim,
                "Delta_Margen_Pct": ((margen_sim / ((q_base*p_base) - (q_base*c_base))) - 1) * 100 if ((q_base*p_base) - (q_base*c_base)) != 0 else 0.0
            })
            
        df_sim_sku = pd.DataFrame(sim_rows)
        
        # Determinar el Escenario que maximiza Margen de Ganancia
        idx_max_margen = df_sim_sku["Margen_Simulado"].idxmax()
        escenario_optimo = df_sim_sku.loc[idx_max_margen]
        
        # Definir Categoría de recomendación estratégica basada en elasticidad pura
        if e > -1.0 and e <= 0:
            categoria_rec = "Subir precio 📈"
            motivo_rec = "El producto es Inelástico. Incrementos en el precio aumentarán los ingresos y protegerán el margen sin castigar drásticamente el volumen."
        elif e <= -1.0:
            categoria_rec = "Bajar precio / Promover 📉"
            motivo_rec = "El producto es Altamente Elástico. Estructuras de descuento o rebajas controladas dispararán el volumen, optimizando la masa de margen total."
        else:
            categoria_rec = "Mantener precio / Revisar 🔄"
            motivo_rec = "Elasticidad inusual positiva. Se aconseja mantener precios constantes y auditar posibles anomalías en el inventario o la captura de datos."
            
        # Desplegar Recomendación Estratégica
        st.success(f"### 🎯 Recomendación Estratégica: **{categoria_rec}**")
        st.write(f"**Justificación:** {motivo_rec}")
        st.write(f"El mejor escenario numérico simulado es un cambio de **{escenario_optimo['Escenario']}**, el cual proyecta un margen de **${escenario_optimo['Margen_Simulado']:,.2f}**.")
        
        # Gráfico Comparativo de Margen e Ingresos por Escenario (Visualmente Atractivo)
        fig_sim = go.Figure()
        fig_sim.add_trace(go.Bar(
            x=df_sim_sku["Escenario"], y=df_sim_sku["Ingreso_Simulado"],
            name="Ingreso Proyectado ($)", marker_color="#3B82F6"
        ))
        fig_sim.add_trace(go.Scatter(
            x=df_sim_sku["Escenario"], y=df_sim_sku["Margen_Simulado"],
            name="Margen Ganancia Proyectado ($)", mode="lines+markers", line=dict(color="#10B981", width=4)
        ))
        fig_sim.update_layout(
            title=f"Impacto Financiero de Cambios de Precio en SKU {selected_sku}",
            xaxis_title="Escenario de Cambio de Precio",
            yaxis_title="Monto ($)",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_sim, use_container_width=True)
        
        # Tabla Detallada de Simulación
        st.markdown("#### 📊 Desglose de Datos Simulados")
        st.dataframe(df_sim_sku.style.format({
            "Precio_Nuevo": "${:.2f}", "Unidades_Simuladas": "{:.1f}", "Ingreso_Simulado": "${:,.2f}", 
            "Margen_Simulado": "${:,.2f}", "Delta_Margen_Pct": "{:+.1f}%"
        }), use_container_width=True)

    # ==========================================
    # SECCIÓN FINAL: CONCLUSIÓN GENERAL CONFIGURABLE (SOLICITADO)
    # ==========================================
    st.markdown("---")
    st.markdown("### 📋 Conclusiones Dinámicas Personalizadas")
    st.markdown("Filtra el alcance por Departamento y/o SKU para generar un reporte ejecutivo automatizado de las palancas de pricing:")
    
    c_df1, c_df2 = st.columns(2)
    with c_df1:
        selected_conclusion_dept = st.selectbox("Filtrar Conclusión por Departamento:", ["Todos"] + list(df_elasticidades_resumen["Departamento"].unique()))
    with c_df2:
        # Filtrar SKUs dependientes del departamento seleccionado
        if selected_conclusion_dept == "Todos":
            available_skus_conclusion = sorted(df_elasticidades_resumen["SKU"].unique())
        else:
            available_skus_conclusion = sorted(df_elasticidades_resumen[df_elasticidades_resumen["Departamento"] == selected_conclusion_dept]["SKU"].unique())
        selected_conclusion_sku = st.selectbox("Filtrar Conclusión por SKU Específico:", available_skus_conclusion)
        
    # Extraer métricas filtradas para armar la conclusión semántica
    row_conclusion = df_elasticidades_resumen[df_elasticidades_resumen["SKU"] == selected_conclusion_sku].iloc[0]
    el_conclusion = row_conclusion["Elasticidad"]
    r2_conclusion = row_conclusion["R2"]
    
    if el_conclusion < -1.0:
        diagnostico_texto = "altamente sensible al precio (Elástico)"
        accion_texto = f"implementar descuentos promocionales estratégicos o fijar el precio óptimo proyectado en el simulador."
    elif el_conclusion >= -1.0 and el_conclusion <= 0:
        diagnostico_texto = "poco sensible a variaciones de precio (Inelástico)"
        accion_texto = f"efectuar capturas ordenadas de margen incrementando paulatinamente el precio base sin arriesgar pérdidas notables de volumen."
    else:
        diagnostico_texto = "con respuesta de demanda anómala/positiva (Veblen/Giffen teórico)"
        accion_texto = f"auditar la consistencia de los datos históricos o revisar si existieron quiebres prolongados de stock en góndola."

    # Render del Reporte Ejecutivo final redactado de manera formal y elegante
    st.markdown(f"""
    <div style="border: 2px solid #1E3A8A; border-radius: 12px; padding: 20px; background-color: #F8FAFC;">
        <h4>📝 Reporte Ejecutivo — Departamento: <span style="color:#3B82F6;">{selected_conclusion_dept}</span> | SKU: <span style="color:#3B82F6;">{selected_conclusion_sku}</span></h4>
        <p>Tras analizar la base histórica consolidada, se concluye que el producto <strong>SKU {selected_conclusion_sku}</strong> cuenta con un coeficiente numérico de elasticidad de <strong>{el_conclusion:.3f}</strong>, clasificándose operativamente como un bien <strong>{diagnostico_texto}</strong>.</p>
        <p>El modelo de regresión presenta una confiabilidad estadística R² de <strong>{r2_conclusion:.2%}</strong>. Con base en esta sensibilidad matemática, la recomendación óptima para la dirección comercial es <strong>{accion_texto}</strong></p>
        <small style="color: #6B7280;">*Nota: Este reporte se genera algorítmicamente y considera los ajustes de elasticidad manuales suministrados en la barra lateral.</small>
    </div>
    <br>
    """, unsafe_allow_html=True)

else:
    # Mensaje de bienvenida amigable si no se han cargado datos aún
    st.warning("👋 Por favor, utiliza la barra lateral izquierda para subir tu histórico de ventas (CSV o Excel) para iniciar el motor de simulación corporativa.")
