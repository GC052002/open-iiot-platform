"""API REST mínima (F1).

===============================================================================
STUB PARA RELLENO POR MODELO ECONÓMICO.
===============================================================================
TODO(econ) — endpoints de F1 (montar el router en app.main):
  - POST /projects        -> load_project(body) + arrancar Runtime + conectar el
                             ConnectionManager como suscriptor del TagCache:
                                 runtime.tag_cache.subscribe(state.manager.on_tag_update)
                                 state.runtime_task = asyncio.create_task(runtime.run())
  - GET  /projects/current-> devolver la topología cargada.
  - GET  /tags            -> listar tags con su último valor (tag_cache.snapshot()).

Contratos ya disponibles: app.models.project.load_project, app.engine.runtime.Runtime.
La autorización RBAC/ABAC es F2/F4 (§3.6, §10.2); en F1 dejar endpoints abiertos
en local pero marcar el punto de inserción del middleware de auth.
"""
