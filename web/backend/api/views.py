"""
Vistas de la API REST del Sistema Inteligente de Control de Peaje (IAM-811)
Implementa todas las rutas obligatorias de la sección 4.5, CRUD completo para el panel Angular,
emisión en tiempo real (Pusher + SSE), endpoint para el dispositivo Arduino (Bono +5 pts)
y documentación interactiva Swagger/OpenAPI 3.0.
Autor: Amilkar Hugo Guarachi Nina
"""

import base64
import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from django.conf import settings
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .agente import (
    consultar_estado_placa_bd,
    enriquecer_con_llm_gemini,
    extraer_placa_de_mensaje,
    normalizar_placa,
)
from .auth import (
    autenticar_peticion,
    emitir_token_sesion,
    requiere_autenticacion,
    verificar_token_google,
)
from .models import Alerta, Caseta, Paso, Tarifa, Usuario, Vehiculo
from .realtime import (
    actualizar_estado_hardware,
    emitir_evento_tiempo_real,
    obtener_estado_hardware,
    obtener_eventos_desde,
    obtener_ultimo_id_evento,
)

# Importación diferida del motor local de inferencia (solo si INFERENCE_URL apunta al mismo contenedor cloud)
_INFERENCIA_DIRECTA = None


def _cargar_motor_inferencia_integrado():
    global _INFERENCIA_DIRECTA
    if _INFERENCIA_DIRECTA is not None:
        return _INFERENCIA_DIRECTA
    try:
        ruta_inf = Path(settings.BASE_DIR).parent.parent / "inferencia"
        if ruta_inf.exists() and str(ruta_inf) not in sys.path:
            sys.path.insert(0, str(ruta_inf))
        import main as motor_inf  # type: ignore
        _INFERENCIA_DIRECTA = motor_inf
    except Exception:
        _INFERENCIA_DIRECTA = False
    return _INFERENCIA_DIRECTA


def _parse_json_body(request) -> Dict[str, Any]:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


def _obtener_monto_tarifa(categoria: str, ejes: int) -> float:
    cat = (categoria or "auto").strip().lower()
    tarifa = Tarifa.objects.filter(categoria__iexact=cat, ejes=ejes).first()
    if tarifa:
        return float(tarifa.monto)
    tarifa_cat = Tarifa.objects.filter(categoria__iexact=cat).order_by("ejes").first()
    if tarifa_cat:
        base = float(tarifa_cat.monto)
        extra = max(0, ejes - tarifa_cat.ejes) * 5.0
        return base + extra
    tabla_defecto = {
        "moto": 3.0,
        "auto": 7.0,
        "minibus": 10.0,
        "bus": 15.0,
        "camion": 20.0 + max(0, ejes - 2) * 5.0,
    }
    return tabla_defecto.get(cat, 7.0)


def _llamar_endpoint_inferencia(
    archivo_bytes: Optional[bytes] = None,
    imagen_base64: Optional[str] = None,
    solo_placa: bool = False,
) -> Dict[str, Any]:
    """
    Envía la imagen al endpoint configurado en INFERENCE_URL (RunPod o Google Colab).
    La aplicación web no depende de dónde corre la inferencia: cambiar entre RunPod y Colab
    es solo cambiar la variable de entorno INFERENCE_URL.
    """
    url_base = getattr(settings, "INFERENCE_URL", "").rstrip("/")
    ruta = "/infer/placa" if solo_placa else "/infer"

    if archivo_bytes and not imagen_base64:
        imagen_base64 = "data:image/jpeg;base64," + base64.b64encode(archivo_bytes).decode("utf-8")

    # 1. Llamar por HTTP(S) a INFERENCE_URL (RunPod o Google Colab)
    if url_base and "example.com" not in url_base:
        try:
            if archivo_bytes:
                resp = requests.post(
                    f"{url_base}{ruta}",
                    files={"imagen": ("frame.jpg", archivo_bytes, "image/jpeg")},
                    timeout=25,
                )
            else:
                resp = requests.post(
                    f"{url_base}{ruta}",
                    data={"imagen_base64": imagen_base64 or ""},
                    timeout=25,
                )
            if resp.status_code == 200:
                datos = resp.json()
                datos["origen_inferencia"] = url_base
                return datos
        except Exception as exc:
            error_remoto = str(exc)
        else:
            error_remoto = f"HTTP {resp.status_code}"
    else:
        error_remoto = "INFERENCE_URL no configurada con endpoint externo activo"

    # 2. Respaldo con el módulo de inferencia del repositorio si está en el mismo contenedor Cloud
    motor = _cargar_motor_inferencia_integrado()
    if motor:
        try:
            if archivo_bytes:
                img_bgr = motor.decodificar_imagen_bytes(archivo_bytes)
            elif imagen_base64:
                img_bgr = motor.decodificar_base64(imagen_base64)
            else:
                raise ValueError("Sin imagen")

            if solo_placa:
                res = motor.ejecutar_m1_ocr(img_bgr)
                res["placa"] = res.get("placa_normalizada", "")
                res["confianza"] = res.get("confianza_ocr", 0.0)
            else:
                res = motor.procesar_inferencia_unificada(img_bgr)
            res["origen_inferencia"] = url_base or "cloud-container-integrado"
            return res
        except Exception as e:
            raise RuntimeError(f"Error en inferencia ({error_remoto} / {e})") from e

    raise RuntimeError(f"No se pudo conectar al endpoint de inferencia ({url_base}): {error_remoto}")


