# Sistema de Navegación GPS para Vehículos en Tiempo Real

Aplicación desarrollada en Python para la adquisición, procesamiento y visualización en tiempo real de datos de posicionamiento GPS en vehículos, validada en pista de pruebas real (INSIA).

## Stack Tecnológico y Fundamentos
- **Lenguaje:** Python
- **Adquisición de Datos:** Lectura de tramas estándar NMEA (`$GPGGA`) por puerto serie a 1 Hz
- **Cálculo Geodésico:** Ecuaciones de Gauss-Krüger para la transformación de coordenadas geográficas (WGS84) a proyección plana UTM
- **Cartografía:** Integración con servicios de mapas georreferenciados

## Características Principales
- **Decodificación y Proyección:** Lectura continua de latitud, longitud y altitud con conversión en tiempo real a coordenadas cartesianas UTM (X, Y).
- **Visualización Dinámica:** Representación en pantalla de la trayectoria y posición actual del vehículo sobre cartografía web.
- **Asistente de Velocidad:** Comparación de la posición y el sentido de la marcha (horario y antihorario) frente a un mapa de límites de velocidad, generando avisos visuales al conductor ante excesos de velocidad.

---
*Proyecto académico — Grado en Ingeniería del Software (ETSISI - UPM).*
