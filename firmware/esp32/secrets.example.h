// Copia este archivo como secrets.h y completa los valores. secrets.h está en .gitignore.
#pragma once

#define WIFI_SSID "tu-red"
#define WIFI_PASSWORD "tu-clave"
#define API_URL "https://plantia.fuken404.dev"
#define DEVICE_KEY "la-misma-DEVICE_API_KEY-configurada-en-Vercel"
#define PLANT_ID "rosita"

// Certificado raíz que firma el HTTPS de la API, en formato PEM.
// Puedes obtenerlo desde el navegador (candado → certificado → raíz → exportar).
const char* ROOT_CA = R"(-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
)";
