# Demo Rama 2 — Edge Push (IOT2050 / MQTT)

Prueba la ingesta **MQTT** sin PLC ni IOT2050 reales: un broker local + un simulador
de Edge que publica telemetría JSON, tal como haría la IOT2050 con Node-RED.

```
[edge_sim.py]  --MQTT-->  [broker.py :1883]  <--sub--  [driver mqtt del backend]  -->  TagCache --> WS --> HMI
   (= IOT2050)               (= broker planta)              (mismo backend)
```

## 1. Instalar dependencias MQTT (en el venv del proyecto)
```bash
pip install aiomqtt amqtt
```

## 2. Arrancar (cada uno en su ventana)
```bash
python tools/mqtt_demo/broker.py       # broker MQTT en :1883
python tools/mqtt_demo/edge_sim.py     # publica temp/nivel/bomba cada 1s a planta/edge1
# + el backend (uvicorn) y el frontend (npm run dev) como siempre
```

## 3. En el editor HMI
1. Arrastra un driver **MQTT**. En el inspector: `host=127.0.0.1`, `port=1883`
   (por defecto se suscribe a todos los tópicos; para acotar, en *Avanzado (JSON)*
   añade `"topic": "planta/edge1"`).
2. **Tags del proyecto** → define tags con el `address` = clave del payload:
   `temp` (float), `nivel` (float), `bomba` (bool), todos con `driver = MQTT`.
3. **Enviar al backend** → **Conectar**.
4. Arrastra widgets (tanque/gráfico/válvula) y enlázalos a `temp`/`nivel`/`bomba`.

Verás los valores en vivo. Con la IOT2050 real, `broker.py`/`edge_sim.py` los
reemplaza Node-RED publicando al broker de planta — **el proyecto no cambia**.

> Nota: `broker.py` es pure-python (amqtt) solo para desarrollo. En planta se usa un
> broker robusto (Mosquitto/EMQX) con TLS.
