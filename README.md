# SingletonProxyObserverTPFI

**Trabajo Práctico Final Integrador — Ingeniería de Software II**
Universidad Autónoma de Entre Ríos (UADER) · Facultad de Ciencia y Tecnología (FCyT)

Implementación en Python de un sistema cliente/servidor que provee servicios corporativos de datos centralizados sobre **AWS DynamoDB**, aplicando los patrones de diseño **Singleton**, **Proxy** y **Observer**.

---

## Tabla de contenidos

1. [Descripción del proyecto](#descripción-del-proyecto)
2. [Arquitectura](#arquitectura)
3. [Componentes](#componentes)
4. [Patrones de diseño aplicados](#patrones-de-diseño-aplicados)
5. [Modelo de datos](#modelo-de-datos)
6. [Protocolo de comunicación](#protocolo-de-comunicación)
7. [Requisitos previos e instalación](#requisitos-previos-e-instalación)
8. [Uso](#uso)
9. [Estructura del proyecto](#estructura-del-proyecto)
10. [Calidad, pruebas y seguridad](#calidad-pruebas-y-seguridad)
11. [CI/CD y documentación](#cicd-y-documentación)
12. [Versionado y archivos de control](#versionado-y-archivos-de-control)
13. [Uso de herramientas de IA](#uso-de-herramientas-de-ia)
14. [Licencia](#licencia)

---

## Descripción del proyecto

Como parte del despliegue de un sistema aplicativo, se requieren componentes que soporten la infraestructura y brinden servicios corporativos para la adquisición de datos centralizados. Entre los datos gestionados se encuentran:

- Datos oficiales de dirección.
- Número de CUIT.
- Número de teléfono de contacto.
- Identificador único de secuencia.

El sistema implementa tres funciones principales:

| Acción | Descripción |
|--------|-------------|
| `get` | Recuperar un registro de datos corporativos por su ID. |
| `set` | Modificar (o crear, si no existe) un registro de datos corporativos. |
| `list` | Listar la totalidad de la tabla de datos corporativos. |

Adicionalmente, los clientes pueden **suscribirse** (`subscribe`) para recibir notificaciones cada vez que se modifique la base de datos, y toda acción queda registrada en una **pista de auditoría**.

---

## Arquitectura

```
┌──────────────────┐                         ┌─────────────────────────────┐
│ SingletonClient  │──── JSON / TCP ────┐    │                             │
└──────────────────┘                    │    │  SingletonProxyObserverTPFI │      ┌───────────────┐
                                        ├───▶│  (servidor de aplicaciones) │─────▶│  AWS DynamoDB │
┌──────────────────┐                    │    │                             │      │ ├ CorporateData│
│ ObserverClient   │◀─── notificaciones ┘    │  Proxy · Singleton · Observer│      │ └ CorporateLog │
└──────────────────┘     (socket abierto)    └─────────────────────────────┘      └───────────────┘
```

Los clientes envían requerimientos en formato JSON mediante sockets TCP al servidor de aplicaciones. Este actúa como intermediario (proxy) hacia DynamoDB, registra cada acción en la tabla de auditoría y notifica a los observadores suscriptos cuando hay modificaciones.

---

## Componentes

El proyecto se compone de tres programas aplicativos:

### 1. `singletonclient.py` — SingletonClient

Cliente que realiza requerimientos de consulta (`get`, `list`) o actualización (`set`) sobre `CorporateData`.

```bash
python singletonclient.py -i=input.json [-o=output.json] [-v]
```

| Argumento | Descripción |
|-----------|-------------|
| `-i` | Archivo JSON de entrada con el requerimiento (obligatorio). |
| `-o` | Archivo JSON de salida. Si se omite, la respuesta se emite por salida estándar. |
| `-v` | Activa mensajes de trace/debug (módulo `logging`) por salida estándar. |

Se comunica con el servidor mediante un socket TCP en puerto configurable (típicamente `localhost:8080`).

**Respuestas esperadas:**

- `get`: registro solicitado de `CorporateData` o `"Error"`.
- `set`: registro modificado o `"Error"`.
- `list`: array con todos los registros de la tabla o `"Error"`.

### 2. `observerclient.py` — ObserverClient

Cliente suscripto como observador de cambios sobre `CorporateData`.

```bash
python observerclient.py [-s=hostname] [-p=port] [-o=output.json] [-v]
```

| Argumento | Descripción |
|-----------|-------------|
| `-s` | Host del servidor (por defecto `localhost`). |
| `-p` | Puerto del servidor (por defecto `8080`). |
| `-o` | Archivo JSON donde se vuelcan las notificaciones recibidas (además de la salida estándar). |
| `-v` | Activa mensajes de trace/debug. |

**Comportamiento:**

- Envía la acción `subscribe` mediante POST y **mantiene el socket abierto** esperando notificaciones.
- Cada notificación (JSON) se muestra por salida estándar y, si se informó, en `output.json`.
- Si el socket se interrumpe, reintenta la conexión periódicamente (cada **30 segundos**, parametrizable) y, al reconectar, reenvía la acción de suscripción.
- Solo termina por cancelación manual o por una excepción distinta del cierre del socket.

### 3. `singletonproxyobserver.py` — SingletonProxyObserverTPFI

Servidor de aplicaciones que opera como proxy de acceso a la base de datos, con acceso singleton y notificación mediante observer, generando además la pista de auditoría.

```bash
python singletonproxyobserver.py [-p=port] [-v]
```

| Argumento | Descripción |
|-----------|-------------|
| `-p` | Puerto TCP de escucha (por defecto `*:8080`). |
| `-v` | Activa mensajes de trace/debug. |

**Funcionalidad por acción recibida:**

| Acción | Comportamiento |
|--------|----------------|
| `subscribe` | Registra el UUID del solicitante, genera registro de auditoría en `CorporateLog` (UUID, sesión, acción, timestamp) y registra el socket para notificaciones posteriores. Admite múltiples suscriptores. |
| `get` | Registra auditoría (UUID, sesión, acción, ID solicitado, timestamp), devuelve el registro solicitado o error, y cierra la conexión. |
| `list` | Registra auditoría (UUID, sesión, acción, timestamp), devuelve todos los registros o error, y cierra la conexión. |
| `set` | Recibe el registro a modificar (los campos no informados no se modifican; si la clave no existe se crea un registro nuevo con los campos no informados en blanco), registra auditoría, retransmite el registro al cliente solicitante **y a todos los suscriptos**. |

El servidor solo termina por cancelación manual o por una excepción distinta del cierre de un socket.

---

## Patrones de diseño aplicados

| Patrón | Aplicación en `singletonproxyobserver.py` |
|--------|-------------------------------------------|
| **Singleton** | El acceso físico a las tablas `CorporateData` y `CorporateLog` se implementa mediante sendas clases bajo el patrón Singleton (una instancia por tabla). |
| **Observer** | La gestión de suscripciones y la notificación de cambios a los clientes suscriptos. |
| **Proxy** | La gestión de las actualizaciones (`list`/`get`/`set`) se canaliza a través de un proxy que media el acceso a la base de datos. |

Toda la implementación debe ser **modular** y utilizar técnicas de **OOP** siempre que sea posible. Los casos de prueba verifican que las clases se implementan efectivamente como los patrones requeridos.

---

## Modelo de datos

Se utilizan dos tablas **previamente creadas** en AWS DynamoDB:

- **`CorporateData`**: contiene los datos corporativos centralizados.
- **`CorporateLog`**: contiene los registros de accesos y modificaciones (pista de auditoría).

### Formato JSON del tuple `CorporateData`

```json
{
  "id": "UADER-FCyT-IS2",
  "cp": "3260",
  "CUIT": "30-70925411-8",
  "domicilio": "25 de Mayo 385-1P",
  "idreq": "473",
  "idSeq": "1146",
  "localidad": "Concepción del Uruguay",
  "provincia": "Entre Rios",
  "sede": "FCyT",
  "seqID": "23",
  "telefono": "03442 43-1442",
  "web": "http://www.uader.edu.ar"
}
```

### Datos de auditoría (`CorporateLog`)

Cada acción registra, según corresponda: **UUID** del cliente (obtenido con `uuid.getnode()`), **sesión** (obtenida con `uuid.uuid4()`), **acción solicitada**, **ID solicitado** (en `get`) y **timestamp**. Los datos de la CPU pueden obtenerse con el paquete `platform`.

---

## Protocolo de comunicación

Los mensajes se intercambian como documentos JSON sobre sockets TCP.

**Ejemplo de requerimiento (`input.json`):**

```json
{
  "UUID": "XXXXXXXXXXXXXXXXXXXXXXX",
  "ID": "ZZZZZZZZZZZZZZZZZZZZZZZ",
  "ACTION": "get"
}
```

- `get`: requiere `UUID`, `ID` y `ACTION`.
- `set`: requiere además todos los campos del tuple `CorporateData` a modificar.
- `list`: **no** se informa `ID`; la respuesta es un array con todos los tuples.
- `subscribe`: requiere `UUID` y `ACTION`.

### Secuencia general

1. **Subscribe:** `ObserverClient` → Servidor: `{UUID, "subscribe"}` → registro en `CorporateLog` → respuesta `OK | Error`.
2. **Set:** `SingletonClient` → Servidor: `{UUID, ID, "set", Data}` → actualización en `CorporateData` + registro en `CorporateLog` → notificación `{UUID, ID, "change", Data}` a los observadores → respuesta `OK | Error` al cliente.
3. **Get:** `SingletonClient` → Servidor: `{UUID, ID, "get"}` → lectura de `CorporateData` + registro en `CorporateLog` → respuesta `{UUID, "get", Data}`.

---

## Requisitos previos e instalación

> Antes de ejecutar el proyecto, complete la instalación y configuración de pre-requisitos indicada en la nota de aplicación **“IS2_NAPP_Arquitectura AWS Python”** (credenciales AWS, acceso a DynamoDB y tablas `CorporateData` y `CorporateLog`).

```bash
# 1. Clonar el repositorio
git clone <URL-del-repositorio>
cd <nombre-del-proyecto>

# 2. Crear y activar el ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
```

---

## Uso

1. **Iniciar el servidor** (terminal 1):

   ```bash
   python singletonproxyobserver.py -p=8080 -v
   ```

2. **Iniciar un observador** (terminal 2):

   ```bash
   python observerclient.py -s=localhost -p=8080 -o=notificaciones.json -v
   ```

3. **Ejecutar requerimientos** (terminal 3):

   ```bash
   python singletonclient.py -i=get.json
   python singletonclient.py -i=set.json -o=salida.json
   python singletonclient.py -i=list.json
   ```

   Al ejecutar un `set`, el observador de la terminal 2 recibirá la notificación del cambio.

---

## Estructura del proyecto

El esqueleto del proyecto se genera con **CookieCutter**. Estructura orientativa:

```
.
├── src/
│   ├── singletonclient.py
│   ├── observerclient.py
│   ├── singletonproxyobserver.py
│   └── ...                      # módulos de soporte (singletons, proxy, observer, log)
├── tests/                       # pruebas unitarias y de aceptación (Pytest)
├── docs/                        # documentación generada (pdoc / Sphinx)
├── diagrams/                    # diagramas UML de actividad y de estado
├── .github/workflows/           # workflow de CI/CD
├── CONTEXT.md
├── CHANGELOG.md
├── README.md
├── LICENSE
├── VERSION
├── BUILD
└── requirements.txt
```

---

## Calidad, pruebas y seguridad

### Pruebas de aceptación automatizadas

Cubren, como mínimo, los siguientes casos y verifican en cada uno el impacto en las tablas `CorporateData` y `CorporateLog`:

- Camino feliz de **cada una** de las acciones, incluyendo los registros en `CorporateLog`.
- Llamada a los programas con argumentos malformados (cada uno).
- Requerimiento sin indicar los datos mínimos necesarios.
- Manejo en los clientes de servidor aplicativo caído.
- Intento de levantar dos veces el servidor de aplicaciones.
- Verificación de que las clases implementan efectivamente los patrones Singleton, Proxy y Observer.

### Herramientas de calidad y seguridad

| Herramienta | Propósito | Criterio de aceptación |
|-------------|-----------|------------------------|
| `ruff` | Reglas de formato y linting | Sin errores |
| `black` | Formato consistente | Sin diferencias |
| PEP 8 | Reglas de formateo | Cumplimiento |
| PEP 257 | Convenciones de docstrings | Sin errores |
| `mypy` | Chequeo estático de tipos | Sin errores |
| `pyright` | Chequeo estático de tipos | Sin errores |
| `pytest` + cobertura | Tests unitarios | Cobertura ≥ **85 %** |
| `bandit` | Evaluación básica de seguridad | Sin observaciones |
| `trufflehog` | Detección de secretos *(opcional)* | — |

Ejecución típica:

```bash
ruff check .
black --check .
mypy src
pyright src
pytest --cov=src --cov-fail-under=85
bandit -r src
```

### Trazas y debug

Los mensajes de trace y debug se emiten por salida estándar mediante el módulo `logging` y se activan únicamente con el argumento `-v` en cada programa.

---

## CI/CD y documentación

- Se automatiza un **workflow en GitHub Actions** que integra la fase completa de CI/CD (formato, análisis estático, tests, seguridad).
- Con cada **Pull Request exitoso** se genera o actualiza la documentación básica con **pdoc** o **Sphinx**, y se actualiza `requirements.txt`.
- La documentación del funcionamiento de los módulos se mantiene actualizada con cada PR.

---

## Versionado y archivos de control

| Archivo | Contenido |
|---------|-----------|
| `README.md` | Naturaleza del proyecto (este documento), mantenido actualizado. |
| `CHANGELOG.md` | Registro de los cambios realizados. |
| `CONTEXT.md` | Prompts utilizados en caso de emplear herramientas de IA. |
| `requirements.txt` | Librerías necesarias para el ambiente virtual. |
| `VERSION` / `BUILD` | Registro de versión y número de build. |
| `LICENSE` | Licencia MIT. |

---

## Uso de herramientas de IA

En caso de utilizar herramientas de IA durante el desarrollo, los prompts empleados se documentan en [`CONTEXT.md`](CONTEXT.md).

---

## Licencia

Este proyecto se distribuye bajo la licencia **MIT**. Ver el archivo [`LICENSE`](LICENSE).

---

## Nota académica

Este trabajo práctico se realiza en forma **individual**. El sistema registra el identificador único de cada CPU donde se ejecuta el trabajo con fines de auditoría, y la cuenta AWS que contiene las tablas tiene activado el módulo de auditoría para registrar la IP y la dirección MAC de los accesos realizados.
