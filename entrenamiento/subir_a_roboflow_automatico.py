"""
Script para Subir Automáticamente los Datasets Pre-Etiquetados (M2 y M3) a Roboflow
IAM-811 Machine Learning y Aprendizaje Profundo
Autor: Amilkar Hugo Guarachi Nina

Uso:
  1. Crea una cuenta gratuita en https://app.roboflow.com
  2. Crea dos proyectos en tu Workspace de Roboflow:
     - Proyecto 1: `peaje-vehiculos-seg` (Tipo: Instance Segmentation)
     - Proyecto 2: `peaje-ruedas-keypoints` (Tipo: Keypoint Detection)
  3. OPCIÓN MÁS RÁPIDA (Sin consola, 10 segundos):
     Arrastra directamente a la web de Roboflow ("Upload Data") los archivos:
     - `datasets_listos_roboflow/dataset_M2_vehiculos_seg.zip`
     - `datasets_listos_roboflow/dataset_M3_ruedas_pose.zip`
     Roboflow reconocerá automáticamente las carpetas `images/`, `labels/` y `data.yaml`
     con todas las máscaras y keypoints ya dibujados.
  4. OPCIÓN POR API (Ejecutando este script):
     python subir_a_roboflow_automatico.py --api-key TU_ROBOFLOW_API_KEY --workspace TU_WORKSPACE
"""

import argparse
from pathlib import Path


def subir_con_sdk(api_key: str, workspace_slug: str, proj_m2: str, proj_m3: str):
    from roboflow import Roboflow

    rf = Roboflow(api_key=api_key)
    ws = rf.workspace(workspace_slug)

    base = Path(__file__).resolve().parent / "datasets_listos_roboflow"
    m2_dir = base / "dataset_M2_vehiculos_seg"
    m3_dir = base / "dataset_M3_ruedas_pose"

    print(f"Subiendo dataset M2 desde {m2_dir} al proyecto {proj_m2}...")
    ws.upload_dataset(
        dataset_path=str(m2_dir),
        project_name=proj_m2,
        num_workers=4,
        project_license="MIT",
        project_type="instance-segmentation",
    )

    print(f"Subiendo dataset M3 desde {m3_dir} al proyecto {proj_m3}...")
    ws.upload_dataset(
        dataset_path=str(m3_dir),
        project_name=proj_m3,
        num_workers=4,
        project_license="MIT",
        project_type="keypoint-detection",
    )
    print("[OK] Ambos datasets fueron subidos a Roboflow con sus etiquetas.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Subir datasets M2 y M3 a Roboflow")
    parser.add_argument("--api-key", required=True, help="Private API Key de Roboflow")
    parser.add_argument("--workspace", required=True, help="ID del Workspace en Roboflow")
    parser.add_argument("--proj-m2", default="peaje-vehiculos-seg", help="Slug del proyecto M2")
    parser.add_argument("--proj-m3", default="peaje-ruedas-keypoints", help="Slug del proyecto M3")
    args = parser.parse_args()
    subir_con_sdk(args.api_key, args.workspace, args.proj_m2, args.proj_m3)
