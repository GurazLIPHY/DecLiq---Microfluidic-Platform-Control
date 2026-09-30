"""
backend_labsmith.py - Pilote matériel LabSmith EIB200 / 4VM02 pour DecLiq (LIPhy).
Matériel pris en compte (Devis Mengel 4677 / WP1 Fig. 3 ANR DecLiq) :
- Contrôleur USB/I2C : LS-EIB200 (DLL uProcess_x64)
- 3 manifolds 4-voies : LS-4VM02-OEM (Adresses I2C : 0x05, 0x08, 0x09)
- 8 vannes 3-voies PCTFE : LS-AV201-T132K (Tubing 1/32", ID 250 µm)
- 1 sélecteur 8-ports PCTFE : LS-AV801-T132K (Tubing 1/32", ID 250 µm)
"""
import time
import re
from typing import Optional, Dict, Tuple
from PyQt6.QtCore import QObject, pyqtSignal, QMutex, QMutexLocker

# Chargement sécurisé de la bibliothèque dynamique propriétaire LabSmith
try:
    from uProcess_x64 import CEIB, C4VM
    UPROCESS_DISPONIBLE = True
except ImportError:
    UPROCESS_DISPONIBLE = False


class BackendLabSmith(QObject):
    # Signaux généraux
    connexion_ok = pyqtSignal(bool)
    scan_infos_recu = pyqtSignal(dict)
    log_msg = pyqtSignal(str)

    # Signaux d'état matériel granulaires
    etat_vanne_modifie = pyqtSignal(int, int, int)   # (adresse, canal, nouvel_etat)
    etat_selecteur_modifie = pyqtSignal(int, int)    # (adresse, nouveau_port)

    # Topologie I2C du banc microfluidique DecLiq
    ROLES_BANC = {
        0x05: {"nom": "Left_Valve", "type": "AV201"},
        0x08: {"nom": "Rigth_Valve", "type": "AV201"},
        0x09: {"nom": "8ports_Valve", "type": "AV801", "canal_selecteur": 1}
    }

    def __init__(self, port_or_index: int | str = 3):
        super().__init__()
        self.com_index = self._extraire_index_port(port_or_index)

        self.eib = None
        self.manifolds = {}
        self.connected = False
        self.mode_simulation = False
        self.pumps = None  # Référence rattachée par frontend_gui vers BackendPumps

        # Verrouillage thread-safe du bus I2C
        self._mutex_bus = QMutex()

        # Registre mémoire des positions physiques réelles
        self.derniers_ports_av801: Dict[int, Optional[int]] = {}
        self.dernieres_pos_av201: Dict[Tuple[int, int], Optional[int]] = {}

    def _extraire_index_port(self, port_or_index: int | str) -> int:
        """Extrait l'entier du port COM (ex. 'COM3' -> 3)."""
        if isinstance(port_or_index, str):
            match = re.search(r'\d+', port_or_index)
            return int(match.group()) if match else 3
        return int(port_or_index)

    def connecter(self, port_cible: Optional[int | str] = None) -> bool:
        """Initialise la liaison série USB avec l'interface EIB200."""
        with QMutexLocker(self._mutex_bus):
            if port_cible is not None:
                self.com_index = self._extraire_index_port(port_cible)

            if not UPROCESS_DISPONIBLE:
                self.mode_simulation = True
                self.connected = True
                self.log_msg.emit("⚠️ DLL 'uProcess_x64' absente : activation du mode SIMULATION banc.")
                self.connexion_ok.emit(True)
                self._analyser_materiel_interne()
                return True

            try:
                self.eib = CEIB()
                res = self.eib.InitConnection(self.com_index)

                if res == 0:
                    self.connected = True
                    self.mode_simulation = False
                    time.sleep(0.3)
                    self.connexion_ok.emit(True)
                    self.log_msg.emit(f"✅ Liaison EIB200 validée sur le port COM{self.com_index}")
                    self._analyser_materiel_interne()
                    return True
                else:
                    self.connected = False
                    self.connexion_ok.emit(False)
                    self.log_msg.emit(f"❌ Échec liaison EIB200 (Code retour C++ : {res})")
                    return False

            except Exception as e:
                self.connected = False
                self.connexion_ok.emit(False)
                self.log_msg.emit(f"❌ Erreur critique d'accès matériel : {e}")
                return False

    def deconnecter(self):
        """Ferme proprement le bus de communication I2C."""
        with QMutexLocker(self._mutex_bus):
            if self.eib and self.connected and not self.mode_simulation:
                try:
                    self.eib.CloseConnection()
                except Exception:
                    pass
            self.connected = False
            self.manifolds.clear()
            self.log_msg.emit("🔒 Liaison contrôleur EIB200 clôturée.")

    def analyser_materiel(self):
        """Scan thread-safe du bus I2C."""
        with QMutexLocker(self._mutex_bus):
            self._analyser_materiel_interne()

    def _analyser_materiel_interne(self):
        """Interroge les 3 manifolds 4VM02 (0x05, 0x08, 0x09) et initialise leurs registres."""
        self.log_msg.emit("🔍 Scan du bus I2C (modules 4VM02 DecLiq)...")
        self.manifolds.clear()
        self.derniers_ports_av801.clear()
        self.dernieres_pos_av201.clear()
        modules_detectes = {}

        for addr, cfg in self.ROLES_BANC.items():
            detecte = False
            if self.mode_simulation:
                detecte = True
            elif self.eib and self.connected:
                try:
                    if self.eib.CmdPing(addr):
                        m = C4VM(self.eib, addr)
                        if m:
                            self.manifolds[addr] = m
                            detecte = True
                except Exception as e:
                    self.log_msg.emit(f"⚠️ Erreur ping I2C à 0x{addr:02X} : {e}")

            if detecte:
                modules_detectes[addr] = {
                    "nom": cfg["nom"],
                    "type": cfg["type"],
                    "canal_selecteur": cfg.get("canal_selecteur", None)
                }

                if cfg["type"] == "AV801":
                    self.derniers_ports_av801[addr] = None
                else:
                    for ch in range(1, 5):
                        self.dernieres_pos_av201[(addr, ch)] = None

                self.log_msg.emit(f"✨ Module actif : {cfg['nom']} (0x{addr:02X}) [{cfg['type']}]")
            else:
                self.log_msg.emit(f"⚠️ Module absent : {cfg['nom']} à 0x{addr:02X}")

        self.scan_infos_recu.emit(modules_detectes)
        self.log_msg.emit(f"🚀 Cartographie prête : {len(modules_detectes)}/3 module(s) en ligne.")

    def attendre_fin_mouvement(self, type_appareil: str = "AV201", delta: int = 1):
        """
        Garantit la stabilisation mécanique requise pour les actionneurs LabSmith :
        - AV201 : ~160 ms par cran de tiroir.
        - AV801 : ~220 ms de latence + 140 ms par port franchi en rotation horaire.
        """
        t_debut = time.perf_counter()

        if type_appareil == "AV801":
            temps_requis = min(1.45, 0.22 + (abs(delta) * 0.14))
        else:
            temps_requis = max(0.16, abs(delta) * 0.16)

        while (time.perf_counter() - t_debut) < temps_requis:
            time.sleep(0.01)

    def regler_vanne_individuelle(self, adresse: int, canal: int, etat: int):
        """Commute une vanne 3-voies AV201 (1: S1, 2: STOP, 3: S3)."""
        with QMutexLocker(self._mutex_bus):
            if not self.connected or (adresse not in self.manifolds and not self.mode_simulation):
                return

            try:
                ancienne_pos = self.dernieres_pos_av201.get((adresse, canal))
                delta = abs(etat - ancienne_pos) if ancienne_pos is not None else 2

                if not self.mode_simulation:
                    m = self.manifolds[adresse]
                    valve = m.GetValve(canal)
                    if valve:
                        valve.CmdSetPos(etat)

                self.attendre_fin_mouvement("AV201", delta=delta)
                self.dernieres_pos_av201[(adresse, canal)] = etat
                self.etat_vanne_modifie.emit(adresse, canal, etat)

                nom = self.ROLES_BANC.get(adresse, {}).get("nom", f"0x{adresse:02X}")
                self.log_msg.emit(f"🚰 {nom} - Canal {canal} -> Pos {etat}")

            except Exception as e:
                self.log_msg.emit(f"❌ Erreur commutation vanne {adresse:02X} ch{canal} : {e}")

    def regler_toutes_vannes(self, adresse: int, etat: int):
        """Commute simultanément les 4 voies d'un manifold AV201 (G ALL / D ALL)."""
        with QMutexLocker(self._mutex_bus):
            if not self.connected or (adresse not in self.manifolds and not self.mode_simulation):
                return

            try:
                delta_max = 1
                for ch in range(1, 5):
                    anc = self.dernieres_pos_av201.get((adresse, ch))
                    d = abs(etat - anc) if anc is not None else 2
                    if d > delta_max:
                        delta_max = d

                if not self.mode_simulation:
                    m = self.manifolds[adresse]
                    m.CmdSetValves(etat, etat, etat, etat)

                self.attendre_fin_mouvement("AV201", delta=delta_max)

                for ch in range(1, 5):
                    self.dernieres_pos_av201[(adresse, ch)] = etat
                    self.etat_vanne_modifie.emit(adresse, ch, etat)

                nom = self.ROLES_BANC.get(adresse, {}).get("nom", f"0x{adresse:02X}")
                self.log_msg.emit(f"⚡ {nom} (COMMANDE GLOBALE) -> Voies 1 à 4 sur Pos {etat}")

            except Exception as e:
                self.log_msg.emit(f"❌ Erreur commande globale manifold 0x{adresse:02X} : {e}")

    def regler_vanne_8ports(self, adresse: int, canal: int, port_cible: int):
        """
        Commute le sélecteur rotatif AV801.
        La rotation s'effectue strictement en sens horaire (CW).
        """
        with QMutexLocker(self._mutex_bus):
            if not self.connected or (adresse not in self.manifolds and not self.mode_simulation):
                return

            try:
                ancien_port = self.derniers_ports_av801.get(adresse)
                if ancien_port is not None:
                    delta_crans = (port_cible - ancien_port) % 8
                    if delta_crans == 0:
                        return
                else:
                    delta_crans = 7

                if not self.mode_simulation:
                    m = self.manifolds[adresse]
                    m.CmdSelect(canal, port_cible)

                self.attendre_fin_mouvement("AV801", delta=delta_crans)
                self.derniers_ports_av801[adresse] = port_cible
                self.etat_selecteur_modifie.emit(adresse, port_cible)

                self.log_msg.emit(f"🔄 AV801 -> Port {port_cible} verrouillé (+{delta_crans} crans)")

            except Exception as e:
                self.log_msg.emit(f"❌ Erreur rotation sélecteur AV801 : {e}")