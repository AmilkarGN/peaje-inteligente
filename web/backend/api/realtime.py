"""
Motor de Tiempo Real (Pusher Channels + Cola SSE + Estado de Hardware Arduino)
IAM-811 Machine Learning y Aprendizaje Profundo
Autor: Amilkar Hugo Guarachi Nina
"""

import datetime
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

from django.conf import settings

try:
    import pusher
    HAS_PUSHER = True
except ImportError:
    HAS_PUSHER = False

_LOCK = threading.Lock()
_EVENTOS_RECIENTES = deque(maxlen=100)
_CONTADOR_EVENTO = 0

# Estado en la nube para el Dispositivo de Hardware Arduino (Bono +5 puntos)
_ESTADO_HARDWARE: Dict[str, Any] = {
    "codigo_evento": 0,
    "fase": "LISTO",               # IDENTIFICANDO | INFERENCIA | PASO_OK | ALERTA_NO_REGISTRADA | ALERTA_SIN_SALDO
    "led_verde": False,
    "led_amarillo": False,
    "led_rojo": False,
    "buzzer": False,
    "barrera_abierta": False,
    "placa": "---",
    "categoria": "---",
    "ejes": 0,
    "pasajeros": 0,
    "monto": 0.0,
    "mensaje_lcd": "PEAJE IAM-811 LISTO",
    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}


def _get_pusher_client():
    if not HAS_PUSHER:
        return None
    if not (settings.PUSHER_APP_ID and settings.PUSHER_KEY and settings.PUSHER_SECRET):
        return None
    try:
        return pusher.Pusher(
            app_id=str(settings.PUSHER_APP_ID),
            key=str(settings.PUSHER_KEY),
            secret=str(settings.PUSHER_SECRET),
            cluster=str(settings.PUSHER_CLUSTER or "us2"),
            ssl=True,
        )
    except Exception:
        return None


def actualizar_estado_hardware(
    fase: str,
    placa: str = "---",
    categoria: str = "---",
    ejes: int = 2,
    pasajeros: int = 1,
    monto: float = 0.0,
) -> Dict[str, Any]:
    """
    Actualiza la señal para el dispositivo físico Arduino (Bono +5 pts):
    - IDENTIFICANDO / INFERENCIA -> LED Amarillo encendido
    - PASO_OK                    -> LED Verde encendido + Barrera abierta (1 beep corto)
    - ALERTA_NO_REGISTRADA       -> LED Rojo parpadeante + Buzzer de alarma
    - ALERTA_SIN_SALDO           -> LED Rojo + Amarillo + Buzzer doble
    """
    global _ESTADO_HARDWARE
    with _LOCK:
        codigo = _ESTADO_HARDWARE["codigo_evento"] + 1
        es_alerta = fase.startswith("ALERTA")
        es_ok = fase == "PASO_OK"
        es_proc = fase in ("IDENTIFICANDO", "INFERENCIA")

        _ESTADO_HARDWARE = {
            "codigo_evento": codigo,
            "fase": fase,
            "led_verde": es_ok,
            "led_amarillo": es_proc or (fase == "ALERTA_SIN_SALDO"),
            "led_rojo": es_alerta,
            "buzzer": es_alerta,
            "barrera_abierta": es_ok,
            "placa": placa or "SIN_PLACA",
            "categoria": categoria,
            "ejes": ejes,
            "pasajeros": pasajeros,
            "monto": monto,
            "mensaje_lcd": f"{placa[:10]} {categoria[:5].upper()} Bs{monto:.0f}" if not es_alerta else f"ALERTA: {placa[:10]}",
            "comando_serial": (
                f"CMD:{codigo}|FASE:{fase}|PLACA:{placa or 'N/A'}|CAT:{categoria}|"
                f"EJES:{ejes}|PAS:{pasajeros}|BS:{monto:.1f}|"
                f"V:{int(es_ok)}|A:{int(es_proc)}|R:{int(es_alerta)}|BZ:{int(es_alerta)}"
            ),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        snapshot = dict(_ESTADO_HARDWARE)
    return snapshot


def obtener_estado_hardware() -> Dict[str, Any]:
    with _LOCK:
        return dict(_ESTADO_HARDWARE)


def emitir_evento_tiempo_real(tipo_evento: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publica un evento inmediato hacia el Panel Web Angular y hacia el monitor de Hardware:
    1. Si Pusher está configurado en .env, emite por WebSockets a `canal-peaje`.
    2. Registra el evento en el buffer SSE / stream para que todos los clientes conectados
       reciban la actualización al instante sin recargar la página.
    """
    global _CONTADOR_EVENTO
    with _LOCK:
        _CONTADOR_EVENTO += 1
        evento = {
            "id_evento": _CONTADOR_EVENTO,
            "evento": tipo_evento,
            "timestamp": time.time(),
            "fecha_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "data": payload,
        }
        _EVENTOS_RECIENTES.append(evento)

    cliente_pusher = _get_pusher_client()
    enviado_pusher = False
    if cliente_pusher is not None:
        try:
            # Para evitar superar el límite de 10KB de Pusher con imágenes base64 largas,
            # enviamos una copia con URL o miniatura ligera por Pusher.
            payload_pusher = dict(payload)
            if "paso" in payload_pusher and isinstance(payload_pusher["paso"], dict):
                paso_copia = dict(payload_pusher["paso"])
                if paso_copia.get("imagen_url", "").startswith("data:image") and len(paso_copia["imagen_url"]) > 6500:
                    paso_copia["imagen_url"] = f"/api/v1/pasos/{paso_copia['id']}/imagen"
                payload_pusher["paso"] = paso_copia

            cliente_pusher.trigger("canal-peaje", tipo_evento, payload_pusher)
            enviado_pusher = True
        except Exception:
            enviado_pusher = False

    evento["enviado_pusher"] = enviado_pusher
    return evento


def obtener_eventos_desde(ultimo_id: int = 0) -> List[Dict[str, Any]]:
    with _LOCK:
        return [e for e in _EVENTOS_RECIENTES if e["id_evento"] > ultimo_id]


def obtener_ultimo_id_evento() -> int:
    with _LOCK:
        return _CONTADOR_EVENTO
