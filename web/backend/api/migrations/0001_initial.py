from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Usuario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email_google", models.EmailField(db_index=True, max_length=254, unique=True)),
                ("nombre", models.CharField(max_length=150)),
                ("rol", models.CharField(choices=[("administrador", "Administrador"), ("operador", "Operador")], default="operador", max_length=30)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "usuarios",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Vehiculo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("placa", models.CharField(db_index=True, max_length=30, unique=True)),
                ("propietario", models.CharField(max_length=150)),
                ("categoria", models.CharField(choices=[("moto", "Moto"), ("auto", "Auto"), ("minibus", "Minibús"), ("camion", "Camión"), ("bus", "Bus")], default="auto", max_length=30)),
                ("ejes", models.IntegerField(default=2)),
                ("saldo", models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "vehiculos",
                "ordering": ["placa"],
            },
        ),
        migrations.CreateModel(
            name="Caseta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                ("ubicacion", models.CharField(max_length=200)),
            ],
            options={
                "db_table": "casetas",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="Tarifa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("categoria", models.CharField(db_index=True, max_length=30)),
                ("ejes", models.IntegerField(default=2)),
                ("monto", models.DecimalField(decimal_places=2, max_digits=10)),
            ],
            options={
                "db_table": "tarifas",
                "ordering": ["categoria", "ejes"],
                "unique_together": {("categoria", "ejes")},
            },
        ),
        migrations.CreateModel(
            name="Paso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("placa_leida", models.CharField(blank=True, default="", max_length=40)),
                ("placa_normalizada", models.CharField(blank=True, db_index=True, default="", max_length=40)),
                ("confianza_ocr", models.FloatField(default=0.0)),
                ("categoria_detectada", models.CharField(default="auto", max_length=30)),
                ("ejes_detectados", models.IntegerField(default=2)),
                ("pasajeros", models.IntegerField(default=1)),
                ("monto", models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ("imagen_url", models.TextField(blank=True, default="")),
                ("estado", models.CharField(default="REGISTRADO", max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("caseta", models.ForeignKey(db_column="caseta_id", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pasos", to="api.caseta")),
                ("usuario", models.ForeignKey(db_column="usuario_id", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pasos", to="api.usuario")),
            ],
            options={
                "db_table": "pasos",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Alerta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(max_length=80)),
                ("atendida", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("paso", models.ForeignKey(db_column="paso_id", on_delete=django.db.models.deletion.CASCADE, related_name="alertas", to="api.paso")),
            ],
            options={
                "db_table": "alertas",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
