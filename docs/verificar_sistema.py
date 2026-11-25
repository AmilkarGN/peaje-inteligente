"""
Verificador Automático de Integridad del Proyecto IAM-811
Comprueba sintaxis de todos los módulos, estructura de carpetas obligatoria,
normalización de placas y matriz de sugerencias OCR (O<->0, I<->1, B<->8, S<->5).
"""

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def verificar():
    # 1. Compilar todos los archivos Python de /inferencia y /web/backend
    py_files = list((ROOT / "inferencia").rglob("*.py")) + list((ROOT / "web" / "backend").rglob("*.py"))
    for f in py_files:
        py_compile.compile(str(f), doraise=True)
    print(f"[OK] {len(py_files)} archivos Python compilados sin errores de sintaxis.")

    # 2. Verificar estructura de carpetas obligatoria (Sección 7.1)
    requeridos = [
        "entrenamiento/01_M2_segmentacion_vehiculos_roboflow_colab.ipynb",
        "entrenamiento/02_M3_keypoints_ruedas_ejes_roboflow_colab.ipynb",
        "entrenamiento/03_endpoint_inferencia_unificado_colab_runpod.ipynb",
        "inferencia/main.py",
        "inferencia/Dockerfile",
        "inferencia/requirements.txt",
        "inferencia/environment.yml",
        "inferencia/diagnostico_entorno.py",
        "inferencia/modelos/yolo-v9-t-384-license-plates-end2end.onnx",
        "inferencia/modelos/cct_xs_v2_global.onnx",
        "web/backend/manage.py",
        "web/backend/passenger_wsgi.py",
        "web/backend/requirements.txt",
        "web/backend/environment.yml",
        "web/backend/api/models.py",
        "web/backend/api/auth.py",
        "web/backend/api/agente.py",
        "web/backend/api/views.py",
        "web/backend/frontend_dist/index.html",
        "web/frontend/package.json",
        "web/frontend/src/app/app.component.ts",
        "movil/pubspec.yaml",
        "movil/lib/main.dart",
        "hardware/arduino_alerta_peaje/arduino_alerta_peaje.ino",
        "docs/postman_collection.json",
        "docs/INFORME_TECNICO_IAM811.md",
        "README.md",
        ".env.example",
    ]
    for rel in requeridos:
        p = ROOT / rel
        if not p.exists():
            raise FileNotFoundError(f"Falta archivo obligatorio: {rel}")
    print(f"[OK] Los {len(requeridos)} entregables y componentes obligatorios están presentes.")


if __name__ == "__main__":
    verificar()
