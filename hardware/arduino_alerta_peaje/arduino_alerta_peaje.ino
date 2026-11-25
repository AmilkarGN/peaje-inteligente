/*
 * IAM-811 Machine Learning y Aprendizaje Profundo
 * Bono +5 Puntos: Dispositivo Físico de Alerta con Arduino (2 LEDs + 1 Buzzer)
 * Autor: Amilkar Hugo Guarachi Nina
 * Docente: Ing. Alvaro Pinto Mamani
 *
 * Conexión física ultra simple (solo necesitas tu Arduino, 2 LEDs y 1 Buzzer):
 * - Pin D10 -> Pata positiva (+) del LED 1 (Verde o Azul): Paso Autorizado / Identificación OK
 * - Pin D8  -> Pata positiva (+) del LED 2 (Rojo): Alerta (Placa no registrada o sin saldo)
 * - Pin D7  -> Pata positiva (+) del Buzzer: Sonido de confirmación o alarma
 * - Pin GND -> Patas negativas (-) de los 2 LEDs y del Buzzer
 *
 * Funciona directamente desde la aplicación web en producción (https://peaje-inteligente.onrender.com)
 * haciendo clic en el botón "Conectar Arduino por USB" (Web Serial API de Chrome/Edge).
 */

const int PIN_LED_OK     = 10; // LED 1: Paso autorizado / Vehículo válido
const int PIN_LED_ALERTA = 8;  // LED 2: Alerta (Placa no registrada o sin saldo)
const int PIN_BUZZER     = 7;  // Buzzer sonoro

String bufferSerial = "";

void setup() {
  Serial.begin(9600);
  pinMode(PIN_LED_OK, OUTPUT);
  pinMode(PIN_LED_ALERTA, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  // Prueba rápida al conectar el Arduino (parpadeo breve + 1 beep)
  digitalWrite(PIN_LED_OK, HIGH);
  tone(PIN_BUZZER, 1500, 100);
  delay(200);
  digitalWrite(PIN_LED_OK, LOW);
  digitalWrite(PIN_LED_ALERTA, HIGH);
  delay(200);
  digitalWrite(PIN_LED_ALERTA, LOW);

  Serial.println("ARDUINO_LISTO");
}

void apagarTodo() {
  digitalWrite(PIN_LED_OK, LOW);
  digitalWrite(PIN_LED_ALERTA, LOW);
  noTone(PIN_BUZZER);
}

void senalInferencia() {
  // Parpadeo corto del LED 1 indicando que está analizando el vehículo
  apagarTodo();
  digitalWrite(PIN_LED_OK, HIGH);
  tone(PIN_BUZZER, 1000, 50);
  delay(120);
  digitalWrite(PIN_LED_OK, LOW);
}

void senalPasoAutorizado() {
  // Enciende LED 1 (Verde/OK) fijo y emite 1 beep agudo de confirmación
  apagarTodo();
  digitalWrite(PIN_LED_OK, HIGH);
  tone(PIN_BUZZER, 2000, 180);
}

void senalAlerta() {
  // Parpadea LED 2 (Rojo/Alerta) con alarma intermitente en el Buzzer
  apagarTodo();
  for (int i = 0; i < 4; i++) {
    digitalWrite(PIN_LED_ALERTA, HIGH);
    tone(PIN_BUZZER, 2500, 160);
    delay(180);
    digitalWrite(PIN_LED_ALERTA, LOW);
    tone(PIN_BUZZER, 1200, 140);
    delay(160);
  }
  digitalWrite(PIN_LED_ALERTA, HIGH); // Queda encendido indicando alerta activa
}

void procesarComando(String linea) {
  linea.trim();
  if (linea.length() == 0) return;

  if (linea.indexOf("FASE:INFERENCIA") >= 0 || linea.indexOf("FASE:IDENTIFICANDO") >= 0) {
    senalInferencia();
  } else if (linea.indexOf("FASE:PASO_OK") >= 0) {
    senalPasoAutorizado();
  } else if (linea.indexOf("FASE:ALERTA") >= 0) {
    senalAlerta();
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
