#!/usr/bin/env bash
set -e

echo "============================================================"
echo "Iniciando Endpoint Unificado de Inferencia en RunPod (IAM-811)"
echo "Autor: Amilkar Hugo Guarachi Nina"
echo "============================================================"

python diagnostico_entorno.py --servicio runpod-gpu

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
