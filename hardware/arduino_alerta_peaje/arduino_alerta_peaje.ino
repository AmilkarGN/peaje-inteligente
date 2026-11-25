/*
 * IAM-811 Machine Learning y Aprendizaje Profundo
 * Bono +5 Puntos: Conexión de Alerta a un Dispositivo de Hardware (Arduino Uno / Nano / Mega)
 * Autor: Amilkar Hugo Guarachi Nina
 * Docente: Ing. Alvaro Pinto Mamani
 *
 * Señaliza físicamente los 4 procesos exigidos en la sección 10:
 * 1. IDENTIFICACIÓN / INFERENCIA -> LED Amarillo (Pin D9) encendido
 * 2. ACCIÓN (PASO_OK)            -> LED Verde (Pin D10) + 1 Beep corto + Servo Barrera 90°
 * 3. ALERTA (NO_REGISTRADA)      -> LED Rojo (Pin D8) parpadeante + Alarma Buzzer (Pin D7)
 * 4. ALERTA (SIN_SALDO)          -> LED Rojo + LED Amarillo + Doble tono Buzzer
 *
 * Compatible con:
 * - Web Serial API directamente desde el navegador abierto en el subdominio HTTPS de producción
 *   (sin servidores locales ni túneles)
 * - Puente Cloud HTTPS (/api/v1/hardware/estado?formato=serial)
 */

#include <Servo.h>

const int PIN_LED_VERDE    = 10;  // Paso autorizado / Acción OK
const int PIN_LED_AMARILLO = 9;   // Identificación e Inferencia en la nube
const int PIN_LED_ROJO     = 8;   // Alerta de evento (Evasión / Sin saldo)
const int PIN_BUZZER       = 7;   // Buzzer sonoro de alerta
const int PIN_SERVO        = 6;   // Servo opcional de barrera de peaje

Servo barreraServo;
String bufferSerial = "";
long ultimoCodigoEvento = -1;

void setup() {
  Serial.begin(9600);
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_AMARILLO, OUTPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  barreraServo.attach(PIN_SERVO);
  barreraServo.write(0); // Barrera cerrada

  // Secuencia de autodiagnóstico al encender el Arduino
  digitalWrite(PIN_LED_AMARILLO, HIGH);
  tone(PIN_BUZZER, 1200, 120);
  delay(200);
  digitalWrite(PIN_LED_AMARILLO, LOW);
  digitalWrite(PIN_LED_VERDE, HIGH);
  delay(200);
  digitalWrite(PIN_LED_VERDE, LOW);

  Serial.println("ARDUINO_PEAJE_IAM811_LISTO");
}

void apagarTodo() {
  digitalWrite(PIN_LED_VERDE, LOW);
  digitalWrite(PIN_LED_AMARILLO, LOW);
  digitalWrite(PIN_LED_ROJO, LOW);
  noTone(PIN_BUZZER);
}

void ejecutarInferenciaActiva() {
  apagarTodo();
  digitalWrite(PIN_LED_AMARILLO, HIGH);
  tone(PIN_BUZZER, 900, 60);
}

void ejecutarPasoAutorizado() {
  apagarTodo();
  digitalWrite(PIN_LED_VERDE, HIGH);
  tone(PIN_BUZZER, 1800, 150);
  barreraServo.write(90); // Abrir barrera
  delay(2500);
  barreraServo.write(0);  // Cerrar barrera
}

void ejecutarAlertaEvasion() {
  apagarTodo();
  barreraServo.write(0);
  for (int i = 0; i < 5; i++) {
    digitalWrite(PIN_LED_ROJO, HIGH);
    tone(PIN_BUZZER, 2400, 180);
    delay(200);
    digitalWrite(PIN_LED_ROJO, LOW);
    tone(PIN_BUZZER, 1200, 150);
    delay(180);
  }
  digitalWrite(PIN_LED_ROJO, HIGH);
}

void ejecutarAlertaSinSaldo() {
  apagarTodo();
  barreraServo.write(0);
  digitalWrite(PIN_LED_ROJO, HIGH);
  digitalWrite(PIN_LED_AMARILLO, HIGH);
  for (int i = 0; i < 3; i++) {
    tone(PIN_BUZZER, 1600, 220);
    delay(300);
  }
}

void procesarComando(String linea) {
  linea.trim();
  if (linea.length() == 0) return;

  if (linea.indexOf("FASE:INFERENCIA") >= 0 || linea.indexOf("FASE:IDENTIFICANDO") >= 0) {
    ejecutarInferenciaActiva();
  } else if (linea.indexOf("FASE:PASO_OK") >= 0) {
    ejecutarPasoAutorizado();
  } else if (linea.indexOf("FASE:ALERTA_NO_REGISTRADA") >= 0) {
    ejecutarAlertaEvasion();
  } else if (linea.indexOf("FASE:ALERTA_SIN_SALDO") >= 0) {
    ejecutarAlertaSinSaldo();
  } else if (linea.indexOf("FASE:LISTO") >= 0) {
    apagarTodo();
  }
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      procesarComando(bufferSerial);
      bufferSerial = "";
    } else {
      bufferSerial += c;
    }
  }
}
