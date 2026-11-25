"""
Rutas globales del Backend Django:
- /api/v1/... -> Todas las rutas REST obligatorias y complementarias
- /api/docs   -> Interfaz Swagger UI / OpenAPI 3.0 interactiva
- /media/...  -> Imágenes de evidencia de los pasos registrados
- /*          -> Sirve el SPA compilado de Angular si está presente
"""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path

from api.views import angular_spa_fallback, openapi_json_view, swagger_ui_view

urlpatterns = [
    path("api/v1/", include("api.urls")),
    path("api/docs", swagger_ui_view, name="swagger-ui"),
    path("api/docs/", swagger_ui_view, name="swagger-ui-slash"),
    path("api/openapi.json", openapi_json_view, name="openapi-json"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += [
    re_path(r"^(?!api/|media/|static/).*$", angular_spa_fallback, name="angular-spa"),
]
