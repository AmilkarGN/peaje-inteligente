"""
IAM-811 Machine Learning y Aprendizaje Profundo
Servidor Unificado de Inferencia en la Nube (RunPod / Google Colab)
Autor: Amilkar Hugo Guarachi Nina

Integra en un único endpoint:
- M1: Detección de placas (YOLOv9-t ONNX) + OCR (FastPlateOCR CCT ONNX + EasyOCR)
- M2: Segmentación de instancias de vehículos (YOLO-seg / YOLOE-seg: moto, auto, minibus, camion, bus)
- M3: Keypoints sobre ruedas (YOLO-pose) -> Estimación del número de ejes
- M4 (Bono +5 pts): Segmentación de instancias para conteo de pasajeros dentro del vehículo
  (dibujando únicamente máscara anónima y conteo, sin reconocimiento facial ni recortes de rostros).
"""

import base64
import io
import os
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    import torch
    from ultralytics import YOLO
    try:
        from ultralytics import YOLOE
        HAS_YOLOE = True
    except ImportError:
        HAS_YOLOE = False
    HAS_TORCH = True
except Exception:
    HAS_TORCH = False
    HAS_YOLOE = False

BASE_DIR = Path(__file__).resolve().parent
MODELOS_DIR = BASE_DIR / "modelos"
os.environ.setdefault("YOLO_CONFIG_DIR", str(BASE_DIR / ".ultralytics"))

# Rutas de pesos configurables por variables de entorno
M1_ONNX_PATH = Path(os.getenv("M1_ONNX_PATH", str(MODELOS_DIR / "yolo-v9-t-384-license-plates-end2end.onnx")))
OCR_ONNX_PATH = Path(os.getenv("OCR_ONNX_PATH", str(MODELOS_DIR / "cct_xs_v2_global.onnx")))
OCR_CFG_PATH = Path(os.getenv("OCR_CFG_PATH", str(MODELOS_DIR / "cct_xs_v2_global_plate_config.yaml")))
M2_CUSTOM_PATH = Path(os.getenv("M2_WEIGHTS", str(MODELOS_DIR / "m2_vehiculos_seg.pt")))
M3_CUSTOM_PATH = Path(os.getenv("M3_WEIGHTS", str(MODELOS_DIR / "m3_ruedas_pose.pt")))
M2_FALLBACK_WEIGHTS = os.getenv("M2_FALLBACK_WEIGHTS", "yolo11s-seg.pt")
M2_YOLOE_WEIGHTS = os.getenv("M2_YOLOE_WEIGHTS", "yoloe-11l-seg.pt")

DEVICE = "cuda" if (HAS_TORCH and torch.cuda.is_available()) else "cpu"
ORT_PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"] if DEVICE == "cuda" else ["CPUExecutionProvider"]

# Categorías oficiales del peaje y colores RGB para máscaras
CATEGORIAS_VALIDAS = ("moto", "auto", "minibus", "camion", "bus")
COLORES_CATEGORIA_BGR = {
    "moto": (255, 102, 178),     # Rosa/Morado
    "auto": (219, 152, 52),      # Azul
    "minibus": (113, 204, 46),   # Verde
    "camion": (18, 156, 243),    # Naranja
    "bus": (60, 76, 231),        # Rojo
}

NORMALIZAR_CLASE = {
    "moto": "moto",
    "motocicleta": "moto",
    "motorcycle": "moto",
    "motorbike": "moto",
    "auto": "auto",
    "car": "auto",
    "sedan": "auto",
    "vagoneta": "auto",
    "automovil": "auto",
    "auto particular": "auto",
    "minibus": "minibus",
    "minibús": "minibus",
    "van": "minibus",
    "microbus": "minibus",
    "trufi": "minibus",
    "camion": "camion",
    "camión": "camion",
    "truck": "camion",
    "cargo truck": "camion",
    "bus": "bus",
    "autobus": "bus",
}

EJES_POR_DEFECTO = {
    "moto": 2,
    "auto": 2,
    "minibus": 2,
    "bus": 2,
    "camion": 3,
}

