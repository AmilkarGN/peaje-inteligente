"""
Modelos de Base de Datos del Sistema Inteligente de Control de Peaje (IAM-811)
Cumple estrictamente el esquema de la sección 4.6 + el campo `pasajeros` de la sección 10 (+5 pts).
Autor: Amilkar Hugo Guarachi Nina
"""

from django.db import models


class Usuario(models.Model):
    ROL_CHOICES = (
        ("administrador", "Administrador"),
        ("operador", "Operador"),
    )

    email_google = models.EmailField(unique=True, db_index=True)
    nombre = models.CharField(max_length=150)
    rol = models.CharField(max_length=30, choices=ROL_CHOICES, default="operador")
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "usuarios"
        ordering = ["id"]

    def to_dict(self):
        return {
            "id": self.id,
            "email_google": self.email_google,
            "nombre": self.nombre,
            "rol": self.rol,
            "activo": self.activo,
        }


class Vehiculo(models.Model):
    CATEGORIA_CHOICES = (
        ("moto", "Moto"),
        ("auto", "Auto"),
        ("minibus", "Minibús"),
        ("camion", "Camión"),
        ("bus", "Bus"),
    )

    placa = models.CharField(max_length=30, unique=True, db_index=True)
    propietario = models.CharField(max_length=150)
    categoria = models.CharField(max_length=30, choices=CATEGORIA_CHOICES, default="auto")
    ejes = models.IntegerField(default=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "vehiculos"
        ordering = ["placa"]

    def to_dict(self):
        return {
            "id": self.id,
            "placa": self.placa,
            "propietario": self.propietario,
            "categoria": self.categoria,
            "ejes": self.ejes,
            "saldo": float(self.saldo),
            "activo": self.activo,
        }


class Caseta(models.Model):
    nombre = models.CharField(max_length=120)
    ubicacion = models.CharField(max_length=200)

    class Meta:
        db_table = "casetas"
        ordering = ["id"]

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "ubicacion": self.ubicacion,
        }


class Tarifa(models.Model):
    categoria = models.CharField(max_length=30, db_index=True)
    ejes = models.IntegerField(default=2)
    monto = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "tarifas"
        unique_together = (("categoria", "ejes"),)
        ordering = ["categoria", "ejes"]

    def to_dict(self):
        return {
            "id": self.id,
            "categoria": self.categoria,
            "ejes": self.ejes,
            "monto": float(self.monto),
        }


class Paso(models.Model):
    placa_leida = models.CharField(max_length=40, blank=True, default="")
    placa_normalizada = models.CharField(max_length=40, db_index=True, blank=True, default="")
    confianza_ocr = models.FloatField(default=0.0)
    categoria_detectada = models.CharField(max_length=30, default="auto")
    ejes_detectados = models.IntegerField(default=2)
    # Bono +5 pts (Sección 10): Identificación y conteo de pasajeros mediante segmentación
    pasajeros = models.IntegerField(default=1)
    monto = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    caseta = models.ForeignKey(
        Caseta,
        on_delete=models.SET_NULL,
        null=True,
        db_column="caseta_id",
        related_name="pasos",
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        db_column="usuario_id",
        related_name="pasos",
    )
    imagen_url = models.TextField(blank=True, default="")
    estado = models.CharField(max_length=50, default="REGISTRADO")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "pasos"
        ordering = ["-created_at", "-id"]

    def to_dict(self):
        return {
            "id": self.id,
            "placa_leida": self.placa_leida,
            "placa_normalizada": self.placa_normalizada,
            "confianza_ocr": round(float(self.confianza_ocr), 4),
            "categoria_detectada": self.categoria_detectada,
            "ejes_detectados": self.ejes_detectados,
            "pasajeros": self.pasajeros,
            "monto": float(self.monto),
            "caseta_id": self.caseta_id,
            "caseta_nombre": self.caseta.nombre if self.caseta else "Caseta Central #1",
            "usuario_id": self.usuario_id,
            "usuario_nombre": self.usuario.nombre if self.usuario else "Operador",
            "imagen_url": self.imagen_url,
            "estado": self.estado,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Alerta(models.Model):
    paso = models.ForeignKey(
        Paso,
        on_delete=models.CASCADE,
        db_column="paso_id",
        related_name="alertas",
    )
    tipo = models.CharField(max_length=80)  # NO_REGISTRADA | SIN_SALDO | LECTURA_FALLIDA
    atendida = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "alertas"
        ordering = ["-created_at", "-id"]

    def to_dict(self):
        p = self.paso
        return {
            "id": self.id,
            "paso_id": self.paso_id,
            "tipo": self.tipo,
            "atendida": self.atendida,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "placa": p.placa_normalizada if p else "",
            "categoria": p.categoria_detectada if p else "",
            "ejes": p.ejes_detectados if p else 2,
            "pasajeros": p.pasajeros if p else 1,
            "monto": float(p.monto) if p else 0.0,
            "caseta_nombre": p.caseta.nombre if (p and p.caseta) else "Caseta Central #1",
            "imagen_url": p.imagen_url if p else "",
        }
