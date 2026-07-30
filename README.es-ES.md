

# F1 Pit Wall

Un panel de control full-stack de ingeniero de carreras de Fórmula 1 con análisis impulsado por IA. Carga cualquier sesión histórica o conéctate a cronometraje en vivo: explora telemetría, estrategia, modelado de energía, reproducción de carreras y chatea con un ingeniero de carrera IA que obtiene datos reales mediante herramientas MCP.

![React](https://img.shields.io/badge/React-19-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![FastF1](https://img.shields.io/badge/FastF1-3.3+-red)
![Claude](https://img.shields.io/badge/AI-Claude%20Sonnet-purple)
![MCP](https://img.shields.io/badge/MCP-Tools-orange)
![Tests](https://img.shields.io/badge/Tests-121%20passing-brightgreen)

---

## Inicio Rápido

### Prerrequisitos

- Python 3.10+
- Node.js 18+
- Una [clave API de Anthropic](https://console.anthropic.com/) (para las funciones de chat con IA)

### Configuración

```bash
git clone <your-repo-url>
cd f1_dashboard

# Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e f1_mcp/

# Frontend
cd frontend
npm install
cd ..
```

### Ejecución

```bash
chmod +x start.sh
./start.sh
```

Abre http://localhost:3000 y listo.

- **Frontend:** http://localhost:3000
- **API del Backend:** http://localhost:8000
- **Detener:** `./start.sh stop`

### Primeros Pasos

1. Selecciona un año, Gran Premio y tipo de sesión en la página principal
2. Haz clic en **Load Session** (la primera carga descarga de los servidores de F1 ~10-30s, se almacena en caché después)
3. Explora cualquier página desde la barra lateral
4. Abre el **chat IA** (burbuja roja, esquina inferior derecha) — ingresa tu clave API de Anthropic una vez, luego pregunta lo que quieras

---

## Funcionalidades

| Página | Qué Hace |
|------|-------------|
| **Race Command** | Resultados, línea temporal de estrategia de neumáticos, clima, conteo de SC/VSC, abandonos (DNF), vuelta rápida |
| **Telemetry Lab** | Superposiciones de velocidad/acelerador/freno de múltiples pilotos, mapa de circuito con mapas de calor |
| **Performance Studio** | Evolución de tiempos por vuelta, degradación de neumáticos, tiempos corregidos por combustible, clasificaciones ajustadas por ritmo |
| **Pit Strategy** | Línea temporal de stints, detección de undercut/overcut, detalles de paradas en boxes, mapeo de eventos SC |
| **Energy Map** | Modelo de recolección/depósito MGU-K (reglas 2026: 350kW), estado de carga de la batería, detección de clipping |
| **Circuit Lab** | Circuito interactivo con zonas de DRS, marcadores de sectores, análisis curva por curva |
| **Race Replay** | Mapa de circuito animado con pilotos, modelo de probabilidad de victoria, barrido de precisión |
| **Compare GP** | Comparación directa entre sesiones: velocidades en curvas, deltas por sector, comparación de tiempos por vuelta |
| **Live Pit Wall** | Transmisión SignalR en tiempo real, tarjetas de pilotos, seguimiento de gaps, alertas de estrategia |
| **AI Debrief** | Análisis de carrera impulsado por Claude con predicciones para la siguiente carrera |

### Chat del Ingeniero de Carrera IA

El widget de chat utiliza **llamadas a herramientas** en lugar de volcar todos los datos en el prompt. Claude selecciona qué datos obtener por pregunta: 21 herramientas que cubren resultados, tiempos por vuelta, paradas en boxes, telemetría, energía, predicciones, adelantamientos y más.

Los nombres de los pilotos se coinciden de forma difusa: "Leclerc", "charles", "LEC", "16" funcionan todos. Las llamadas a herramientas se muestran como etiquetas verdes debajo de cada mensaje para que puedas ver exactamente qué datos usó Claude.

---

## Stack Tecnológico

| Capa | Tecnología |
|-------|------|
| **Backend** | Python, FastAPI, FastF1, NumPy, SciPy, Pandas |
| **Frontend** | React 19, Vite, Tailwind CSS, Plotly.js, Framer Motion |
| **IA** | API de Anthropic Claude (llamadas a herramientas) |
| **MCP** | Paquete f1_mcp (servidor MCP local para Claude Desktop) |
| **Datos** | Cronometraje oficial de F1 vía FastF1 (almacenado en caché localmente) |
| **Pruebas** | pytest (121 pruebas — unitarias + de integración) |

---

## Servidor MCP de F1

El directorio `f1_mcp/` es un paquete de Python independiente e instalable que expone datos de carreras de F1 como herramientas MCP. Impulsa el chat IA del panel **y** funciona como servidor independiente para Claude Desktop, Cursor o cualquier cliente compatible con MCP.

### Cómo Funciona

```
Claude Desktop / Chat del Panel
       |
       | "¿Quién ganó la carrera de Baréin 2024?"
       v
  Claude selecciona herramientas:  race_result()
       |
       v
  El servidor f1_mcp ejecuta la herramienta
       |
       v
  FastF1 carga los datos (en caché local)
       |
       v
  Retorna JSON estructurado -> Claude responde
```

Sin API alojada. Sin credenciales necesarias para los datos. Todo se ejecuta localmente en tu máquina.

### Uso con Claude Desktop

1. Instala el paquete:
```bash
source venv/bin/activate
pip install -e f1_mcp/
```

2. Añade a la configuración de Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "f1": {
      "command": "/path/to/f1_dashboard/venv/bin/python",
      "args": ["-m", "f1_mcp"]
    }
  }
}
```
Usa la ruta completa a tu Python de venv (ejecuta `which python` con venv activado para encontrarla).

3. Reinicia Claude Desktop (Cmd+Q, vuelve a abrir). Verás un ícono de herramientas en la entrada del chat.

4. Pregunta a Claude: *"Carga la clasificación de Mónaco 2024 y dime quién consiguió la pole"*

### Herramientas MCP

| Herramienta | Descripción |
|------|-------------|
| `load_session` | Carga una carrera/clasificación/práctica — nombres de carreras difusos ("monza", "spa", "silverstone") |
| `season_calendar` | Calendario de F1 para un año |
| `race_result` | Clasificación completa de la carrera |
| `qualifying_result` | Tiempos Q1/Q2/Q3 |
| `lap_times` | Datos vuelta a vuelta de un piloto |
| `fastest_laps` | Vueltas rápidas clasificadas |
| `pit_stops` | Detalles de paradas en boxes |
| `tire_stints` | Compuesto de neumáticos y desglose de stints |
| `driver_telemetry` | Resumen de velocidad/acelerador/freno de una vuelta |
| `head_to_head` | Comparación entre dos pilotos en todas las métricas |
| `weather` | Condiciones meteorológicas de la sesión |
| `session_summary` | Visión rápida (ganador, abandonos, vueltas, vuelta rápida) |
| `track_evolution` | Cómo cambiaron el agarre y el ritmo durante la sesión |
| `overtake_analysis` | Cambios de posición y deltas de ritmo entre pilotos |
| `identify_driver` | Resuelve un nombre difuso a información completa del piloto |
| `list_drivers` | Todos los pilotos de la sesión |
| `session_status` | Verifica qué sesión está cargada |

El chat del panel tiene 4 herramientas adicionales que usan análisis específicos del backend: `energy_analysis`, `tyre_predictions`, `session_insights`, `overtake_probability`, `win_probability`.

### Normalización de Entrada Difusa

No es necesario conocer códigos exactos. El paquete resuelve:

| Dices | Se resuelve en |
|---------|-------------|
| "Leclerc", "charles", "LEC", "16" | Charles Leclerc (LEC) |
| "checo", "Perez", "11" | Sergio Perez (PER) |
| "spa" | Gran Premio de Bélgica |
| "monza" | Gran Premio de Italia |
| "silverstone" | Gran Premio de Gran Bretaña |
| "qualifying", "quali", "Q" | Sesión de clasificación |

---

## Pruebas

El paquete f1_mcp tiene un conjunto completo de pruebas:

```bash
cd f1_mcp

# Solo pruebas unitarias (sin red, instantáneo)
pytest tests/ -m "not integration" -v

# Suite completa de pruebas (descarga datos de F1 en la primera ejecución, en caché después)
pytest tests/ -v
```

**121 pruebas** que cubren:
- 60 pruebas de normalización (códigos de pilotos, nombres, apodos, números, carreras, sesiones)
- 40 pruebas del gestor de sesiones (ciclo de vida, extracción de datos, carga difusa, manejo de errores)
- 21 pruebas del servidor MCP (registro de herramientas, ejecución, formato de salida)

---

## Estructura del Proyecto

```
f1_dashboard/
  backend/
    main.py                # Backend FastAPI (todos los endpoints + chat IA)
  frontend/src/
    pages/                 # 11 componentes de página
    components/
      ChatWidget.jsx       # Chat IA con visualización de llamadas a herramientas
      Layout.jsx           # Navegación de barra lateral
      CircuitSVG.jsx       # Renderizador de circuito SVG
    hooks/
      useApi.js            # Envoltorio para Fetch
  f1_mcp/                  # Paquete independiente de servidor MCP
    src/f1_mcp/
      normalize.py         # Resolución difusa de pilotos/carreras/sesiones
      session.py           # Gestor de sesiones FastF1 + extracción de datos
      server.py            # Servidor MCP + definiciones de herramientas
    tests/                 # 121 pruebas (pytest)
    pyproject.toml         # Configuración del paquete
  cache/                   # Caché de datos FastF1 (creación automática)
  start.sh                 # Script de inicio/parada
  requirements.txt         # Dependencias de Python
```

---

## Comandos para Desarrolladores

```bash
# Iniciar todo
./start.sh

# Detener todo
./start.sh stop

# Reinicio rápido
./start.sh stop && ./start.sh

# Reconstruir frontend + reiniciar
./start.sh stop
cd frontend && npm install && npm run build && cd ..
./start.sh

# Instalar/actualizar todas las dependencias
source venv/bin/activate
pip install -r requirements.txt
pip install -e f1_mcp/

# Eliminar procesos obsoletos (si los puertos están bloqueados)
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null

# Ejecutar pruebas
cd f1_mcp && pytest tests/ -v
```

---

## Endpoints de la API

| Endpoint | Descripción |
|----------|-------------|
| `POST /api/session/load` | Cargar una sesión de F1 |
| `GET /api/session/overview` | Resultados, clima, estrategia, métricas |
| `GET /api/session/drivers` | Lista de pilotos con colores de equipo |
| `GET /api/session/telemetry/multi` | Telemetría de múltiples pilotos |
| `GET /api/session/laptimes` | Tiempos por vuelta, degradación, SC/VSC |
| `GET /api/session/predictions` | Vida de neumáticos, clasificaciones ajustadas por ritmo |
| `GET /api/session/energy` | Modelo de recolección/depósito de energía |
| `GET /api/session/pitstrategy` | Paradas en boxes, stints, undercut/overcut |
| `GET /api/session/replay` | Probabilidad de victoria por vuelta |
| `GET /api/session/insights` | Comentarios de carrera generados automáticamente |
| `GET /api/session/overtake-probability` | Puntuación de adelantamientos |
| `GET /api/session/track-evolution` | Cambios de agarre/temperatura |
| `GET /api/session/circuit` | Diseño del circuito con zonas de DRS |
| `GET /api/session/trackmap` | Circuito con superposición de telemetría |
| `POST /api/session/chat` | Chat IA (llamadas a herramientas) |
| `POST /api/session/debrief` | Debrief de carrera IA |
| `GET /api/live/data` | Datos de cronometraje en vivo |
| `POST /api/live/start` | Iniciar grabación en vivo |
| `POST /api/live/stop` | Detener grabación en vivo |
| `GET /api/live/driver/{n}` | Detalle de piloto en vivo |
| `GET /api/live/driver/{n}/zones` | Análisis de telemetría por zona |
| `POST /api/compare` | Comparación entre sesiones |
| `GET /api/events/{year}` | Calendario de F1 |

---

## Notas

- **Caché:** FastF1 almacena en caché los datos de la sesión en `cache/`. La primera carga contacta a los servidores de F1; las cargas posteriores son instantáneas.
- **Chat IA:** Usa llamadas a herramientas (no stuffing de contexto). Claude selecciona qué datos obtener por pregunta. 21 herramientas disponibles. Las llamadas a herramientas se muestran como etiquetas verdes en la interfaz.
- **AI Debrief:** Requiere una clave API de Anthropic ingresada en la interfaz.
- **Cronometraje en Vivo:** Se conecta al flujo SignalR de F1 durante sesiones en vivo. Análisis incremental para actualizaciones por debajo de un segundo.
- **Servidor MCP:** El paquete f1_mcp es un instalable independiente que funciona con Claude Desktop de forma independiente al panel.
- **Datos:** Todos los datos de F1 provienen de servidores de cronometraje públicos vía FastF1. No se necesitan claves API ni cuentas para acceder a los datos.

---

## Licencia

MIT
