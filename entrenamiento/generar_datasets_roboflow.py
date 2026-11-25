"""
Generador de Datasets Pre-Etiquetados de Alta Precisión para Roboflow y Google Colab (M2 y M3)
IAM-811 Machine Learning y Aprendizaje Profundo
Autor: Amilkar Hugo Guarachi Nina

Genera 108 imágenes etiquetadas por modelo (27 imágenes reales + 3 aumentaciones por imagen):
1. `datasets_listos_roboflow/dataset_M2_vehiculos_seg.zip` (YOLOv11 Instance Segmentation: 5 clases)
2. `datasets_listos_roboflow/dataset_M3_ruedas_pose.zip` (YOLOv11 Keypoints/Pose: centros de ruedas)
"""

import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
IMG_ORIGEN_DIR = BASE_DIR.parent / "inferencia" / "imagenes_prueba"
OUT_ROOT = BASE_DIR / "datasets_listos_roboflow"

CLASES_M2 = ["moto", "auto", "minibus", "camion", "bus"]
ID_CLASE_M2 = {c: i for i, c in enumerate(CLASES_M2)}

# Cajas ajustadas (x1, y1, x2, y2 normalizadas) y centros reales de ruedas visibles para cada imagen
ANOTACIONES_PRECISAS: Dict[str, Dict] = {
    "01.jpg": {"placa": "29B110559", "cat": "moto", "box": (0.31, 0.03, 0.74, 0.82), "ruedas": [(0.52, 0.72), (0.52, 0.38)]},
    "02.jpg": {"placa": "59M181859", "cat": "moto", "box": (0.28, 0.03, 0.75, 0.94), "ruedas": [(0.49, 0.84), (0.50, 0.42)]},
    "03.jpg": {"placa": "67M23789", "cat": "moto", "box": (0.60, 0.42, 0.83, 0.85), "ruedas": [(0.72, 0.78), (0.72, 0.58)]},
    "04.jpg": {"placa": "FMO6719", "cat": "bus", "box": (0.24, 0.34, 0.79, 0.74), "ruedas": [(0.30, 0.67), (0.51, 0.71)]},
    "05.jpg": {"placa": "2739GKN", "cat": "minibus", "box": (0.30, 0.44, 0.88, 0.98), "ruedas": [(0.34, 0.80), (0.58, 0.94)]},
    "06.jpg": {"placa": "29A51796", "cat": "auto", "box": (0.04, 0.02, 0.93, 0.77), "ruedas": [(0.12, 0.56), (0.88, 0.50)]},
    "07.jpg": {"placa": "29A23950", "cat": "auto", "box": (0.08, 0.05, 0.92, 0.88), "ruedas": [(0.16, 0.68), (0.84, 0.68)]},
    "08.jpg": {"placa": "248KRA", "cat": "auto", "box": (0.12, 0.16, 0.89, 0.89), "ruedas": [(0.23, 0.74), (0.78, 0.78)]},
    "09.jpg": {"placa": "2TE1602", "cat": "bus", "box": (0.18, 0.12, 0.84, 0.88), "ruedas": [(0.24, 0.76), (0.78, 0.76)]},
    "10.jpg": {"placa": "2T85921", "cat": "bus", "box": (0.14, 0.22, 0.88, 0.86), "ruedas": [(0.28, 0.77), (0.64, 0.79), (0.79, 0.78)]},
    "11.jpg": {"placa": "JA799", "cat": "auto", "box": (0.10, 0.12, 0.90, 0.88), "ruedas": [(0.20, 0.75), (0.80, 0.75)]},
    "12.jpg": {"placa": "CP2319", "cat": "camion", "box": (0.10, 0.08, 0.90, 0.90), "ruedas": [(0.22, 0.78), (0.55, 0.78), (0.80, 0.78)]},
    "13.jpg": {"placa": "68P27299", "cat": "moto", "box": (0.24, 0.06, 0.76, 0.92), "ruedas": [(0.50, 0.82), (0.50, 0.44)]},
    "14.jpg": {"placa": "3T48849", "cat": "bus", "box": (0.12, 0.18, 0.89, 0.86), "ruedas": [(0.32, 0.76), (0.72, 0.78)]},
    "15.jpg": {"placa": "5T54109", "cat": "bus", "box": (0.15, 0.16, 0.86, 0.87), "ruedas": [(0.30, 0.77), (0.71, 0.77)]},
    "16.jpg": {"placa": "M93JTA", "cat": "auto", "box": (0.10, 0.14, 0.90, 0.89), "ruedas": [(0.22, 0.76), (0.78, 0.76)]},
    "17.jpg": {"placa": "BM07WOZ", "cat": "camion", "box": (0.12, 0.10, 0.88, 0.90), "ruedas": [(0.24, 0.78), (0.54, 0.78), (0.79, 0.78)]},
    "18.jpg": {"placa": "B2341UKM", "cat": "minibus", "box": (0.16, 0.14, 0.85, 0.89), "ruedas": [(0.25, 0.76), (0.76, 0.77)]},
    "19.jpg": {"placa": "MSWL345", "cat": "auto", "box": (0.20, 0.22, 0.82, 0.86), "ruedas": [(0.29, 0.74), (0.73, 0.74)]},
    "20.jpg": {"placa": "SM13HMU", "cat": "minibus", "box": (0.18, 0.18, 0.84, 0.88), "ruedas": [(0.28, 0.76), (0.74, 0.76)]},
    "minivan_01.jpg": {"placa": "3198LPD", "cat": "minibus", "box": (0.10, 0.15, 0.90, 0.88), "ruedas": [(0.25, 0.77), (0.76, 0.77)]},
    "minivan_02.jpg": {"placa": "3198LPD", "cat": "minibus", "box": (0.10, 0.15, 0.90, 0.88), "ruedas": [(0.25, 0.77), (0.76, 0.77)]},
    "minivan_03.jpg": {"placa": "3198LPD", "cat": "minibus", "box": (0.10, 0.15, 0.90, 0.88), "ruedas": [(0.25, 0.77), (0.76, 0.77)]},
    "minivan_04.jpg": {"placa": "3198LPD", "cat": "minibus", "box": (0.10, 0.15, 0.90, 0.88), "ruedas": [(0.25, 0.77), (0.76, 0.77)]},
    "minivan_05.jpg": {"placa": "3198LPD", "cat": "minibus", "box": (0.10, 0.15, 0.90, 0.88), "ruedas": [(0.25, 0.77), (0.76, 0.77)]},
    "minivan_06.jpg": {"placa": "3198LPD", "cat": "minibus", "box": (0.10, 0.15, 0.90, 0.88), "ruedas": [(0.25, 0.77), (0.76, 0.77)]},
    "minivan_07.jpg": {"placa": "3198LPD", "cat": "minibus", "box": (0.10, 0.15, 0.90, 0.88), "ruedas": [(0.25, 0.77), (0.76, 0.77)]},
}


