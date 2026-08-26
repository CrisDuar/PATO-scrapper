# Cómo se limpian y normalizan los datos del IPM

El scraper descarga hojas de Excel y CSV del DANE tal como fueron publicadas: con títulos
fusionados, columnas por año, celdas combinadas y encabezados con tildes rotas. Este documento
explica, paso a paso, qué transforma `app/cleaner/` y por qué cada regla existe.

## Resumen del flujo

Cuando se llama a `POST /jobs/{id}/clean`, `clean_job_files()` ejecuta cuatro etapas en orden
sobre cada archivo descargado del job:

1. **Extracción** — `block_extractor.py`: separa cada hoja en tablas individuales (bloques).
2. **Normalización** — `normalizer.py`: repara texto, tipa valores, quita duplicados.
3. **Clasificación** — `table_mapper.py`: decide a qué sub-tabla pertenece cada bloque.
4. **Exportación / Carga** — `exporter.py` + `loader.py`: CSV/Excel y, para 3 tablas, PostgreSQL.

El resultado son 9 sub-tablas planas (una por tipo de indicador del IPM) más un cajón
`sin_clasificar` para lo que no se pudo mapear, exportadas como CSV individuales y como un único
`datos_limpios.xlsx`. De esas 9, solo 3 tienen un mapeo acordado hacia el esquema estrella de
PostgreSQL; el resto queda disponible solo como archivo.

## 1. Extracción de bloques

Un archivo del DANE no es "una tabla": es una hoja con varios bloques de tabla separados por filas
vacías o títulos sueltos. `block_extractor.py` recorre cada hoja fila por fila reconociendo el
patrón `[filas vacías] → [título opcional] → [encabezado] → [filas de datos]` y produce un
`DataBlock` por cada tabla que encuentra.

### Celdas combinadas (merged cells)

Excel permite fusionar celdas para "ahorrarse" repetir un valor (una etiqueta de fila como "Sexo"
que abarca dos filas, un título que ocupa 8 columnas). `openpyxl` solo devuelve el valor en la
celda superior-izquierda de la fusión y deja el resto en blanco.

> **Regla:** se propaga (forward-fill) el valor de cualquier fusión vertical que cubra únicamente
> filas de datos (dos o más filas con números en el resto de columnas), pero **no** las fusiones
> que caen en la zona de encabezados. Fusionar ahí también rompería la detección de la fila de
> título y de la fila de años.

Además, el DANE suele omitir directamente la etiqueta de dominio en las filas siguientes de un
mismo grupo (sin fusión real), así que hay un segundo mecanismo,
`_forward_fill_orphan_first_column`, que solo actúa cuando la fila "huérfana" tiene exactamente la
forma de una fila de datos del mismo grupo (columna 2 con texto, resto numérico).

### Formato ancho → formato largo (unpivot)

Muchas tablas del DANE están en formato ancho: una columna por año, o una columna por
región/país. Para análisis y carga se necesita formato largo: una fila por combinación de
categoría y período.

**Antes (ancho):**

```
Dominio      2018   2019   2020
Nacional     17.8   16.9   18.1
Cabecera     10.4    9.7   11.0
```

**Después (largo):**

```
Dominio    Anio  Valor
Nacional   2018  17.8
Nacional   2019  16.9
Nacional   2020  18.1
Cabecera   2018  10.4
...
```

Esto ocurre cuando el encabezado termina en una columna tipo "Año" o "Dominio/País/Región" y la
fila inmediatamente debajo contiene, en vez de datos, los rótulos reales (los años o los nombres
de grupo). `_unpivot_wide_years` y `_unpivot_wide_groups` generan una fila nueva por cada celda de
valor, descartando las celdas vacías.

### Un caso específico del DANE: columna "Características..."

Algunas hojas traen una columna rotulada *"Características de la persona"* (con el valor
constante "Sexo" repetido) seguida de una columna sin encabezado que contiene el dato real
(Hombre/Mujer). `_fix_blank_characteristic_header` detecta este patrón puntual y renombra la
columna vacía a `Sexo Persona` o `Sexo Jefe Hogar` según el contexto, para que deje de perderse
como columna anónima.

## 2. Normalización