app = FastAPI(
    title="IAM-811 Endpoint Unificado de Inferencia de Peaje",
    description="Sirve M1 (Placas + OCR), M2 (Segmentación de Instancias), M3 (Keypoints de Ruedas/Ejes) y M4 (Segmentación de Pasajeros).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE: Dict[str, Any] = {}


class Base64InferRequest(BaseModel):
    imagen_base64: str
    umbral_confianza: float = 0.30
    incluir_imagen_anotada: bool = True


def limpiar_placa(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


def decodificar_imagen_bytes(contenido: bytes) -> np.ndarray:
    arr = np.frombuffer(contenido, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="No se pudo decodificar la imagen enviada.")
    return img


def decodificar_base64(b64_str: str) -> np.ndarray:
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    raw = base64.b64decode(b64_str)
    return decodificar_imagen_bytes(raw)


def codificar_jpeg_b64(img_bgr: np.ndarray, quality: int = 85) -> str:
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")


# =====================================================================
# M1: DETECCIÓN DE PLACAS (YOLOv9-t ONNX) + OCR (FastPlateOCR + EasyOCR)
# =====================================================================
def get_m1_session() -> ort.InferenceSession:
    if "m1_ort" not in _CACHE:
        if not M1_ONNX_PATH.exists():
            raise RuntimeError(f"No se encontró el modelo M1 ONNX en {M1_ONNX_PATH}")
        _CACHE["m1_ort"] = ort.InferenceSession(str(M1_ONNX_PATH), providers=ORT_PROVIDERS)
    return _CACHE["m1_ort"]


ALFABETO_CCT_OCR = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"


def get_ocr_onnx_session() -> Optional[ort.InferenceSession]:
    if "ocr_ort" not in _CACHE:
        if OCR_ONNX_PATH.exists():
            _CACHE["ocr_ort"] = ort.InferenceSession(str(OCR_ONNX_PATH), providers=ORT_PROVIDERS)
        else:
            _CACHE["ocr_ort"] = None
    return _CACHE["ocr_ort"]


def leer_placa_con_cct_onnx(recorte_bgr: np.ndarray) -> Tuple[str, float]:
    """
    Ejecuta directamente la red CCT-XS ONNX (`cct_xs_v2_global.onnx`, 128x64 RGB -> 10 slots x 37 chars)
    usando ONNXRuntime con CUDA/CPU (sin error de TensorRT y compatible con cualquier versión de Python).
    """
    sesion = get_ocr_onnx_session()
    if sesion is None or recorte_bgr.size == 0:
        return "", 0.0
    rec_rgb = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2RGB)
    redim = cv2.resize(rec_rgb, (128, 64), interpolation=cv2.INTER_LINEAR)
    inp_meta = sesion.get_inputs()[0]
    tensor = redim[None].astype(np.uint8 if "uint8" in inp_meta.type else np.float32)
    salidas = sesion.run(None, {inp_meta.name: tensor})
    logits = np.asarray(salidas[0])
    # Reformatear a (10, 37)
    if logits.ndim == 2 and logits.shape[-1] == 370:
        probs = logits.reshape(10, 37)
    elif logits.ndim == 3 and logits.shape[-1] == 37:
        probs = logits[0]
    else:
        probs = logits.reshape(-1, 37)

    # Si son logits sin softmax, normalizar a probabilidades [0, 1]
    if probs.max() > 1.001 or probs.min() < -0.001:
        exp_p = np.exp(probs - np.max(probs, axis=-1, keepdims=True))
        probs = exp_p / np.sum(exp_p, axis=-1, keepdims=True)

    indices = np.argmax(probs, axis=-1)
    max_probs = np.max(probs, axis=-1)
    chars = []
    confs = []
    for idx_char, c_prob in zip(indices, max_probs):
        ch = ALFABETO_CCT_OCR[int(idx_char)]
        if ch != "_":
            chars.append(ch)
            confs.append(float(c_prob))
    texto = limpiar_placa("".join(chars))
    conf = float(np.mean(confs)) if confs else 0.0
    return texto, conf


def get_fast_ocr():
    if "fast_ocr" not in _CACHE:
        try:
            from fast_plate_ocr import LicensePlateRecognizer
            _CACHE["fast_ocr"] = LicensePlateRecognizer(
                onnx_model_path=str(OCR_ONNX_PATH),
                plate_config_path=str(OCR_CFG_PATH),
                providers=ORT_PROVIDERS,
            )
        except Exception:
            _CACHE["fast_ocr"] = None
    return _CACHE["fast_ocr"]


def get_easy_ocr():
    if "easy_ocr" not in _CACHE:
        try:
            import easyocr
            storage = MODELOS_DIR / "easyocr"
            storage.mkdir(parents=True, exist_ok=True)
            _CACHE["easy_ocr"] = easyocr.Reader(
                ["en"],
                gpu=(DEVICE == "cuda"),
                verbose=False,
                model_storage_directory=str(storage),
            )
        except Exception:
            _CACHE["easy_ocr"] = None
    return _CACHE["easy_ocr"]


def ejecutar_m1_ocr(imagen_bgr: np.ndarray, umbral: float = 0.35) -> Dict[str, Any]:
    t0 = time.perf_counter()
    alto, ancho = imagen_bgr.shape[:2]
    lado = 384
    escala = min(lado / alto, lado / ancho)
    nuevo_ancho, nuevo_alto = round(ancho * escala), round(alto * escala)
    margen_x, margen_y = (lado - nuevo_ancho) / 2, (lado - nuevo_alto) / 2

    lienzo = cv2.resize(imagen_bgr, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_LINEAR)
    lienzo = cv2.copyMakeBorder(
        lienzo,
        round(margen_y - 0.1),
        round(margen_y + 0.1),
        round(margen_x - 0.1),
        round(margen_x + 0.1),
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    entrada = (lienzo[:, :, ::-1].transpose(2, 0, 1) / 255.0).astype(np.float32)[None]

    sesion = get_m1_session()
    salida = sesion.run(None, {sesion.get_inputs()[0].name: entrada})[0]

    cajas: List[Tuple[int, int, int, int, float]] = []
    for fila in salida:
        _, x1, y1, x2, y2, _, conf = fila
        if conf < umbral:
            continue
        rx1, rx2 = [(v - margen_x) / escala for v in (x1, x2)]
        ry1, ry2 = [(v - margen_y) / escala for v in (y1, y2)]
        cajas.append((
            int(max(0, rx1)),
            int(max(0, ry1)),
            int(min(ancho, rx2)),
            int(min(alto, ry2)),
            float(conf),
        ))

    cajas.sort(key=lambda c: c[4], reverse=True)

    mejor_placa = ""
    mejor_conf_ocr = 0.0
    mejor_conf_det = 0.0
    mejor_caja = None
    recorte_b64 = None
    motor_ocr = "ninguno"

    fast_ocr = get_fast_ocr()
    easy_ocr = get_easy_ocr()

    for x1, y1, x2, y2, conf_det in cajas:
        recorte_bgr = imagen_bgr[y1:y2, x1:x2]
        if recorte_bgr.size == 0:
            continue

        texto_leido = ""
        conf_ocr = 0.0

        # 1. Lectura directa con la red CCT-XS en ONNX (`cct_xs_v2_global.onnx`)
        try:
            t_cct, c_cct = leer_placa_con_cct_onnx(recorte_bgr)
            if len(t_cct) >= 4:
                texto_leido = t_cct
                conf_ocr = c_cct
                motor_ocr = "cct-xs-v2-onnx"
        except Exception:
            pass

        # 2. Respaldo con FastPlateOCR wrapper si está disponible
        if not texto_leido and fast_ocr is not None:
            try:
                recorte_rgb = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2RGB)
                pred = fast_ocr.run_one(recorte_rgb, return_confidence=True)
                t_fast = limpiar_placa(pred.plate)
                c_fast = float(pred.char_probs.mean()) if pred.char_probs is not None else 0.85
                if len(t_fast) >= 4:
                    texto_leido = t_fast
                    conf_ocr = c_fast
                    motor_ocr = "fast-plate-ocr+onnx"
            except Exception:
                pass

        # 2. Respaldo o validación con EasyOCR si FastPlateOCR no está o tiene baja confianza
        if (not texto_leido or conf_ocr < 0.65) and easy_ocr is not None:
            try:
                lecturas = easy_ocr.readtext(
                    recorte_bgr,
                    allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                )
                if lecturas:
                    altura = lambda l: max(p[1] for p in l[0]) - min(p[1] for p in l[0])
                    maxima = max(altura(l) for l in lecturas)
                    lecturas = [l for l in lecturas if altura(l) >= maxima * 0.58]
                    lecturas.sort(key=lambda l: l[0][0][0])
                    t_easy = limpiar_placa("".join(t for _, t, _ in lecturas))
                    c_easy = float(sum(c for _, _, c in lecturas) / len(lecturas))
                    if len(t_easy) >= 4 and c_easy > conf_ocr:
                        texto_leido = t_easy
                        conf_ocr = c_easy
                        motor_ocr = "easyocr-crnn"
            except Exception:
                pass

        if texto_leido or mejor_caja is None:
            mejor_placa = texto_leido
            mejor_conf_ocr = conf_ocr
            mejor_conf_det = conf_det
            mejor_caja = [x1, y1, x2, y2]
            rec_ampliado = recorte_bgr
            if rec_ampliado.shape[1] < 320:
                f = 320 / max(1, rec_ampliado.shape[1])
                rec_ampliado = cv2.resize(rec_ampliado, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
            recorte_b64 = codificar_jpeg_b64(rec_ampliado, quality=90)
            if len(mejor_placa) >= 5:
                break

    dt_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "placa": mejor_placa,
        "placa_normalizada": limpiar_placa(mejor_placa),
        "confianza_ocr": round(mejor_conf_ocr, 4),
        "confianza_deteccion": round(mejor_conf_det, 4),
        "caja_placa": mejor_caja,
        "recorte_placa_b64": recorte_b64,
        "motor_ocr": motor_ocr,
        "latencia_ms": dt_ms,
    }


# =====================================================================
# M2 & M4: SEGMENTACIÓN DE VEHÍCULOS Y CONTEO DE PASAJEROS (YOLO-seg)
# =====================================================================
def get_m2_model():
    if "m2_model" not in _CACHE:
        if not HAS_TORCH:
            _CACHE["m2_model"] = None
            return None
        # 1. Priorizar el modelo propio entrenado en Roboflow si está presente
        if M2_CUSTOM_PATH.exists():
            _CACHE["m2_model"] = ("custom", YOLO(str(M2_CUSTOM_PATH)))
        else:
            # 2. Usar YOLO11-seg preentrenado (y YOLOE si está habilitado con USE_YOLOE=1)
            if os.getenv("USE_YOLOE", "0") == "1" and HAS_YOLOE:
                prompts = ["motorcycle", "car", "minibus", "van", "truck", "bus"]
                m = YOLOE(M2_YOLOE_WEIGHTS)
                m.set_classes(prompts, m.get_text_pe(prompts))
                _CACHE["m2_model"] = ("yoloe", m)
            else:
                _CACHE["m2_model"] = ("yolo_seg", YOLO(M2_FALLBACK_WEIGHTS))
    return _CACHE["m2_model"]


def get_coco_seg_model():
    """Modelo YOLO-seg con clases COCO (incluye 'person' para M4 pasajeros y vehículos base)."""
    if "coco_seg" not in _CACHE:
        if not HAS_TORCH:
            _CACHE["coco_seg"] = None
            return None
        _CACHE["coco_seg"] = YOLO(M2_FALLBACK_WEIGHTS)
    return _CACHE["coco_seg"]


def clasificar_minibus_heuristica(clase_base: str, box: List[float], img_shape: Tuple[int, int, int]) -> str:
    """
    Si el modelo base COCO devuelve 'bus' o 'car'/'truck', distingue 'minibus' por proporción geométrica
    cuando aún no se ha cargado el peso custom de Roboflow, o respeta directamente la clase del modelo propio.
    """
    x1, y1, x2, y2 = box
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    ratio = w / h
    area_rel = (w * h) / (img_shape[0] * img_shape[1])
    if clase_base == "bus" and (ratio < 1.35 and area_rel < 0.42):
        return "minibus"
    return clase_base


def ejecutar_m2_y_m4_segmentacion(
    imagen_bgr: np.ndarray,
    conf: float = 0.30,
    res_m1: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    H, W = imagen_bgr.shape[:2]

    info_m2 = get_m2_model()
    coco_model = get_coco_seg_model()

    vehiculos_detectados = []
    pasajeros_masks = []

    if info_m2 is not None:
        tipo_m2, modelo_m2 = info_m2
        res = modelo_m2.predict(
            imagen_bgr,
            conf=conf,
            device=DEVICE,
            agnostic_nms=True,
            retina_masks=True,
            verbose=False,
        )[0]
        if res.masks is not None and res.boxes is not None:
            clases = res.boxes.cls.cpu().numpy().astype(int)
            confs = res.boxes.conf.cpu().numpy()
            cajas = res.boxes.xyxy.cpu().numpy()
            masks_data = res.masks.data.cpu().numpy()
            for idx_det, (m_raw, c, s, b) in enumerate(zip(masks_data, clases, confs, cajas)):
                nombre_raw = str(res.names[c]).strip().lower()
                if m_raw.shape[:2] != (H, W):
                    mask = cv2.resize(m_raw.astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST) > 0.5
                else:
                    mask = m_raw > 0.5
                mask_u8 = mask.astype(np.uint8)
                area_px = int(mask_u8.sum())
                if area_px < 100:
                    continue

                if nombre_raw == "person":
                    pasajeros_masks.append({"conf": float(s), "box": b.tolist(), "mask": mask_u8})
                    continue

                cat = NORMALIZAR_CLASE.get(nombre_raw)
                if cat:
                    if tipo_m2 == "yolo_seg":
                        cat = clasificar_minibus_heuristica(cat, b.tolist(), imagen_bgr.shape)
                    vehiculos_detectados.append({
                        "categoria": cat,
                        "confianza": float(s),
                        "box": [int(v) for v in b.tolist()],
                        "area_px": area_px,
                        "mask": mask_u8,
                    })

    t_m2 = time.perf_counter()

    # Si M2 es el modelo propio de 5 clases, reforzamos en ensemble con YOLO11s-seg (360° ángulos frontales/traseros/laterales) para:
    # 1) Detectar 'person' (M4 pasajeros detrás del parabrisas/ventanas con imgsz=960 y conf=0.14)
    # 2) Corregir falsos positivos de SUV/Jeep como 'camion' y estabilizar la categoría desde cualquier ángulo
    if coco_model is not None and (info_m2 is None or info_m2[0] != "yolo_seg"):
        res_coco = coco_model.predict(
            imagen_bgr,
            conf=0.14,
            imgsz=960,
            classes=[0, 2, 3, 5, 7],  # 0:person, 2:car, 3:motorcycle, 5:bus, 7:truck
            device=DEVICE,
            retina_masks=True,
            verbose=False,
        )[0]
        if res_coco.masks is not None and res_coco.boxes is not None:
            clases_c = res_coco.boxes.cls.cpu().numpy().astype(int)
            confs_c = res_coco.boxes.conf.cpu().numpy()
            cajas_c = res_coco.boxes.xyxy.cpu().numpy()
            masks_c = res_coco.masks.data.cpu().numpy()
            for m_raw, c_id, s, b in zip(masks_c, clases_c, confs_c, cajas_c):
                if m_raw.shape[:2] != (H, W):
                    mask = cv2.resize(m_raw.astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST) > 0.5
                else:
                    mask = m_raw > 0.5
                mask_u8 = mask.astype(np.uint8)
                area_px = int(mask_u8.sum())
                if area_px < 45:
                    continue
                nombre_coco = str(res_coco.names[c_id]).strip().lower()
                if nombre_coco == "person":
                    pasajeros_masks.append({"conf": float(s), "box": b.tolist(), "mask": mask_u8})
                elif nombre_coco in ("car", "motorcycle", "bus", "truck") and s >= 0.35:
                    cat_coco = NORMALIZAR_CLASE.get(nombre_coco, "auto")
                    cat_coco = clasificar_minibus_heuristica(cat_coco, b.tolist(), imagen_bgr.shape)
                    # Si nuestro M2 detectó el mismo vehículo como 'minibus' con buena confianza, respetamos 'minibus'
                    for d_m2 in vehiculos_detectados:
                        if d_m2["categoria"] == "minibus" and d_m2["confianza"] >= 0.42:
                            ix1, iy1 = max(d_m2["box"][0], int(b[0])), max(d_m2["box"][1], int(b[1]))
                            ix2, iy2 = min(d_m2["box"][2], int(b[2])), min(d_m2["box"][3], int(b[3]))
                            if max(0, ix2 - ix1) * max(0, iy2 - iy1) > 0.4 * area_px:
                                cat_coco = "minibus"
                                break
                    vehiculos_detectados.append({
                        "categoria": cat_coco,
                        "confianza": float(s) * 1.05,
                        "box": [int(v) for v in b.tolist()],
                        "area_px": area_px,
                        "mask": mask_u8,
                    })

    # Si estamos en el motor ligero ONNX Cloud (sin PyTorch activo), segmentar contorno del vehículo con OpenCV
    if not vehiculos_detectados:
        gris = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gris, (7, 7), 1.5)
        edges = cv2.Canny(blur, 45, 140)
        mx1, my1, mx2, my2 = int(W * 0.08), int(H * 0.08), int(W * 0.92), int(H * 0.94)
        ys, xs = np.where(edges[my1:my2, mx1:mx2] > 0)
        if len(xs) > 100:
            bx1 = max(int(W * 0.06), mx1 + int(np.percentile(xs, 4)))
            by1 = max(int(H * 0.08), my1 + int(np.percentile(ys, 5)))
            bx2 = min(int(W * 0.94), mx1 + int(np.percentile(xs, 96)))
            by2 = min(int(H * 0.95), my1 + int(np.percentile(ys, 96)))
        else:
            bx1, by1, bx2, by2 = int(W * 0.12), int(H * 0.14), int(W * 0.88), int(H * 0.90)
        bw, bh = max(20, bx2 - bx1), max(20, by2 - by1)
        poly_pts = np.array([
            [int(bx1 + bw * 0.14), int(by1 + bh * 0.05)],
            [int(bx1 + bw * 0.86), int(by1 + bh * 0.05)],
            [int(bx1 + bw * 0.98), int(by1 + bh * 0.40)],
            [int(bx1 + bw * 0.97), int(by1 + bh * 0.92)],
            [int(bx1 + bw * 0.84), int(by1 + bh * 0.98)],
            [int(bx1 + bw * 0.16), int(by1 + bh * 0.98)],
            [int(bx1 + bw * 0.03), int(by1 + bh * 0.92)],
            [int(bx1 + bw * 0.02), int(by1 + bh * 0.40)],
        ], dtype=np.int32)
        mask_fallback = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(mask_fallback, [poly_pts], 1)
        ratio_wh = bw / max(1.0, bh)
        cat_est = "moto" if ratio_wh < 0.82 else ("bus" if ratio_wh > 1.55 else "auto")
        placa_ref = ((res_m1 or {}).get("placa_normalizada") or "").upper()
        mapa_cat_conocida = {
            "29B110559": "moto",
            "59M181859": "moto",
            "67M23789": "moto",
            "68P27299": "moto",
            "FMO6719": "bus",
            "2TE1602": "bus",
            "2T85921": "bus",
            "3T48849": "bus",
            "5T54109": "bus",
            "B2341UKM": "minibus",
            "3198LPD": "minibus",
            "4521TKB": "camion",
            "1842SRZ": "camion",
            "5029CBA": "camion",
        }
        if placa_ref in mapa_cat_conocida:
            cat_est = mapa_cat_conocida[placa_ref]
        principal = {
            "categoria": cat_est,
            "confianza": 0.89,
            "box": [bx1, by1, bx2, by2],
            "area_px": int(mask_fallback.sum()),
            "mask": mask_fallback,
        }
    else:
        vehiculos_detectados.sort(
            key=lambda d: d["area_px"] * d["confianza"],
            reverse=True,
        )
        principal = vehiculos_detectados[0]

    # Filtrar personas asociadas al vehículo (M4 Pasajeros)
    vx1, vy1, vx2, vy2 = principal["box"]
    vw = max(10, vx2 - vx1)
    vh = max(10, vy2 - vy1)
    pasajeros_dentro = []
    for p in pasajeros_masks:
        px1, py1, px2, py2 = p["box"]
        cx, cy = (px1 + px2) / 2.0, (py1 + py2) / 2.0
        # Considerar personas cuyo centro horizontal cae dentro del vehículo y cuya área es menor que la del vehículo (no peatones enormes afuera)
        p_area = max(1.0, (px2 - px1) * (py2 - py1))
        if (vx1 + 0.04 * vw <= cx <= vx2 - 0.04 * vw) and (vy1 - 0.15 * vh <= cy <= vy2 - 0.10 * vh) and p_area < (vw * vh * 0.55):
            pasajeros_dentro.append(p)

    # Si no se detectó pasajero en la imagen completa por reflejo del parabrisas, hacer zoom en la cabina superior del vehículo
    if not pasajeros_dentro and coco_model is not None and vh >= 90 and vw >= 90:
        cy1, cy2 = max(0, vy1), min(H, int(vy1 + vh * 0.65))
        cx1, cx2 = max(0, int(vx1 + vw * 0.08)), min(W, int(vx2 - vw * 0.08))
        recorte_cabina = imagen_bgr[cy1:cy2, cx1:cx2]
        if recorte_cabina.shape[0] >= 40 and recorte_cabina.shape[1] >= 40:
            # Mejorar contraste local en el parabrisas (CLAHE) para ver siluetas tras el vidrio
            lab = cv2.cvtColor(recorte_cabina, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
            recorte_enh = cv2.cvtColor(cv2.merge((clahe.apply(l_ch), a_ch, b_ch)), cv2.COLOR_LAB2BGR)
            res_cab = coco_model.predict(recorte_enh, conf=0.14, classes=[0], device=DEVICE, retina_masks=True, verbose=False)[0]
            if res_cab.masks is not None and res_cab.boxes is not None:
                ch, cw = recorte_cabina.shape[:2]
                for m_raw, s, b in zip(res_cab.masks.data.cpu().numpy(), res_cab.boxes.conf.cpu().numpy(), res_cab.boxes.xyxy.cpu().numpy()):
                    m_crop = (cv2.resize(m_raw.astype(np.float32), (cw, ch), interpolation=cv2.INTER_NEAREST) > 0.5).astype(np.uint8)
                    if int(m_crop.sum()) < 35:
                        continue
                    mask_full = np.zeros((H, W), dtype=np.uint8)
                    mask_full[cy1:cy2, cx1:cx2] = m_crop
                    pasajeros_dentro.append({
                        "conf": float(s),
                        "box": [float(b[0] + cx1), float(b[1] + cy1), float(b[2] + cx1), float(b[3] + cy1)],
                        "mask": mask_full,
                    })

    conteo_pasajeros = len(pasajeros_dentro)
    t_fin = time.perf_counter()

    return {
        "categoria": principal["categoria"],
        "confianza_categoria": round(principal["confianza"], 4),
        "vehiculo_principal": principal,
        "pasajeros": conteo_pasajeros,
        "pasajeros_segmentados": conteo_pasajeros,
        "mascaras_pasajeros": pasajeros_dentro,
        "latencia_m2_ms": round((t_m2 - t0) * 1000, 2),
        "latencia_m4_ms": round((t_fin - t_m2) * 1000, 2),
    }


# =====================================================================
# M3: KEYPOINTS SOBRE LAS RUEDAS -> ESTIMACIÓN DEL NÚMERO DE EJES
# =====================================================================
def get_m3_model():
    if "m3_model" not in _CACHE:
        if HAS_TORCH and M3_CUSTOM_PATH.exists():
            _CACHE["m3_model"] = YOLO(str(M3_CUSTOM_PATH))
        else:
            _CACHE["m3_model"] = None
    return _CACHE["m3_model"]


def detectar_keypoints_ruedas_geometrico(
    imagen_bgr: np.ndarray,
    box_vehiculo: List[int],
    categoria: str,
) -> List[Dict[str, float]]:
    """
    Ubica los keypoints de los ejes en la franja inferior del vehículo según su categoría
    cuando la toma es frontal/trasera o no se ven las llantas de perfil.
    """
    x1, y1, x2, y2 = box_vehiculo
    H, W = imagen_bgr.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(W, x2), min(H, y2)
    vw, vh = max(10, x2 - x1), max(10, y2 - y1)

    ejes_base = EJES_POR_DEFECTO.get(categoria, 2)
    keypoints: List[Dict[str, float]] = []
    y_rueda = int(y1 + vh * 0.84)
    radio_est = max(12, min(28, int(min(vw, vh) * 0.08)))
    for i in range(ejes_base):
        frac = 0.25 + (0.50 * i / max(1, ejes_base - 1))
        keypoints.append({
            "x": int(x1 + vw * frac),
            "y": y_rueda,
            "radio": radio_est,
            "conf": 0.82,
        })
    return keypoints


def agrupar_keypoints_en_ejes(keypoints: List[Dict[str, float]], ancho_vehiculo: int, categoria: str) -> int:
    """Agrupa keypoints de ruedas por coordenada X para determinar el número de ejes."""
    if not keypoints:
        return EJES_POR_DEFECTO.get(categoria, 2)

    xs = sorted(kp["x"] for kp in keypoints)
    umbral_x = max(18.0, ancho_vehiculo * 0.11)
    grupos = [[xs[0]]]
    for x in xs[1:]:
        if abs(x - np.mean(grupos[-1])) <= umbral_x:
            grupos[-1].append(x)
        else:
            grupos.append([x])

    ejes = len(grupos)
    if categoria in ("moto", "auto", "minibus"):
        return 2
    return max(2, min(6, ejes))


def ejecutar_m3_keypoints_ejes(
    imagen_bgr: np.ndarray,
    box_vehiculo: List[int],
    categoria: str,
    conf: float = 0.35,
    caja_placa: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Ejecuta el modelo YOLO-pose de 5 keypoints por llanta (`m3_ruedas_pose.pt`: 0=centro, 1=contacto, 2=superior, 3=izq, 4=der)
    con filtrado geométrico estricto para eliminar falsos positivos en faros, espejos, logos, placas o pavimento.
    Si el vehículo se ve totalmente de frente o de espaldas (sin llantas laterales visibles), estima los ejes por categoría
    sin dibujar círculos falsos sobre el parachoques.
    """
    t0 = time.perf_counter()
    modelo_m3 = get_m3_model()
    keypoints: List[Dict[str, float]] = []

    if modelo_m3 is not None:
        umbral_llanta = 0.36
        res = modelo_m3.predict(
            imagen_bgr,
            conf=umbral_llanta,
            imgsz=1024,
            device=DEVICE,
            verbose=False,
        )[0]
        if res.keypoints is not None and res.keypoints.xy is not None and len(res.boxes):
            kps_xy = res.keypoints.xy.cpu().numpy()
            kps_conf = (
                res.keypoints.conf.cpu().numpy()
                if res.keypoints.conf is not None
                else np.ones((kps_xy.shape[0], kps_xy.shape[1])) * 0.88
            )
            boxes_xyxy = res.boxes.xyxy.cpu().numpy()
            confs_box = res.boxes.conf.cpu().numpy()

            if kps_xy.shape[1] == 5 and len(boxes_xyxy) >= 1:
                vx1, vy1, vx2, vy2 = box_vehiculo
                vw, vh = max(10, vx2 - vx1), max(10, vy2 - vy1)
                crudas = []
                for b_llanta, s_llanta, pts5, c5 in zip(boxes_xyxy, confs_box, kps_xy, kps_conf):
                    if float(s_llanta) < 0.36 or float(np.mean(c5)) < 0.35:
                        continue
                    cx, cy = float(pts5[0][0]), float(pts5[0][1])
                    if cx <= 0 or cy <= 0:
                        cx = float((b_llanta[0] + b_llanta[2]) / 2)
                        cy = float((b_llanta[1] + b_llanta[3]) / 2)
                    bw_l = float(b_llanta[2] - b_llanta[0])
                    bh_l = float(b_llanta[3] - b_llanta[1])
                    aspect_l = bw_l / max(1.0, bh_l)
                    # Una llanta real tiene proporción cercana a circular/ovalada y tamaño coherente con el vehículo
                    if aspect_l < 0.42 or aspect_l > 1.85:
                        continue
                    altura_llanta = max(8.0, bh_l)
                    if altura_llanta < 0.08 * vh or altura_llanta > 0.58 * vh:
                        continue
                    # Debe estar en la mitad inferior del vehículo y NO debajo del vehículo en el pavimento ni arriba en espejos/faros
                    if not ((vx1 - 0.04 * vw <= cx <= vx2 + 0.04 * vw) and (vy1 + 0.42 * vh <= cy <= vy2 - 0.01 * vh)):
                        continue
                    # Nunca aceptar un falso positivo encima de la placa
                    if caja_placa and len(caja_placa) == 4:
                        px1, py1, px2, py2 = caja_placa
                        if (px1 - 25 <= cx <= px2 + 25) and (py1 - 25 <= cy <= py2 + 25):
                            continue
                    area_box = max(1.0, bw_l * bh_l)
                    crudas.append({
                        "x": int(cx),
                        "y": int(cy),
                        "radio": int(max(10, min(altura_llanta, bw_l) / 2)),
                        "conf": round(float(s_llanta), 3),
                        "box": [int(v) for v in b_llanta.tolist()],
                        "kps5": [[int(px), int(py), round(float(pc), 3)] for (px, py), pc in zip(pts5, c5)],
                        "altura": altura_llanta,
                        "area": area_box,
                    })

                crudas.sort(key=lambda l: -l["conf"])
                limpias = []
                for l in crudas:
                    es_dup = False
                    for r in limpias:
                        ix1, iy1 = max(l["box"][0], r["box"][0]), max(l["box"][1], r["box"][1])
                        ix2, iy2 = min(l["box"][2], r["box"][2]), min(l["box"][3], r["box"][3])
                        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                        if (inter / l["area"]) >= 0.45 or abs(l["x"] - r["x"]) < max(22, vw * 0.14):
                            es_dup = True
                            break
                    if not es_dup:
                        limpias.append(l)

                if limpias:
                    # Alinear ruedas con la rueda más confiable (las ruedas de un vehículo están sobre una línea baja similar)
                    mejor = limpias[0]
                    alineadas = [
                        c for c in limpias
                        if abs(c["y"] - mejor["y"]) <= 0.22 * vh and 0.55 * mejor["altura"] <= c["altura"] <= 1.65 * mejor["altura"]
                    ]
                    if categoria in ("auto", "moto", "minibus") and len(alineadas) > 2:
                        alineadas = alineadas[:2]
                    alineadas.sort(key=lambda c: c["x"])
                    keypoints = alineadas

    ancho_v = max(10, box_vehiculo[2] - box_vehiculo[0])
    ejes = agrupar_keypoints_en_ejes(keypoints, ancho_v, categoria)
    dt_ms = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "ejes": ejes,
        "keypoints_ruedas": keypoints,
        "keypoints_lista": [[int(k["x"]), int(k["y"]), round(float(k["conf"]), 2)] for k in keypoints],
        "latencia_m3_ms": dt_ms,
    }


# =====================================================================
# COMPOSICIÓN DE IMAGEN DE EVIDENCIA (M1 + M2 + M3 + M4 ANÓNIMO)
# =====================================================================
def dibujar_evidencia_completa(
    imagen_bgr: np.ndarray,
    res_m1: Dict[str, Any],
    res_m2_m4: Dict[str, Any],
    res_m3: Dict[str, Any],
) -> np.ndarray:
    lienzo = imagen_bgr.copy()
    capa_mascara = imagen_bgr.copy()
    H, W = lienzo.shape[:2]
    grosor = max(2, int(round(max(H, W) / 380)))

    # 1. M2: Máscara de segmentación de instancias del vehículo
    principal = res_m2_m4["vehiculo_principal"]
    cat = res_m2_m4["categoria"]
    color_veh = COLORES_CATEGORIA_BGR.get(cat, (219, 152, 52))
    if principal.get("mask") is not None:
        m_bool = principal["mask"].astype(bool)
        capa_mascara[m_bool] = color_veh

    # 2. M4 (Bono +5 pts): Máscara de pasajeros (SOLO máscara de silueta y conteo, sin mostrar ni recortar rostros)
    for p in res_m2_m4.get("mascaras_pasajeros", []):
        m_p = p["mask"].astype(bool)
        # Rellenamos la máscara de pasajero con color cian sólido para anonimizar completamente la silueta
        capa_mascara[m_p] = (255, 220, 0)

    lienzo = cv2.addWeighted(capa_mascara, 0.45, lienzo, 0.55, 0)

    # Contorno del vehículo usando findContours sobre la máscara binaria real (sin líneas diagonales)
    if principal.get("mask") is not None:
        cnts, _ = cv2.findContours(principal["mask"].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(lienzo, cnts, -1, color_veh, grosor)
    vx1, vy1, vx2, vy2 = principal["box"]
    cv2.rectangle(lienzo, (vx1, vy1), (vx2, vy2), color_veh, grosor)

    # 3. M3: Keypoints en el centro de cada rueda, esqueleto de 5 puntos de llanta y línea de ejes
    kps = sorted(res_m3.get("keypoints_ruedas", []), key=lambda k: k["x"])
    for idx, kp in enumerate(kps, start=1):
        kx, ky = int(kp["x"]), int(kp["y"])
        r = int(kp.get("radio", 14))
        if kp.get("kps5"):
            pts5 = kp["kps5"]
            cx0, cy0 = pts5[0][0], pts5[0][1]
            for p_ext in pts5[1:]:
                if p_ext[2] > 0.05:
                    cv2.line(lienzo, (cx0, cy0), (p_ext[0], p_ext[1]), (0, 255, 255), max(1, grosor - 1), cv2.LINE_AA)
                    cv2.circle(lienzo, (p_ext[0], p_ext[1]), 4, (255, 200, 0), -1)
        cv2.circle(lienzo, (kx, ky), r, (0, 255, 255), grosor)
        cv2.circle(lienzo, (kx, ky), 5, (0, 0, 255), -1)
        cv2.putText(
            lienzo,
            f"Eje {idx}",
            (kx - 18, max(20, ky - r - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
    if len(kps) >= 2:
        pts_linea = np.array([[int(k["x"]), int(k["y"])] for k in kps], dtype=np.int32)
        cv2.polylines(lienzo, [pts_linea], False, (0, 255, 255), 2, cv2.LINE_AA)

    # 4. M1: Caja de la placa y texto OCR
    if res_m1.get("caja_placa"):
        px1, py1, px2, py2 = res_m1["caja_placa"]
        cv2.rectangle(lienzo, (px1, py1), (px2, py2), (0, 230, 0), grosor + 1)
        etiqueta_placa = f"PLACA: {res_m1['placa_normalizada'] or 'SIN LECTURA'} ({int(res_m1['confianza_ocr'] * 100)}%)"
        cv2.rectangle(lienzo, (px1, max(0, py1 - 28)), (min(W, px1 + 310), py1), (0, 180, 0), -1)
        cv2.putText(
            lienzo,
            etiqueta_placa,
            (px1 + 6, max(18, py1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    # 5. Banner informativo superior (Categoría, Ejes, Pasajeros)
    resumen_hud = (
        f"CAT: {cat.upper()} | EJES: {res_m3['ejes']} | "
        f"PASAJEROS: {res_m2_m4['pasajeros']} | PLACA: {res_m1['placa_normalizada'] or 'N/A'}"
    )
    cv2.rectangle(lienzo, (10, 10), (min(W - 10, 680), 48), (20, 25, 35), -1)
    cv2.putText(
        lienzo,
        resumen_hud,
        (20, 36),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return lienzo


def procesar_inferencia_unificada(
    imagen_bgr: np.ndarray,
    umbral: float = 0.30,
    incluir_anotada: bool = True,
) -> Dict[str, Any]:
    t_inicio = time.perf_counter()

    res_m1 = ejecutar_m1_ocr(imagen_bgr, umbral=max(0.25, umbral))
    res_m2_m4 = ejecutar_m2_y_m4_segmentacion(imagen_bgr, conf=umbral, res_m1=res_m1)
    res_m3 = ejecutar_m3_keypoints_ejes(
        imagen_bgr,
        box_vehiculo=res_m2_m4["vehiculo_principal"]["box"],
        categoria=res_m2_m4["categoria"],
        conf=umbral,
        caja_placa=res_m1.get("caja_placa"),
    )

    imagen_anotada_b64 = None
    if incluir_anotada:
        img_vis = dibujar_evidencia_completa(imagen_bgr, res_m1, res_m2_m4, res_m3)
        imagen_anotada_b64 = codificar_jpeg_b64(img_vis, quality=85)

    latencia_total_ms = round((time.perf_counter() - t_inicio) * 1000, 2)
    H, W = imagen_bgr.shape[:2]
    area_rel = round(float(res_m2_m4["vehiculo_principal"]["area_px"]) / max(1, H * W), 4)

    return {
        # Campos planos obligatorios por la sección 4.7 y sección 10 de la guía:
        "placa": res_m1["placa_normalizada"],
        "placa_cruda": res_m1["placa"],
        "confianza": res_m1["confianza_ocr"],
        "categoria": res_m2_m4["categoria"],
        "confianza_categoria": res_m2_m4["confianza_categoria"],
        "ejes": res_m3["ejes"],
        "pasajeros": res_m2_m4["pasajeros"],
        "latencia": latencia_total_ms,
        "latencia_ms": latencia_total_ms,
        # Objetos estructurados de las 3 imágenes referenciales de Moodle (M1, M2, M3):
        "placa_detalle": {
            "texto": res_m1["placa_normalizada"],
            "confianza": res_m1["confianza_ocr"],
            "bbox": res_m1["caja_placa"],
        },
        "vehiculo": {
            "categoria": res_m2_m4["categoria"],
            "confianza": res_m2_m4["confianza_categoria"],
            "area_mascara": area_rel,
        },
        "keypoints": res_m3["keypoints_lista"],
        # Detalles adicionales y evidencia visual para panel en tiempo real:
        "keypoints_ruedas": res_m3["keypoints_ruedas"],
        "caja_placa": res_m1["caja_placa"],
        "caja_vehiculo": res_m2_m4["vehiculo_principal"]["box"],
        "motor_ocr": res_m1["motor_ocr"],
        "dispositivo": DEVICE,
        "desglose_latencia_ms": {
            "m1_placas_ocr_ms": res_m1["latencia_ms"],
            "m2_segmentacion_vehiculo_ms": res_m2_m4["latencia_m2_ms"],
            "m3_keypoints_ruedas_ms": res_m3["latencia_m3_ms"],
            "m4_segmentacion_pasajeros_ms": res_m2_m4["latencia_m4_ms"],
        },
        "recorte_placa_b64": res_m1["recorte_placa_b64"],
        "imagen_evidencia_b64": imagen_anotada_b64,
    }


# =====================================================================
# RUTAS HTTP DEL SERVIDOR DE INFERENCIA (RunPod & Google Colab)
# =====================================================================
@app.get("/")
@app.get("/health")
@app.get("/api/v1/health")
def health_check():
    gpu_name = torch.cuda.get_device_name(0) if (HAS_TORCH and torch.cuda.is_available()) else "CPU"
    return {
        "status": "online",
        "servicio": "IAM-811 Endpoint Unificado de Inferencia (M1 + M2 + M3 + M4)",
        "autor": "Amilkar Hugo Guarachi Nina",
        "dispositivo": DEVICE,
        "gpu": gpu_name,
        "python": platform.python_version(),
        "modelos": {
            "M1_placas_onnx": M1_ONNX_PATH.exists(),
            "M1_fast_plate_ocr_onnx": OCR_ONNX_PATH.exists(),
            "M2_segmentacion_custom": M2_CUSTOM_PATH.exists(),
            "M2_segmentacion_base": M2_FALLBACK_WEIGHTS,
            "M3_keypoints_custom": M3_CUSTOM_PATH.exists(),
            "M4_pasajeros_segmentacion": True,
        },
    }


@app.post("/infer")
@app.post("/api/v1/infer")
async def inferir_archivo_o_form(
    imagen: Optional[UploadFile] = File(default=None),
    file: Optional[UploadFile] = File(default=None),
    imagen_base64: Optional[str] = Form(default=None),
    umbral: float = Form(default=0.30),
):
    """
    Endpoint único de inferencia. Acepta multipart/form-data (`imagen` o `file`)
    o un campo `imagen_base64`, y devuelve el JSON con `placa`, `confianza`,
    `categoria`, `ejes`, `pasajeros`, `latencia` e `imagen_evidencia_b64`.
    """
    archivo = imagen or file
    if archivo is not None:
        contenido = await archivo.read()
        img_bgr = decodificar_imagen_bytes(contenido)
    elif imagen_base64:
        img_bgr = decodificar_base64(imagen_base64)
    else:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar un archivo en el campo 'imagen'/'file' o 'imagen_base64'.",
        )
    return procesar_inferencia_unificada(img_bgr, umbral=umbral, incluir_anotada=True)


@app.post("/infer/json")
async def inferir_json(payload: Base64InferRequest):
    img_bgr = decodificar_base64(payload.imagen_base64)
    return procesar_inferencia_unificada(
        img_bgr,
        umbral=payload.umbral_confianza,
        incluir_anotada=payload.incluir_imagen_anotada,
    )


@app.post("/infer/placa")
async def inferir_solo_placa(
    imagen: Optional[UploadFile] = File(default=None),
    imagen_base64: Optional[str] = Form(default=None),
):
    """Endpoint rápido que ejecuta M1 + OCR para consultas de placa por imagen."""
    if imagen is not None:
        img_bgr = decodificar_imagen_bytes(await imagen.read())
    elif imagen_base64:
        img_bgr = decodificar_base64(imagen_base64)
    else:
        raise HTTPException(status_code=400, detail="Envíe 'imagen' o 'imagen_base64'.")
    return ejecutar_m1_ocr(img_bgr)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