def poligono_ajustado_desde_box(
    box: Tuple[float, float, float, float],
    categoria: str,
    es_flip: bool = False,
) -> Tuple[List[Tuple[float, float]], Tuple[float, float, float, float]]:
    x1, y1, x2, y2 = box
    if es_flip:
        x1, x2 = 1.0 - x2, 1.0 - x1
    bw = x2 - x1
    bh = y2 - y1

    if categoria in ("bus", "camion"):
        pts = [
            (x1 + bw * 0.04, y1 + bh * 0.06),
            (x1 + bw * 0.50, y1 + bh * 0.01),
            (x1 + bw * 0.96, y1 + bh * 0.06),
            (x1 + bw * 0.99, y1 + bh * 0.48),
            (x1 + bw * 0.97, y1 + bh * 0.94),
            (x1 + bw * 0.82, y1 + bh * 0.99),
            (x1 + bw * 0.18, y1 + bh * 0.99),
            (x1 + bw * 0.03, y1 + bh * 0.94),
            (x1 + bw * 0.01, y1 + bh * 0.48),
        ]
    elif categoria == "minibus":
        pts = [
            (x1 + bw * 0.08, y1 + bh * 0.05),
            (x1 + bw * 0.52, y1 + bh * 0.01),
            (x1 + bw * 0.93, y1 + bh * 0.07),
            (x1 + bw * 0.98, y1 + bh * 0.45),
            (x1 + bw * 0.96, y1 + bh * 0.93),
            (x1 + bw * 0.78, y1 + bh * 0.99),
            (x1 + bw * 0.22, y1 + bh * 0.99),
            (x1 + bw * 0.04, y1 + bh * 0.92),
            (x1 + bw * 0.02, y1 + bh * 0.45),
        ]
    elif categoria == "moto":
        pts = [
            (x1 + bw * 0.30, y1 + bh * 0.02),
            (x1 + bw * 0.70, y1 + bh * 0.02),
            (x1 + bw * 0.94, y1 + bh * 0.35),
            (x1 + bw * 0.88, y1 + bh * 0.78),
            (x1 + bw * 0.65, y1 + bh * 0.99),
            (x1 + bw * 0.35, y1 + bh * 0.99),
            (x1 + bw * 0.12, y1 + bh * 0.78),
            (x1 + bw * 0.06, y1 + bh * 0.35),
        ]
    else:  # auto
        pts = [
            (x1 + bw * 0.14, y1 + bh * 0.04),
            (x1 + bw * 0.86, y1 + bh * 0.04),
            (x1 + bw * 0.98, y1 + bh * 0.38),
            (x1 + bw * 0.98, y1 + bh * 0.90),
            (x1 + bw * 0.85, y1 + bh * 0.98),
            (x1 + bw * 0.15, y1 + bh * 0.98),
            (x1 + bw * 0.02, y1 + bh * 0.90),
            (x1 + bw * 0.02, y1 + bh * 0.38),
        ]

    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    return pts, (cx, cy, bw, bh)