Cada bloque extraído pasa por `normalize_blocks()`, que actúa sobre encabezados y valores por
igual.

### Reparación de encoding (mojibake)

Los archivos fuente mezclan encodings: algunos vienen en latin-1/cp1252 y al leerlos como UTF-8
aparecen secuencias rotas ("Año" se convierte en un carácter de reemplazo ilegible).
`fix_mojibake()` reintenta decodificar el texto como latin-1 y como cp1252, y se queda con la
variante que tiene menos caracteres de reemplazo.

### Normalización de texto

| Transformación | Entrada | Salida |
|---|---|---|
| Unicode a forma canónica (NFC) | "Año" descompuesto | "Año" precompuesto |
| Espacios no separables → espacio normal | `"Dominio\xa0"` | `"Dominio "` |
| Colapso de espacios múltiples + trim | `"  Dominio   Nacional "` | `"Dominio Nacional"` |

Esto asegura que dos celdas visualmente idénticas pero con bytes distintos ("Año " con espacio
final invisible, vs "Año") se traten como el mismo valor al comparar encabezados entre archivos.

### Slugs de columna

Cada encabezado limpio se convierte además en una clave interna ("header key"): minúsculas, sin
tildes, sin símbolos, con guiones bajos. `"Privación por Analfabetismo"` se convierte en
`privacion_por_analfabetismo`. Estas claves son las que usa la etapa de clasificación para
reconocer una columna sin importar cómo esté escrito el encabezado original en cada archivo.

### Tipado de valores

Cada celda se re-tipa según el nombre de su columna: si la clave de columna es
`anio`/`ano`/`year`, se fuerza a entero; si el texto es numérico (tras cambiar coma por punto y
quitar el símbolo `%`), se convierte a `float` o a `int` cuando no tiene parte decimal; cualquier
otro valor se deja como texto ya normalizado. Las celdas vacías se convierten en `None`.

### Filas vacías y duplicadas

Una fila donde *todas* las celdas quedaron en `None` se descarta. Las filas restantes se
deduplican por igualdad exacta de todos sus valores ya normalizados y tipados, conservando la
primera aparición.

## 3. Clasificación en sub-tablas

El proyecto define 9 `TableSpec` en `schema.py` — una por indicador del IPM (IPM por dominio,
privaciones por hogar, incidencia por sexo, contribución relativa, población en pobreza
multidimensional, etc.). Cada una declara sus columnas destino, su **clave natural** (para
deduplicar/upsert) y qué claves de encabezado debe tener un bloque de origen para pertenecer a
esa tabla.

### Coincidencia por columnas, desempate por título

`match_table()` prueba cada `TableSpec` contra las claves de encabezado del bloque (incluyendo
alias, p. ej. `valor` → `ipm`, o `ano` → `anio`) y elige la especificación que resuelve más
columnas. Si dos specs empatan —por ejemplo, "incidencia por sexo de la persona" e "incidencia
por sexo del jefe de hogar" comparten exactamente las mismas columnas base— se usa el título del
bloque (`TITLE_HINTS`) para decidir cuál es.

### Año inferido del título

Algunos anexos (p. ej. "Contribuciones...") solo reportan el año más reciente y lo ponen en el
título de la tabla en vez de en una columna. Si el bloque no tiene columna de año,
`_infer_year_from_title()` extrae el último número de 4 dígitos plausible (1900–2100) del título
y lo usa como año.

### Deduplicación final por clave natural

Al consolidar todos los bloques de todos los archivos de un job en una misma sub-tabla, pueden
aparecer filas repetidas (el mismo dato en dos anexos distintos) o filas incompletas. Antes de
exportar, `_dedupe_rows()`:

- Descarta cualquier fila donde algún campo de la clave natural sea `None`.
- Deduplica por esa clave natural, quedándose con la primera aparición.
- Ordena primero por las columnas de categoría (dominio, sexo, variable...) y deja el año al
  final, para que el CSV se lea como una serie de tiempo agrupada, en vez de años intercalados
  entre grupos distintos.

## 4. Exportación