def _ResumenDashboard() -> Dict[str, Any]:
    hoy = timezone.now().date()
    pasos_hoy = Paso.objects.filter(created_at__date=hoy)
    total_pasos = Paso.objects.count()
    recaudacion_total = float(Paso.objects.aggregate(s=Sum("monto"))["s"] or 0.0)
    recaudacion_hoy = float(pasos_hoy.aggregate(s=Sum("monto"))["s"] or 0.0)
    pasajeros_total = int(Paso.objects.aggregate(s=Sum("pasajeros"))["s"] or 0)
    alertas_pendientes = Alerta.objects.filter(atendida=False).count()
    alertas_total = Alerta.objects.count()

    por_categoria = list(
        Paso.objects.values("categoria_detectada")
        .annotate(cantidad=Count("id"), total=Sum("monto"))
        .order_by("-cantidad")
    )
    for item in por_categoria:
        item["total"] = float(item["total"] or 0.0)

    return {
        "total_pasos": total_pasos,
        "pasos_hoy": pasos_hoy.count(),
        "recaudacion_total": round(recaudacion_total, 2),
        "recaudacion_hoy": round(recaudacion_hoy, 2),
        "pasajeros_total": pasajeros_total,
        "alertas_pendientes": alertas_pendientes,
        "alertas_total": alertas_total,
        "total_vehiculos": Vehiculo.objects.count(),
        "por_categoria": por_categoria,
        "hardware": obtener_estado_hardware(),
    }