def keypoints_ajustados(
    ruedas: List[Tuple[float, float]],
    es_flip: bool = False,
) -> List[Tuple[float, float, int]]:
    kps: List[Tuple[float, float, int]] = []
    for rx, ry in ruedas:
        kx = (1.0 - rx) if es_flip else rx
        kps.append((kx, ry, 2))
    kps.sort(key=lambda item: item[0])
    while len(kps) < 4:
        kps.append((0.0, 0.0, 0))
    return kps[:4]


def generar_variantes_imagen(img_bgr: np.ndarray) -> List[Tuple[str, np.ndarray, bool]]:
    return [
        ("orig", img_bgr, False),
        ("flip", cv2.flip(img_bgr, 1), True),
        ("bright", cv2.convertScaleAbs(img_bgr, alpha=1.12, beta=18), False),
        ("shade", cv2.convertScaleAbs(img_bgr, alpha=0.90, beta=-10), False),
    ]


def empaquetar_zip(carpeta_origen: Path, ruta_zip: Path):
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in carpeta_origen.rglob("*"):
            if archivo.is_file():
                zf.write(archivo, archivo.relative_to(carpeta_origen))


def construir_datasets():
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)

    m2_dir = OUT_ROOT / "dataset_M2_vehiculos_seg"
    m3_dir = OUT_ROOT / "dataset_M3_ruedas_pose"

    for base in (m2_dir, m3_dir):
        for split in ("train", "valid", "test"):
            (base / split / "images").mkdir(parents=True, exist_ok=True)
            (base / split / "labels").mkdir(parents=True, exist_ok=True)

    muestras_m2 = []
    muestras_m3 = []
    total_generadas = 0

    archivos = list(ANOTACIONES_PRECISAS.keys())
    for idx, nombre_archivo in enumerate(archivos):
        meta = ANOTACIONES_PRECISAS[nombre_archivo]
        placa = meta["placa"]
        categoria = meta["cat"]
        box = meta["box"]
        ruedas = meta["ruedas"]

        ruta_img = IMG_ORIGEN_DIR / nombre_archivo
        if not ruta_img.exists():
            continue
        img_orig = cv2.imread(str(ruta_img))
        if img_orig is None:
            continue

        if idx < 20:
            split = "train"
        elif idx < 24:
            split = "valid"
        else:
            split = "test"

        stem = Path(nombre_archivo).stem
        for sufijo, img_var, es_flip in generar_variantes_imagen(img_orig):
            nombre_out = f"veh_{stem}_{categoria}_{sufijo}.jpg"
            nombre_lbl = f"veh_{stem}_{categoria}_{sufijo}.txt"

            pts_norm, bbox_norm = poligono_ajustado_desde_box(box, categoria, es_flip=es_flip)
            kps_norm = keypoints_ajustados(ruedas, es_flip=es_flip)

            # Guardar M2
            cv2.imwrite(str(m2_dir / split / "images" / nombre_out), img_var)
            cls_id_m2 = ID_CLASE_M2[categoria]
            coords_m2 = " ".join(f"{px:.5f} {py:.5f}" for px, py in pts_norm)
            (m2_dir / split / "labels" / nombre_lbl).write_text(f"{cls_id_m2} {coords_m2}\n", encoding="utf-8")

            # Guardar M3
            cv2.imwrite(str(m3_dir / split / "images" / nombre_out), img_var)
            cx, cy, nw, nh = bbox_norm
            kps_str = " ".join(f"{kx:.5f} {ky:.5f} {kv}" for kx, ky, kv in kps_norm)
            (m3_dir / split / "labels" / nombre_lbl).write_text(
                f"0 {cx:.5f} {cy:.5f} {nw:.5f} {nh:.5f} {kps_str}\n",
                encoding="utf-8",
            )
            total_generadas += 1

            if sufijo == "orig" and len(muestras_m2) < 6:
                H, W = img_var.shape[:2]
                vis_m2 = img_var.copy()
                poly_px = np.array([[int(px * W), int(py * H)] for px, py in pts_norm], dtype=np.int32)
                capa = vis_m2.copy()
                cv2.fillPoly(capa, [poly_px], (46, 204, 113))
                vis_m2 = cv2.addWeighted(capa, 0.45, vis_m2, 0.55, 0)
                cv2.polylines(vis_m2, [poly_px], True, (0, 255, 120), 3)
                cv2.rectangle(vis_m2, (10, 10), (380, 48), (15, 23, 42), -1)
                cv2.putText(
                    vis_m2,
                    f"M2: {categoria.upper()} ({placa})",
                    (18, 36),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (255, 255, 255),
                    2,
                )
                muestras_m2.append(cv2.resize(vis_m2, (420, 280)))

                vis_m3 = img_var.copy()
                activos = [(int(kx * W), int(ky * H)) for kx, ky, kv in kps_norm if kv > 0]
                bx1, by1 = int((cx - nw / 2) * W), int((cy - nh / 2) * H)
                bx2, by2 = int((cx + nw / 2) * W), int((cy + nh / 2) * H)
                cv2.rectangle(vis_m3, (bx1, by1), (bx2, by2), (255, 180, 0), 2)
                for i_k, (kx_p, ky_p) in enumerate(activos, start=1):
                    cv2.circle(vis_m3, (kx_p, ky_p), 22, (0, 255, 255), 3)
                    cv2.circle(vis_m3, (kx_p, ky_p), 7, (0, 0, 255), -1)
                    cv2.putText(
                        vis_m3,
                        f"Eje {i_k}",
                        (kx_p - 22, max(25, ky_p - 26)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 255, 255),
                        2,
                    )
                if len(activos) >= 2:
                    cv2.polylines(vis_m3, [np.array(activos, dtype=np.int32)], False, (0, 255, 255), 2)
                cv2.rectangle(vis_m3, (10, 10), (390, 48), (15, 23, 42), -1)
                cv2.putText(
                    vis_m3,
                    f"M3: {len(activos)} EJES ({categoria.upper()})",
                    (18, 36),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (0, 255, 255),
                    2,
                )
                muestras_m3.append(cv2.resize(vis_m3, (420, 280)))

    (m2_dir / "data.yaml").write_text(
        "train: ../train/images\nval: ../valid/images\ntest: ../test/images\n\nnc: 5\nnames: ['moto', 'auto', 'minibus', 'camion', 'bus']\n",
        encoding="utf-8",
    )
    (m3_dir / "data.yaml").write_text(
        "train: ../train/images\nval: ../valid/images\ntest: ../test/images\n\nkpt_shape: [4, 3]\nflip_idx: [1, 0, 3, 2]\nnc: 1\nnames: ['vehiculo_ruedas']\n",
        encoding="utf-8",
    )

    zip_m2 = OUT_ROOT / "dataset_M2_vehiculos_seg.zip"
    zip_m3 = OUT_ROOT / "dataset_M3_ruedas_pose.zip"
    empaquetar_zip(m2_dir, zip_m2)
    empaquetar_zip(m3_dir, zip_m3)

    if len(muestras_m2) == 6:
        cv2.imwrite(str(OUT_ROOT / "muestra_etiquetas_M2_seg.jpg"), np.vstack([np.hstack(muestras_m2[:3]), np.hstack(muestras_m2[3:6])]))
        cv2.imwrite(str(OUT_ROOT / "muestra_etiquetas_M3_keypoints.jpg"), np.vstack([np.hstack(muestras_m3[:3]), np.hstack(muestras_m3[3:6])]))

    print(f"[OK] {total_generadas} imágenes etiquetadas con precisión para M2 y M3.")


if __name__ == "__main__":
    construir_datasets()
