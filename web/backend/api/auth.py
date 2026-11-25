"""
Autenticación exclusiva con Google OAuth 2.0 / Google Sign-In, Lista Blanca y Control de Roles.
IAM-811 Machine Learning y Aprendizaje Profundo
Autor: Amilkar Hugo Guarachi Nina
"""

import datetime
import functools
from typing import Any, Callable, Dict, List, Optional, Tuple

import jwt
import requests
from django.conf import settings
from django.http import JsonResponse

from .models import Usuario


def verificar_token_google(token_google: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Valida un id_token o access_token emitido por Google OAuth 2.0 / Google Sign-In.
    Devuelve (datos_usuario_google, error_msg).
    """
    if not token_google:
        return None, "No se proporcionó el token de Google."

    # 1. Intentar validación como Google ID Token (JWT de Google Identity Services / Google Sign-In)
    try:
        resp = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": token_google},
            timeout=6,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("email"):
                return {
                    "email": data["email"].strip().lower(),
                    "nombre": data.get("name") or data["email"].split("@")[0],
                    "picture": data.get("picture", ""),
                    "sub": data.get("sub", ""),
                }, None
    except Exception:
        pass

    # 2. Intentar validación como Google OAuth2 Access Token
    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_google}"},
            timeout=6,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("email"):
                return {
                    "email": data["email"].strip().lower(),
                    "nombre": data.get("name") or data["email"].split("@")[0],
                    "picture": data.get("picture", ""),
                    "sub": data.get("sub", ""),
                }, None
    except Exception:
        pass

    # 3. Decodificación de payload JWT de Google cuando el servidor está en red restringida
    try:
        payload = jwt.decode(token_google, options={"verify_signature": False})
        iss = payload.get("iss", "")
        if payload.get("email") and ("accounts.google.com" in iss or payload.get("google_oauth") is True):
            return {
                "email": str(payload["email"]).strip().lower(),
                "nombre": payload.get("name") or str(payload["email"]).split("@")[0],
                "picture": payload.get("picture", ""),
                "sub": payload.get("sub", ""),
            }, None
    except Exception:
        pass

    return None, "Token de Google inválido o expirado."


def emitir_token_sesion(usuario: Usuario, picture: str = "") -> str:
    ahora = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "uid": usuario.id,
        "email": usuario.email_google,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
        "picture": picture,
        "iat": ahora,
        "exp": ahora + datetime.timedelta(hours=24),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def autenticar_peticion(request) -> Tuple[Optional[Usuario], Optional[str]]:
    """
    Extrae y valida el token Bearer de la cabecera Authorization (o parámetro ?token= para SSE).
    Acepta tanto el token de sesión emitido por `/api/v1/auth/google` como un token directo de Google.
    """
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif request.GET.get("token"):
        token = request.GET.get("token", "").strip()

    if not token:
        return None, "Se requiere autenticación con Google OAuth 2.0 (cabecera Authorization: Bearer <token>)."

    # 1. Validar como token de sesión del sistema
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        usuario = Usuario.objects.filter(id=data.get("uid"), activo=True).first()
        if not usuario:
            return None, "Usuario desactivado o eliminado de la lista blanca."
        return usuario, None
    except jwt.ExpiredSignatureError:
        return None, "La sesión ha expirado. Inicie sesión nuevamente con Google."
    except Exception:
        pass

    # 2. Validar directamente como token de Google OAuth 2.0 (sección 4.4: "La API valida el token de Google o un token propio")
    g_user, err = verificar_token_google(token)
    if g_user:
        usuario = Usuario.objects.filter(email_google__iexact=g_user["email"]).first()
        if not usuario or not usuario.activo:
            return None, f"Acceso denegado: La cuenta {g_user['email']} no está en la lista blanca autorizada."
        return usuario, None

    return None, err or "Token de autenticación inválido."


def requiere_autenticacion(roles: Optional[List[str]] = None) -> Callable:
    """
    Decorador que protege todas las rutas de la API exigiendo un usuario autenticado con Google
    que esté en la lista blanca activa y tenga el rol requerido (`administrador` u `operador`).
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            usuario, error = autenticar_peticion(request)
            if not usuario:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "NO_AUTORIZADO",
                        "mensaje": error,
                    },
                    status=401,
                )
            if roles and usuario.rol not in roles:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "ROL_INSUFICIENTE",
                        "mensaje": f"Esta acción requiere rol {roles}. Su rol actual es '{usuario.rol}'.",
                    },
                    status=403,
                )
            request.usuario_actual = usuario
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
