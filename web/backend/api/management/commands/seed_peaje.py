"""
Seeder oficial de la Base de Datos del Peaje Inteligente (IAM-811)
Carga:
- Lista blanca de Google OAuth 2.0 (incluyendo `doc.alvaro.pinto.ma@unifranz.edu.bo` y `guamilkar@gmail.com` como administradores)
- Tarifas oficiales por categoría y número de ejes
- Casetas de peaje
- 24 vehículos de prueba (incluyendo las 20 placas reales del hito de `CREDITOS_INFERENCIA.txt`)
- Pasos iniciales y alertas para demostrar de inmediato los 4 estados del Agente Conversacional
"""

from django.core.management.base import BaseCommand

from api.models import Alerta, Caseta, Paso, Tarifa, Usuario, Vehiculo


class Command(BaseCommand):
    help = "Inicializa la base de datos con usuarios autorizados, tarifas, casetas y más de 20 vehículos de prueba."

    def handle(self, *args, **options):
        # 1. Lista Blanca de Usuarios Google OAuth 2.0 (Sección 4.4)
        usuarios_iniciales = [
            {
                "email_google": "doc.alvaro.pinto.ma@unifranz.edu.bo",
                "nombre": "Ing. Alvaro Pinto Mamani (Docente IAM-811)",
                "rol": "administrador",
                "activo": True,
            },
            {
                "email_google": "guamilkar@gmail.com",
                "nombre": "Amilkar Hugo Guarachi Nina",
                "rol": "administrador",
                "activo": True,
            },
            {
                "email_google": "guamilkar@gmial.com",
                "nombre": "Amilkar Hugo Guarachi Nina",
                "rol": "administrador",
                "activo": True,
            },
            {
                "email_google": "operador.peaje@unifranz.edu.bo",
                "nombre": "Operador de Caseta Turno 1",
                "rol": "operador",
                "activo": True,
            },
        ]
        for u_data in usuarios_iniciales:
            Usuario.objects.update_or_create(
                email_google=u_data["email_google"],
                defaults=u_data,
            )

        # 2. Casetas
        casetas_iniciales = [
            {"id": 1, "nombre": "Caseta Central #1 - Autopista", "ubicacion": "Autopista La Paz - El Alto Km 4"},
            {"id": 2, "nombre": "Caseta Achica Arriba #2", "ubicacion": "Carretera La Paz - Oruro Km 38"},
            {"id": 3, "nombre": "Caseta Urujara #3", "ubicacion": "Ruta a Los Yungas Km 12"},
        ]
        for c_data in casetas_iniciales:
            Caseta.objects.update_or_create(id=c_data["id"], defaults=c_data)

        # 3. Tarifas según Categoría (M2) y Número de Ejes (M3)
        tarifas_iniciales = [
            ("moto", 2, 3.00),
            ("auto", 2, 7.00),
            ("minibus", 2, 10.00),
            ("bus", 2, 15.00),
            ("bus", 3, 22.00),
            ("camion", 2, 20.00),
            ("camion", 3, 28.00),
            ("camion", 4, 36.00),
            ("camion", 5, 45.00),
        ]
        for cat, ejes, monto in tarifas_iniciales:
            Tarifa.objects.update_or_create(
                categoria=cat,
                ejes=ejes,
                defaults={"monto": monto},
            )

        # 4. 24 Vehículos de Prueba (las 20 placas reales de 01.jpg - 20.jpg + 4 placas nacionales)
        vehiculos_prueba = [
            # Placas de las 20 imágenes reales (01.jpg - 20.jpg)
            ("29B110559", "Amilkar Hugo Guarachi Nina", "moto", 2, 120.00, True),
            ("59M181859", "Carlos Mamani Quispe", "moto", 2, 85.00, True),
            ("67M23789", "Lucía Condori Choque", "moto", 2, 60.00, True),
            ("FMO6719", "Trans Copacabana S.R.L.", "bus", 3, 240.00, True),
            ("2739GKN", "Rodrigo Vargas Flores", "auto", 2, 95.00, True),
            ("29A51796", "María Elena Torrez", "auto", 2, 110.00, True),
            ("29A23950", "Jorge Luis Aduviri", "auto", 2, 4.00, True),   # Saldo bajo para probar alerta SIN_SALDO
            ("248KRA", "Gabriela Mendoza", "auto", 2, 75.00, True),
            ("2TE1602", "Sindicato Interciudad Bus", "bus", 2, 310.00, True),
            ("2T85921", "Flota Bolívar Express", "bus", 3, 180.00, True),
            ("JA799", "Fernando Apaza", "auto", 2, 64.00, True),
            ("CP2319", "Valeria Gutiérrez", "auto", 2, 90.00, True),
            ("68P27299", "Miguel Ángel Callisaya", "moto", 2, 45.00, True),
            ("3T48849", "Transporte Altiplano S.A.", "bus", 2, 195.00, True),
            ("5T54109", "Expreso del Sur", "bus", 2, 220.00, True),
            ("M93JTA", "Daniela Rojas Paz", "auto", 2, 88.00, True),
            ("BM07WOZ", "Sebastián Morales", "auto", 2, 105.00, True),
            ("B2341UKM", "Cooperativa Minibuses Libertad", "minibus", 2, 150.00, True),
            ("MSWL345", "Patricia Velasco", "auto", 2, 72.00, True),
            ("SM13HMU", "Andrés Salazar", "auto", 2, 130.00, True),
            # 4 vehículos adicionales de carga y transporte público
            ("4521TKB", "Transporte Pesado Andino", "camion", 3, 340.00, True),
            ("3198LPD", "Sindicato Minibuses Villa Victoria", "minibus", 2, 115.00, True),
            ("1842SRZ", "Logística Oriental Cargo", "camion", 4, 2.00, True),  # Saldo bajo
            ("5029CBA", "Distribuidora Cochabamba", "camion", 3, 260.00, True),
        ]

        for placa, prop, cat, ejes, saldo, activo in vehiculos_prueba:
            Vehiculo.objects.update_or_create(
                placa=placa,
                defaults={
                    "propietario": prop,
                    "categoria": cat,
                    "ejes": ejes,
                    "saldo": saldo,
                    "activo": activo,
                },
            )

        # 5. Sembrar pasos iniciales si aún no hay pasos para que los 4 estados del Agente estén listos
        if Paso.objects.count() == 0:
            caseta1 = Caseta.objects.get(id=1)
            caseta2 = Caseta.objects.get(id=2)
            admin_user = Usuario.objects.filter(email_google="guamilkar@gmail.com").first()

            # Pasos de vehículos registrados ("Registrada y con paso")
            Paso.objects.create(
                placa_leida="29B110559",
                placa_normalizada="29B110559",
                confianza_ocr=0.96,
                categoria_detectada="moto",
                ejes_detectados=2,
                pasajeros=1,
                monto=3.00,
                caseta=caseta1,
                usuario=admin_user,
                imagen_url="",
                estado="AUTORIZADO",
            )
            Paso.objects.create(
                placa_leida="FMO-6719",
                placa_normalizada="FMO6719",
                confianza_ocr=0.94,
                categoria_detectada="bus",
                ejes_detectados=3,
                pasajeros=14,
                monto=22.00,
                caseta=caseta1,
                usuario=admin_user,
                imagen_url="",
                estado="AUTORIZADO",
            )
            Paso.objects.create(
                placa_leida="2739-GKN",
                placa_normalizada="2739GKN",
                confianza_ocr=0.95,
                categoria_detectada="auto",
                ejes_detectados=2,
                pasajeros=3,
                monto=7.00,
                caseta=caseta2,
                usuario=admin_user,
                imagen_url="",
                estado="AUTORIZADO",
            )
            Paso.objects.create(
                placa_leida="B2341UKM",
                placa_normalizada="B2341UKM",
                confianza_ocr=0.93,
                categoria_detectada="minibus",
                ejes_detectados=2,
                pasajeros=9,
                monto=10.00,
                caseta=caseta1,
                usuario=admin_user,
                imagen_url="",
                estado="AUTORIZADO",
            )

            # Paso de vehículo NO registrado en padrón ("Identificada no registrada" + Alerta en vivo)
            paso_evasor = Paso.objects.create(
                placa_leida="EVASOR-901",
                placa_normalizada="EVASOR901",
                confianza_ocr=0.91,
                categoria_detectada="camion",
                ejes_detectados=3,
                pasajeros=2,
                monto=28.00,
                caseta=caseta1,
                usuario=admin_user,
                imagen_url="",
                estado="NO_REGISTRADA",
            )
            Alerta.objects.create(
                paso=paso_evasor,
                tipo="PLACA_NO_REGISTRADA",
                atendida=False,
            )

            # Paso de vehículo registrado pero sin saldo suficiente
            paso_sin_saldo = Paso.objects.create(
                placa_leida="29A23950",
                placa_normalizada="29A23950",
                confianza_ocr=0.92,
                categoria_detectada="auto",
                ejes_detectados=2,
                pasajeros=2,
                monto=7.00,
                caseta=caseta2,
                usuario=admin_user,
                imagen_url="",
                estado="SIN_SALDO",
            )
            Alerta.objects.create(
                paso=paso_sin_saldo,
                tipo="VEHICULO_SIN_SALDO",
                atendida=False,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Base de datos inicializada: {Usuario.objects.count()} usuarios en lista blanca, "
                f"{Vehiculo.objects.count()} vehículos, {Tarifa.objects.count()} tarifas, "
                f"{Caseta.objects.count()} casetas, {Paso.objects.count()} pasos, {Alerta.objects.count()} alertas."
            )
        )
