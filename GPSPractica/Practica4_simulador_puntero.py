import os
import sys
import serial
import math
import threading
import queue
import time
import tkinter as tk
import tkintermapview #pip3 install tkintermapview

from Datum import WGS84

# ==========================================
# CARGA MAPA INSIA
# ==========================================

def cargar_mapa(ruta_fichero):
    mapa = []
    try:
        with open(ruta_fichero, 'r') as f:
            for linea in f:
                partes = linea.strip().split()
                if len(partes) != 3:
                    continue
                utm_n = float(partes[0])
                utm_e = float(partes[1])
                v_max = float(partes[2])
                mapa.append((utm_e, utm_n, v_max))
    except FileNotFoundError:
        print(f"Aviso: No se encontró el mapa en {ruta_fichero}. Se usará un mapa vacío.")
    return mapa

# ==========================================
# PUNTO MÁS CERCANO (CON REGLA DE 30 METROS)
# ==========================================

def punto_mas_cercano(utm_e, utm_n, mapa):
    min_dist = float('inf')
    punto = None
    idx_final = 0

    for i, p in enumerate(mapa):
        dist = math.sqrt((utm_e - p[0])**2 + (utm_n - p[1])**2)
        if dist < min_dist:
            min_dist = dist
            punto = p
            idx_final = i

    if min_dist > 30.0:
        return None, -1

    return punto, idx_final

# ==========================================
# DIRECCIÓN
# ==========================================

def direccion(p1, p2):
    return (p2[0] - p1[0], p2[1] - p1[1])

def producto_escalar(v1, v2):
    return (v1[0]*v2[0] + v1[1]*v2[1])

# ==========================================
# GPS -> UTM
# ==========================================

def conversorUTM(latitud, longitud, datum):
    a = datum.a
    e2 = datum.e2

    huso = int((longitud + 180) / 6) + 1
    longCent = math.radians(huso * 6 - 183)

    latRad = math.radians(latitud)
    longRad = math.radians(longitud)

    N = a / math.sqrt(1 - e2 * math.sin(latRad)**2)
    T = math.tan(latRad)**2
    C = e2 * math.cos(latRad)**2
    A = math.cos(latRad) * (longRad - longCent)

    M = a * (
        (1 - e2/4 - 3*e2**2/64 - 5*e2**3/256) * latRad
        - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * latRad)
        + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * latRad)
        - (35 * e2 ** 3 / 3072) * math.sin(6 * latRad)
    )

    UTM_E = 0.9996 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T ** 2 + 72 * C - 58 * e2) * A ** 5 / 120) + 500000
    UTM_N = 0.9996 * (M + N * math.tan(latRad) * (A ** 2 / 2 + (5 - T + 9 * C + 4 * C ** 2) * A ** 4 / 24 + (61 - 58 * T + T ** 2 + 600 * C - 330 * e2) * A ** 6 / 720))

    if latitud < 0:
        UTM_N += 10000000

    return UTM_E, UTM_N, huso

# ==========================================
# VELOCIDAD FILTRADA
# ==========================================

def eliminar_redundancia(buffer_puntos):
    p1, p2, p3 = buffer_puntos
    d13 = math.sqrt((p3[0] - p1[0])**2 + (p3[1] - p1[1])**2)
    t13 = p3[2] - p1[2]

    if t13 <= 0:
        return 0.0

    velocidad_ms = d13 / t13
    return velocidad_ms * 3.6

# ==========================================
# INTERFAZ (HUD + TECLADO + RATÓN)
# ==========================================

