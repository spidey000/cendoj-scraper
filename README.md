# 🇪🇸 Cendoj PDF Discovery System

**Sistema industrial de descubrimiento exhaustivo de enlaces PDF del Cendoj**

[![Status](https://img.shields.io/badge/status-active-brightgreen.svg)](https://github.com/spidey000/cendoj-scraper)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 📖 Tabla de Contenidos

- [Descripción](#descripción)
- [Características](#características)
- [Arquitectura](#arquitectura)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Uso del CLI](#uso-del-cli)
- [Esquema de Base de Datos](#esquema-de-base-de-datos)
- [Anti-Blocking Stack](#anti-blocking-stack)
- [Rendimiento Estimado](#rendimiento-estimado)
- [Troubleshooting](#troubleshooting)
- [Desarrollo](#desarrollo)
- [Licencia](#licencia)

---

## 📝 Descripción

El **Cendoj PDF Discovery System** es una herramienta de código abierto diseñada para **descubrir exhaustivamente todos los enlaces de documentos PDF** del [Centro de Documentación Judicial (Cendoj)](https://www.cendoj.es) de España.

### **Propósito Principal**

> **Objetivo**: Encontrar el **100% de los enlaces PDF** disponibles en el Cendoj, sin ser bloqueado por el servidor.

Este proyecto **ya no se centra en descargar archivos**, sino en **descubrir y catalogar** todos los enlaces existentes. El sistema:

- ✅ Realiza **crawling profundo** (Breadth-First Search) sin límites de profundidad
- ✅ **Evita bloqueos** mediante rotación automática de proxies, user-agents y rate limiting adaptativo
- ✅ Detecta y **maneja CAPTCHAs** automáticamente (pausa para resolución manual)
- ✅ **Registra todo** en una base de datos SQLite con tracking completo
- ✅ **Resumible**: puedes interrumpir con `Ctrl+C` y continuar después
- ✅ **Escalable**: puede correr durante semanas de forma autónoma

### **Casos de Uso**

- Investigación académica del derecho español
- Creación de archivos legales distribuidos
- Análisis de jurisprudencia a gran escala
- Proyectos de justicia abierta
- Backup legal de sentencias

---

## ✨ Características

### **🔍 Sistema de Discovery**

| Característica | Descripción |
|----------------|-------------|
| **Modo Shallow** | Extrae solo de tablas HTML (rápido, superficie) |
| **Modo Deep** | BFS con profundidad limitada (balanceado) |
| **Modo Full** | **BFS sin límites** - encuentra TODOS los enlaces |
| **Extracción multi-método** | CSS selectors + Regex + Script scanning |
| **Deduplicación inteligente** | URLs normalizadas, evita duplicados |
| **Validación opcional** | HEAD request para verificar accesibilidad |
| **Sesiones persistentes** | Resume desde último punto automáticamente |

### **🛡️ Anti-Blocking Multi-Capa**

1. **Proxy Manager**: Pool de 3000+ proxies públicos rotativos
2. **User-Agent Pool**: 50+ fingerprints de navegadores reales
3. **Rate Limiter Adaptativo**: Se ajusta automáticamente ante 429s
4. **Behavior Simulator**: Retrasos y movimientos humanos (opcional)
5. **CAPTCHA Handler**: Detección + screenshot + pausa manual
6. **Fingerprint Spoofing**: Enmascara automatización (WebGL, Canvas, WebRTC)

### **📊 Base de Datos Completa**

```sql
-- Enlaces PDF descubiertos
pdf_links (id, url, normalized_url, status, discovered_at, ...)

-- Sesiones de discovery (resumible)
discovery_sessions (id, mode, status, pages_visited, ...)

-- Salud de proxies
proxy_health (proxy_url, score, success_rate, ...)
```

### **🔧 CLI Completo**

```bash
python cli.py discover      # Iniciar discovery
python cli.py stats         # Ver estadísticas
python cli.py export        # Exportar enlaces
python cli.py proxies       # Estado del pool
python cli.py sessions      # Sesiones recientes
```

### **📈 Monitoreo en Tiempo Real**

- Logs estructurados (JSON opcional)
- Métricas de success rate por proxy
- Tracking de CAPTCHAs detectados
- Estadísticas de páginas/segundo
- Alertas automáticas (archivos)

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Interface                           │
│                  (cli.py - Click commands)                     │
├─────────────────────────────────────────────────────────────────┤
│                    DiscoveryScanner                            │
│   ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌──────────┐  │
│   │Navigator │  │DeepCrawler│  │ProxyManager│  │UAPool    │  │
│   │(shallow) │  │(BFS)     │  │(3000+ IPs) │  │(50+ UAs) │  │
│   └──────────┘  └──────────┘  └────────────┘  └──────────┘  │
├─────────────────────────────────────────────────────────────────┤
│              Anti-Blocking Stack                               │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │RateLimiter │  │CaptchaHandler│  │BehaviorSim   │         │
│  │(adaptive)  │  │(auto-detect) │  │(human-like)  │         │
│  └────────────┘  └──────────────┘  └──────────────┘         │
├─────────────────────────────────────────────────────────────────┤
│                Persistence Layer                               │
│            SQLite (pdf_links, sessions, proxy_health)         │
└─────────────────────────────────────────────────────────────────┘
```

**Flujo de Discovery Full**:

```
1. Inicialización
   ├─ Cargar configuración
   ├─ Inicializar DB
   ├─ Fetch proxies (Proxifly + ProxyScrape)
   ├─ Validar proxies (test concurrente)
   ├─ Cargar User-Agents
   └─ Crear sesión en DB

2. Crawl BFS
   ├─ URL semilla → Browser (con proxy + UA)
   ├─ Extraer PDFs (CSS + Regex + Scripts)
   ├─ Guardar en DB (deduplicación)
   ├─ Validar URLs (HEAD request opcional)
   ├─ Extraer enlaces internos
   ├─ Añadir a cola BFS
   ├─ Rotar proxy/UA
   ├─ Aplicar rate limiting
   ├─ Detectar CAPTCHA (pausar si se encuentra)
   └─ Persistir estado cada 100 páginas

3. Finalización
   ├─ Guardar estado final
   ├─ Actualizar sesión DB
   └─ Generar reporte
```

---

## 🚀 Instalación

### **Requisitos del Sistema**

- Python 3.8+
- 4GB RAM mínimo (8GB recomendado)
- Espacio en disco: 10GB+ (DB puede crecer a Millions de registros)
- Conexión a internet estable

### **Pasos**

```bash
# 1. Clonar repositorio
git clone https://github.com/spidey000/cendoj-scraper.git
cd cendoj-scraper

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
pip install -U playwright
playwright install chromium

# 4. Configurar directorios
mkdir -p data/sessions data/backups logs

# 5. Setup inicial de proxies (una sola vez)
python scripts/setup_proxies.py

# 6. Actualizar user agents (opcional pero recomendado)
python scripts/harvest_agents.py
```

---

## ⚙️ Configuración

### **Archivos de Configuración**

| Archivo | Propósito |
|---------|-----------|
| `config/sites.yaml` | Configuración principal (sites, discovery, anti-blocking) |
| `config/user_agents.txt` | Pool de user agents (uno por línea) |
| `.env` | Variables de entorno (opcional, para overrides) |

### **Configuración Esencial (`config/sites.yaml`)**

```yaml
# ============================================
# DISCOVERY CONFIGURATION
# ============================================
discovery:
  mode: "full"              # shallow|deep|full
  max_depth: 0              # 0 = unlimited
  validate_on_discovery: true  # HEAD request después de encontrar PDF
  deduplicate: true

# ============================================
# ANTI-BLOCKING STACK
# ============================================
anti_blocking:
  proxy:
    enabled: true
    sources: ["proxifly", "proxyscraper"]
    refresh_hours: 6
    min_anonymity: "elite"
    test_before_use: true
    rotate_per_request: true

  user_agent:
    pool_file: "config/user_agents.txt"
    rotate_per_session: true

  rate_limiting:
    requests_per_minute: 20   # Ajustar según respuesta del servidor
    backoff_on_429: true

  captcha:
    auto_detect: true
    pause_on_captcha: true   # Pausar para resolución manual

# ============================================
# BROWSER
# ============================================
browser:
  headless: true
  stealth: true
  timeout: 60000  # 60s para deep crawl
```

### **Overrides con Variables de Entorno**

Puedes sobreescribir cualquier configuración con variables de entorno:

```bash
export CENDOJ__DISCOVERY__MODE=full
export CENDOJ__ANTI_BLOCKING__PROXY__ENABLED=true
export CENDOJ__RATE_LIMITING__REQUESTS_PER_MINUTE=30
```

Formato: `CENDOJ__SECTION__SUBSECTION__KEY=value`

---

## 💻 Uso del CLI

### **Comandos Principales**

#### **1. Discover (Descubrir PDFs)**

```bash
# Modo FULL (recomendado) - BFS sin límites
python cli.py discover --mode full --validate

# Modo DEEP - BFS con límite de profundidad
python cli.py discover --mode deep --validate --limit 1000

# Modo SHALLOW - Solo tablas (más rápido, menos completo)
python cli.py discover --mode shallow --limit 500

# Reanudar sesión interrumpida
python cli.py discover --mode full --resume

# Sin validación (solo discover, más rápido)
python cli.py discover --mode full --no-validate

# Con límite de páginas (debug/testing)
python cli.py discover --mode full --limit 100
```

**Opciones**:
- `--mode`: Modo de discovery (shallow|deep|full)
- `--validate` / `--no-validate`: Realizar HEAD request para verificar URLs
- `--resume`: Reanudar última sesión interrumpida
- `--limit N`: Límite de páginas a visitar (0 = sin límite)

#### **2. Estadísticas**

```bash
python cli.py stats
```

Salida de ejemplo:
```
📊 ESTADÍSTICAS DE DISCOVERY
========================================
📄 Enlaces PDF:
   Total descubiertos: 45,231
   Accesibles: 41,892 (92.6%)
   Rotos: 2,145 (4.7%)
   Bloqueados: 1,194 (2.6%)
   Validados: 43,000 (95.1%)

🔄 Sesiones:
   Total: 3
   Completadas: 2
   Fallidas: 0
   En ejecución: 1

📅 Última sesión:
   ID: abc123def456
   Modo: full
   Estado: running
   Páginas visitadas: 15,234
   Enlaces encontrados: 45,231
```

#### **3. Exportar Enlaces**

```bash
# Exportar todos los enlaces accesibles a CSV
python cli.py export --status accessible --output accessible_links.csv

# Exportar solo los rotos a JSON
python cli.py export --status broken --output broken.json

# Exportar todos los descubiertos (texto plano, un URL por línea)
python cli.py export --status discovered --output all_urls.txt --limit 10000
```

**Formatos soportados**: `.csv`, `.json`, `.txt`

#### **4. Gestión de Proxies**

```bash
# Ver estado del pool
python cli.py proxies

# Refresh manual del pool
python scripts/setup_proxies.py

# Test de performance (stress test)
python scripts/test_proxies.py
```

#### **5. Sesiones**

```bash
# Listar sesiones recientes
python cli.py sessions

# Ver detalles de una sesión específica (en DB directly)
sqlite3 data/cendoj.db "SELECT * FROM discovery_sessions ORDER BY start_time DESC LIMIT 5;"
```

---

## 📊 Esquema de Base de Datos

### **Tablas Principales**

#### **`pdf_links`** - Enlaces PDF descubiertos

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | INTEGER PK | ID interno |
| `url` | TEXT | URL original descubierta |
| `normalized_url` | TEXT UNIQUE | URL normalizada (sin query params irrelevantes) |
| `source_url` | TEXT | Página donde se encontró el enlace |
| `discovery_session_id` | TEXT FK | Sesión que lo descubrió |
| `discovered_at` | DATETIME | Timestamp de descubrimiento |
| `validated_at` | DATETIME | Timestamp de validación (HEAD) |
| `status` | TEXT | discovered\|validated\|accessible\|broken\|blocked\|downloaded |
| `http_status` | INTEGER | Código HTTP de validación |
| `content_type` | TEXT | MIME type |
| `content_length` | INTEGER | Tamaño en bytes |
| `final_url` | TEXT | URL después de redirects |
| `redirect_count` | INTEGER | Número de redirects |
| `validation_error` | TEXT | Error si falló validación |
| `extraction_method` | TEXT | css\|regex\|script_scan\|sitemap |
| `extraction_confidence` | FLOAT | Confianza 0-1 |
| `metadata` | JSON | `{"depth": 2, "site_key": "cendoj", ...}` |

**Índices**:
- `idx_pdf_links_normalized_url` (único)
- `idx_pdf_links_discovery_session`
- `idx_pdf_links_status`
- `idx_pdf_links_discovered_at`

#### **`discovery_sessions`** - Tracking de sesiones

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | TEXT PK | UUID de sesión |
| `start_time` | DATETIME | Inicio |
| `end_time` | DATETIME | Fin (NULL si running) |
| `mode` | TEXT | shallow\|deep\|full |
| `max_depth` | INTEGER | Profundidad máxima (0=unlimited) |
| `total_pages_visited` | INTEGER | Páginas visitadas |
| `total_links_found` | INTEGER | Enlaces encontrados |
| `new_links` | INTEGER | Enlaces nuevos (no duplicados) |
| `duplicates_skipped` | INTEGER | Duplicados evitados |
| `status` | TEXT | running\|completed\|failed\|interrupted\|cancelled |
| `interrupted_at` | JSON | Estado para resume: `{"queue_size": 123, ...}` |
| `config_snapshot` | JSON | Config usada en esta sesión |
| `errors` | INTEGER | Total de errores |

#### **`proxy_health`** - Salud de proxies

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `proxy_url` | TEXT PK | `http://ip:port` |
| `source` | TEXT | proxifly\|proxyscraper\|... |
| `protocol` | TEXT | http\|https\|socks4\|socks5 |
| `ip` | TEXT | IP address |
| `port` | INTEGER | Port |
| `country` | STRING(2) | Código ISO país |
| `anonymity` | TEXT | elite\|anonymous\|transparent |
| `total_requests` | INTEGER | Total requests realizados |
| `successful_requests` | INTEGER | Requests exitosos |
| `avg_response_time` | FLOAT | Tiempo promedio (segundos) |
| `score` | FLOAT | Score 0-100 (calculado) |
| `is_healthy` | BOOLEAN | ¿Proxy usable? |
| `last_check` | DATETIME | Última validación |

---

## 🛡️ Anti-Blocking Stack

### **1. Proxy Manager**

**Fuentes públicas automáticas**:
- **Proxifly**: ~2,800 proxies (actualización cada 5 min)
- **ProxyScrape**: ~6,500 proxies (actualización cada 30 min)

**Funcionamiento**:
```python
# Cada request:
proxy = proxy_manager.get_next_proxy()  # Weighted random por score
response = make_request(url, proxy=proxy)
proxy_manager.mark_result(proxy, success=response.ok)
```

**Scoring** (0-100):
- 50% Success rate
- 25% Response time (<2s = 25pts, 2-5s = 15pts, >5s = 5pts)
- 15% Recency bonus (éxito reciente)
- -20% Penalty por error reciente

**Auto-pruning**: Proxies con score <10 se descartan automáticamente.

**Cache**: `data/proxies_cache.json` persistente entre ejecuciones.

---

### **2. Rate Limiter Adaptativo**

```python
# Inicialización
limiter = AdaptiveRateLimiter(
    requests_per_minute=20,    # Base rate
    burst_size=5,              # Burst inicial
    backoff_on_429=True,       # Reducir al recibir 429
    decrease_factor=0.5,       # Reducir 50% en 429
    max_backoff_seconds=300    # Max backoff 5 minutos
)

# Uso
await limiter.wait()  # Bloquea hasta tener token

# Al recibir 429:
limiter.on_429()  # Reduce rate automáticamente

# Tras éxito:
limiter.on_success()  # Recupera rate gradualmente (10% por éxito)
```

**Comportamiento**:
- Empieza a 20 req/min
- Si recibes 429 → baja a 10 req/min, backoff 10s
- Siguientes 429 → backoff exponencial (40s, 90s, 160s...)
- Cada request exitoso → recupera 10% del rate perdido
- Rate nunca baja de 1 req/min

---

### **3. User-Agent Pool**

```python
ua_pool = UserAgentPool('config/user_agents.txt')
ua_pool.load()  # Lee 50+ UAs del archivo

# Rotación por sesión
ua_pool.set_session_ua()  # Elegir uno al azar al inicio

# O por request
ua = ua_pool.get_random()
```

**UAs incluidos** (ejemplos):
- Chrome 120 Windows/Mac/Linux
- Firefox 120 Windows/Linux
- Safari 17 macOS
- Edge 120 Windows
- Chrome Android, Safari iOS
- Opera, Brave

**Actualización**: `python scripts/harvest_agents.py`

---

### **4. CAPTCHA Handler**

```python
captcha = CAPTCHAHandler(
    screenshots_dir='data/sessions/captchas',
    pause_on_captcha=True,
    auto_screenshot=True
)

# En cada página:
should_skip = await captcha.should_skip_url(page, session_id)
if should_skip:
    continue  # Saltar esta URL
```

**Detección**:
- Patrones de texto (captcha, recaptcha, "verification", etc.)
- Selectores CSS específicos (iframe[src*='recaptcha'])
- Títulos de página
- Headers de Cloudflare

**Al detectar**:
1. 📸 Screenshot automático
2. 📝 Log con URL y timestamp
3. ⚠️ Alerta visible en consola
4. ⏸️ Pausa esperando resolución manual
5. ✅ Continuar o saltar URL

---

## 📈 Rendimiento Estimado

### **Capacidad Teórica**

| Métrica | Valor |
|---------|-------|
| Proxies en pool | 3,000+ (validados cada 6h) |
| User-Agents | 50+ (rotación por sesión) |
| Rate limit por proxy | 20 req/min |
| **Req/min teórico** | **60,000** (3,000 × 20) |
| **Req/min realista** | **15,000-25,000** (latencia, 429s, validaciones) |

### **Rendimiento por Día**

Asumiendo **20,000 requests/día**:

```
Páginas/día:       500,000 - 800,000 (promedio 25ms/request)
Enlaces PDF/día:   50,000 - 100,000 (10% de páginas contienen PDFs)
DB size/día:       ~200-500 MB (metadata de enlaces)
```

### **Tiempo Total Estimado Cendoj**

- **Páginas estimadas**: 500,000 - 1,000,000+
- **Duración**: **10-20 días** (corriendo 24/7)
- **Enlaces PDF**: 50,000 - 100,000+

---

## 🐛 Troubleshooting

### **Problema: No hay proxies disponibles**

```bash
# Ver estado
python cli.py proxies

# Si pool vacío, refrescar manualmente
python scripts/setup_proxies.py

# Ver logs
tail -f logs/cendoj_scraper.log
```

**Solución**: 
- Verificar conexión a internet
- Las fuentes públicas pueden estar temporalmente down
- Revisar `data/proxies_cache.json`

---

### **Problema: Muchos 429/403**

```yaml
# En config/sites.yaml, reducir rate:
anti_blocking:
  rate_limiting:
    requests_per_minute: 10  # Más conservador
    backoff_on_429: true
```

**Solución**:
1. Reducir `requests_per_minute`
2. Aumentar `burst_size` (para más espacio entre bursts)
3. El adaptive limiter debería manejar esto automáticamente

---

### **Problema: CAPTCHAs constantes**

```yaml
# Desactivar comportamientos "sospechosos"
anti_blocking:
  behavior:
    simulate_human: false  # Menos humano = más detectable?
  proxy:
    rotate_per_request: true  # Asegurar rotación
```

**Solución**:
- Los CAPTCHAs son señal de que estás siendo detectado
- Revisar configuración de stealth
- Considerar agregar más delays
- Si aparecen, el handler pausa y permite resolución manual

---

### **Problema: Redis/DB lleno de duplicados**

```sql
-- Ver duplicados
SELECT normalized_url, COUNT(*) as cnt
FROM pdf_links
GROUP BY normalized_url
HAVING cnt > 1;

-- Limpiar (mantener el más reciente)
DELETE FROM pdf_links
WHERE id NOT IN (
    SELECT MAX(id) FROM pdf_links GROUP BY normalized_url
);
```

**Nota**: El sistema ya deduplica en tiempo real, pero si hay bugs, puedes limpiar manualmente.

---

### **Problema: Interrupción y no resume**

```bash
# Ver sesiones interrumpidas
python cli.py sessions

# Reanudar explícitamente
python cli.py discover --mode full --resume
```

**Nota**: La sesión se guarda cada 100 páginas en `data/sessions/`

---

### **Problema: Proxies lentos (>10s)**

```bash
# Test individual
python scripts/test_proxies.py  # Opción 1 (quick test)

# Ver scores en DB
SELECT proxy_url, avg_response_time, score
FROM proxy_health
WHERE is_healthy = 1
ORDER BY score DESC
LIMIT 20;
```

**Solución**: El sistema auto-prueba y descarta lentos. Si persisten, ajustar timeout en `config/sites.yaml` browser.timeout.

---

## 🛠️ Desarrollo

### **Estructura del Proyecto**

```
cendoj/
├── cli.py                    # CLI principal (Click)
├── config/
│   ├── settings.py          # Config object con properties
│   ├── sites.yaml           # Config YAML principal
│   └── user_agents.txt      # UA pool
├── scraper/
│   ├── discovery_scanner.py # Orquestador principal
│   ├── deep_crawler.py      # BFS crawler
│   ├── navigator.py         # Navegador (shallow mode)
│   ├── browser.py           # BrowserManager con stealth
│   └── models.py            # Dataclasses (Sentence, etc.)
├── utils/
│   ├── proxy_manager.py     # Gestión de proxies
│   ├── ua_pool.py           # Pool de UAs
│   ├── adaptive_limiter.py  # Rate limiter adaptativo
│   ├── behavior_simulator.py# Simulación humana
│   ├── captcha_handler.py   # Manejo CAPTCHA
│   ├── fingerprint.py       # Spoofing (existente)
│   ├── rate_limiter.py      # Simple rate limiter (legacy)
│   └── logger.py            # Logging setup
├── storage/
│   ├── database.py          # SQLAlchemy engine/session
│   └── schemas.py           # Modelos SQLAlchemy
├── scripts/
│   ├── setup_proxies.py     # Inicializar pool
│   ├── test_proxies.py      # Benchmark proxies
│   └── harvest_agents.py    # Actualizar UAs
├── data/
│   ├── sessions/            # .pkl de sesiones para resume
│   ├── proxies_cache.json   # Cache de proxies
│   └── cendoj.db            # SQLite DB principal
└── logs/
    ├── cendoj_scraper.log
    └── discovery_YYYY-MM-DD.log
```

---

### **Workflow de Desarrollo**

```bash
# 1. Crear branch feature
git checkout -b feature/nueva-funcionalidad

# 2. Desarrollo
# ... modificar código ...

# 3. Test (solo syntax check por ahora)
python3 -m py_compile utils/nuevo_modulo.py

# 4. Commit
git add .
git commit -m "feat: descripción clara"

# 5. Push y PR
git push origin feature/nueva-funcionalidad
# Abrir PR en GitHub
```

---

### **Añadir Nuevo Método de Extracción**

Ejemplo: agregar extracción desde sitemap.xml

1. **Config**: Añadir en `config/sites.yaml`:
   ```yaml
   sitemap:
     enabled: true
     urls:
       - "https://www.cendoj.es/sitemap.xml"
   ```

2. **Código**: En `scraper/discovery_scanner.py` o crear `scraper/sitemap_parser.py`:
   ```python
   async def parse_sitemap(self, url):
       # Fetch sitemap
       # Extraer URLs
       # Filtrar .pdf
       # Retornar lista
   ```

3. **Integración**: En `DiscoveryScanner._get_seed_urls()`:
   ```python
   if self.config.sitemap_enabled:
       sitemap_urls = await parse_sitemap()
       seed_urls.extend(sitemap_urls)
   ```

---

## 📚 API Reference (Python)

### **DiscoveryScanner**

```python
from scraper.discovery_scanner import DiscoveryScanner
from config.settings import Config

config = Config()
scanner = DiscoveryScanner(config)

# Inicializar
await scanner.initialize()

# Run (async generator)
async for pdf in scanner.run():
    print(pdf['url'], pdf.get('validation'))

# Cleanup
await scanner.cleanup()
```

### **ProxyManager**

```python
from utils.proxy_manager import ProxyManager

pm = ProxyManager({'min_proxies_required': 100})
await pm.initialize()

proxy = pm.get_next_proxy('weighted')  # weighted|round_robin|random|best

# Marcar resultado
pm.mark_result(proxy, success=True, response_time=1.23)
# o
pm.mark_result(proxy, success=False, error="Timeout")

# Stats
stats = pm.get_stats()
```

### **DeepCrawler**

```python
from scraper.deep_crawler import DeepCrawler

crawler = DeepCrawler(
    browser_manager=browser,
    config=config,
    proxy_manager=pm,
    ua_pool=ua_pool,
    rate_limiter=limiter
)

await crawler.initialize(session_id='uuid', seed_urls=['https://...'])
async for pdf in crawler.crawl():
    process(pdf)
```

---

## 🤝 Contributing

### **Guidelines**

1. **Fork** el repositorio
2. **Branch**: `git checkout -b feature/mi-feature`
3. **Code** siguiendo PEP8, type hints, docstrings
4. **Test**: Al menos comprobación de sintaxis
5. **Commit**: Mensajes claros, Conventional Commits
6. **PR**: Descripción detallada, screenshots si es UI

### **Áreas de Contribución**

- **Optimización de discovery**: Mejores selectores para Cendoj
- **Anti-blocking**: Nuevas fuentes de proxies, mejor fingerprinting
- **UI/UX**: Dashboard web en tiempo real
- **Tests**: Unit y integration tests
- **Documentación**: Ejemplos, guías específicas
- **Performance**: Parallel crawling, async optimizations

---

## ⚖️ Legal Considerations

### **Uso Permitido**

Este proyecto está diseñado para:

- ✅ **Investigación académica** en derecho y jurisprudencia
- ✅ **Análisis legal** y estudios de sentencias
- ✅ **Iniciativas de justicia abierta**
- ✅ **Archivo público** de documentos legales

### **Restricciones**

- ❌ **Uso comercial** sin permiso expreso
- ❌ **Redistribución** de PDFs con derechos de autor
- ❌ **Scraping agresivo** (respetar rate limits)
- ❌ **Evasión de medidas de seguridad** deliberada

### **Responsabilidad**

El usuario es responsable de:

- Cumplir la **ley española** sobre documentos públicos
- Respetar los **términos de servicio** del Cendoj
- **No sobrecargar** los servidores (usa rate limiting!)
- Verificar **restricciones de copyright** antes de usar datos

Este proyecto no está afiliado con el Poder Judicial español ni el Cendoj.

---

## 📄 License

MIT License - ver [LICENSE](LICENSE) para detalles.

---

## 🙏 Acknowledgments

- **Inspiración**: Comunidad de web scraping y openness
- **Proxies públicos**: Proxifly, ProxyScrape
- **Librerías**: Playwright, SQLAlchemy, Tenacity, Click
- **Legal**: Poder Judicial de España por hacer públicos estos documentos

---

## 📞 Contact & Support

- **Issues**: [GitHub Issues](https://github.com/spidey000/cendoj-scraper/issues)
- **Discusiones**: [GitHub Discussions](https://github.com/spidey000/cendoj-scraper/discussions)
- **Email**: spidey00@gmail.com (soporte limitado)

---

**⭐ Si este proyecto te es útil, considera darle una estrella en GitHub!**

**Última actualización**: Febrero 2025 (v2.0 - Massive Discovery System)
