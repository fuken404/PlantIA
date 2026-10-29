// PlantIA · firmware de referencia para ESP32
//
// Hardware:
//   - Sensor capacitivo de humedad de suelo v1.2 → GPIO 34 (entrada analógica)
//   - DHT22 (temperatura) → GPIO 4, con resistencia de 10 kΩ a 3.3 V
// Librerías: "DHT sensor library" de Adafruit (Gestor de librerías del IDE de Arduino).
//
// Copia secrets.example.h como secrets.h y completa tus datos (secrets.h no se sube al repo).

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <DHT.h>
#include "secrets.h"

#define SOIL_PIN 34
#define DHT_PIN 4
#define DHT_TYPE DHT22

// Calibración del sensor de suelo: lectura en aire (seco) y sumergido en agua (húmedo).
const int SOIL_DRY = 3200;
const int SOIL_WET = 1300;
const unsigned long INTERVAL_MS = 30UL * 60UL * 1000UL;  // cada 30 minutos

DHT dht(DHT_PIN, DHT_TYPE);

float readSoilHumidity() {
  long total = 0;
  for (int i = 0; i < 10; i++) {
    total += analogRead(SOIL_PIN);
    delay(50);
  }
  float raw = total / 10.0;
  float pct = (SOIL_DRY - raw) * 100.0 / (SOIL_DRY - SOIL_WET);
  return constrain(pct, 0, 100);
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(500);
}

void sendReading(float humidity, float temperature) {
  WiFiClientSecure client;
  client.setCACert(ROOT_CA);  // certificado raíz de la API (ver secrets.example.h)

  HTTPClient http;
  http.begin(client, String(API_URL) + "/api/readings");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);

  char body[128];
  snprintf(body, sizeof(body), "{\"plant_id\":\"%s\",\"humidity\":%.1f,\"temperature\":%.1f}",
           PLANT_ID, humidity, temperature);
  int code = http.POST(body);
  Serial.printf("POST /api/readings → %d\n", code);
  http.end();
}

void setup() {
  Serial.begin(115200);
  dht.begin();
}

void loop() {
  connectWiFi();
  float temperature = dht.readTemperature();
  float humidity = readSoilHumidity();
  if (WiFi.status() == WL_CONNECTED && !isnan(temperature)) {
    sendReading(humidity, temperature);
  } else {
    Serial.println("Sin WiFi o lectura inválida del DHT22; se reintenta en el próximo ciclo");
  }
  delay(INTERVAL_MS);
}
