"""
Rutas `/api/v1/...` del Sistema Inteligente de Control de Peaje (IAM-811)
Incluye las 7 rutas obligatorias de la sección 4.5 + endpoints CRUD para Angular y Arduino.
"""

from django.urls import path

from . import views

urlpatterns = [
    # 7 Rutas mínimas obligatorias (Sección 4.5):
    path("auth/google", views.auth_google_view, name="auth-google"),
    path("pasos/frame", views.registrar_paso_frame_view, name="pasos-frame"),
    path("placas/consultar", views.consultar_placa_texto_view, name="placas-consultar"),
    path("placas/consultar-imagen", views.consultar_placa_imagen_view, name="placas-consultar-imagen"),
    path("placas/<str:placa>/historial", views.historial_placa_view, name="placas-historial"),
    path("casetas/<int:id>/resumen", views.resumen_caseta_view, name="casetas-resumen"),
    path("agente/chat", views.agente_chat_view, name="agente-chat"),

    # Rutas del Panel Web en Tiempo Real, CRUD, Estado de Inferencia y Hardware Arduino:
    path("dashboard/resumen", views.dashboard_resumen_view, name="dashboard-resumen"),
    path("vehiculos", views.vehiculos_list_create_view, name="vehiculos-list-create"),
    path("vehiculos/<int:id>", views.vehiculo_detail_view, name="vehiculo-detail"),
    path("pasos", views.pasos_list_view, name="pasos-list"),
    path("alertas", views.alertas_list_update_view, name="alertas-list"),
    path("alertas/<int:id>", views.alertas_list_update_view, name="alerta-update"),
    path("configuracion", views.tarifas_casetas_usuarios_view, name="configuracion"),
    path("estado-inferencia", views.estado_inferencia_view, name="estado-inferencia"),
    path("eventos/stream", views.eventos_poll_o_sse_view, name="eventos-stream"),
    path("hardware/estado", views.hardware_estado_cloud_view, name="hardware-estado"),
    path("imagenes-prueba", views.imagenes_prueba_list_view, name="imagenes-prueba"),
]
