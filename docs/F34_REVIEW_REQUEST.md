# Solicitud de revisión — Fase 3.4 · LogicNode sandbox

> **Para:** GLM 5.2 y Gemini (revisores externos).
> **De:** el equipo (implementación por Claude/Opus).
> **Repo:** `GC052002/open-iiot-platform` · rama `main` · PR **#28**.
> **Foco:** SEGURIDAD del sandbox de ejecución de expresiones del usuario.

## 0. Cómo queremos la revisión

Este bloque ejecuta **lógica definida por el usuario** en el backend → es el punto más
sensible de seguridad del proyecto. Priorizad, en este orden:

1. **Escape del sandbox / RCE**: ¿alguna expresión `expr` puede importar módulos, leer
   ficheros, acceder a atributos/dunder, ejecutar código, o tocar el intérprete?
2. **DoS**: ¿puede una expresión colgar/tumbar el motor (bucle, recursión, `9**9**9`,
   memoria)? El motor es `async` de un solo hilo: un cómputo bloqueante congela TODO.
3. **Robustez del pipeline**: bucles de realimentación (`A→logic→A`), fugas de estado
   entre proyectos, o un LogicNode roto que rompa el flujo de otros tags.
4. Después: correctitud de las estrategias y del wiring.

Devolved una **tabla**: `# | Severidad (BLOCKER/MEDIA/BAJA/NIT) | archivo:línea |
problema | sugerencia`.

## 1. Contexto

Plataforma IIoT/SCADA. Backend Python (FastAPI+asyncio). Un `LogicNode` transforma
tags: lee un tag de entrada (`params.input`), calcula, y publica un **tag derivado**
(`params.output`) de vuelta al `TagCache`, que fluye a WS/widgets/historiador. El
binding es por `tag_id` (contrato §3.10).

Decisión: la ejecución vive en el **backend** (el motor posee el flujo de datos), no en
el navegador. Estrategias built-in **puras** (`scale`/`avg`/`deadband`) + `expr` (sandbox).

## 2. Qué se entregó (PR #28)

- `backend/app/logic/strategies.py`
  - `scale(a,b)`, `_MovingAverage(window)`, `_Deadband(deadband)` — puras, sobre floats.
  - `_SafeExpr(expr, params)` — **sandbox asteval**:
    - `Interpreter(minimal=True, use_numpy=False)` (fallback sin `minimal` en versiones viejas);
    - solo `x` + parámetros **numéricos** (no bool, no callables) entran al symtable;
    - `MAX_EXPR_LEN = 500`;
    - fail-safe: cualquier error → `None` (nunca propaga).
  - `build_compute(strategy, params) -> compute(x) -> float | None`.
- `backend/app/logic/engine.py`
  - `LogicRunner` (input→output, `compute`), `LogicEngine` (suscriptor **delta** del
    TagCache; publica derivados). `output == input` se descarta (anti auto-bucle).
- `backend/app/state.py` — `LogicEngine` global suscrito; register/unregister por proyecto.
- `pyproject.toml` — `asteval>=0.9.31,<2` (pure-python, air-gapped).
- Frontend — `expr` en la paleta; `input`/`output` en el inspector.

**Tests: backend 82→98** (+16): estrategias, 5 expresiones maliciosas bloqueadas, límite
de longitud, params no numéricos filtrados, compute/publish del engine, e2e vía TagCache.

## 3. Preguntas concretas (donde MÁS queremos crítica)

1. **asteval como frontera de seguridad**: ¿es suficiente para un contexto no-confiable,
   o hay vectores conocidos (p. ej. acceso a `__class__` vía algún builtin permitido,
   f-strings, comprehensions costosas)? ¿Deberíamos además limitar nodos del AST o
   funciones disponibles explícitamente (allowlist en vez de la denylist de asteval)?
2. **DoS por CPU/memoria**: no hay timeout ni límite de operaciones. asteval reciente
   tiene `max_time`/límites de longitud de string y de potencia — ¿los activamos?
   ¿Ejecutar el cómputo en `run_in_executor` con timeout para no bloquear el event loop?
3. **Ciclos de realimentación**: descartamos `output==input`, pero un ciclo `A→B→A` (dos
   LogicNodes) podría oscilar. ¿Detección de ciclos al registrar, o basta con el deadband
   del TagCache + documentarlo?
4. **Aislamiento entre proyectos**: `_SafeExpr` cachea un `Interpreter` por runner; los
   runners se reconstruyen en `register_project`. ¿Veis fuga de estado/símbolos entre
   proyectos o entre ciclos de cómputo?
5. **Tipos/quality**: si la entrada es `quality="bad"`/`None`, `compute` devuelve `None`
   (no publica). ¿El derivado debería propagar `quality="bad"` explícitamente en vez de
   quedarse con el último valor bueno?

## 4. Diferido a propósito (NO reabrir salvo riesgo)

- **WASM (Wasmer/Extism) para Python real**: diferido; asteval cubre expresiones
  aritméticas (el caso mayoritario). Si veis que asteval no es defendible para
  no-confiable, ese es justo el argumento para priorizar WASM — decídnoslo.
- Fase 4 (Redis, ABAC/Casbin, Vault, TimescaleDB, OTel), Python 3.14 (R7).

## 5. Cómo ejecutarlo

```
cd backend && IIOT_ALLOW_ANONYMOUS=true pytest -q tests/test_f3_logic.py   # 16 verdes
# e2e: cargar un proyecto con un LogicNode {strategy:scale, params:{input,output,a,b}}
#      y verificar el tag derivado por WS.
```

Gracias.
