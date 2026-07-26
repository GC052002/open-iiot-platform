================================================================================
PROMPT MAESTRO DE ARQUITECTURA: PLATAFORMA IIoT OPEN-SOURCE (REEMPLAZO WINCC/SCADA)
================================================================================

[OBJETIVO DEL PROYECTO]
Diseñar e implementar un software de código abierto, modular y seguro para la Industria 4.0. 
El sistema funcionará como un entorno de diseño visual e interactivo (estilo Node-RED / WinCC / Ignition) 
para la integración de sistemas, monitoreo HMI, control y comunicación con PLCs e instrumentación industrial, 
sin las restricciones de licencias costosas.

[ARQUITECTURA DEL SISTEMA]
El sistema se dividirá en dos capas totalmente desacopladas (Cliente-Servidor) e interoperables:

1. FRONTEND (UI & Canvas Interactivo):
   - Tecnologías: React + React Flow (Canvas interactivo para diagramas de procesos basándonos en nodos).
   - Componentes principales:
     * Paleta lateral: Nodos de comunicación (Drivers), Nodos de Lógica (Escalado/Filtros) y Widgets HMI (Tanques, Válvulas, Gráficos).
     * Canvas: Espacio para arrastrar, conectar y posicionar nodos.
     * Inspector de Propiedades: Drawer/Modal lateral dinámico para configurar parámetros (IPs del PLC, direcciones de memoria/DBs, tags, polling rates).
   - Resiliencia: Guardado temporal automático en LocalStorage / IndexedDB para prevenir pérdida de datos por fallas de red local.

2. BACKEND (Motor Asíncrono de Procesamiento):
   - Lenguaje y Framework: Python 3.11+ con FastAPI.
   - Motor de Comunicaciones: Ejecución asíncrona (asyncio) de tareas de lectura/escritura (Polling) usando drivers nativos:
     * Siemens S7 (`python-snap7`)
     * Modbus TCP (`pymodbus`)
     * OPC UA (`asyncua` con certificados X.509)
     * MQTT (`paho-mqtt` con TLS)
   - Transmisión en Tiempo Real: Motor de WebSockets en FastAPI para streaming bidireccional entre el Backend y la UI React.
   - Definición de Proyectos (JSON): La topología del proyecto, posición de nodos y configuración se almacena e importa en formato JSON estructurado.

3. MÓDULOS DE VALOR AGREGADO:
   - Alarmas y Notificaciones: Evaluación de umbrales en tiempo real + Notificaciones por Telegram (Bot API), Correo SMTP y registro histórico.
   - Gestión Adaptable de Red (3 Modos):
     a) Local Aislado (Air-Gapped): Funciona 100% offline sin dependencias externas CDN, seguro para redes de control cerradas.
     b) Híbrido: Operación local ininterrumpida con opción de exposición remota vía VPN/Túnel seguro para monitoreo en vivo fuera de planta.
     c) Solo Nube (Cloud-Native): Alojado en servidor WAN/VPS para gestión distribuida multi-planta.
   - Seguridad: RBAC (Roles de Administrador/Ingeniero vs. Operador con canvas bloqueado), cifrado de credenciales con Fernet.
   - Despliegue: Contenedorizado completamente mediante Docker Compose (`docker-compose.yml`).

[TAREA / PREGUNTA PARA LA IA RECEPTORA]
Hola. Estoy colaborando en la arquitectura de esta plataforma IIoT industrial en Python y React. 
A partir de las especificaciones anteriores:
1. Revisa la arquitectura propuesta y proporciona críticas constructivas o cuellos de botella técnicos que identifiques.
2. Ayúdanos a estructurar o refactorizar el código para el motor de WebSockets en Python/FastAPI y la integración de las comunicaciones industriales.
3. Propón mejoras de diseño o patrones de software (ej. Pattern Factory para los drivers) para asegurar máxima modularidad.