class InterfazGPS:

    def __init__(self, root, line_queue):
        self.line_queue = line_queue
        
        # Variables de estado para la simulación
        self.simulacion_activa = False
        self.lat_actual = 40.4168
        self.lon_actual = -3.7038

        self.map_widget = tkintermapview.TkinterMapView(
            root,
            width=1200,
            height=700,
            corner_radius=0
        )
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_position(self.lat_actual, self.lon_actual)
        self.map_widget.set_zoom(17)

        # Eventos de interacción (Ratón y Teclado)
        self.map_widget.add_left_click_map_command(self.simular_click_mapa)
        root.bind("<Up>", self.mover_teclado)
        root.bind("<Down>", self.mover_teclado)
        root.bind("<Left>", self.mover_teclado)
        root.bind("<Right>", self.mover_teclado)

        self.marker = None
        self.path_coords = []
        self.path_dibujo = None

        # HUD
        self.frame = tk.Frame(root, bg="white")
        self.frame.place(x=10, y=10)

        self.label = tk.Label(
            self.frame,
            text="Vel: 0.0 | Lim: ---",
            font=("Consolas", 16, "bold"),
            bg="white",
            width=32
        )
        self.label.pack()

    def simular_click_mapa(self, coordenada):
        self.simulacion_activa = True # Bloquea el GPS físico
        self.lat_actual, self.lon_actual = coordenada
        self.line_queue.put(("SIM", self.lat_actual, self.lon_actual))

    def mover_teclado(self, event):
        self.simulacion_activa = True # Bloquea el GPS físico
        
        # Unos ~2.2 metros de desplazamiento por pulsación
        delta_lat = 0.00002 
        # Ajuste trigonométrico para que la longitud sea proporcional a la latitud
        delta_lon = 0.00002 / math.cos(math.radians(self.lat_actual)) if math.cos(math.radians(self.lat_actual)) != 0 else 0.00002

        if event.keysym == 'Up':
            self.lat_actual += delta_lat
        elif event.keysym == 'Down':
            self.lat_actual -= delta_lat
        elif event.keysym == 'Left':
            self.lon_actual -= delta_lon
        elif event.keysym == 'Right':
            self.lon_actual += delta_lon

        self.line_queue.put(("SIM", self.lat_actual, self.lon_actual))

    def actualizar(self, latitud, longitud, velocidad, limite_kmh, color):
        # Mantenemos las variables actualizadas por si pasamos al modo teclado
        self.lat_actual = latitud
        self.lon_actual = longitud

        self.map_widget.set_position(latitud, longitud)

        if self.marker:
            self.marker.delete()

        self.marker = self.map_widget.set_marker(latitud, longitud, text="Coche")

        self.path_coords.append((latitud, longitud))
        if len(self.path_coords) > 1:
            if self.path_dibujo:
                self.path_dibujo.delete()
            self.path_dibujo = self.map_widget.set_path(self.path_coords, color="blue", width=4)

        prefijo = "[SIM] " if self.simulacion_activa else ""

        if limite_kmh == 999.0:
            texto_hud = f"{prefijo}Vel: {velocidad:.1f} | Fuera de pista"
        else:
            texto_hud = f"{prefijo}Vel: {velocidad:.1f} | Lim: {limite_kmh:.0f}"

        self.label.config(text=texto_hud, bg=color)

# ==========================================
# LECTOR GPS
# ==========================================

def leer_datos_gps(puerto_serie, line_queue, stop_event):
    try:
        with serial.Serial(
            port=puerto_serie,
            baudrate=4800,
            timeout=1
        ) as datos:
            while not stop_event.is_set():
                linea = datos.readline().decode('ascii', errors='ignore').strip()
                if linea.startswith('$GPGGA'):
                    line_queue.put(linea)
    except Exception as e:
        print(f"\n[Aviso] No hay GPS real conectado en {puerto_serie}.")
        print("Usa el ratón o las flechas del teclado para moverte.\n")

# ==========================================
# PROCESAMIENTO
# ==========================================

