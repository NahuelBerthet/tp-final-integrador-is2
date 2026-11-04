# Guía de ejecución — TP Final Integrador IS2

> **Sistema:** Infraestructura de datos corporativos con patrones Singleton, Proxy y Observer  
> **Base de datos:** AWS DynamoDB (tablas `CorporateData` y `CorporateLog`)  
> **Lenguaje:** Python 3.13+

---

## 1. Pre-requisitos

### 1.1 Credenciales AWS
Antes de ejecutar cualquier programa, configurar las credenciales de AWS:

```bash
aws configure
```

Ingresar cuando lo solicite:
- **AWS Access Key ID** → (clave de acceso)
- **AWS Secret Access Key** → (clave secreta)
- **Default region name** → `us-east-1` (o la región donde están las tablas)
- **Default output format** → `json`

Las tablas DynamoDB necesarias son:
- `CorporateData` — clave primaria: `id` (String)
- `CorporateLog`  — clave primaria: `id` (String)

### 1.2 Entorno virtual Python (ya creado)
El entorno `.venv` ya está configurado en el proyecto. Activarlo con:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat
```

---

## 2. Estructura de archivos relevantes

```
tp-final-integrador-is2/
├── singletonproxyobserver.py   ← Punto de entrada del SERVIDOR
├── singletonclient.py          ← Punto de entrada del CLIENTE get/set/list
├── observerclient.py           ← Punto de entrada del CLIENTE observer
├── data/
│   ├── input/
│   │   ├── input_get.json      ← Registros para consultar
│   │   ├── input_set.json      ← Registros para crear o modificar
│   │   └── input_list.json     ← Registros para listar
│   └── output/
│       |── respuesta_get_*.json    ← Respuesta de consulta get
│       |── respuesta_set_*.json    ← Respuesta de consulta set
│       |── respuesta_list_*.json    ← Respuesta de consulta list
├── src/
│   └── tp_final_integrador_is2/
│       ├── database.py         ← Patrón Singleton (CorporateData + CorporateLog)
│       ├── observer.py         ← Patrón Observer (SubscriptionManager)
│       ├── proxy.py            ← Patrón Proxy (CorporateDataProxy)
│       ├── singletonproxyobserver.py   ← Lógica del servidor
│       ├── singletonclient.py          ← Lógica del cliente
│       └── observerclient.py           ← Lógica del observer
└── tests/
|    ├── test_acceptance.py      ← Tests de aceptación (camino feliz)
|    ├── test_singletonclient.py
|    ├── test_observerclient.py
|    ├── test_singletonproxyobserver.py
|    ├── test_database.py
|    ├── test_observer.py
|    └── test_proxy.py
|── README.md         ← Naturaleza del problema 
|── CHANGELOG.md      ← Memoria de los cambios realizados
|── CONTEXT.md        ← Promps y respuestas de la IA
```

---

## 3. Ejecutar el servidor de aplicaciones

El servidor debe iniciarse **primero**, antes que cualquier cliente.

```bash
# Forma básica (puerto 8080 por defecto)
python singletonproxyobserver.py

# Especificando puerto
python singletonproxyobserver.py -p=9090

# Con salida de depuración verbose
python singletonproxyobserver.py -p=8080 -v

# Especificando host e interfaz de red
python singletonproxyobserver.py -p=8080 -s=127.0.0.1 -v
```

El servidor queda **corriendo en espera de conexiones**. Para detenerlo: `Ctrl + C`.

---

## 4. Ejecutar el cliente Singleton (get / set / list)

El cliente lee un archivo JSON de entrada y envía el requerimiento al servidor.

### 4.1 Formato del archivo JSON de entrada

```json
{
  "UUID": "1234",
  "ACTION": "get",
  "ID": "NahuelB_tpfi"
}
```

| Campo    | Obligatorio          | Descripción                                      |
|----------|----------------------|--------------------------------------------------|
| `UUID`   | No (se autodetecta)  | Identificador de CPU. Se genera automáticamente si falta |
| `ACTION` | **Sí**               | `"get"`, `"set"` o `"list"`                     |
| `ID`     | Solo para get y set  | Clave del registro en CorporateData              |
| demás    | Solo para set        | Campos del tuple CorporateData a modificar       |

### 4.2 Ejemplos de archivos de entrada

**Consultar un registro (get):**
```json
{
  "UUID": "1234",
  "ACTION": "get",
  "ID": "NahuelB_tpfi"
}
```

**Modificar/crear un registro (set):**
```json
{
  "UUID": "1234",
  "ACTION": "set",
  "ID": "NahuelB_tpfi",
  "cp": "3260",
  "CUIT": "30-70925411-8",
  "domicilio": "25 de Mayo 385-1P",
  "localidad": "Concepcion del Uruguay",
  "provincia": "Entre Rios",
  "sede": "FCyT",
  "telefono": "03442 20-3411",
  "web": "http://www.uader.edu.ar"
}
```

**Listar todos los registros (list):**
```json
{
  "UUID": "123456789",
  "ACTION": "list"
}
```

### 4.3 Comandos de ejecución

```bash
# Salida por consola (stdout)
python singletonclient.py -i=input.json

