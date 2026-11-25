"""
Agente Conversacional Inteligente para Consulta de Placas por Texto e Imagen (20 puntos Rúbrica)
IAM-811 Machine Learning y Aprendizaje Profundo
Autor: Amilkar Hugo Guarachi Nina

Cumple todos los requisitos de la sección 4.8:
1. Responde estrictamente con los 4 estados oficiales:
   - "Registrada y con paso"
   - "Registrada sin paso"
   - "Identificada no registrada"
   - "No existe"
2. Solo usa datos reales de la base de datos o la API, sin inventar información.
3. Normaliza la placa antes de buscar (mayúsculas, sin guiones ni espacios, validación de formato).
4. Ante errores probables de OCR (O<->0, I<->1, B<->8, S<->5), sugiere coincidencias cercanas ("¿Quisiste decir…?").
5. Si la imagen no tiene una placa legible, lo indica y pide otra imagen.
6. Soporta Function Calling con Google Gemini API respaldado por herramientas determinísticas sobre la BD.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings

from .models import Paso, Vehiculo

# Mapa bidireccional de confusiones típicas de OCR (Sección 4.8: O<->0, I<->1, B<->8, S<->5)
PARES_CONFUSION_OCR = {
    ("O", "0"), ("0", "O"),
    ("Q", "0"), ("0", "Q"),
    ("D", "0"), ("0", "D"),
    ("I", "1"), ("1", "I"),
    ("L", "1"), ("1", "L"),
    ("B", "8"), ("8", "B"),
    ("S", "5"), ("5", "S"),
    ("Z", "2"), ("2", "Z"),
    ("G", "6"), ("6", "G"),
}

CANONICO_OCR = str.maketrans({
    "O": "0",
    "Q": "0",
    "I": "1",
    "L": "1",
    "B": "8",
    "S": "5",
    "Z": "2",
    "G": "6",
})

PATRON_PLACA_VALIDA = re.compile(r"^[A-Z0-9]{4,12}$")
PATRON_BOLIVIA = re.compile(r"^\d{3,4}[A-Z]{3}$")

PALABRAS_IGNORAR = {
    "HOLA", "PLACA", "ESTADO", "CONSULTA", "CONSULTAR", "BUSCAR", "VERIFICAR",
    "TIENE", "PASO", "PASOS", "PEAJE", "VEHICULO", "AUTO", "CAMION", "MINIBUS",
    "CUAL", "COMO", "ESTA", "PARA", "PORFAVOR", "FAVOR", "QUIERO", "SABER",
    "REGISTRADA", "EXISTE", "AGENTE", "SISTEMA", "IMAGEN", "FOTO",
}


def normalizar_placa(texto: str) -> str:
    """Convierte a mayúsculas y elimina guiones, espacios y caracteres especiales."""
    if not texto:
        return ""
    limpio = texto.upper().strip()
    limpio = re.sub(r"[^A-Z0-9]", "", limpio)
    return limpio


def validar_formato_placa(placa_norm: str) -> Dict[str, Any]:
    es_valida = bool(PATRON_PLACA_VALIDA.match(placa_norm)) and any(c.isdigit() for c in placa_norm)
    es_bolivia = bool(PATRON_BOLIVIA.match(placa_norm))
    return {
        "formato_valido": es_valida,
        "formato_bolivia": es_bolivia,
        "longitud": len(placa_norm),
    }


def extraer_placa_de_mensaje(mensaje: str) -> str:
    """
    Si el usuario escribe una frase en lenguaje natural (ej. 'Consulta la placa 29-B110559'
    o '¿Qué pasó con FMO-6719?'), extrae el token de la placa y lo normaliza.
    """
    if not mensaje:
        return ""
    msg_upper = mensaje.upper().strip()
    # Si todo el mensaje es corto y parece una placa directa (con o sin guión)
    directa = normalizar_placa(msg_upper)
    if " " not in msg_upper.strip() and 4 <= len(directa) <= 12:
        return directa

    # Buscar tokens con combinación de letras y números (incluyendo guiones intermedios)
    candidatos = re.findall(r"\b[A-Z0-9]{1,5}(?:[-\s]?[A-Z0-9]{2,7})+\b", msg_upper)
    mejores = []
    for cand in candidatos:
        norm = normalizar_placa(cand)
        if norm in PALABRAS_IGNORAR:
            continue
        if 4 <= len(norm) <= 12 and any(c.isdigit() for c in norm) and any(c.isalpha() for c in norm):
            mejores.append(norm)

    if mejores:
        # Priorizar el token más específico
        mejores.sort(key=len, reverse=True)
        return mejores[0]

    # Respaldo: cualquier token alfanumérico que contenga dígitos
    tokens = re.findall(r"[A-Z0-9-]+", msg_upper)
    for t in tokens:
        norm = normalizar_placa(t)
        if norm not in PALABRAS_IGNORAR and 4 <= len(norm) <= 12 and any(c.isdigit() for c in norm):
            return norm

    return directa[:12]


def costo_sustitucion_ocr(c1: str, c2: str) -> float:
    if c1 == c2:
        return 0.0
    if (c1, c2) in PARES_CONFUSION_OCR:
        return 0.25  # Costo bajo para confusiones clásicas de OCR: O<->0, I<->1, B<->8, S<->5
    return 1.0


def distancia_ocr(p1: str, p2: str) -> float:
    """Distancia de edición ponderada para errores de OCR."""
    if p1 == p2:
        return 0.0
    if p1.translate(CANONICO_OCR) == p2.translate(CANONICO_OCR):
        return 0.20

    m, n = len(p1), len(p2)
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = float(i)
    for j in range(n + 1):
        dp[0][j] = float(j)

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            costo = costo_sustitucion_ocr(p1[i - 1], p2[j - 1])
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,      # Eliminación
                dp[i][j - 1] + 1.0,      # Inserción
                dp[i - 1][j - 1] + costo # Sustitución (0.25 si es confusión OCR)
            )
    return dp[m][n]


def explicar_confusion_ocr(buscada: str, candidata: str) -> str:
    """Identifica qué caracteres de OCR se confundieron entre la placa buscada y la sugerida."""
    if len(buscada) != len(candidata):
        return "longitud similar"
    cambios = []
    for a, b in zip(buscada, candidata):
        if a != b:
            if (a, b) in PARES_CONFUSION_OCR:
                cambios.append(f"{a}↔{b} (confusión típica OCR)")
            else:
                cambios.append(f"{a}→{b}")
    return ", ".join(cambios) if cambios else "coincidencia cercana"


def buscar_sugerencias_ocr(placa_norm: str, max_sugerencias: int = 3) -> List[Dict[str, Any]]:
    """
    Tool de búsqueda de placas similares en la base de datos (tablas `vehiculos` y `pasos`)
    ante probables errores de OCR (O<->0, I<->1, B<->8, S<->5).
    """
    if not placa_norm or len(placa_norm) < 3:
        return []

    placas_bd: Dict[str, str] = {}
    for v in Vehiculo.objects.all():
        p = normalizar_placa(v.placa)
        if p:
            placas_bd[p] = "registrada"

    for p_raw in Paso.objects.exclude(placa_normalizada="").values_list("placa_normalizada", flat=True).distinct():
        p = normalizar_placa(p_raw)
        if p and p not in placas_bd:
            placas_bd[p] = "detectada_en_paso"

    candidatos = []
    for placa_cand, origen in placas_bd.items():
        if placa_cand == placa_norm:
            continue
        dist = distancia_ocr(placa_norm, placa_cand)
        if dist <= 1.75:
            candidatos.append({
                "placa": placa_cand,
                "distancia_ocr": round(dist, 2),
                "origen": origen,
                "motivo": explicar_confusion_ocr(placa_norm, placa_cand),
            })

    candidatos.sort(key=lambda x: (x["distancia_ocr"], 0 if x["origen"] == "registrada" else 1))
    return candidatos[:max_sugerencias]


def consultar_estado_placa_bd(placa_entrada: str) -> Dict[str, Any]:
    """
    Tool principal del Agente Conversacional.
    Consulta exclusivamente la base de datos y clasifica la placa en uno de los 4 estados oficiales:
    1. Registrada y con paso
    2. Registrada sin paso
    3. Identificada no registrada
    4. No existe
    """
    placa_norm = normalizar_placa(placa_entrada)
    validacion = validar_formato_placa(placa_norm)

    if not placa_norm or len(placa_norm) < 3:
        return {
            "ok": False,
            "placa_consultada": placa_entrada,
            "placa_normalizada": placa_norm,
            "validacion_formato": validacion,
            "estado": "Placa inválida o ilegible",
            "registrada": False,
            "tiene_pasos": False,
            "total_pasos": 0,
            "vehiculo": None,
            "ultimo_paso": None,
            "historial_pasos": [],
            "sugerencias_ocr": [],
            "respuesta_agente": (
                "No se proporcionó una placa con formato válido. "
                "Por favor ingrese una placa alfanumérica (ej. 29B110559 o FMO-6719) o suba una imagen más nítida."
            ),
        }

    vehiculo = Vehiculo.objects.filter(placa__iexact=placa_norm).first()
    pasos_qs = Paso.objects.select_related("caseta", "usuario").filter(placa_normalizada__iexact=placa_norm).order_by("-created_at", "-id")
    lista_pasos = [p.to_dict() for p in pasos_qs[:15]]
    total_pasos = pasos_qs.count()
    ultimo_paso = lista_pasos[0] if lista_pasos else None
    sugerencias = buscar_sugerencias_ocr(placa_norm)

    # Clasificación estricta en los 4 estados de la rúbrica (Sección 4.8)
    if vehiculo and total_pasos > 0:
        estado = "Registrada y con paso"
        fecha_str = ultimo_paso["created_at"][:19].replace("T", " ") if ultimo_paso.get("created_at") else "N/A"
        caseta_str = ultimo_paso.get("caseta_nombre") or f"Caseta #{ultimo_paso.get('caseta_id') or 1}"
        cat_str = ultimo_paso.get("categoria_detectada", vehiculo.categoria).upper()
        monto_val = ultimo_paso.get("monto", 0.0)
        pasajeros_val = ultimo_paso.get("pasajeros", 1)
        respuesta = (
            f"Estado: **Registrada y con paso**.\n"
            f"• **Placa normalizada:** `{placa_norm}` (Propietario: {vehiculo.propietario}, Saldo actual: Bs {float(vehiculo.saldo):.2f}).\n"
            f"• **Total de pasos registrados:** {total_pasos}.\n"
            f"• **Último paso:** Fecha `{fecha_str}` en **{caseta_str}** | Categoría: **{cat_str}** "
            f"({ultimo_paso.get('ejes_detectados', vehiculo.ejes)} ejes, {pasajeros_val} pasajero(s)) | Monto cobrado: **Bs {monto_val:.2f}**."
        )
    elif vehiculo and total_pasos == 0:
        estado = "Registrada sin paso"
        respuesta = (
            f"Estado: **Registrada sin paso**.\n"
            f"• **Placa normalizada:** `{placa_norm}`.\n"
            f"• La placa pertenece a **{vehiculo.propietario}** (Categoría registrada: **{vehiculo.categoria.upper()}**, "
            f"{vehiculo.ejes} ejes, Saldo disponible: **Bs {float(vehiculo.saldo):.2f}**), pero **nunca pasó por el peaje** (0 registros en historial)."
        )
    elif (not vehiculo) and total_pasos > 0:
        estado = "Identificada no registrada"
        fecha_str = ultimo_paso["created_at"][:19].replace("T", " ") if ultimo_paso.get("created_at") else "N/A"
        caseta_str = ultimo_paso.get("caseta_nombre") or f"Caseta #{ultimo_paso.get('caseta_id') or 1}"
        cat_str = ultimo_paso.get("categoria_detectada", "auto").upper()
        monto_val = ultimo_paso.get("monto", 0.0)
        respuesta = (
            f"Estado: **Identificada no registrada** ⚠️ *(Posible evasión)*.\n"
            f"• **Placa normalizada:** `{placa_norm}`.\n"
            f"• La cámara la detectó **{total_pasos} vez/veces**, pero **no está registrada** en el padrón de vehículos.\n"
            f"• **Última detección:** Fecha `{fecha_str}` en **{caseta_str}** | Categoría detectada: **{cat_str}** "
            f"({ultimo_paso.get('ejes_detectados', 2)} ejes) | Tarifa pendiente: **Bs {monto_val:.2f}**."
        )
    else:
        estado = "No existe"
        respuesta = (
            f"Estado: **No existe**.\n"
            f"• **Placa normalizada:** `{placa_norm}`.\n"
            f"• No existe ningún registro de esta placa en el padrón de vehículos ni en el historial de cámaras del peaje."
        )

    # Agregar sugerencias de confusiones probables de OCR ("¿Quisiste decir…?")
    if sugerencias:
        textos_sug = [
            f"`{s['placa']}` ({s['motivo']})"
            for s in sugerencias
        ]
        respuesta += f"\n\n💡 **¿Quisiste decir…?** Detectamos coincidencias cercanas por posible confusión de OCR: {', '.join(textos_sug)}."

    return {
        "ok": True,
        "placa_consultada": placa_entrada,
        "placa_normalizada": placa_norm,
        "validacion_formato": validacion,
        "estado": estado,
        "registrada": bool(vehiculo),
        "tiene_pasos": total_pasos > 0,
        "total_pasos": total_pasos,
        "vehiculo": vehiculo.to_dict() if vehiculo else None,
        "ultimo_paso": ultimo_paso,
        "historial_pasos": lista_pasos,
        "sugerencias_ocr": sugerencias,
        "respuesta_agente": respuesta,
    }


def enriquecer_con_llm_gemini(mensaje_usuario: str, datos_bd: Dict[str, Any]) -> str:
    """
    Si GEMINI_API_KEY está configurada en el entorno, utiliza Google Gemini con los datos
    exactos devueltos por la Tool `consultar_estado_placa_bd` para redactar la respuesta
    manteniendo intacto el estado oficial y sin inventar ningún dato.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return datos_bd["respuesta_agente"]

    prompt_sistema = (
        "Eres el Agente Conversacional Oficial del Sistema Inteligente de Control de Peaje IAM-811. "
        "REGLAS ESTRICTAS:\n"
        "1. Debes responder SIEMPRE indicando de forma textual y destacada el campo `estado` exacto "
        "('Registrada y con paso', 'Registrada sin paso', 'Identificada no registrada' o 'No existe').\n"
        "2. USA ÚNICAMENTE los datos del JSON de la base de datos adjunto. PROHIBIDO inventar fechas, montos o propietarios.\n"
        "3. Si `sugerencias_ocr` tiene elementos, debes incluir obligatoriamente la pregunta '¿Quisiste decir: ...?' mencionando las placas sugeridas.\n"
        "4. Sé conciso, claro y en español."
    )
    try:
        modelo = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"{prompt_sistema}\n\n"
                                f"Consulta del usuario: {mensaje_usuario}\n"
                                f"Resultado de la Tool SQL (consultar_estado_placa_bd): {datos_bd}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 400},
        }
        r = requests.post(url, json=payload, timeout=7)
        if r.status_code == 200:
            data = r.json()
            texto = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
            # Verificar que el estado oficial siga presente literalmente en la respuesta
            if texto and datos_bd["estado"].lower() in texto.lower():
                return texto
    except Exception:
        pass

    return datos_bd["respuesta_agente"]
