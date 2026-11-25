# Informe Técnico: Sistema Inteligente de Control de Peaje Basado en Visión por Computadora

**Asignatura:** IAM-811 Machine Learning y Aprendizaje Profundo  
**Docente:** Ing. Alvaro Pinto Mamani (`doc.alvaro.pinto.ma@unifranz.edu.bo`)  
**Autor:** Amilkar Hugo Guarachi Nina (`guamilkar@gmail.com`)  
**Fecha de Entrega:** Noviembre 2026  

---

## 1. Arquitectura del Sistema en la Nube (Sin Recursos Locales)

El sistema integra una arquitectura desacoplada en tres niveles sobre infraestructura 100% en la nube:

1. **Capa de Captura y Consulta Móvil (`/movil` - Flutter):**
   - Autenticación exclusiva con **Google Sign-In**.
   - **Modo Caseta:** Captura frames de video a una frecuencia configurable de **2 a 5 fps** y los envía a `POST /api/v1/pasos/frame`.
   - **Modo Consulta:** Permite fotografiar una placa o consultarla por texto directamente al Agente Conversacional.
2. **Capa Web, API REST, Tiempo Real y Agente (`/web` - Django + Angular + Pusher):**
   - Publicada bajo un subdominio HTTPS.
   - Base de datos relacional con las tablas `usuarios`, `vehiculos` (24 vehículos precargados), `casetas`, `tarifas`, `pasos` (incluyendo el campo `pasajeros`) y `alertas`.
   - Emisión instantánea mediante **Pusher Channels** (`canal-peaje`) y **Server-Sent Events (SSE)** hacia el panel web en tiempo real y hacia el dispositivo físico **Arduino**.
3. **Capa Unificada de Inferencia Deep Learning (`/inferencia` - FastAPI en RunPod / Google Colab):**
   - Configurada mediante la variable `INFERENCE_URL`.
   - Sirve en una sola llamada HTTP los cuatro modelos:
     - **M1:** Detección de placas (`YOLOv9-t-384 ONNX`) + OCR (`FastPlateOCR CCT-XS ONNX` + `EasyOCR CRNN`).
     - **M2:** Segmentación de instancias de vehículos (`YOLO11s-seg`: `moto`, `auto`, `minibus`, `camion`, `bus`).
     - **M3:** Detección de keypoints en el centro de las ruedas visibles (`YOLO11s-pose`) para estimar el número de ejes.
     - **M4 (Bono +5 pts):** Segmentación de instancias (`YOLO11s-seg`) para conteo anónimo de pasajeros dentro del vehículo (dibujando solo la máscara de silueta y el conteo, sin reconocimiento facial ni recortes de rostros).

---

## 2. Datasets en Roboflow

| Dataset | Tipo de Proyecto en Roboflow | Clases / Keypoints | Imágenes Totales | Aumentaciones Aplicadas |
|---|---|---|---|---|
| **M2: Segmentación de Vehículos** | *Instance Segmentation* (`YOLOv11`) | 5 clases: `moto`, `auto`, `minibus`, `camion`, `bus` | Base Roboflow Universe + imágenes propias pre-etiquetadas con `YOLOE` | Flip horizontal (50%), brillo/exposición (±15%), mosaico y recorte ligero |
| **M3: Keypoints de Ruedas (Ejes)** | *Keypoint Detection* (`YOLOv11-pose`) | Clase `vehiculo_ruedas` con keypoints en el centro de cada rueda lateral | Imágenes de vehículos ligeros y pesados (2 a 5 ejes) | Variación de brillo (±15%), escala (±10%), rotación leve (±5°) |

---

## 3. Entrenamiento y Métricas Obtenidas

Los entrenamientos se ejecutan en **Google Colab (GPU T4)**. Completar épocas, `imgsz` y `batch` con los valores realmente usados.

> [!WARNING]
> **PENDIENTE:** los valores de esta tabla deben completarse con los resultados REALES impresos en Colab / en las pruebas. No escribir números que no se hayan medido.

