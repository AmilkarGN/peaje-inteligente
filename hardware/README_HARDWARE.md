# Bono +5 Puntos: Dispositivo Físico de Alerta con Arduino (Uno / Nano / Mega)

## Diagrama de Conexión de Pines (Arduino Uno / Nano / Mega)

| Componente Físico | Pin Arduino | Función en el Sistema de Peaje |
|---|---|---|
| **LED Verde** (+ resistencia 220 Ω) | `Pin D10` | **Acción / Paso Autorizado**: Se enciende cuando la placa está registrada y tiene saldo suficiente. |
| **LED Amarillo** (+ resistencia 220 Ω) | `Pin D9` | **Identificación e Inferencia**: Se enciende cuando la caseta envía un frame a `INFERENCE_URL` (RunPod/Colab). |
| **LED Rojo** (+ resistencia 220 Ω) | `Pin D8` | **Alerta en Tiempo Real**: Parpadea cuando se detecta una placa no registrada (evasión) o sin saldo. |
| **Buzzer Activo / Pasivo** | `Pin D7` | **Alarma Sonora**: Emite 1 tono corto en paso válido y sirena bitonal en alerta de placa no registrada. |
| **Micro Servo SG90 (Opcional)** | `Pin D6` | **Barrera Física**: Se abre a 90° en `PASO_OK` y permanece cerrada (0°) ante alertas. |
| **GND común** | `GND` | Tierra común de LEDs, Buzzer y Servo. |

## Cómo conectarlo directamente al Subdominio en la Nube (0 recursos locales)

1. Carga el archivo `arduino_alerta_peaje.ino` en tu **Arduino Uno / Nano / Mega** desde el Arduino IDE.
2. El panel web publicado en tu subdominio HTTPS consume los eventos en tiempo real de **Pusher** y `/api/v1/hardware/estado`, y puede enviar la trama serial `CMD:...|FASE:...|PLACA:...` directamente al puerto USB del Arduino mediante **Web Serial API** del navegador Chrome/Edge o mediante un módulo WiFi ESP8266/ESP32 que consulte `https://tu-subdominio.com/api/v1/hardware/estado?formato=serial`.
