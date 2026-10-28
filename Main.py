# =====================================================================
#  Avancement d'impression 3D sur M5StickC PLUS2 (UIFlow 2)
#  Source des données : API Moonraker de l'imprimante (celle de Fluidd)
#  Affiche : état, pourcentage, barre de progression,
#            temps écoulé, temps restant, et bip à la fin
#  Auteur : Jean-Paul Laville
#  Utilisation de Claude
#  Date : Octobre 2026
#  Version : 1.0
# =====================================================================

import M5
from M5 import *
import network
import requests
import time

# ---------------------------------------------------------------------
#  CONFIGURATION : à adapter
# ---------------------------------------------------------------------
WIFI_SSID = "TON_WIFI"           # Réseau Wi-Fi de l'imprimante (2,4 GHz obligatoire)
WIFI_PASS = "TON_MOT_DE_PASSE"
PRINTER = "http://192.168.1.81:7125"   # Adresse de Moonraker (port 7125)
REFRESH = 10                     # Secondes entre deux mises à jour

# Requête envoyée à l'imprimante : état de l'impression + avancement
URL = PRINTER + "/printer/objects/query?print_stats&virtual_sdcard"

# ---------------------------------------------------------------------
#  INITIALISATION DE L'ECRAN
# ---------------------------------------------------------------------
print("Demarrage")
M5.begin()
Widgets.setRotation(1)           # Mode paysage (240 x 135)
Widgets.fillScreen(0x000000)     # Fond noir

# Les 4 textes de l'écran, de haut en bas :
lbl_state = Widgets.Label("Demarrage...", 5, 2, 1.0, 0xffffff, 0x000000, Widgets.FONTS.DejaVu18)  # état
lbl_pct   = Widgets.Label("", 5, 25, 1.0, 0x00ff00, 0x000000, Widgets.FONTS.DejaVu40)             # pourcentage
# (la barre de progression est dessinée à y = 68, voir draw_bar)
lbl_elap  = Widgets.Label("", 5, 85, 1.0, 0xaaaaaa, 0x000000, Widgets.FONTS.DejaVu18)             # temps écoulé
lbl_rem   = Widgets.Label("", 5, 108, 1.0, 0xffffff, 0x000000, Widgets.FONTS.DejaVu18)            # temps restant

# ---------------------------------------------------------------------
#  VARIABLES DE SUIVI (mémoire entre deux mises à jour)
# ---------------------------------------------------------------------
last_state = None    # Etat lors de la mise à jour précédente (pour détecter la fin)
estimated = None     # Durée totale estimée par le slicer, en secondes
last_file = None     # Dernier fichier lu (pour ne chercher l'estimation qu'une fois)

