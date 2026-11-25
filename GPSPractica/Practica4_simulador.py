import os
import sys
import math
import tkinter as tk
import tkintermapview #pip3 install tkintermapview

from Datum import WGS84

# ==========================================
# CARGA MAPA INSIA
# ==========================================

def cargar_mapa(ruta_fichero):
    mapa = []
    with open(ruta_fichero, 'r') as f:
        for linea in f:
            partes = linea.strip().split()
            if len(partes) != 3: continue
            utm_n = float(partes[0])
            utm_e = float(partes[1])
            v_max = float(partes[2])
            mapa.append((utm_e, utm_n, v_max))
    return mapa

# ==========================================
# PRE-PROCESAR ARCHIVO DE SIMULACION
# ==========================================

def cargar_cadena_simulacion(ruta_fichero):
    puntos = []
    print(f"Cargando archivo de simulacion: {ruta_fichero}...")
    
    with open(ruta_fichero, 'r') as f:
        for linea in f:
            linea = linea.strip()
            if not linea.startswith('$GPGGA'): continue
            
            campos = linea.split(',')
            if len(campos) < 7 or campos[6] == '0' or campos[2] == '' or campos[4] == '':
                continue

            try:
                latitud = float(campos[2][:2]) + float(campos[2][2:]) / 60
                longitud = float(campos[4][:3]) + float(campos[4][3:]) / 60
                if campos[3] == 'S': latitud = -latitud
                if campos[5] == 'W': longitud = -longitud

                hora_str = campos[1]
                if not hora_str: continue
                
                h = int(hora_str[0:2])
                m = int(hora_str[2:4])
                s = float(hora_str[4:])
                t_segundos = h * 3600 + m * 60 + s

                utm_e, utm_n, _ = conversorUTM(latitud, longitud, WGS84)

                puntos.append({
                    'lat': latitud,
                    'lon': longitud,
                    'utm_e': utm_e,
                    'utm_n': utm_n,
                    'tiempo': t_segundos
                })
            except ValueError:
                continue
            
    print(f"Completado. {len(puntos)} puntos cargados en memoria.")
    return puntos

# ==========================================
# MATEMATICAS Y FISICAS
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
    if latitud < 0: UTM_N += 10000000
    return UTM_E, UTM_N, huso

def eliminar_redundancia(buffer_puntos):
    p1, p2, p3 = buffer_puntos
    d13 = math.sqrt((p3['utm_e'] - p1['utm_e'])**2 + (p3['utm_n'] - p1['utm_n'])**2)
    t13 = p3['tiempo'] - p1['tiempo']
    if t13 <= 0: return 0.0
    return (d13 / t13) * 3.6

# ==========================================
# REPRODUCTOR INTERACTIVO
# ==========================================

class ReproductorGPS:
    def __init__(self, root, mapa, puntos_gps):
        self.root = root
        self.mapa = mapa
        self.puntos = puntos_gps
        
        self.idx = 0
        self.is_playing = False
        self.total_puntos = len(puntos_gps) - 1

        self.map_widget = tkintermapview.TkinterMapView(root, width=1200, height=700, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_zoom(17)
        
        self.marker = None
        self.path_dibujo = None

        self.frame_vel = tk.Frame(root, bg="white")
        self.frame_vel.place(x=10, y=10)
        self.label_vel = tk.Label(self.frame_vel, text="Cargando...", font=("Consolas", 16, "bold"), bg="white", width=28)
        self.label_vel.pack()

        self.frame_controles = tk.Frame(root, bg="#2b2b2b", padx=10, pady=5)
        self.frame_controles.place(relx=0.98, y=10, anchor="ne")
        
        texto_leyenda = (
            "CONTROLES DEL SIMULADOR\n"
            "-------------------------\n"
            "[P] Play / Pausa (1s, +50)\n"
            "[->] Avanzar 100 puntos\n"
            "[<-] Retroceder 100 puntos"
        )
        self.label_controles = tk.Label(self.frame_controles, text=texto_leyenda, font=("Consolas", 10, "bold"), bg="#2b2b2b", fg="white", justify="left")
        self.label_controles.pack()

        self.root.bind("<p>", self.toggle_play)
        self.root.bind("<Right>", self.avanzar)
        self.root.bind("<Left>", self.retroceder)

        if self.total_puntos > 0:
            self.procesar_y_dibujar()

    def toggle_play(self, event=None):
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.label_controles.config(fg="#00ff00") 
            self.auto_play()
        else:
            self.label_controles.config(fg="white") 

    def auto_play(self):
        if self.is_playing:
            self.idx = min(self.idx + 50, self.total_puntos)
            self.procesar_y_dibujar()
            if self.idx < self.total_puntos:
                self.root.after(1000, self.auto_play)
            else:
                self.is_playing = False
                self.label_controles.config(fg="white")

    def avanzar(self, event=None):
        if not self.is_playing:
            self.idx = min(self.idx + 100, self.total_puntos)
            self.procesar_y_dibujar()

    def retroceder(self, event=None):
        if not self.is_playing:
            self.idx = max(self.idx - 100, 0)
            self.procesar_y_dibujar()

    def procesar_y_dibujar(self):
        punto = self.puntos[self.idx]

        print(f"Punto actual: {self.idx} / {self.total_puntos}")

        if self.idx >= 2:
            velocidad = eliminar_redundancia(self.puntos[self.idx-2 : self.idx+1])
        else:
            velocidad = 0.0

        pmc, _ = punto_mas_cercano(punto['utm_e'], punto['utm_n'], self.mapa)

        if pmc is None:
            v_max = 999.0
            color = "white"
        else:
            v_max = pmc[2]
            if velocidad < v_max * 0.9: color = "green"
            elif velocidad < v_max * 1.1: color = "yellow"
            else: color = "red"

        # VUELVO A ACTIVAR EL SEGUIMIENTO DE CAMARA PARA QUE NO SE ESCAPE
        self.map_widget.set_position(punto['lat'], punto['lon'])

        if self.marker: self.marker.delete()
        self.marker = self.map_widget.set_marker(punto['lat'], punto['lon'], text="Coche")

        inicio_estela = max(0, self.idx - 50)
        coords_estela = [(p['lat'], p['lon']) for p in self.puntos[inicio_estela : self.idx+1]]
        
        if len(coords_estela) > 1:
            if self.path_dibujo: self.path_dibujo.delete()
            self.path_dibujo = self.map_widget.set_path(coords_estela, color="blue", width=4)

        if v_max == 999.0:
            texto_hud = f"Vel: {velocidad:.1f} | Fuera de pista"
        else:
            texto_hud = f"Vel: {velocidad:.1f} | Lim: {v_max:.0f}"

        self.label_vel.config(text=texto_hud, bg=color)

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    directorio_script = os.path.dirname(os.path.abspath(sys.argv[0]))
    
    ruta_mapa = os.path.join(directorio_script, "sources", "Mapa_INSIA2.txt")
    ruta_cadena = os.path.join(directorio_script, "sources", "p4_sources", "cadena14.txt")

    mapa_datos = cargar_mapa(ruta_mapa)
    puntos_simulacion = cargar_cadena_simulacion(ruta_cadena)

    root = tk.Tk()
    root.title("Reproductor Interactivo - Practica 4 Navegacion GPS")
    root.geometry("1200x700")

    if puntos_simulacion:
        app = ReproductorGPS(root, mapa_datos, puntos_simulacion)
    else:
        print("Error: No se pudieron cargar datos del archivo cadena14.txt")

    root.mainloop()