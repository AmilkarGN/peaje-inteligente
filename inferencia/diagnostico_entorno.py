"""
Script de Diagnóstico de Entorno en la Nube (Bono +5 puntos: Gestión de Entornos)
IAM-811 Machine Learning y Aprendizaje Profundo
Autor: Amilkar Hugo Guarachi Nina

Uso en RunPod / Google Colab / Servidor Web:
    python diagnostico_entorno.py --servicio inferencia-runpod
"""

import argparse
import datetime
import json
import os
import platform
import sys
from pathlib import Path

os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(__file__).resolve().parent / ".ultralytics"))


def obtener_version(modulo_nombre: str) -> str:
    try:
        mod = __import__(modulo_nombre)
        return getattr(mod, "__version__", "instalado (sin __version__)")
    except Exception as e:
        return f"no instalado ({e.__class__.__name__})"


def ejecutar_diagnostico(servicio: str, guardar_archivo: bool = True) -> dict:
    info = {
        "fecha_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "estudiante": "Amilkar Hugo Guarachi Nina",
        "servicio": servicio,
        "sistema_operativo": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "nodo_hostname": platform.node(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "entorno_virtual": os.environ.get("CONDA_DEFAULT_ENV")
        or os.environ.get("VIRTUAL_ENV")
        or "system/container",
        "librerias": {
            "torch": obtener_version("torch"),
            "torchvision": obtener_version("torchvision"),
            "ultralytics": obtener_version("ultralytics"),
            "onnxruntime": obtener_version("onnxruntime"),
            "cv2": obtener_version("cv2"),
            "fast_plate_ocr": obtener_version("fast_plate_ocr"),
            "easyocr": obtener_version("easyocr"),
            "fastapi": obtener_version("fastapi"),
            "django": obtener_version("django"),
        },
        "cuda": {
            "disponible": False,
            "version_cuda_torch": None,
            "version_cudnn": None,
            "cantidad_gpus": 0,
            "dispositivos": [],
        },
    }

    try:
        import torch

        info["cuda"]["disponible"] = bool(torch.cuda.is_available())
        info["cuda"]["version_cuda_torch"] = torch.version.cuda
        info["cuda"]["version_cudnn"] = (
            torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None
        )
        if torch.cuda.is_available():
            n = torch.cuda.device_count()
            info["cuda"]["cantidad_gpus"] = n
            for i in range(n):
                props = torch.cuda.get_device_properties(i)
                info["cuda"]["dispositivos"].append({
                    "id": i,
                    "nombre": props.name,
                    "vram_gb": round(props.total_memory / (1024 ** 3), 2),
                    "capacidad_computo": f"{props.major}.{props.minor}",
                })
    except Exception:
        pass

    try:
        import onnxruntime as ort

        info["onnxruntime_providers"] = ort.get_available_providers()
    except Exception:
        info["onnxruntime_providers"] = []

    lineas = [
        "=" * 72,
        "DIAGNÓSTICO DE ENTORNO EN LA NUBE - IAM-811 CONTROL DE PEAJE",
        "=" * 72,
        f"Estudiante         : {info['estudiante']}",
        f"Servicio           : {info['servicio']}",
        f"Fecha UTC          : {info['fecha_utc']}",
        f"Sistema Operativo  : {info['sistema_operativo']} ({info['nodo_hostname']})",
        f"Python             : {info['python_version']} ({info['python_executable']})",
        f"Entorno Activo     : {info['entorno_virtual']}",
        "-" * 72,
        f"PyTorch (torch)    : {info['librerias']['torch']}",
        f"CUDA disponible    : {info['cuda']['disponible']}",
        f"Versión CUDA       : {info['cuda']['version_cuda_torch']}",
        f"Versión cuDNN      : {info['cuda']['version_cudnn']}",
        f"GPUs detectadas    : {info['cuda']['cantidad_gpus']}",
    ]
    for g in info["cuda"]["dispositivos"]:
        lineas.append(f"  -> GPU #{g['id']}        : {g['nombre']} ({g['vram_gb']} GB VRAM, CC {g['capacidad_computo']})")
    lineas.extend([
        f"Ultralytics YOLO   : {info['librerias']['ultralytics']}",
        f"ONNX Runtime       : {info['librerias']['onnxruntime']} (Providers: {info['onnxruntime_providers']})",
        f"OpenCV (cv2)       : {info['librerias']['cv2']}",
        f"FastPlateOCR       : {info['librerias']['fast_plate_ocr']}",
        f"EasyOCR            : {info['librerias']['easyocr']}",
        f"FastAPI            : {info['librerias']['fastapi']}",
        f"Django             : {info['librerias']['django']}",
        "=" * 72,
    ])
    reporte_txt = "\n".join(lineas)
    print(reporte_txt)

    if guardar_archivo:
        out_dir = Path(__file__).resolve().parent
        (out_dir / f"diagnostico_{servicio}.txt").write_text(reporte_txt, encoding="utf-8")
        (out_dir / f"diagnostico_{servicio}.json").write_text(
            json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnóstico de entorno IAM-811")
    parser.add_argument("--servicio", default="inferencia-cloud", help="Nombre del entorno o servicio")
    args = parser.parse_args()
    ejecutar_diagnostico(args.servicio)
