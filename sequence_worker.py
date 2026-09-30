"""
sequence_worker.py - Moteur d'exécution asynchrone pour la plateforme DecLiq (LIPhy).
- Exécution non-bloquante du protocole fluidique multi-étapes.
- Précision temporelle via time.perf_counter().
- Support natif des 4 briques : AV201, AV801, Pousse-seringues (q1/q2) et Pauses.
- Arrêt d'urgence thread-safe et internationalisation complète des logs.
"""
import time
from typing import List, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

from i18n import tr


class SequenceWorker(QThread):
    log_seq = pyqtSignal(str)
    termine = pyqtSignal(bool, str)
    etape_en_cours = pyqtSignal(int)          # Index 0-based (-1 au repos)
    progression = pyqtSignal(int, int)        # (étape_actuelle, total_étapes)
    temps_restant_pause = pyqtSignal(float)   # Secondes restantes sur un palier

    def __init__(self, backend, etapes: List[Dict[str, Any]], backend_pumps=None):
        super().__init__()
        self.backend = backend
        self.backend_pumps = backend_pumps or getattr(backend, "pumps", None)
        self.etapes = etapes
        self._mutex = QMutex()
        self._is_running = True

    def stop(self):
        """Déclenche l'interruption immédiate du protocole."""
        with QMutexLocker(self._mutex):
            self._is_running = False

    def _doit_continuer(self) -> bool:
        """Vérifie l'état d'exécution de manière thread-safe."""
        with QMutexLocker(self._mutex):
            return self._is_running

    def run(self):
        total = len(self.etapes)
        self.log_seq.emit(tr("log_seq_start", total=total))

        for index, etape in enumerate(self.etapes):
            if not self._doit_continuer():
                self._abandonner(index)
                return

            self.etape_en_cours.emit(index)
            self.progression.emit(index + 1, total)
            type_bloc = etape.get("type")

            try:
                # -------------------------------------------------------------
                # 1. ACTIONNEURS AV201 (3-VOIES AMONT 0x05 / AVAL 0x08)
                # -------------------------------------------------------------
                if type_bloc == "AV201":
                    addr = int(etape.get("addr", 0x05))
                    canal = etape.get("canal", 1)
                    action = str(etape.get("action", "1"))

                    if "1" in action:
                        etat = 1
                    elif any(k in action for k in ("STOP", "Fermé", "2")):
                        etat = 2
                    else:
                        etat = 3

                    nom_module = self.backend.ROLES_BANC.get(addr, {}).get("nom", f"Module 0x{addr:02X}")
                    t_start = time.perf_counter()

                    if canal in ("ALL", 0, "Tous (GLOBAL)"):
                        self.log_seq.emit(tr("log_seq_valves_all", i=index+1, total=total, nom=nom_module, etat=etat))
                        self.backend.regler_toutes_vannes(addr, etat)
                    else:
                        canal_int = int(str(canal).replace("Canal", "").strip())
                        self.log_seq.emit(tr("log_seq_valves_single", i=index+1, total=total, 
                                             nom=nom_module, canal=canal_int, action=action, etat=etat))
                        self.backend.regler_vanne_individuelle(addr, canal_int, etat)

                    dt = time.perf_counter() - t_start
                    self.log_seq.emit(tr("log_seq_valve_time", i=index+1, total=total, dt=dt))

                # -------------------------------------------------------------
                # 2. SÉLECTEUR 8-PORTS AV801 (COMMUTATION ROTATIVE 0x09)
                # -------------------------------------------------------------
                elif type_bloc == "AV801":
                    addr = int(etape.get("addr", 0x09))
                    port = int(etape.get("port", 1))
                    cfg_module = self.backend.ROLES_BANC.get(addr, {})
                    canal_sel = cfg_module.get("canal_selecteur", 1)

                    self.log_seq.emit(tr("log_seq_av801_rot", i=index+1, total=total, port=port))
                    t_start = time.perf_counter()
                    self.backend.regler_vanne_8ports(addr, canal_sel, port)
                    dt = time.perf_counter() - t_start
                    self.log_seq.emit(tr("log_seq_av801_time", i=index+1, total=total, port=port, dt=dt))

                # -------------------------------------------------------------
                # 3. POUSSE-SERINGUES (q1 LIQUIDES / q2 GAZ)
                # -------------------------------------------------------------
                elif type_bloc == "Pump":
                    pumps = self.backend_pumps or getattr(self.backend, "pumps", None)
                    if not pumps:
                        self.log_seq.emit(tr("log_seq_pump_skip", i=index+1, total=total))
                    else:
                        pump_id = int(etape.get("pump_id", 1))
                        action = str(etape.get("action", "withdraw")).lower()
                        est_stop = any(k in action for k in ("stop", "arr", "arrêt"))

                        if est_stop:
                            if pump_id == 0:
                                pumps.arreter_tout()
                                self.log_seq.emit(tr("log_seq_pump_stop_all", i=index+1, total=total, 
                                                     default=f"[{index+1}/{total}] ⏹ Arrêt de toutes les seringues"))
                            else:
                                pumps.arreter(pump_id)
                                self.log_seq.emit(tr("log_seq_pump_stop", i=index+1, total=total, id=pump_id))
                        else:
                            debit = float(etape.get("debit", 0.25))
                            unite = str(etape.get("unite", "µL/min"))
                            sens = "infuse" if "infuse" in action else "withdraw"
                            
                            cibles = [1, 2] if pump_id == 0 else [pump_id]
                            for pid in cibles:
                                pumps.demarrer(pid, debit=debit, unite=unite, sens=sens)

                            dir_txt = tr("sens_inf_long") if sens == "infuse" else tr("sens_wdr_long")
                            id_label = "1 & 2" if pump_id == 0 else str(pump_id)
                            self.log_seq.emit(tr("log_seq_pump_run", i=index+1, total=total, 
                                                 id=id_label, dir=dir_txt, debit=debit, unite=unite))

                # -------------------------------------------------------------
                # 4. TEMPORISATION / INCUBATION (DÉCOMPTE ACTIF)
                # -------------------------------------------------------------
                elif type_bloc == "Pause":
                    duree_sec = self._calculer_duree(etape.get("duree"))
                    self.log_seq.emit(tr("log_seq_pause_start", i=index+1, total=total, duree=duree_sec))

                    t_debut = time.perf_counter()
                    dernier_log = t_debut

                    while True:
                        if not self._doit_continuer():
                            self._abandonner(index)
                            return

                        ecoule = time.perf_counter() - t_debut
                        restant = max(0.0, duree_sec - ecoule)
                        self.temps_restant_pause.emit(restant)

                        if ecoule >= duree_sec:
                            break

                        now = time.perf_counter()
                        if duree_sec >= 15.0 and (now - dernier_log) >= 10.0:
                            self.log_seq.emit(tr("log_seq_pause_remain", i=index+1, total=total, restant=restant))
                            dernier_log = now

                        time.sleep(0.05)

                    self.log_seq.emit(tr("log_seq_pause_done", i=index+1, total=total))

            except Exception as e:
                self.etape_en_cours.emit(-1)
                self.log_seq.emit(tr("log_seq_err_block", step=index+1, err=str(e)))
                self.termine.emit(False, str(e))
                return

        self.etape_en_cours.emit(-1)
        self.progression.emit(total, total)
        self.log_seq.emit(tr("log_seq_success"))
        self.termine.emit(True, tr("status_success"))

    def _calculer_duree(self, raw_duree: Any) -> float:
        """Convertit les durées en secondes selon l'unité sélectionnée."""
        if isinstance(raw_duree, dict):
            val = float(raw_duree.get("valeur", 1.0))
            unite = str(raw_duree.get("unite", "s")).lower()
            if "min" in unite:
                return val * 60.0
            if "h" in unite:
                return val * 3600.0
            return val
        try:
            return float(raw_duree)
        except (TypeError, ValueError):
            return 1.0

    def _abandonner(self, index_interrompu: int):
        """Sécurise l'arrêt du protocole en cas d'interruption opérateur."""
        self.etape_en_cours.emit(-1)
        self.log_seq.emit(tr("log_seq_abort", step=index_interrompu+1))
        pumps = self.backend_pumps or getattr(self.backend, "pumps", None)
        if pumps:
            pumps.arreter_tout()
        self.termine.emit(False, tr("status_user_abort"))