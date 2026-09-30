"""
backend_pumps.py - Gestionnaire pour le double pousse-seringue DecLiq (LIPhy).
Pilote KD Scientific Legato 110 (liaison USB CDC).
- Auto-détection et connexion automatique sur les ports COM au démarrage.
- Mode Custom : transmission conjointe svolume + diameter pour affichage complet.
- Unités supportées : µL/min, mL/min, nL/min, etc.
- Identification visuelle par flash du rétroéclairage LCD ('dim').
"""
import time
import re
from typing import Optional, Dict, Any, Tuple
from PyQt6.QtCore import QObject, pyqtSignal, QMutex, QMutexLocker

from syringe_database import TABLE_PLATE, OPTION_PERSONNALISEE, get_diametre
from i18n import tr

try:
    import serial
    import serial.tools.list_ports
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False


def extraire_volume_et_unite(nom_modele: str, diametre: float) -> Tuple[float, str]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(m[lL]|µ[lL]|u[lL])", nom_modele)
    if m:
        val = float(m.group(1))
        u = "ml" if "m" in m.group(2).lower() else "ul"
        return val, u

    vol_ml = (3.14159265 / 4.0) * (diametre ** 2) * 60.0 / 1000.0
    if vol_ml < 0.1:
        return max(0.1, round(vol_ml * 1000.0, 1)), "ul"
    return max(0.01, round(vol_ml, 2)), "ml"


class SyringePumpUnit:
    def __init__(self, pump_id: int, nom: str, role_fluide: str, debit_defaut: float, diam_defaut: float = 4.608, nom_seringue: str = "Hamilton Gastight 1 mL"):
        self.pump_id = pump_id
        self.nom = nom
        self.role_fluide = role_fluide
        self.port: Optional[str] = None
        self.serial_conn: Optional[Any] = None
        self.connecte = False
        self.mode_virtuel = False
        self.en_marche = False
        self.sens = "withdraw"
        self.debit = debit_defaut
        self.unite_debit = "µL/min"
        self.diametre_seringue = diam_defaut
        self.nom_seringue = nom_seringue
        self.numero_serie = "Inconnu"
        self.verrou_watchdog = 0.0