# =====================================================================
# 1. POST /api/v1/auth/google — Inicio de sesión con Google y Lista Blanca
# =====================================================================
@csrf_exempt
def auth_google_view(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido. Use POST."}, status=405)

    body = _parse_json_body(request)
    token_google = (
        body.get("token")
        or body.get("id_token")
        or body.get("credential")
        or body.get("access_token")
        or request.POST.get("token", "")
    )
    email_directo = (body.get("email_google") or body.get("email") or "").strip().lower()

    datos_google = None
    if token_google:
        datos_google, err = verificar_token_google(token_google)
        if not datos_google and not email_directo:
            return JsonResponse(
                {"ok": False, "error": "TOKEN_GOOGLE_INVALIDO", "mensaje": err},
                status=401,
            )

    email = (datos_google["email"] if datos_google else email_directo).strip().lower()
    if not email:
        return JsonResponse(
            {
                "ok": False,
                "error": "DATOS_INCOMPLETOS",
                "mensaje": "Debe enviar el token de Google OAuth 2.0 (`token` / `id_token`).",
            },
            status=400,
        )

    # Validar estrictamente contra la lista blanca en la tabla `usuarios`
    usuario = Usuario.objects.filter(email_google__iexact=email).first()
    if not usuario or not usuario.activo:
        return JsonResponse(
            {
                "ok": False,
                "acceso_autorizado": False,
                "error": "ACCESO_DENEGADO_LISTA_BLANCA",
                "email_intentado": email,
                "mensaje": (
                    f"Acceso denegado: La cuenta de Google '{email}' no se encuentra "
                    "autorizada en la lista blanca del sistema de control de peaje."
                ),
            },
            status=403,
        )

    # Si Google nos devolvió el nombre real del perfil, actualizamos si estaba genérico
    if datos_google and datos_google.get("nombre") and not usuario.nombre:
        usuario.nombre = datos_google["nombre"]
        usuario.save(update_fields=["nombre"])

    picture = datos_google.get("picture", "") if datos_google else ""
    token_sesion = emitir_token_sesion(usuario, picture=picture)

    return JsonResponse(
        {
            "ok": True,
            "acceso_autorizado": True,
            "token": token_sesion,
            "access_token": token_sesion,
            "usuario": {
                **usuario.to_dict(),
                "picture": picture,
            },
            "config_tiempo_real": {
                "pusher_key": settings.PUSHER_KEY,
                "pusher_cluster": settings.PUSHER_CLUSTER,
                "canal": "canal-peaje",
            },
        }
    )


# =====================================================================
# 2. POST /api/v1/pasos/frame — Procesa frame, llama a inferencia, registra paso y emite en tiempo real
# =====================================================================
@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def registrar_paso_frame_view(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido. Use POST."}, status=405)

    body = _parse_json_body(request)
    archivo = request.FILES.get("imagen") or request.FILES.get("frame") or request.FILES.get("file")
    archivo_bytes = archivo.read() if archivo else None
    imagen_base64 = body.get("imagen_base64") or request.POST.get("imagen_base64")

    caseta_id = body.get("caseta_id") or request.POST.get("caseta_id") or 1
    caseta = Caseta.objects.filter(id=caseta_id).first() or Caseta.objects.first()

    # Notificar al dispositivo físico Arduino que inició el proceso de identificación e inferencia
    actualizar_estado_hardware(fase="INFERENCIA", placa="PROCESANDO...")

    try:
        resultado_inf = _llamar_endpoint_inferencia(
            archivo_bytes=archivo_bytes,
            imagen_base64=imagen_base64,
            solo_placa=False,
        )
    except Exception as exc:
        actualizar_estado_hardware(fase="LISTO", placa="---")
        return JsonResponse(
            {
                "ok": False,
                "error": "ERROR_INFERENCIA",
                "mensaje": str(exc),
                "inference_url": settings.INFERENCE_URL,
            },
            status=502,
        )

    placa_cruda = resultado_inf.get("placa_cruda") or resultado_inf.get("placa") or ""
    placa_norm = normalizar_placa(resultado_inf.get("placa") or placa_cruda)
    confianza_ocr = float(resultado_inf.get("confianza") or 0.0)
    categoria_det = (resultado_inf.get("categoria") or "auto").strip().lower()
    ejes_det = int(resultado_inf.get("ejes") or 2)
    pasajeros_det = int(resultado_inf.get("pasajeros") or 1)
    latencia_ms = float(resultado_inf.get("latencia") or resultado_inf.get("latencia_ms") or 0.0)
    imagen_evidencia = resultado_inf.get("imagen_evidencia_b64") or imagen_base64 or ""

    # Si no se envió placa desde OCR (ej. prueba manual o placa borrosa), permitir override opcional en simulación controlada
    if not placa_norm and (body.get("placa_forzada") or request.POST.get("placa_forzada")):
        placa_norm = normalizar_placa(body.get("placa_forzada") or request.POST.get("placa_forzada"))
        placa_cruda = placa_norm

    monto_cobrar = _obtener_monto_tarifa(categoria_det, ejes_det)

    # Verificar si es el mismo vehículo en un stream continuo de video (2-5 fps) dentro de los últimos 8 segundos
    hace_8_seg = timezone.now() - datetime.timedelta(seconds=8)
    paso_reciente = (
        Paso.objects.filter(
            placa_normalizada__iexact=placa_norm,
            caseta=caseta,
            created_at__gte=hace_8_seg,
        ).first()
        if placa_norm
        else None
    )

    vehiculo = Vehiculo.objects.filter(placa__iexact=placa_norm).first() if placa_norm else None
    tipo_alerta = None

    if paso_reciente:
        # En stream de video continuo (2-5 fps), actualizamos la evidencia del paso en curso sin cobrar doble
        paso = paso_reciente
        if confianza_ocr >= paso.confianza_ocr:
            paso.confianza_ocr = confianza_ocr
            paso.imagen_url = imagen_evidencia
            paso.categoria_detectada = categoria_det
            paso.ejes_detectados = ejes_det
            paso.pasajeros = pasajeros_det
            paso.save()
        estado_paso = paso.estado
        alerta_creada = paso.alertas.first()
    else:
        if not placa_norm:
            estado_paso = "SIN_LECTURA_PLACA"
            tipo_alerta = "PLACA_NO_REGISTRADA"
        elif not vehiculo or not vehiculo.activo:
            estado_paso = "NO_REGISTRADA"
            tipo_alerta = "PLACA_NO_REGISTRADA"
        elif float(vehiculo.saldo) < monto_cobrar:
            estado_paso = "SIN_SALDO"
            tipo_alerta = "VEHICULO_SIN_SALDO"
        else:
            estado_paso = "AUTORIZADO"
            vehiculo.saldo = float(vehiculo.saldo) - monto_cobrar
            vehiculo.save(update_fields=["saldo"])

        paso = Paso.objects.create(
            placa_leida=placa_cruda or placa_norm or "ILEGIBLE",
            placa_normalizada=placa_norm,
            confianza_ocr=confianza_ocr,
            categoria_detectada=categoria_det,
            ejes_detectados=ejes_det,
            pasajeros=pasajeros_det,
            monto=monto_cobrar,
            caseta=caseta,
            usuario=request.usuario_actual,
            imagen_url=imagen_evidencia,
            estado=estado_paso,
        )

        alerta_creada = None
        if tipo_alerta:
            alerta_creada = Alerta.objects.create(
                paso=paso,
                tipo=tipo_alerta,
                atendida=False,
            )

    # Actualizar el estado para el dispositivo de hardware Arduino (Bono +5 pts)
    if estado_paso == "AUTORIZADO":
        fase_hw = "PASO_OK"
    elif estado_paso == "SIN_SALDO":
        fase_hw = "ALERTA_SIN_SALDO"
    else:
        fase_hw = "ALERTA_NO_REGISTRADA"

    estado_hw = actualizar_estado_hardware(
        fase=fase_hw,
        placa=placa_norm or "ILEGIBLE",
        categoria=categoria_det,
        ejes=ejes_det,
        pasajeros=pasajeros_det,
        monto=monto_cobrar,
    )

    resumen_actual = _ResumenDashboard()

    # Emitir en tiempo real al panel web (Pusher + stream SSE)
    payload_rt = {
        "paso": paso.to_dict(),
        "alerta": alerta_creada.to_dict() if alerta_creada else None,
        "vehiculo": vehiculo.to_dict() if vehiculo else None,
        "resumen": resumen_actual,
        "hardware": estado_hw,
        "latencia_inferencia_ms": latencia_ms,
    }
    emitir_evento_tiempo_real("nuevo-paso", payload_rt)
    if alerta_creada:
        emitir_evento_tiempo_real("nueva-alerta", payload_rt)

    return JsonResponse(
        {
            "ok": True,
            "placa": placa_norm,
            "placa_leida": paso.placa_leida,
            "confianza": confianza_ocr,
            "categoria": categoria_det,
            "ejes": ejes_det,
            "pasajeros": pasajeros_det,
            "tarifa": monto_cobrar,
            "monto": monto_cobrar,
            "estado": estado_paso,
            "saldo_restante": float(vehiculo.saldo) if vehiculo else None,
            "latencia": latencia_ms,
            "paso": paso.to_dict(),
            "alerta": alerta_creada.to_dict() if alerta_creada else None,
            "hardware": estado_hw,
            "inferencia_detalle": {
                "keypoints_ruedas": resultado_inf.get("keypoints_ruedas", []),
                "desglose_latencia_ms": resultado_inf.get("desglose_latencia_ms", {}),
                "recorte_placa_b64": resultado_inf.get("recorte_placa_b64"),
                "dispositivo": resultado_inf.get("dispositivo", "cloud"),
            },
        },
        status=201,
    )


# =====================================================================
# 3. POST /api/v1/placas/consultar — Consulta una placa por texto y devuelve su estado
# =====================================================================
@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def consultar_placa_texto_view(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido. Use POST."}, status=405)

    body = _parse_json_body(request)
    placa_input = (
        body.get("placa")
        or body.get("texto")
        or request.POST.get("placa")
        or ""
    ).strip()

    resultado = consultar_estado_placa_bd(placa_input)
    resultado["respuesta_agente"] = enriquecer_con_llm_gemini(
        f"Consultar estado de la placa {placa_input}",
        resultado,
    )
    return JsonResponse(resultado)


# =====================================================================
# 4. POST /api/v1/placas/consultar-imagen — Consulta una placa por imagen (M1 + OCR) y devuelve su estado
# =====================================================================
@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def consultar_placa_imagen_view(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido. Use POST."}, status=405)

    body = _parse_json_body(request)
    archivo = request.FILES.get("imagen") or request.FILES.get("file")
    archivo_bytes = archivo.read() if archivo else None
    imagen_base64 = body.get("imagen_base64") or request.POST.get("imagen_base64")

    if not archivo_bytes and not imagen_base64:
        return JsonResponse(
            {
                "ok": False,
                "error": "IMAGEN_REQUERIDA",
                "mensaje": "Debe adjuntar una imagen en el campo `imagen` o `imagen_base64`.",
            },
            status=400,
        )

    try:
        res_ocr = _llamar_endpoint_inferencia(
            archivo_bytes=archivo_bytes,
            imagen_base64=imagen_base64,
            solo_placa=False,
        )
    except Exception as exc:
        return JsonResponse(
            {"ok": False, "error": "ERROR_INFERENCIA_OCR", "mensaje": str(exc)},
            status=502,
        )

    placa_detectada = normalizar_placa(res_ocr.get("placa") or res_ocr.get("placa_normalizada") or "")
    conf_ocr = float(res_ocr.get("confianza") or res_ocr.get("confianza_ocr") or 0.0)

    # Requisito Sección 4.8: "Si la imagen no tiene una placa legible, lo indica y pide otra imagen."
    if not placa_detectada or len(placa_detectada) < 3:
        return JsonResponse(
            {
                "ok": True,
                "placa_legible": False,
                "placa_detectada": "",
                "confianza_ocr": conf_ocr,
                "estado": "Imagen sin placa legible",
                "sugerencias_ocr": [],
                "recorte_placa_b64": res_ocr.get("recorte_placa_b64"),
                "imagen_evidencia_b64": res_ocr.get("imagen_evidencia_b64"),
                "respuesta_agente": (
                    "No se detectó una placa legible en la imagen enviada. "
                    "Por favor, tome o suba otra imagen donde la placa del vehículo se vea con mayor claridad e iluminación."
                ),
            }
        )

    datos_bd = consultar_estado_placa_bd(placa_detectada)
    datos_bd["placa_legible"] = True
    datos_bd["placa_detectada"] = placa_detectada
    datos_bd["confianza_ocr"] = round(conf_ocr, 4)
    datos_bd["categoria_detectada_imagen"] = res_ocr.get("categoria")
    datos_bd["ejes_detectados_imagen"] = res_ocr.get("ejes")
    datos_bd["pasajeros_detectados_imagen"] = res_ocr.get("pasajeros")
    datos_bd["recorte_placa_b64"] = res_ocr.get("recorte_placa_b64")
    datos_bd["imagen_evidencia_b64"] = res_ocr.get("imagen_evidencia_b64")
    datos_bd["respuesta_agente"] = (
        f"**Placa leída por visión artificial (M1 + OCR):** `{placa_detectada}` "
        f"(Confianza OCR: {conf_ocr * 100:.1f}%).\n\n"
        + enriquecer_con_llm_gemini(f"Imagen con placa leída {placa_detectada}", datos_bd)
    )
    return JsonResponse(datos_bd)


# =====================================================================
# 5. GET /api/v1/placas/{placa}/historial — Historial de pasos de una placa
# =====================================================================
@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def historial_placa_view(request, placa: str):
    placa_norm = normalizar_placa(placa)
    vehiculo = Vehiculo.objects.filter(placa__iexact=placa_norm).first()
    pasos = Paso.objects.select_related("caseta", "usuario").filter(placa_normalizada__iexact=placa_norm).order_by("-created_at", "-id")
    return JsonResponse(
        {
            "ok": True,
            "placa_consultada": placa,
            "placa_normalizada": placa_norm,
            "registrada": bool(vehiculo),
            "vehiculo": vehiculo.to_dict() if vehiculo else None,
            "total_pasos": pasos.count(),
            "historial": [p.to_dict() for p in pasos],
        }
    )


# =====================================================================
# 6. GET /api/v1/casetas/{id}/resumen — Conteo y recaudación del día por caseta
# =====================================================================
@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def resumen_caseta_view(request, id: int):
    caseta = Caseta.objects.filter(id=id).first()
    if not caseta:
        return JsonResponse({"ok": False, "mensaje": f"No existe la caseta con id={id}."}, status=404)

    hoy = timezone.now().date()
    pasos_caseta_total = Paso.objects.filter(caseta=caseta)
    pasos_caseta_hoy = pasos_caseta_total.filter(created_at__date=hoy)

    recaudacion_dia = float(pasos_caseta_hoy.aggregate(s=Sum("monto"))["s"] or 0.0)
    recaudacion_total = float(pasos_caseta_total.aggregate(s=Sum("monto"))["s"] or 0.0)
    pasajeros_dia = int(pasos_caseta_hoy.aggregate(s=Sum("pasajeros"))["s"] or 0)

    desglose_categorias = list(
        pasos_caseta_total.values("categoria_detectada")
        .annotate(conteo=Count("id"), recaudacion=Sum("monto"))
        .order_by("-conteo")
    )
    for d in desglose_categorias:
        d["recaudacion"] = float(d["recaudacion"] or 0.0)

    return JsonResponse(
        {
            "ok": True,
            "caseta": caseta.to_dict(),
            "fecha": hoy.isoformat(),
            "conteo_dia": pasos_caseta_hoy.count(),
            "recaudacion_dia": round(recaudacion_dia, 2),
            "pasajeros_dia": pasajeros_dia,
            "conteo_historico": pasos_caseta_total.count(),
            "recaudacion_historica": round(recaudacion_total, 2),
            "desglose_categorias": desglose_categorias,
            "ultimos_pasos": [p.to_dict() for p in pasos_caseta_total[:10]],
        }
    )


# =====================================================================
# 7. POST /api/v1/agente/chat — Mensaje al agente conversacional (por texto o imagen)
# =====================================================================
@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def agente_chat_view(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido. Use POST."}, status=405)

    body = _parse_json_body(request)
    mensaje = (
        body.get("mensaje")
        or body.get("texto")
        or body.get("placa")
        or request.POST.get("mensaje")
        or ""
    ).strip()

    archivo = request.FILES.get("imagen") or request.FILES.get("file")
    archivo_bytes = archivo.read() if archivo else None
    imagen_base64 = body.get("imagen_base64") or request.POST.get("imagen_base64")

    # Si el usuario envió una imagen al chat del agente, ejecutamos primero M1 + OCR
    if archivo_bytes or imagen_base64:
        return consultar_placa_imagen_view(request)

    if not mensaje:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "Envíe un `mensaje` con la placa a consultar o adjunte una `imagen`.",
            },
            status=400,
        )

    placa_extraida = extraer_placa_de_mensaje(mensaje)
    datos_bd = consultar_estado_placa_bd(placa_extraida)
    datos_bd["mensaje_usuario"] = mensaje
    datos_bd["respuesta_agente"] = enriquecer_con_llm_gemini(mensaje, datos_bd)
    return JsonResponse(datos_bd)


# =====================================================================
# RUTAS COMPLEMENTARIAS PARA EL PANEL WEB ANGULAR Y HARDWARE ARDUINO
# =====================================================================
@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def dashboard_resumen_view(request):
    resumen = _ResumenDashboard()
    resumen["ultimos_pasos"] = [p.to_dict() for p in Paso.objects.select_related("caseta", "usuario").all()[:20]]
    resumen["ultimas_alertas"] = [a.to_dict() for a in Alerta.objects.select_related("paso", "paso__caseta").all()[:15]]
    resumen["casetas"] = [c.to_dict() for c in Caseta.objects.all()]
    resumen["ultimo_id_evento"] = obtener_ultimo_id_evento()
    return JsonResponse({"ok": True, **resumen})


@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def vehiculos_list_create_view(request):
    if request.method == "GET":
        q = request.GET.get("q", "").strip()
        qs = Vehiculo.objects.all()
        if q:
            q_norm = normalizar_placa(q)
            qs = qs.filter(placa__icontains=q_norm) | qs.filter(propietario__icontains=q)
        return JsonResponse({"ok": True, "vehiculos": [v.to_dict() for v in qs]})

    if request.method == "POST":
        if request.usuario_actual.rol != "administrador":
            return JsonResponse({"ok": False, "mensaje": "Solo el administrador puede registrar vehículos."}, status=403)
        body = _parse_json_body(request)
        placa = normalizar_placa(body.get("placa", ""))
        if not placa:
            return JsonResponse({"ok": False, "mensaje": "La placa es obligatoria."}, status=400)
        if Vehiculo.objects.filter(placa__iexact=placa).exists():
            return JsonResponse({"ok": False, "mensaje": f"La placa {placa} ya está registrada."}, status=400)
        v = Vehiculo.objects.create(
            placa=placa,
            propietario=body.get("propietario", "Propietario Registrado"),
            categoria=(body.get("categoria") or "auto").lower(),
            ejes=int(body.get("ejes") or 2),
            saldo=float(body.get("saldo") or 50.0),
            activo=bool(body.get("activo", True)),
        )
        return JsonResponse({"ok": True, "vehiculo": v.to_dict()}, status=201)

    return JsonResponse({"ok": False, "mensaje": "Método no permitido."}, status=405)


@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def vehiculo_detail_view(request, id: int):
    v = Vehiculo.objects.filter(id=id).first()
    if not v:
        return JsonResponse({"ok": False, "mensaje": "Vehículo no encontrado."}, status=404)

    if request.method == "GET":
        return JsonResponse({"ok": True, "vehiculo": v.to_dict()})

    if request.usuario_actual.rol != "administrador":
        return JsonResponse({"ok": False, "mensaje": "Solo el administrador puede modificar o eliminar vehículos."}, status=403)

    if request.method in ("PUT", "PATCH"):
        body = _parse_json_body(request)
        if "placa" in body and body["placa"]:
            v.placa = normalizar_placa(body["placa"])
        if "propietario" in body:
            v.propietario = body["propietario"]
        if "categoria" in body:
            v.categoria = body["categoria"].lower()
        if "ejes" in body:
            v.ejes = int(body["ejes"])
        if "saldo" in body:
            v.saldo = float(body["saldo"])
        if "activo" in body:
            v.activo = bool(body["activo"])
        v.save()
        return JsonResponse({"ok": True, "vehiculo": v.to_dict()})

    if request.method == "DELETE":
        v.delete()
        return JsonResponse({"ok": True, "mensaje": "Vehículo eliminado correctamente."})

    return JsonResponse({"ok": False, "mensaje": "Método no permitido."}, status=405)


@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def pasos_list_view(request):
    qs = Paso.objects.select_related("caseta", "usuario").all()[:100]
    return JsonResponse({"ok": True, "pasos": [p.to_dict() for p in qs]})


@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def alertas_list_update_view(request, id: Optional[int] = None):
    if request.method == "GET":
        qs = Alerta.objects.select_related("paso", "paso__caseta").all()[:100]
        return JsonResponse({"ok": True, "alertas": [a.to_dict() for a in qs]})

    if request.method in ("PATCH", "PUT", "POST") and id is not None:
        alerta = Alerta.objects.filter(id=id).first()
        if not alerta:
            return JsonResponse({"ok": False, "mensaje": "Alerta no encontrada."}, status=404)
        alerta.atendida = True
        alerta.save(update_fields=["atendida"])
        actualizar_estado_hardware(fase="LISTO", placa=alerta.paso.placa_normalizada if alerta.paso else "---")
        emitir_evento_tiempo_real("alerta-atendida", {"alerta": alerta.to_dict(), "resumen": _ResumenDashboard()})
        return JsonResponse({"ok": True, "alerta": alerta.to_dict()})

    return JsonResponse({"ok": False, "mensaje": "Método no permitido."}, status=405)


@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def tarifas_casetas_usuarios_view(request):
    if request.method == "GET":
        return JsonResponse(
            {
                "ok": True,
                "tarifas": [t.to_dict() for t in Tarifa.objects.all()],
                "casetas": [c.to_dict() for c in Caseta.objects.all()],
                "usuarios": [u.to_dict() for u in Usuario.objects.all()],
            }
        )

    if request.method == "POST":
        if request.usuario_actual.rol != "administrador":
            return JsonResponse({"ok": False, "mensaje": "Requiere rol administrador."}, status=403)
        body = _parse_json_body(request)
        tipo = body.get("tipo_entidad", "usuario")
        if tipo == "usuario":
            email = (body.get("email_google") or "").strip().lower()
            if not email:
                return JsonResponse({"ok": False, "mensaje": "Email de Google requerido."}, status=400)
            u, _ = Usuario.objects.update_or_create(
                email_google=email,
                defaults={
                    "nombre": body.get("nombre") or email.split("@")[0],
                    "rol": body.get("rol") or "operador",
                    "activo": bool(body.get("activo", True)),
                },
            )
            return JsonResponse({"ok": True, "usuario": u.to_dict()}, status=201)
        elif tipo == "tarifa":
            t, _ = Tarifa.objects.update_or_create(
                categoria=(body.get("categoria") or "auto").lower(),
                ejes=int(body.get("ejes") or 2),
                defaults={"monto": float(body.get("monto") or 7.0)},
            )
            return JsonResponse({"ok": True, "tarifa": t.to_dict()}, status=201)

    return JsonResponse({"ok": False, "mensaje": "Método no permitido."}, status=405)


@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def estado_inferencia_view(request):
    """
    Página 'Estado: indica si el endpoint de inferencia responde' (Sección 4.2).
    También permite actualizar INFERENCE_URL en caliente (POST) cuando cambia el túnel de Colab o RunPod.
    """
    if request.method == "POST":
        body = _parse_json_body(request)
        nueva_url = (body.get("inference_url") or "").strip().rstrip("/")
        if nueva_url.startswith("http://") or nueva_url.startswith("https://"):
            settings.INFERENCE_URL = nueva_url
            os.environ["INFERENCE_URL"] = nueva_url

    url_base = settings.INFERENCE_URL
    t0 = time.perf_counter()
    remoto_ok = False
    detalle = {}

    if url_base and "example.com" not in url_base:
        try:
            r = requests.get(f"{url_base}/health", timeout=6)
            if r.status_code == 200:
                remoto_ok = True
                detalle = r.json()
        except Exception as exc:
            detalle = {"aviso_remoto": str(exc)}

    motor_local = _cargar_motor_inferencia_integrado()
    if not remoto_ok and motor_local:
        try:
            detalle = motor_local.health_check()
            remoto_ok = True
        except Exception as exc:
            detalle = {"error": str(exc)}

    latencia_ping_ms = round((time.perf_counter() - t0) * 1000, 2)
    return JsonResponse(
        {
            "ok": True,
            "responde": remoto_ok,
            "inference_url": url_base,
            "latencia_ping_ms": latencia_ping_ms,
            "detalle_endpoint": detalle,
            "pusher_configurado": bool(settings.PUSHER_KEY),
            "gemini_configurado": bool(settings.GEMINI_API_KEY),
            "hardware": obtener_estado_hardware(),
            "verificado_en": timezone.now().isoformat(),
        }
    )


@csrf_exempt
def eventos_poll_o_sse_view(request):
    """
    Devuelve los eventos en tiempo real desde `ultimo_id` (o stream SSE)
    para complementar Pusher Channels.
    """
    usuario, err = autenticar_peticion(request)
    if not usuario:
        return JsonResponse({"ok": False, "mensaje": err}, status=401)

    ultimo_id = int(request.GET.get("desde", "0") or 0)
    if request.GET.get("modo") == "sse":
        def event_stream():
            cursor = ultimo_id
            for _ in range(25):
                nuevos = obtener_eventos_desde(cursor)
                for ev in nuevos:
                    cursor = ev["id_evento"]
                    yield f"id: {cursor}\nevent: {ev['evento']}\ndata: {json.dumps(ev['data'])}\n\n"
                time.sleep(1)
        resp = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        resp["Cache-Control"] = "no-cache"
        return resp

    eventos = obtener_eventos_desde(ultimo_id)
    return JsonResponse(
        {
            "ok": True,
            "ultimo_id_evento": obtener_ultimo_id_evento(),
            "eventos": eventos,
            "hardware": obtener_estado_hardware(),
        }
    )


@csrf_exempt
def hardware_estado_cloud_view(request):
    """
    Endpoint en la nube para el Dispositivo Físico Arduino Uno/Nano/Mega (Bono +5 puntos).
    Permite consultar el último estado de identificación, inferencia, acción o alerta,
    o disparar una prueba de alerta hacia el hardware físico.
    """
    if request.method == "POST":
        body = _parse_json_body(request)
        estado = actualizar_estado_hardware(
            fase=body.get("fase", "ALERTA_NO_REGISTRADA"),
            placa=body.get("placa", "TEST-999"),
            categoria=body.get("categoria", "camion"),
            ejes=int(body.get("ejes", 3)),
            pasajeros=int(body.get("pasajeros", 2)),
            monto=float(body.get("monto", 25.0)),
        )
        emitir_evento_tiempo_real("evento-hardware", {"hardware": estado})
        return JsonResponse({"ok": True, "hardware": estado})

    estado = obtener_estado_hardware()
    if request.GET.get("formato") == "serial":
        return HttpResponse(estado["comando_serial"] + "\n", content_type="text/plain")
    return JsonResponse({"ok": True, "hardware": estado})


@csrf_exempt
@requiere_autenticacion(roles=["administrador", "operador"])
def imagenes_prueba_list_view(request):
    """
    Lista las 20 imágenes reales del hito (`01.jpg` a `20.jpg`) alojadas en el servidor
    para poder disparar pruebas de inferencia en vivo desde la Web o la App Móvil con 1 clic.
    """
    carpeta = Path(settings.BASE_DIR).parent.parent / "inferencia" / "imagenes_prueba"
    archivos = sorted(carpeta.glob("*.jpg")) if carpeta.exists() else []

    if request.GET.get("archivo"):
        nombre = Path(request.GET["archivo"]).name
        ruta = carpeta / nombre
        if not ruta.exists():
            return JsonResponse({"ok": False, "mensaje": "Imagen no encontrada."}, status=404)
        b64 = "data:image/jpeg;base64," + base64.b64encode(ruta.read_bytes()).decode("utf-8")
        return JsonResponse({"ok": True, "nombre": nombre, "imagen_base64": b64})

    return JsonResponse(
        {
            "ok": True,
            "imagenes": [f.name for f in archivos],
        }
    )


# =====================================================================
# DOCUMENTACIÓN OPENAPI 3.0 / SWAGGER UI INTERACTIVA (/api/docs)
# =====================================================================
def openapi_json_view(request):
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "IAM-811 Sistema Inteligente de Control de Peaje — API REST",
            "version": "1.0.0",
            "description": (
                "API REST oficial del Laboratorio Final de Hito (IAM-811 Machine Learning y Aprendizaje Profundo). "
                "Autor: Amilkar Hugo Guarachi Nina. Docente: Ing. Alvaro Pinto Mamani. "
                "Todas las rutas (excepto `/api/v1/auth/google`) exigen autenticación Bearer con Google OAuth 2.0."
            ),
        },
        "components": {
            "securitySchemes": {
                "BearerGoogleAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            }
        },
        "security": [{"BearerGoogleAuth": []}],
        "paths": {
            "/api/v1/auth/google": {
                "post": {
                    "summary": "Recibe el token de Google desde la app/web y devuelve el token de sesión del sistema",
                    "security": [],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"token": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Token de sesión emitido"}, "403": {"description": "Cuenta fuera de lista blanca"}},
                }
            },
            "/api/v1/pasos/frame": {
                "post": {
                    "summary": "Recibe un frame desde la app, llama a INFERENCE_URL (M1+M2+M3+M4), registra el paso y lo emite en tiempo real",
                    "responses": {"201": {"description": "Paso registrado y emitido en tiempo real"}},
                }
            },
            "/api/v1/placas/consultar": {
                "post": {
                    "summary": "Consulta una placa por texto y devuelve su estado entre los 4 estados oficiales + sugerencias OCR",
                    "responses": {"200": {"description": "Estado de la placa"}},
                }
            },
            "/api/v1/placas/consultar-imagen": {
                "post": {
                    "summary": "Consulta una placa por imagen (M1 + OCR) y devuelve su estado entre los 4 estados oficiales",
                    "responses": {"200": {"description": "Placa leída y estado en el sistema"}},
                }
            },
            "/api/v1/placas/{placa}/historial": {
                "get": {
                    "summary": "Historial de pasos de una placa",
                    "parameters": [{"name": "placa", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Lista histórica de pasos"}},
                }
            },
            "/api/v1/casetas/{id}/resumen": {
                "get": {
                    "summary": "Conteo y recaudación del día para una caseta",
                    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "Resumen diario e histórico de la caseta"}},
                }
            },
            "/api/v1/agente/chat": {
                "post": {
                    "summary": "Mensaje (texto o imagen) al Agente Conversacional con Function Calling",
                    "responses": {"200": {"description": "Respuesta del agente conversacional"}},
                }
            },
            "/api/v1/vehiculos": {
                "get": {"summary": "Listar padrón de vehículos"},
                "post": {"summary": "Registrar nuevo vehículo (Administrador)"},
            },
            "/api/v1/estado-inferencia": {
                "get": {"summary": "Verifica si el endpoint de inferencia en RunPod/Colab responde"},
            },
            "/api/v1/hardware/estado": {
                "get": {"summary": "Estado en la nube para el dispositivo de alerta Arduino (Bono +5 pts)"},
            },
        },
    }
    return JsonResponse(spec)


def swagger_ui_view(request):
    html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>IAM-811 Control de Peaje — Swagger API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: '/api/openapi.json',
        dom_id: '#swagger-ui',
      });
    };
  </script>
</body>
</html>"""
    return HttpResponse(html, content_type="text/html")


def angular_spa_fallback(request):
    """Sirve el index.html del build de Angular si existe, o redirige al panel web."""
    candidatos = [
        Path(settings.BASE_DIR) / "frontend_dist" / "index.html",
        Path(settings.BASE_DIR).parent / "frontend" / "dist" / "peaje-angular" / "browser" / "index.html",
    ]
    for index_file in candidatos:
        if index_file.exists():
            return HttpResponse(index_file.read_text(encoding="utf-8"), content_type="text/html")

    return JsonResponse(
        {
            "sistema": "IAM-811 Sistema Inteligente de Control de Peaje",
            "autor": "Amilkar Hugo Guarachi Nina",
            "documentacion_swagger": "/api/docs",
            "openapi_json": "/api/openapi.json",
            "api_base": "/api/v1/",
        }
    )
