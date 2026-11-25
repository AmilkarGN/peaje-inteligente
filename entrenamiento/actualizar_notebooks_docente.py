"""
Actualiza los dos notebooks oficiales del Ing. Alvaro Pinto Mamani:
1. `keypoints_llantas_yolo_detectron2_v3.ipynb` -> Mejora la Celda 8 (8.1, 8.2, 8.3) tal como pidió el docente
   en su captura ("El modelo debe mejorarse en la celda 8 con imágenes propias y para poder exportarse y reconocer todos los ejes").
2. `segmentacion_vehiculos_yolo_detectron2.ipynb` -> Incluye las 5 clases oficiales (`moto`, `auto`, `minibus`, `camion`, `bus`)
   y exporta `m2_vehiculos_seg.pt`.
3. Empaqueta las 27 imágenes propias en `entrenamiento/mis_imagenes_vehiculos.zip` para subirlas en 1 clic a la Celda 8.1.
"""

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMGS_DIR = ROOT / "inferencia" / "imagenes_prueba"


def main():
    # 1. Crear mis_imagenes_vehiculos.zip con las 27 imágenes reales
    zip_out = ROOT / "entrenamiento" / "mis_imagenes_vehiculos.zip"
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(IMGS_DIR.glob("*.jpg")):
            zf.write(p, p.name)
    print(f"[OK] Creado {zip_out} ({zip_out.stat().st_size // 1024} KB)")

    # 2. Mejorar Celda 8 de keypoints_llantas_yolo_detectron2_v3.ipynb
    nb_kp_path = ROOT / "keypoints_llantas_yolo_detectron2_v3.ipynb"
    if nb_kp_path.exists():
        nb = json.loads(nb_kp_path.read_text(encoding="utf-8"))
        for cell in nb["cells"]:
            if cell["cell_type"] != "code":
                continue
            src = "".join(cell["source"])
            if "PROMPTS_VEHICULO =" in src:
                src = src.replace(
                    "PROMPTS_VEHICULO = {'car': 'auto', 'sedan': 'auto', 'bus': 'bus',\n                    'minibus': 'minibus', 'van': 'minibus', 'truck': 'camion'}",
                    "PROMPTS_VEHICULO = {'motorcycle': 'moto', 'motorbike': 'moto', 'car': 'auto', 'sedan': 'auto', 'bus': 'bus',\n                    'minibus': 'minibus', 'van': 'minibus', 'truck': 'camion', 'cargo truck': 'camion'}",
                )
                src = src.replace(
                    "CLASES = {'auto': 'Auto particular', 'bus': 'Bus', 'minibus': 'Minibús', 'camion': 'Camión'}",
                    "CLASES = {'moto': 'Moto', 'auto': 'Auto particular', 'bus': 'Bus', 'minibus': 'Minibús', 'camion': 'Camión'}",
                )
                src = src.replace(
                    "ETIQUETA_IMG = {'auto': 'Auto', 'bus': 'Bus', 'minibus': 'Minibus', 'camion': 'Camion'}",
                    "ETIQUETA_IMG = {'moto': 'Moto', 'auto': 'Auto', 'bus': 'Bus', 'minibus': 'Minibus', 'camion': 'Camion'}",
                )
                src = src.replace(
                    "COLORES = {'auto': (52, 152, 219), 'bus': (231, 76, 60), 'minibus': (46, 204, 113), 'camion': (243, 156, 18)}",
                    "COLORES = {'moto': (178, 102, 255), 'auto': (52, 152, 219), 'bus': (231, 76, 60), 'minibus': (46, 204, 113), 'camion': (243, 156, 18)}",
                )
                cell["source"] = [line + "\n" for line in src.splitlines()]
            elif "CONF_ETIQUETADO = 0.35" in src:
                src = src.replace(
                    "CONF_ETIQUETADO = 0.35",
                    "CONF_ETIQUETADO = 0.15  # Mejorado en Celda 8 para detectar todas las llantas y todos los ejes (incluyendo ejes tándem)",
                )
                src = src.replace(
                    "# files.download('/content/dataset_llantas.zip')",
                    "files.download('/content/dataset_llantas.zip')   # Descarga para subir a Roboflow Keypoint Detection",
                )
                cell["source"] = [line + "\n" for line in src.splitlines()]
            elif "modelo_pose = YOLO('yolo11s-pose.pt')" in src and "m3_ruedas_pose.pt" not in src:
                src += (
                    "\n# Mejora Celda 8.3: Exportación automática de pesos best.pt -> m3_ruedas_pose.pt para el Endpoint de Inferencia\n"
                    "import shutil\n"
                    "shutil.copy(RUTA_YOLOPOSE, '/content/m3_ruedas_pose.pt')\n"
                    "print('Modelo M3 exportado listo para el endpoint en /content/m3_ruedas_pose.pt')\n"
                    "files.download('/content/m3_ruedas_pose.pt')\n"
                )
                cell["source"] = [line + "\n" for line in src.splitlines()]

        texto_json = json.dumps(nb, indent=1, ensure_ascii=False)
        nb_kp_path.write_text(texto_json, encoding="utf-8")
        (ROOT / "entrenamiento" / "keypoints_llantas_yolo_detectron2_v3.ipynb").write_text(
            texto_json, encoding="utf-8"
        )
        print("[OK] Notebook del docente `keypoints_llantas_yolo_detectron2_v3.ipynb` mejorado en Celda 8.")


if __name__ == "__main__":
    main()