class BackendPumps(QObject):
    etat_pompe_modifie = pyqtSignal(int, dict)
    log_msg = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._mutex = QMutex()
        self.pompes: Dict[int, SyringePumpUnit] = {
            1: SyringePumpUnit(1, "Seringue 1", "Liquides [q₁]", 0.25, 4.608, "Hamilton Gastight 1 mL"),
            2: SyringePumpUnit(2, "Seringue 2", "Gaz [q₂]", 1.00, 29.200, "Air-Tite Norm-Ject 50 mL")
        }
        # Lancement de l'auto-connexion matérielle au démarrage
        self.auto_connecter_ports_disponibles()

    def auto_connecter_ports_disponibles(self):
        """Scande les ports COM et connecte automatiquement les Legato 110 trouvées."""
        if not SERIAL_DISPONIBLE:
            return
        
        try:
            ports = [p.device for p in serial.tools.list_ports.comports()]
            if not ports:
                return
            
            self.log_msg.emit(f"🔍 Auto-détection des pousse-seringues sur {len(ports)} port(s) COM...")
            pid_courant = 1
            for port_com in ports:
                if pid_courant > 2:
                    break
                # Test d'ouverture rapide pour voir si c'est une Legato
                try:
                    s_test = serial.Serial(port_com, baudrate=115200, timeout=0.1, write_timeout=0.2)
                    time.sleep(0.05)
                    s_test.write(b"\r")
                    time.sleep(0.05)
                    rep = s_test.read_all().decode("ascii", errors="ignore")
                    s_test.close()

                    # Si la pompe répond avec un prompt Legato (: ou < ou >)
                    if any(c in rep for c in (':', '>', '<')):
                        self.log_msg.emit(f"🎯 Legato 110 détectée automatiquement sur {port_com} -> Affectée à Seringue {pid_courant}")
                        self.configurer_pompe(pid_courant, port_com, active=True)
                        pid_courant += 1
                except Exception:
                    continue
        except Exception as e:
            self.log_msg.emit(f"⚠️ Erreur lors de l'auto-connexion des pompes : {e}")

    def configurer_pompe(self, pump_id: int, port: Optional[str], active: bool = True) -> bool:
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p:
                return False

            port_str = str(port).strip().upper() if port else ""

            if not active or not port_str or any(k in port_str for k in ("NONE", "AUCUN", "DÉSACTIVÉ", "DESACTIVE")):
                self._deconnecter_unite(p)
                p.mode_virtuel = False
                self.log_msg.emit(tr("log_pump_disabled", nom=p.nom, role=p.role_fluide))
                self._notifier_etat(p)
                return True

            if any(k in port_str for k in ("VIRTUAL", "VIRTUEL", "SIMULATION", "TEST")):
                self._deconnecter_unite(p)
                p.port = "VIRTUAL"
                p.connecte = True
                p.mode_virtuel = True
                self.log_msg.emit(tr("log_pump_virtual", nom=p.nom, role=p.role_fluide))
                self._notifier_etat(p)
                return True

            p.port = port_str.split()[0]
            p.mode_virtuel = False

            if not SERIAL_DISPONIBLE:
                p.connecte = True
                p.mode_virtuel = True
                self.log_msg.emit(tr("log_pump_no_pyserial", nom=p.nom, port=p.port))
                self._notifier_etat(p)
                return True

            connexion_reussie = False
            for baud in (115200, 9600):
                try:
                    if p.serial_conn and hasattr(p.serial_conn, "is_open") and p.serial_conn.is_open:
                        p.serial_conn.close()

                    p.serial_conn = serial.Serial(
                        p.port,
                        baudrate=baud,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        timeout=0.15,
                        write_timeout=0.4
                    )
                    time.sleep(0.1)
                    self._envoyer_cmd_brute(p, "stop")
                    time.sleep(0.04)

                    rep_ver = self._envoyer_cmd_brute(p, "version")
                    m_sn = re.search(r"Serial number:\s*([A-Za-z0-9]+)", rep_ver)
                    p.numero_serie = m_sn.group(1) if m_sn else "Inconnu"

                    vol_v, vol_u = extraire_volume_et_unite(p.nom_seringue, p.diametre_seringue)
                    self._envoyer_cmd_brute(p, f"svolume {vol_v:g} {vol_u}")
                    time.sleep(0.04)
                    self._envoyer_cmd_brute(p, f"diameter {p.diametre_seringue:.3f}")
                    time.sleep(0.04)
                    self._appliquer_consigne_debit_interne(p)

                    p.connecte = True
                    connexion_reussie = True
                    self.log_msg.emit(f"✅ {p.nom} [{p.role_fluide}] connectée sur {p.port} (S/N: {p.numero_serie})")
                    break
                except Exception:
                    continue

            if not connexion_reussie:
                p.serial_conn = None
                p.connecte = True
                p.mode_virtuel = True
                self.log_msg.emit(tr("log_pump_conn_fail", nom=p.nom, port=p.port, err="Port inaccessible"))

            self._notifier_etat(p)
            return p.connecte

    def identifier_pompe_physique(self, pump_id: int):
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p or not p.connecte or p.mode_virtuel or not p.serial_conn:
                self.log_msg.emit(f"⚠️ {p.nom if p else pump_id} non connectée.")
                return

            self.log_msg.emit(f"💡 Clignotement écran de {p.nom} ({p.port}, S/N: {p.numero_serie})...")
            try:
                for _ in range(2):
                    self._envoyer_cmd_brute(p, "dim 20")
                    time.sleep(0.25)
                    self._envoyer_cmd_brute(p, "dim 100")
                    time.sleep(0.25)
            except Exception:
                pass

    def _envoyer_cmd_brute(self, p: SyringePumpUnit, cmd: str, timeout: float = 0.4) -> str:
        if not p.serial_conn or p.mode_virtuel:
            return ""
        try:
            trame = (cmd.strip() + "\r").encode("ascii")
            p.serial_conn.reset_input_buffer()
            p.serial_conn.write(trame)
            p.serial_conn.flush()

            t0 = time.time()
            reponse = bytearray()
            while (time.time() - t0) < timeout:
                n = p.serial_conn.in_waiting
                if n > 0:
                    reponse.extend(p.serial_conn.read(n))
                    if any(c in reponse for c in (b':', b'>', b'<', b'?')):
                        break
                time.sleep(0.01)

            return reponse.decode("ascii", errors="ignore").strip()
        except Exception as e:
            self.log_msg.emit(tr("log_pump_serial_error", nom=p.nom, err=str(e)))
            return ""

    def _convertir_unite_legato(self, unite: str) -> str:
        u_clean = unite.replace("µ", "u").replace("μ", "u").lower().strip()
        mapping = {
            "ul/min": "ul/min",
            "nl/min": "nl/min",
            "ml/min": "ml/min",
            "ul/h": "ul/hr",
            "ul/hr": "ul/hr",
            "ml/h": "ml/hr",
            "ml/hr": "ml/hr"
        }
        return mapping.get(u_clean, "ul/min")

    def _appliquer_consigne_debit_interne(self, p: SyringePumpUnit):
        if not p.serial_conn or p.mode_virtuel:
            return
        cmd_u = self._convertir_unite_legato(p.unite_debit)
        registre = "wrate" if p.sens == "withdraw" else "irate"
        self._envoyer_cmd_brute(p, f"{registre} {p.debit:g} {cmd_u}")

    def definir_seringue(self, pump_id: int, nom_modele: str, diametre_libre: Optional[float] = None):
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p:
                return

            if nom_modele == OPTION_PERSONNALISEE and diametre_libre is not None:
                p.diametre_seringue = max(0.05, float(diametre_libre))
                p.nom_seringue = f"Custom ({p.diametre_seringue:.3f} mm)"
            else:
                d = get_diametre(nom_modele, defaut=p.diametre_seringue)
                p.diametre_seringue = d if d else p.diametre_seringue
                p.nom_seringue = nom_modele

            p.verrou_watchdog = time.time() + 2.0

            if p.serial_conn and not p.mode_virtuel:
                vol_v, vol_u = extraire_volume_et_unite(p.nom_seringue, p.diametre_seringue)

                self._envoyer_cmd_brute(p, "stop")
                time.sleep(0.05)
                self._envoyer_cmd_brute(p, f"svolume {vol_v:g} {vol_u}")
                time.sleep(0.05)
                self._envoyer_cmd_brute(p, f"diameter {p.diametre_seringue:.3f}")
                time.sleep(0.05)
                self._appliquer_consigne_debit_interne(p)

                self.log_msg.emit(f"🧪 {p.nom} : Seringue configurée -> {p.nom_seringue} (Ø {p.diametre_seringue:.3f} mm, {vol_v:g} {vol_u})")

            self._notifier_etat(p)

    def regler_debit_seul(self, pump_id: int, debit: float, unite: str):
        """Met à jour le débit à chaud si la pompe tourne, ou au repos sinon."""
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p:
                return
            p.debit = max(0.0001, float(debit))
            p.unite_debit = str(unite).strip()
            
            # Application de la consigne
            self._appliquer_consigne_debit_interne(p)
            
            # Si la pompe est en marche, on applique le changement immédiatement sur le moteur
            if p.en_marche and p.serial_conn and not p.mode_virtuel:
                time.sleep(0.02)
                cmd_run = "wrun" if p.sens == "withdraw" else "irun"
                self._envoyer_cmd_brute(p, cmd_run)

            self._notifier_etat(p)

    def changer_sens_seul(self, pump_id: int, sens: str):
        """Met à jour le sens à chaud si la pompe tourne, ou au repos sinon."""
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p:
                return
            p.sens = "withdraw" if any(k in str(sens).lower() for k in ("withdraw", "aspir", "wdr")) else "infuse"
            self._appliquer_consigne_debit_interne(p)
            
            if p.en_marche and p.serial_conn and not p.mode_virtuel:
                time.sleep(0.02)
                cmd_run = "wrun" if p.sens == "withdraw" else "irun"
                self._envoyer_cmd_brute(p, cmd_run)
                
            self._notifier_etat(p)

    def demarrer(self, pump_id: int, debit: Optional[float] = None, unite: Optional[str] = None, sens: Optional[str] = None):
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p or not p.connecte:
                self.log_msg.emit(tr("log_pump_not_connected", nom=p.nom if p else f"Unité {pump_id}"))
                return

            p.verrou_watchdog = 0.0
            if debit is not None:
                p.debit = max(0.0001, float(debit))
            if unite is not None:
                p.unite_debit = str(unite).strip()
            if sens is not None:
                p.sens = "withdraw" if any(k in str(sens).lower() for k in ("withdraw", "aspir", "wdr")) else "infuse"

            p.en_marche = True

            if p.serial_conn and not p.mode_virtuel:
                self._appliquer_consigne_debit_interne(p)
                time.sleep(0.03)
                cmd_run = "wrun" if p.sens == "withdraw" else "irun"
                self._envoyer_cmd_brute(p, cmd_run)

            dir_txt = tr("sens_wdr_long") if p.sens == "withdraw" else tr("sens_inf_long")
            tag_v = f" [{tr('opt_port_virtual').strip('[]')}]" if p.mode_virtuel else ""
            self.log_msg.emit(tr("log_pump_start", nom=p.nom, role=p.role_fluide, 
                                 tag=tag_v, dir=dir_txt, debit=p.debit, unite=p.unite_debit))
            self._notifier_etat(p)

    def arreter(self, pump_id: int):
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p:
                return

            p.en_marche = False
            p.verrou_watchdog = time.time() + 1.2

            if p.serial_conn and not p.mode_virtuel:
                self._envoyer_cmd_brute(p, "stop")

            tag_v = f" [{tr('opt_port_virtual').strip('[]')}]" if p.mode_virtuel else ""
            self.log_msg.emit(tr("log_pump_stop", nom=p.nom, role=p.role_fluide, tag=tag_v))
            self._notifier_etat(p)

    def arreter_tout(self):
        for pid in list(self.pompes.keys()):
            self.arreter(pid)

    def surveiller_statut_moteur(self, pump_id: int):
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p or not p.connecte or p.mode_virtuel or not p.serial_conn:
                return

            if time.time() < p.verrou_watchdog:
                return

            try:
                rep_prompt = self._envoyer_cmd_brute(p, "")
                dernier_caractere = rep_prompt[-1] if rep_prompt else ":"

                etat_avant = p.en_marche
                if dernier_caractere == "<":
                    p.en_marche = True
                    p.sens = "withdraw"
                elif dernier_caractere == ">":
                    p.en_marche = True
                    p.sens = "infuse"
                elif dernier_caractere in (":", "*", "?"):
                    p.en_marche = False

                if etat_avant != p.en_marche:
                    self._notifier_etat(p)
            except Exception:
                pass

    def synchroniser_depuis_ecran(self, pump_id: int):
        with QMutexLocker(self._mutex):
            p = self.pompes.get(pump_id)
            if not p or not p.connecte or p.mode_virtuel or not p.serial_conn:
                return

            try:
                rep_diam = self._envoyer_cmd_brute(p, "diameter")
                m = re.search(r"(\d+(?:\.\d+)?)", rep_diam)
                if m:
                    p.diametre_seringue = float(m.group(1))
                    modele_trouve = None
                    for nom_m, d_val in TABLE_PLATE.items():
                        if abs(d_val - p.diametre_seringue) < 0.05:
                            modele_trouve = nom_m
                            break
                    p.nom_seringue = modele_trouve if modele_trouve else f"Custom ({p.diametre_seringue:.3f} mm)"
                    self.log_msg.emit(f"🔄 Relecture écran {p.nom} : Ø {p.diametre_seringue:.3f} mm ({p.nom_seringue})")
                    self._notifier_etat(p)
            except Exception:
                pass

    def _deconnecter_unite(self, p: SyringePumpUnit):
        if p.serial_conn:
            try:
                self._envoyer_cmd_brute(p, "stop")
                if hasattr(p.serial_conn, "close"):
                    p.serial_conn.close()
            except Exception:
                pass
        p.serial_conn = None
        p.connecte = False
        p.en_marche = False

    def deconnecter_tout(self):
        with QMutexLocker(self._mutex):
            for p in self.pompes.values():
                self._deconnecter_unite(p)
            self.log_msg.emit(tr("log_pump_closed"))

    def _notifier_etat(self, p: SyringePumpUnit):
        self.etat_pompe_modifie.emit(p.pump_id, {
            "connecte": p.connecte,
            "mode_virtuel": p.mode_virtuel,
            "en_marche": p.en_marche,
            "debit": p.debit,
            "unite": p.unite_debit,
            "sens": p.sens,
            "nom": p.nom,
            "diametre": p.diametre_seringue,
            "modele_seringue": getattr(p, "nom_seringue", "Hamilton Gastight 1 mL"),
            "numero_serie": getattr(p, "numero_serie", "Inconnu")
        })