# ---------------------------------------------------------------------
#  FONCTIONS
# ---------------------------------------------------------------------
def wifi_connect():
    """Connecte le M5 au Wi-Fi (20 s maximum). Renvoie True si connecté."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        # Désactive l'économie d'énergie du Wi-Fi (évite les coupures)
        wlan.config(pm=network.WLAN.PM_NONE)
    except Exception as e:
        print("PM non supporte:", e)

    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASS)
        t = 0
        while not wlan.isconnected() and t < 20:
            lbl_state.setText("WiFi %ds" % t)   # Compteur affiché pendant la connexion
            print("WiFi", t)
            time.sleep(1)
            t += 1

    if wlan.isconnected():
        print("IP:", wlan.ifconfig())
        lbl_state.setText("WiFi OK")
        time.sleep(3)                           # Laisse le réseau se stabiliser
        return True

    lbl_state.setText("WiFi echec")
    print("WiFi echec")
    return False


def fmt(sec):
    """Convertit des secondes en texte du type 1h15m."""
    sec = int(sec)
    return "%dh%02dm" % (sec // 3600, (sec % 3600) // 60)


def draw_bar(pct, color):
    """Dessine la barre de progression : fond gris, partie remplie en couleur."""
    M5.Lcd.fillRect(5, 68, 230, 10, 0x333333)                    # Fond de la barre
    M5.Lcd.fillRect(5, 68, int(230 * pct / 100), 10, color)      # Partie remplie


def beep_fin():
    """Trois bips pour signaler la fin (ou l'échec) de l'impression."""
    Speaker.setVolumePercentage(0.6)
    for _ in range(3):
        Speaker.tone(2500, 300)    # Fréquence en Hz, durée en ms
        time.sleep(0.5)


def get_estimated(filename):
    """Demande à l'imprimante la durée totale estimée par le slicer.
    Renvoie un nombre de secondes, ou None si l'info est indisponible."""
    try:
        fname = filename.replace(" ", "%20")     # Les espaces doivent être encodés dans l'URL
        r = requests.get(PRINTER + "/server/files/metadata?filename=" + fname, timeout=5)
        meta = r.json()["result"]
        r.close()
        return meta.get("estimated_time")
    except Exception as e:
        print("META ERREUR:", type(e).__name__, e)
        return None


def update():
    """Interroge l'imprimante et met à jour tout l'affichage."""
    global last_state, estimated, last_file
    try:
        # --- 1. Récupération des données ---
        r = requests.get(URL, timeout=5)
        s = r.json()["result"]["status"]
        r.close()

        state = s["print_stats"]["state"]                # standby / printing / paused / complete / error
        filename = s["print_stats"]["filename"]          # Nom du fichier en cours
        pct = s["virtual_sdcard"]["progress"] * 100      # Avancement en %
        elapsed = s["print_stats"]["print_duration"]     # Temps d'impression écoulé (s)

        # --- 2. Bip si l'impression vient de se terminer ou de planter ---
        if last_state == "printing" and state in ("complete", "error"):
            beep_fin()
        last_state = state

        # --- 3. Temps estimé : récupéré une seule fois par fichier ---
        if filename and filename != last_file:
            estimated = get_estimated(filename)
            last_file = filename

        # --- 4. Couleur selon l'état ---
        colors = {
            "printing": 0x00ff00,   # vert
            "paused": 0xffaa00,     # orange
            "complete": 0x00aaff,   # bleu
            "error": 0xff0000,      # rouge
        }
        color = colors.get(state, 0xffffff)   # blanc pour les autres états

        # --- 5. Affichage de l'état, du pourcentage et du temps écoulé ---
        lbl_state.setText(state)
        lbl_pct.setText("%d %%" % pct)
        lbl_elap.setText("Ecoule: " + fmt(elapsed))

        # --- 6. Affichage du temps restant ---
        if state == "printing":
            if estimated:
                # Cas idéal : durée estimée par le slicer moins temps écoulé
                lbl_rem.setText("Reste:  " + fmt(max(estimated - elapsed, 0)))
            elif pct >= 3:
                # Sinon : estimation à partir de la vitesse d'avancement
                total = elapsed / (pct / 100)
                lbl_rem.setText("Reste:  " + fmt(total - elapsed))
            else:
                lbl_rem.setText("Reste:  --")     # Trop tôt pour estimer
        elif state == "complete":
            lbl_rem.setText("Termine")
        else:
            lbl_rem.setText("Reste:  --")

        # --- 7. Barre de progression ---
        draw_bar(pct, color)

    except Exception as e:
        # En cas de problème, le nom de l'erreur s'affiche en haut de l'écran
        # et le détail dans la console WebTerminal
        print("ERREUR:", type(e).__name__, e)
        lbl_state.setText(type(e).__name__)

# ---------------------------------------------------------------------
#  PROGRAMME PRINCIPAL
# ---------------------------------------------------------------------
print("Debut wifi")
while not wifi_connect():
    time.sleep(5)              # Réessaie toutes les 5 s tant que le Wi-Fi est absent
print("Wifi fini")

while True:
    M5.update()
    print("Update...")
    update()                   # Interroge l'imprimante et rafraîchit l'écran
    time.sleep(REFRESH)        # Pause avant la prochaine mise à jour