`exporter.py` añade a cada fila tres columnas de trazabilidad — `fuente`, `fecha_extraccion`,
`fecha_carga` — y escribe cada sub-tabla como un CSV independiente en
`datos_limpios/<tabla>.csv`, además de consolidar todas las hojas en un único
`datos_limpios.xlsx` para revisión manual. Los bloques que no calzaron con ninguna `TableSpec` se
exportan aparte en `sin_clasificar.csv` con su título, encabezados y archivo de origen, para que
alguien los revise a mano.

## 5. Carga a PostgreSQL

De las 9 sub-tablas, solo 3 tienen un mapeo acordado hacia el esquema estrella real de la base de
datos (`geographic_area` / `indicator` / `ipm_statistic`):

| Sub-tabla | indicator.code | Vista de referencia |
|---|---|---|
| `ipm_por_dominio` | `MPI` | `vw_ipm_by_domain` |
| `proporcion_privaciones` | `INTENSITY_A` | `vw_average_deprivations` |
| `privaciones_por_hogar` | un código por variable (ver abajo) | `vw_deprivations_by_variable` |

Las 6 sub-tablas restantes se siguen exportando a CSV/Excel, pero se omiten de la carga a
PostgreSQL hasta que el equipo acuerde su convención de `indicator.code`.

### Slug de indicador (para privaciones_por_hogar)

Como `privaciones_por_hogar` no tiene un indicador fijo (cada variable de privación es su propio
indicador), `_slug_indicator_code()` genera el código a partir del nombre de la variable:
mayúsculas, sin tildes, símbolos reemplazados por guion bajo, truncado a 50 caracteres (límite de
`varchar(50)` en la columna). Es determinístico — el mismo texto de entrada siempre produce el
mismo código — para que el `UPSERT` sea idempotente.

**Variable:** `Privación por Analfabetismo` → **indicator.code:** `PRIVACION_POR_ANALFABETISMO`

### Upsert idempotente

La carga completa de un job corre dentro de **una sola transacción**: si alguna tabla falla, se
revierte todo el job (no quedan cargas parciales). Cada fila se resuelve así:

1. `get_or_create_geographic_area()` busca o crea el área por `(name, level)`.
2. `get_or_create_indicator()` hace `UPSERT` por `code` (único).
3. `upsert_ipm_statistics()` inserta/actualiza la fila de `ipm_statistic` usando como clave
   `(geographic_area_id, indicator_id, period, breakdown_type, breakdown_value)` — volver a
   cargar el mismo job no duplica filas, las actualiza.

## Por qué se normaliza así: el problema de fondo

Todas estas reglas resuelven el mismo problema: los archivos del DANE están diseñados para
**lectura humana en Excel**, no para consumo por máquina. Usan fusión de celdas para "no
repetirse", ponen contexto (año, dominio) en el título en vez de en una columna, y mezclan
formato ancho y largo según lo que se vea mejor impreso. Ninguna de esas convenciones es estable
entre archivos ni entre años.

La normalización existe para que dos maneras distintas de expresar el mismo dato — `"Año "` vs
`"Año"`, una tabla ancha vs una larga, "Sexo Persona" vs una columna sin nombre — terminen en la
**misma representación canónica** antes de compararse o cargarse. Sin esto, cada archivo nuevo
del DANE rompería el mapeo a sub-tablas o, peor, generaría filas silenciosamente duplicadas con
claves ligeramente distintas.

La deduplicación por clave natural y el `UPSERT` en PostgreSQL persiguen la misma idea desde el
otro extremo: permiten volver a correr `clean` y `load` sobre el mismo job (o sobre jobs que se
solapan en período/dominio) sin que la base de datos acumule filas repetidas ni datos
inconsistentes.

## Límites actuales

- **6 / 9 tablas** sin mapeo a PostgreSQL — siguen disponibles solo como CSV/Excel hasta que se
  defina su `indicator.code`.
- **`sin_clasificar`** — un bloque que no calza con ninguna `TableSpec` no se pierde, pero
  tampoco se carga: requiere revisión manual del CSV de salida.
- **Heurísticas del DANE** — reglas como `_fix_blank_characteristic_header` o el forward-fill de
  columna huérfana están ajustadas a patrones observados en archivos concretos del DANE; un
  formato nuevo puede necesitar una regla nueva.

---

*Basado en el código de `app/cleaner/` en la rama `data-cleaner`.*