# Salida a archivo JSON
python singletonclient.py -i=input.json -o=output.json

# Con verbose y servidor remoto
python singletonclient.py -i=input.json -o=output.json -s=192.168.1.10 -p=8080 -v
```

| Argumento | Descripción                                     | Default     |
|-----------|-------------------------------------------------|-------------|
| `-i`      | **Obligatorio.** Archivo JSON de entrada        | —           |
| `-o`      | Archivo JSON de salida (opcional)               | stdout      |
| `-s`      | Host del servidor                               | `localhost` |
| `-p`      | Puerto TCP del servidor                         | `8080`      |
| `-v`      | Modo verbose (trazas de depuración)             | desactivado |

---

## 5. Ejecutar el cliente Observer (suscriptor)

El observer se conecta al servidor y **queda escuchando** notificaciones en tiempo real cada vez que se realiza un `set`.

```bash
# Conexion basica (localhost:8080)
python observerclient.py

# Especificando servidor y puerto
python observerclient.py -s=127.0.0.1 -p=8080

# Guardando notificaciones en archivo
python observerclient.py -s=127.0.0.1 -p=8080 -o=notificaciones.json

# Con retry personalizado y verbose
python observerclient.py -s=127.0.0.1 -p=8080 -r=15 -v
```

| Argumento | Descripción                                          | Default      |
|-----------|------------------------------------------------------|--------------|
| `-s`      | Host del servidor                                    | `localhost`  |
| `-p`      | Puerto TCP del servidor                              | `8080`       |
| `-o`      | Archivo de salida para notificaciones (opcional)     | stdout       |
| `-r`      | Intervalo de reintento en segundos (server caído)    | `30`         |
| `-v`      | Modo verbose                                         | desactivado  |

El cliente solo termina con `Ctrl + C` o por excepción no recuperable.  
Si el servidor cae, **reintenta automáticamente** cada `-r` segundos.

---

## 6. Presentacion


### Servidor
```bash
python singletonproxyobserver.py -p=8080 -v
```

### Observer (suscriptor)
```bash
python observerclient.py -s 127.0.0.1 -p=8080 -v
```

###  Cliente Singleton

**Crear el registro (set)**
```bash
python singletonclient.py -i .\data\input\input_set.json -o .\data\output\respuesta_set.json -v
```

**Consultar el registro (get)**
```bash
python singletonclient.py -i .\data\input\input_get.json -o .\data\output\respuesta_get.json -v
```

**Listar todos los registros (list)**
```bash
python singletonclient.py -i .\data\input\input_list.json -o .\data\output\respuesta_list.json -v
```

---

## 7. Tests automatizados

### Todos los tests
```bash
python -m pytest -v
```

### Solo los tests de aceptación (camino feliz)
```bash
python -m pytest tests\test_acceptance.py -v
```

### Con reporte de cobertura
```bash
python -m pytest --cov=tp_final_integrador_is2 --cov-report=term-missing
```

### Verificacion de calidad de codigo
#### Ruff
```bash
ruff check src tests
```
#### Black
```bash
black . # --check para validar
```
#### PEP8
```bash
ruff check --select E,W .
```
#### PEP257
```bash
ruff check --select D .
```
#### MYPY
```bash
mypy src tests
```
#### PYRIGHT
```bash
pyright src tests
```
---

## 8. Tabla de patrones de diseño implementados

| Patron       | Clase(s)                                    | Archivo          | Rol                                              |
|--------------|---------------------------------------------|------------------|--------------------------------------------------|
| **Singleton** | `CorporateDataRepository`                  | `database.py`    | Unica instancia de acceso a tabla CorporateData  |
| **Singleton** | `CorporateLogRepository`                   | `database.py`    | Unica instancia de acceso a tabla CorporateLog   |
| **Observer**  | `SubscriptionManager`, `SocketObserver`    | `observer.py`    | Notificacion en tiempo real a clientes subscriptos |
| **Proxy**     | `CorporateDataProxy`, `CorporateDataService` | `proxy.py`     | Auditoria, control de acceso y delegacion        |
| **Servidor**  | `SingletonProxyObserverServer`             | `singletonproxyobserver.py` | Integra los 3 patrones via TCP      |

---

## 9. Respuestas esperadas del servidor

| Accion     | Respuesta exitosa                          | Respuesta de error |
|------------|--------------------------------------------|--------------------|
| `get`      | JSON con el tuple CorporateData solicitado | `"Error"`          |
| `set`      | JSON con el tuple CorporateData modificado | `"Error"`          |
| `list`     | Array JSON con todos los registros         | `"Error"`          |
| `subscribe`| (sin respuesta inmediata — espera eventos) | —                  |

Cada operacion genera ademas un registro en la tabla **CorporateLog** con:
- `id` — UUID de la entrada de log
- `CPUid` / `UUID` — identificador del cliente solicitante
- `sessionid` — identificador unico de sesion
- `action` — accion realizada
- `timestamp` — fecha y hora de la operacion
- `requested_id` — ID del registro accedido (solo en `get` y `set`)