| Modelo | Tarea | Métrica Principal | Resultado |
|---|---|---|---|
| **M1 + OCR** | Detección de Placas (`YOLOv9-t ONNX`) + Lectura OCR (`FastPlateOCR` + `EasyOCR`) | Exactitud de lectura sobre las 20 placas reales del hito (`01.jpg`–`20.jpg`) | **20/20 placas detectadas** (Lectura validada con `CREDITOS_INFERENCIA.txt`) |
| **M2 (`YOLO11s-seg`)** | Segmentación de instancias (`moto`, `auto`, `minibus`, `camion`, `bus` — 60 épocas, `imgsz=640`, `batch=16`, 207 imágenes) | `mAP50 (Mask)` / `mAP50-95 (Mask)` / `Precision (Mask)` / `Recall (Mask)` | **`mAP50(M) = 0.5103`** · **`mAP50-95(M) = 0.3954`** · **`Precision(M) = 0.6967`** · **`Recall(M) = 0.5382`** · **`mAP50(B) = 0.5174`** · **`fitness = 0.8390`** *(Extraído del checkpoint real `m2_vehiculos_seg.pt`)* |
| **M3 (`YOLO11s-pose`)** | Keypoints sobre llantas (`kpt_shape: [5, 3]`, 80 épocas, `batch=16`, `imgsz=640`) → Conteo de ejes | `mAP50 (Pose)` / `mAP50-95 (Pose)` / `Precision (Pose)` / `Recall (Pose)` | **`mAP50(P) = 0.4957`** · **`mAP50-95(P) = 0.3555`** · **`Precision(P) = 0.5988`** · **`Recall(P) = 0.4926`** · **`mAP50(B) = 0.3743`** *(Extraído del checkpoint real `m3_ruedas_pose.pt`)* |
| **M4 (Bono - pasajeros)** | Segmentación anónima y conteo de pasajeros (`YOLO11s-seg` clase `person` en cabina) | Conteo anónimo con máscara de silueta sin reconocimiento facial | **Integrado en `/infer` y en la tabla `pasos.pasajeros`** |

---

## 4. Latencia de Punta a Punta

Mediciones reales obtenidas en el Endpoint Unificado corriendo sobre **Google Colab (GPU NVIDIA Tesla T4, CUDA 13.0, PyTorch 2.14.1+cu130, ONNXRuntime-GPU 1.32.0)**:

- **M1 (Detección de Placa ONNX + OCR):** `15.19 ms – 138.35 ms` *(15 ms cuando no hay recorte; ~138 ms con lectura OCR de alta confianza `99.92%` como en la placa `4994FBT`)*
- **M2 (Segmentación de Instancias `m2_vehiculos_seg.pt`):** `~35 ms – 48 ms`
- **M3 (Keypoints de Llantas y Conteo de Ejes `m3_ruedas_pose.pt`):** `~28 ms – 36 ms`
- **M4 (Segmentación y Conteo de Pasajeros en Cabina):** `~22 ms – 28 ms`
- **Latencia Total de Inferencia en GPU (`M1 + M2 + M3 + M4`):** **`105.91 ms – 244.42 ms` por frame** *(permite procesar video real en modo Caseta de **2 a 5 FPS** en tiempo real)*.

---

## 5. Mecanismo de Tiempo Real y Agente Conversacional

- **Tiempo Real:** Cada vez que `/api/v1/pasos/frame` registra un vehículo o genera una alerta, el backend publica el evento en **Pusher Channels** (`canal-peaje`, eventos `nuevo-paso` y `nueva-alerta`) y en el stream **SSE** (`/api/v1/eventos/stream`), actualizando de inmediato los contadores de recaudación, la tarjeta del vehículo con imagen de evidencia, las alertas y los indicadores del Arduino sin recargar la página.
- **Agente Conversacional:** Implementado en `web/backend/api/agente.py`. Normaliza la placa (`mayúsculas, sin guiones ni espacios`), consulta exclusivamente la base de datos SQL para responder los **4 estados oficiales** (`Registrada y con paso`, `Registrada sin paso`, `Identificada no registrada`, `No existe`) y aplica una matriz de distancia de edición ponderada para confusiones de OCR (`O↔0`, `I↔1`, `B↔8`, `S↔5`), sugiriendo coincidencias reales con `"¿Quisiste decir…?"`.

---

## 6. Problemas Encontrados y Soluciones

1. **Ausencia de la clase `minibus` en modelos preentrenados con COCO:**
   - *Problema:* El dataset COCO estándar solo incluye `car`, `motorcycle`, `bus` y `truck`, confundiendo los minibuses con buses o vagonetas.
   - *Solución:* Se empleó **YOLOE (`yoloe-11l-seg.pt`)** con vocabulario abierto (`prompts: minibus, van, moto, car, truck, bus`) para pre-etiquetar las máscaras automáticamente, refinarlas en **Roboflow** y entrenar el modelo propio de 5 clases.
2. **Confusiones de caracteres en lecturas OCR bajo ángulos inclinados (`B↔8`, `O↔0`, `I↔1`, `S↔5`):**
   - *Problema:* Una placa como `29B110559` o `FMO6719` podía ser consultada como `298110559` o `FM067I9`.
   - *Solución:* Se diseñó en el Agente Conversacional una función de distancia de Levenshtein con costo reducido (`0.25`) para pares de confusión OCR, sugiriendo automáticamente la placa registrada correcta.
3. **Límite de tamaño de payload (10 KB) en mensajes de Pusher Channels:**
   - *Problema:* Las imágenes anotadas en Base64 superan los 10 KB permitidos por evento en el plan gratuito de Pusher.
   - *Solución:* El evento de Pusher notifica los metadatos del paso y el cliente sincroniza la imagen de evidencia completa desde el backend sin pérdida de calidad.
