# 📈 Simulador de Elasticidad de Precios & Pricing Dinámico

Esta aplicación web interactiva, desarrollada en Python utilizando **Streamlit**, permite automatizar el análisis financiero de elasticidad-precio de la demanda y simular escenarios óptimos de maximización de ingresos y márgenes.

## 🚀 Características Incorporadas

* **Carga Flexible de Datos**: Soporta formatos `.csv` y `.xlsx` (Excel) con cualquier nomenclatura de archivo.
* **Validación Estricta de Columnas**: Antes de procesar la información, evalúa la presencia de variables mandatorias arrojando advertencias descriptivas si faltan campos indispensables.
* **Ajuste y Sobreescritura Manual**: El usuario puede fijar manualmente una elasticidad determinada para cualquier SKU específico, actualizando en cascada los tableros de pricing.
* **Análisis Multivariable de Promociones**: La app funciona con o sin archivo de promociones unificadas. Si la base opcional de promos es provista, refina el cálculo de las regresiones log-log.
* **Gráficos Empresariales de Alta Gama**: Desarrollados con paletas cromáticas optimizadas mediante Plotly.
* **Reporte Dinámico**: Módulo final de conclusiones ejecutivas personalizable de forma instantánea por SKU o Departamento.

## 📋 Estructura de Datos Requerida

### 1. Histórico de Ventas
El archivo debe contener las siguientes columnas (no importa el orden):
* `tran_date`: Fecha de la operación.
* `prod_nbr`: Código del SKU/Producto.
* `qty`: Unidades vendidas.
* `net_sale`: Venta neta (ingreso monetario).
* `costo2` *(Opcional)*: Costo total de adquisición de la línea.
* `dept_nm` *(Opcional)*: Departamento comercial.

### 2. Base de Promociones (Opcional)
* `SKU`: Código correlativo del producto (`prod_nbr`).
* `Fecha_Inicio` y `Fecha_Fin`: Ventana de tiempo promocional.
* `Porcentaje`: Porcentaje numérico del descuento (ej: 15 para 15%).

## 🛠️ Instrucciones para Ejecución Local

1. Clona este repositorio:
   ```bash
   git clone [https://github.com/TU-USUARIO/TU-REPOSITORIO.git](https://github.com/TU-USUARIO/TU-REPOSITORIO.git)
   cd TU-REPOSITORIO