def procesar_datos_queue(line_queue, stop_event, root, interfaz, mapa):
    buffer_puntos = []
    velocidad_kmh = 0.0

    while not stop_event.is_set():
        try:
            item = line_queue.get(timeout=1)
            
            hora_utc = "000000"
            satelites = "0"
            calidad = "0"

            # CASO 1: Viene del puerto serie real
            if isinstance(item, str):
                if interfaz.simulacion_activa:
                    # Si el usuario ha usado el teclado o ratón, ignoramos el GPS físico
                    continue 

                campos = item.split(',')
                if campos[6] == '0' or campos[2] == '' or campos[4] == '':
                    continue

                latitud = float(campos[2][:2]) + float(campos[2][2:]) / 60
                longitud = float(campos[4][:3]) + float(campos[4][3:]) / 60

                if campos[3] == 'S': latitud = -latitud
                if campos[5] == 'W': longitud = -longitud
                
                hora_utc = campos[1]
                calidad = campos[6]
                satelites = campos[7]

            # CASO 2: Viene del click o teclado (Tupla generada por Interfaz)
            elif isinstance(item, tuple) and item[0] == "SIM":
                _, latitud, longitud = item
                hora_utc = time.strftime("%H%M%S", time.gmtime())
                calidad = "1 (SIM)"
                satelites = "99"

            else:
                continue

            UTM_E, UTM_N, _ = conversorUTM(latitud, longitud, WGS84)
            tiempo_actual = time.time()

            buffer_puntos.append((UTM_E, UTM_N, tiempo_actual))

            if len(buffer_puntos) > 3:
                buffer_puntos.pop(0)

            if len(buffer_puntos) == 3:
                velocidad_kmh = eliminar_redundancia(buffer_puntos)

                punto, idx = punto_mas_cercano(UTM_E, UTM_N, mapa)
                sentido_contrario = False

                if punto is None:
                    v_max = 999.0
                    color = "white"
                else:
                    v_max = punto[2]
                    v_coche = direccion(buffer_puntos[-2], buffer_puntos[-1])

                    if idx < len(mapa)-1:
                        v_mapa = direccion(mapa[idx], mapa[idx+1])
                    else:
                        v_mapa = direccion(mapa[idx-1], mapa[idx])

                    sentido = producto_escalar(v_coche, v_mapa)
                    if sentido < 0:
                        sentido_contrario = True

                    if velocidad_kmh < v_max * 0.9: color = "green"
                    elif velocidad_kmh < v_max * 1.1: color = "yellow"
                    else: color = "red"

                print("\n" + "="*30)
                print(f"POSICION | Hora: {hora_utc} | Modo: {'SIM' if interfaz.simulacion_activa else 'REAL'}")
                print(f"Latitud: {latitud:.6f} | Longitud: {longitud:.6f}")
                print(f"UTM X: {UTM_E:.3f} | UTM Y: {UTM_N:.3f}")
                print("-" * 30)
                
                texto_cons_lim = "Fuera de pista" if v_max == 999.0 else f"{v_max:.2f} km/h"
                print(f"Vel: {velocidad_kmh:.2f} km/h | Limite: {texto_cons_lim}")
                
                if sentido_contrario:
                    print("AVISO: SENTIDO CONTRARIO")
                print("="*30)

                root.after(0, interfaz.actualizar, latitud, longitud, velocidad_kmh, v_max, color)

        except queue.Empty:
            continue

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    puerto_gps = "COM5"

    directorio_script = os.path.dirname(os.path.abspath(sys.argv[0]))
    ruta_mapa = os.path.join(directorio_script, "sources", "Mapa_INSIA2.txt")

    mapa_datos = cargar_mapa(ruta_mapa)

    root = tk.Tk()
    root.title("Practica 4 - Navegacion GPS Online + Modo Simulador")
    root.geometry("1200x700")

    line_queue = queue.Queue()

    interfaz = InterfazGPS(root, line_queue)
    stop_event = threading.Event()

    t1 = threading.Thread(target=leer_datos_gps, args=(puerto_gps, line_queue, stop_event), daemon=True)
    t2 = threading.Thread(target=procesar_datos_queue, args=(line_queue, stop_event, root, interfaz, mapa_datos), daemon=True)

    t1.start()
    t2.start()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        stop_event.set()