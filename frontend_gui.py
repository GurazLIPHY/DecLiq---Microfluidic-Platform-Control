"""
frontend_gui.py - Interface principale de la plateforme DecLiq (LIPhy).
- Tableau de bord opérationnel pour le banc microfluidique ANR DecLiq.
- Pilotage vannes LabSmith (EIB200) et pousse-seringues KD Scientific Legato 110.
- Synchronisation manuelle / automatique des seringues et débits.
- Watchdog non-intrusif préservant l'affichage tactile de la pompe.
"""
import os
import sys
import time
import warnings
from datetime import datetime

# Neutralisation du warning PyQt6-sip sur les sous-classes dérivées
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*sipPyTypeDict.*")


def ressource_path(nom_fichier: str) -> str:
    """Renvoie le chemin absolu du fichier, compatible environnement dev et PyInstaller."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, nom_fichier)


from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, 
    QHBoxLayout, QGridLayout, QWidget, QLabel, QGroupBox, 
    QTextEdit, QScrollArea, QTabWidget, QSplitter, 
    QFileDialog, QStackedWidget, QRadioButton, 
    QButtonGroup, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, QSettings, QTimer
from PyQt6.QtGui import QIcon

from backend_labsmith import BackendLabSmith
from backend_pumps import BackendPumps
from synoptic_widget import SynopticWidget
from sequence_panel import SequencePanel
from ui_components import DecLiqDoubleSpinBox, DecLiqComboBox
from theme_manager import get_stylesheet
from i18n import tr, set_langue
from syringe_database import get_tous_les_modeles, get_diametre, OPTION_PERSONNALISEE

try:
    import serial.tools.list_ports
    SERIAL_LIST_OK = True
except ImportError:
    SERIAL_LIST_OK = False


def scanner_ports_systeme() -> list[str]:
    """Scanne et formate la liste des ports COM disponibles sur la machine."""
    if not SERIAL_LIST_OK:
        return [f"COM{i}" for i in range(1, 9)]
    try:
        ports = serial.tools.list_ports.comports()
        if not ports:
            return [f"COM{i}" for i in range(1, 9)]
        return [f"{p.device} ({p.description.split('(')[0].strip()})" for p in ports]
    except Exception:
        return [f"COM{i}" for i in range(1, 9)]


class DecLiqFrontEnd(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DecLiq - Microfluidic Platform Control (LIPhy)")
        self.setWindowIcon(QIcon(ressource_path("icon.svg")))
        self.setMinimumSize(980, 680)

        self.settings = QSettings("LIPhy", "DecLiq_App")
        self.mode_sombre = True
        self.facteur_zoom = 1.0
        self.taille_police = 10

        self.boutons_manuel_av201 = {}
        self.labels_etat_av201 = {}
        self.boutons_manuel_av801 = {}
        self.labels_etat_av801 = {}
        self.widgets_pompes = {}
        self.widgets_cfg_seringues = {}

        self.pompes_en_marche = set()
        self.pulse_phase_pompes = 0
        self.timer_pulse_pompes = QTimer(self)
        self.timer_pulse_pompes.setInterval(80)
        self.timer_pulse_pompes.timeout.connect(self._animer_pulse_pompes)

        # 1. Thread Vannes LabSmith (EIB200)
        self.thread_labsmith = QThread()
        self.backend = BackendLabSmith(3)
        self.backend.moveToThread(self.thread_labsmith)
        self.thread_labsmith.start()

        self.backend.connexion_ok.connect(self.maj_statut_connexion_labsmith)
        self.backend.scan_infos_recu.connect(self.construire_interface_dynamique)
        self.backend.log_msg.connect(self.ajouter_log)
        self.backend.etat_vanne_modifie.connect(lambda *_: self.actualiser_vue_simple())
        self.backend.etat_selecteur_modifie.connect(lambda *_: self.actualiser_vue_simple())

        # 2. Thread Pousse-seringues
        self.thread_pumps = QThread()
        self.backend_pumps = BackendPumps()
        self.backend_pumps.moveToThread(self.thread_pumps)
        self.thread_pumps.start()

        self.backend_pumps.log_msg.connect(self.ajouter_log)
        self.backend.pumps = self.backend_pumps

        self.init_ui()
        self.charger_parametres()

        self._appliquer_port_eib()
        self._appliquer_port_pompe(1)
        self._appliquer_port_pompe(2)

        # Lancement de l'auto-détection des pompes connectées
        self.auto_detecter_et_connecter_pompes()

        # 3. Watchdog de surveillance des liaisons matérielles (toutes les 1500 ms)
        self.timer_watchdog = QTimer(self)
        self.timer_watchdog.setInterval(1500)
        self.timer_watchdog.timeout.connect(self._surveiller_connexions_materielles)
        self.timer_watchdog.start()

    def init_ui(self):
        main_layout = QHBoxLayout()
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(10)

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.document().setMaximumBlockCount(1500)

        self.tabs = QTabWidget()

        # Onglet 1 : Contrôle Manuel
        self.tab_manuel = QWidget()
        lay_man = QVBoxLayout(self.tab_manuel)
        self.pile_vues_manuel = QStackedWidget()

        self.scroll_manuel_classique = QScrollArea()
        self.scroll_manuel_classique.setWidgetResizable(True)
        self.widget_manuel_boutons = QWidget()
        self.layout_manuel_vannes = QVBoxLayout(self.widget_manuel_boutons)
        self.layout_manuel_vannes.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.layout_manuel_vannes.addWidget(self._creer_panneau_pompes_manuel())

        self.widget_modules_labsmith = QWidget()
        self.layout_modules_labsmith = QVBoxLayout(self.widget_modules_labsmith)
        self.layout_modules_labsmith.setContentsMargins(0, 0, 0, 0)
        self.layout_manuel_vannes.addWidget(self.widget_modules_labsmith)

        self.scroll_manuel_classique.setWidget(self.widget_manuel_boutons)
        self.pile_vues_manuel.addWidget(self.scroll_manuel_classique)

        self.vue_synoptique = SynopticWidget(self.backend)
        self.backend_pumps.etat_pompe_modifie.connect(self.vue_synoptique.maj_etat_pompe)
        self.pile_vues_manuel.addWidget(self.vue_synoptique)
        lay_man.addWidget(self.pile_vues_manuel)

        # Onglet 2 : Séquenceur
        self.panel_sequenceur = SequencePanel(self.backend)
        self.panel_sequenceur.log_demande.connect(self.ajouter_log)
        self.panel_sequenceur.effacer_log_demande.connect(self.console_log.clear)
        self.panel_sequenceur.sequence_terminee.connect(self.actualiser_tout)

        # Onglet 3 : Options & Configuration
        self.scroll_options = QScrollArea()
        self.scroll_options.setWidgetResizable(True)
        self.scroll_options.setStyleSheet("QScrollArea { border: none; }")
        self.tab_options = QWidget()
        self.init_options_ui()
        self.scroll_options.setWidget(self.tab_options)

        self.tabs.addTab(self.tab_manuel, tr("tab_manuel"))
        self.tabs.addTab(self.panel_sequenceur, tr("tab_sequence"))
        self.tabs.addTab(self.scroll_options, tr("tab_options"))
        self.splitter.addWidget(self.tabs)

        # Volet Droit : État matériel & Console
        self.widget_droite = QWidget()
        lay_d = QVBoxLayout(self.widget_droite)
        lay_d.setContentsMargins(0, 0, 0, 0)

        self.grp_dispositifs = QGroupBox(tr("grp_devices"))
        lay_disp = QGridLayout(self.grp_dispositifs)
        lay_disp.setContentsMargins(12, 10, 12, 10)
        lay_disp.setHorizontalSpacing(12)
        lay_disp.setVerticalSpacing(8)

        self._statut_eib_ok = None
        self._statut_pompes = {1: {}, 2: {}}

        # Colonne 0 : Titres d'appareils alignés à droite pour repère vertical des ':'
        self.lbl_titre_eib = QLabel(f"<b>{tr('dev_valves_eib')}</b>")
        self.lbl_titre_p1 = QLabel(f"<b>{tr('dev_pump_1')}</b>")
        self.lbl_titre_p2 = QLabel(f"<b>{tr('dev_pump_2')}</b>")
        for lbl in (self.lbl_titre_eib, self.lbl_titre_p1, self.lbl_titre_p2):
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        lay_disp.addWidget(self.lbl_titre_eib, 0, 0)
        lay_disp.addWidget(self.lbl_titre_p1, 1, 0)
        lay_disp.addWidget(self.lbl_titre_p2, 2, 0)

        # Colonne 1 : Badges d'état calibrés (largeur fixe 95 px, sans caractère tronqué)
        self.badge_eib = QLabel(tr("badge_connecting", default="CONNEXION"))
        self.badge_p1 = QLabel(tr("badge_disabled", default="DÉSACTIVÉ"))
        self.badge_p2 = QLabel(tr("badge_disabled", default="DÉSACTIVÉ"))
        for b in (self.badge_eib, self.badge_p1, self.badge_p2):
            b.setFixedWidth(95)
            b.setFixedHeight(22)
            b.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._styliser_badge(b, "neutre", b.text())

        lay_disp.addWidget(self.badge_eib, 0, 1)
        lay_disp.addWidget(self.badge_p1, 1, 1)
        lay_disp.addWidget(self.badge_p2, 2, 1)

        # Colonne 2 : Détails techniques (Port COM, S/N)
        self.lbl_detail_eib = QLabel("COM3")
        self.lbl_detail_p1 = QLabel("—")
        self.lbl_detail_p2 = QLabel("—")
        for d in (self.lbl_detail_eib, self.lbl_detail_p1, self.lbl_detail_p2):
            d.setStyleSheet("color: #cbd5e1; font-family: 'Consolas', 'Segoe UI', monospace; font-size: 9pt;")
            d.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        lay_disp.addWidget(self.lbl_detail_eib, 0, 2)
        lay_disp.addWidget(self.lbl_detail_p1, 1, 2)
        lay_disp.addWidget(self.lbl_detail_p2, 2, 2)

        lay_disp.setColumnStretch(0, 0)
        lay_disp.setColumnStretch(1, 0)
        lay_disp.setColumnStretch(2, 1)

        self.backend_pumps.etat_pompe_modifie.connect(self.maj_statut_pompe)
        lay_d.addWidget(self.grp_dispositifs)

        lay_h = QHBoxLayout()
        self.lbl_logs_header = QLabel(f"<b>{tr('console_title')}</b>")
        self.btn_clear = QPushButton(tr("btn_clear"))
        self.btn_clear.clicked.connect(self.console_log.clear)
        self.btn_export = QPushButton(tr("btn_export"))
        self.btn_export.clicked.connect(self.exporter_logs)
        lay_h.addWidget(self.lbl_logs_header)
        lay_h.addStretch()
        lay_h.addWidget(self.btn_clear)
        lay_h.addWidget(self.btn_export)
        lay_d.addLayout(lay_h)

        lay_d.addWidget(self.console_log)
        self.splitter.addWidget(self.widget_droite)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([680, 420])

        main_layout.addWidget(self.splitter)
        wc = QWidget()
        wc.setLayout(main_layout)
        self.setCentralWidget(wc)

    def _styliser_badge(self, label: QLabel, mode: str, texte: str):
        """Applique un badge plat contrasté sans symbole susceptible de débordement."""
        couleurs = {
            "vert": ("rgba(16, 185, 129, 0.15)", "#10b981", "#10b981"),
            "ambre": ("rgba(245, 158, 11, 0.15)", "#f59e0b", "#f59e0b"),
            "rouge": ("rgba(239, 68, 68, 0.15)", "#ef4444", "#ef4444"),
            "neutre": ("rgba(141, 153, 174, 0.10)", "#8d99ae", "#334155"),
        }
        bg, fg, border = couleurs.get(mode, couleurs["neutre"])
        label.setText(texte)
        label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                font-size: 8pt;
                font-weight: bold;
                padding: 1px 4px;
            }}
        """)

    # =========================================================================
    # BANDEAU POUSSE-SERINGUES (COMMANDE MANUELLE)
    # =========================================================================
    def _creer_panneau_pompes_manuel(self) -> QGroupBox:
        self.grp_pompes_manuel = QGroupBox(tr("grp_pumps_manual"))
        lay = QVBoxLayout(self.grp_pompes_manuel)
        lay.setSpacing(6)
        lay.setContentsMargins(8, 10, 8, 8)

        for pid, nom, col, d_defaut in [
            (1, "Seringue 1 [q₁ Liquides]", "#00b4d8", 0.25),
            (2, "Seringue 2 [q₂ Gaz]", "#10b981", 1.00)
        ]:
            ligne = QWidget()
            l_ligne = QHBoxLayout(ligne)
            l_ligne.setContentsMargins(6, 4, 6, 4)
            l_ligne.setSpacing(8)
            ligne.setStyleSheet(f"""
                QWidget {{
                    background-color: rgba(120, 130, 150, 0.05);
                    border: 1px solid rgba(120, 130, 150, 0.2);
                    border-left: 4px solid {col};
                    border-radius: 4px;
                }}
            """)

            lbl_titre = QLabel(f"<b>{nom}</b>")
            lbl_titre.setMinimumWidth(160)
            lbl_titre.setStyleSheet(f"color: {col}; border: none;")

            sp_debit = DecLiqDoubleSpinBox()
            sp_debit.setRange(0.001, 1000.0)
            sp_debit.setValue(d_defaut)
            sp_debit.setDecimals(3)
            sp_debit.setSingleStep(0.05)
            sp_debit.setMinimumWidth(85)

            cb_unite = DecLiqComboBox()
            cb_unite.addItems(["µL/min", "mL/min", "nL/min", "µL/h", "mL/h"])
            cb_unite.setCurrentIndex(0)

            cb_sens = DecLiqComboBox()
            cb_sens.addItems(["Aspiration (withdraw)", "Infusion"])

            btn_toggle = QPushButton(tr("btn_launch"))
            btn_toggle.setToolTip(tr("tip_pump_toggle"))
            btn_toggle.setMinimumWidth(100)

            sp_debit.valueChanged.connect(lambda val, p=pid, u=cb_unite: self.backend_pumps.regler_debit_seul(p, val, u.currentText()))
            cb_unite.currentIndexChanged.connect(lambda idx, sp=sp_debit, c=cb_unite, p=pid: (
                self._adapter_plage_debit(sp, c),
                self.backend_pumps.regler_debit_seul(p, sp.value(), c.currentText())
            ))
            cb_sens.currentIndexChanged.connect(lambda idx, p=pid: self.backend_pumps.changer_sens_seul(
                p, "withdraw" if idx == 0 else "infuse"
            ))

            btn_toggle.clicked.connect(lambda chk, p=pid: self._action_toggle_pompe(p))

            l_ligne.addWidget(lbl_titre)
            l_ligne.addWidget(sp_debit)
            l_ligne.addWidget(cb_unite)
            l_ligne.addWidget(cb_sens)
            l_ligne.addWidget(btn_toggle)

            self.widgets_pompes[pid] = {
                "lbl_titre": lbl_titre,
                "debit": sp_debit,
                "unite": cb_unite,
                "sens": cb_sens,
                "btn_toggle": btn_toggle
            }
            lay.addWidget(ligne)

        return self.grp_pompes_manuel

    def auto_detecter_et_connecter_pompes(self):
        """Scanne les ports COM, affecte les pompes physiques trouvées et déconnecte les autres."""
        if not SERIAL_LIST_OK:
            return

        try:
            ports = serial.tools.list_ports.comports()
            if not ports:
                return

            ports_candidats = []
            for p in ports:
                dev = p.device
                if self.backend.connected and f"COM{self.backend.com_index}".upper() == dev.upper():
                    continue
                try:
                    s = serial.Serial(dev, baudrate=115200, timeout=0.1, write_timeout=0.2)
                    time.sleep(0.05)
                    s.write(b"\r")
                    time.sleep(0.05)
                    rep = s.read_all().decode("ascii", errors="ignore")
                    s.close()
                    if any(c in rep for c in (':', '>', '<')):
                        ports_candidats.append(dev)
                except Exception:
                    continue

            # Seringue 1 : Liaison si détectée
            if len(ports_candidats) >= 1:
                idx = self.cb_com_p1.findText(ports_candidats[0], Qt.MatchFlag.MatchStartsWith)
                if idx >= 0:
                    self.cb_com_p1.setCurrentIndex(idx)
                    self.ajouter_log(f"🎯 Auto-bind S1 : {ports_candidats[0]}")
            else:
                idx_des = self.cb_com_p1.findText("[Désactivé", Qt.MatchFlag.MatchStartsWith)
                if idx_des >= 0:
                    self.cb_com_p1.setCurrentIndex(idx_des)

            # Seringue 2 : Liaison si second port disponible, sinon désactivation
            if len(ports_candidats) >= 2:
                idx = self.cb_com_p2.findText(ports_candidats[1], Qt.MatchFlag.MatchStartsWith)
                if idx >= 0:
                    self.cb_com_p2.setCurrentIndex(idx)
                    self.ajouter_log(f"🎯 Auto-bind S2 : {ports_candidats[1]}")
            else:
                idx_des = self.cb_com_p2.findText("[Désactivé", Qt.MatchFlag.MatchStartsWith)
                if idx_des >= 0:
                    self.cb_com_p2.setCurrentIndex(idx_des)

            # Relecture différée du diamètre sur les pompes actives
            QTimer.singleShot(400, self._synchroniser_manuellement_pompes)

        except Exception as e:
            self.ajouter_log(f"⚠️ Erreur auto-détection frontend : {e}")

    def _adapter_plage_debit(self, spin: DecLiqDoubleSpinBox, combo: DecLiqComboBox):
        unite = combo.currentText()
        val = spin.value()

        if unite == "µL/min":
            spin.setRange(0.001, 1000.0)
            spin.setDecimals(3)
            spin.setSingleStep(0.05)
        elif unite == "mL/min":
            spin.setRange(0.001, 1000.0)
            spin.setDecimals(3)
            spin.setSingleStep(0.1)
        elif unite == "nL/min":
            spin.setRange(0.1, 50000.0)
            spin.setDecimals(1)
            spin.setSingleStep(10.0)
            spin.setValue(val * 1000.0 if val < 50.0 else val)
        elif unite == "µL/h":
            spin.setRange(0.1, 20000.0)
            spin.setDecimals(2)
            spin.setSingleStep(1.0)
            spin.setValue(val * 60.0 if val < 200.0 else val)
        elif unite == "mL/h":
            spin.setRange(0.001, 60.0)
            spin.setDecimals(4)
            spin.setSingleStep(0.01)
            spin.setValue(val / 1000.0 if val > 10.0 else val)

    def _action_toggle_pompe(self, pid: int):
        w = self.widgets_pompes.get(pid)
        if not w:
            return

        p = self.backend_pumps.pompes.get(pid)
        if not p or (not p.connecte and not getattr(p, "mode_virtuel", False)):
            self.ajouter_log(f"⚠️ {p.nom if p else pid} non connectée.")
            return

        if p.en_marche or pid in self.pompes_en_marche:
            self.backend_pumps.arreter(pid)
            self.pompes_en_marche.discard(pid)
            w["btn_toggle"].setText(tr("btn_launch"))
            w["btn_toggle"].setStyleSheet("")
            if not self.pompes_en_marche and self.timer_pulse_pompes.isActive():
                self.timer_pulse_pompes.stop()
        else:
            debit = w["debit"].value()
            unite = w["unite"].currentText()
            sens = "withdraw" if w["sens"].currentIndex() == 0 else "infuse"
            self.backend_pumps.demarrer(pid, debit=debit, unite=unite, sens=sens)
            self.pompes_en_marche.add(pid)
            w["btn_toggle"].setText(tr("btn_stop_pump"))
            if not self.timer_pulse_pompes.isActive():
                self.timer_pulse_pompes.start()

    def _animer_pulse_pompes(self):
        self.pulse_phase_pompes = (self.pulse_phase_pompes + 1) % 20
        alpha = int(130 + 125 * abs(10 - self.pulse_phase_pompes) / 10.0)

        for pid in list(self.pompes_en_marche):
            w = self.widgets_pompes.get(pid)
            if not w:
                continue
            col_hex = "#00f5d4" if pid == 1 else "#10b981"
            bg_hex = "#005f73" if pid == 1 else "#064e3b"
            r, g, b = int(col_hex[1:3], 16), int(col_hex[3:5], 16), int(col_hex[5:7], 16)

            w["btn_toggle"].setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_hex};
                    border: 2px solid rgba({r}, {g}, {b}, {alpha / 255.0:.2f});
                    color: #ffffff;
                    font-weight: bold;
                    padding: 5px 12px;
                    border-radius: 4px;
                }}
            """)

    # =========================================================================
    # OPTIONS & LIAISONS SÉRIE
    # =========================================================================
    def init_options_ui(self):
        lay = QVBoxLayout(self.tab_options)
        lay.setSpacing(10)
        lay.setContentsMargins(10, 10, 10, 10)

        # 1. Mode d'affichage
        self.grp_v = QGroupBox(tr("grp_view"))
        lay_v = QVBoxLayout(self.grp_v)
        self.rad_classique = QRadioButton(tr("view_simple"))
        self.rad_graphique = QRadioButton(tr("view_synoptic"))
        self.grp_btn_vue = QButtonGroup(self)
        self.grp_btn_vue.addButton(self.rad_classique, 0)
        self.grp_btn_vue.addButton(self.rad_graphique, 1)
        self.grp_btn_vue.idClicked.connect(self.changer_mode_vue)
        lay_v.addWidget(self.rad_classique)
        lay_v.addWidget(self.rad_graphique)
        lay.addWidget(self.grp_v)

        # 2. Configuration matérielle et liaisons série
        self.grp_com = QGroupBox(tr("grp_hardware_cfg"))
        lay_com = QGridLayout(self.grp_com)
        lay_com.setVerticalSpacing(8)
        lay_com.setHorizontalSpacing(10)

        self.btn_rescan = QPushButton(tr("btn_scan_com"))
        self.btn_rescan.clicked.connect(self.recharger_ports_com)
        lay_com.addWidget(self.btn_rescan, 0, 0, 1, 2)

        # Vannes LabSmith (EIB200)
        self.lbl_cfg_eib = QLabel(f"<b>{tr('dev_valves_eib')}</b>")
        lay_com.addWidget(self.lbl_cfg_eib, 1, 0)
        self.cb_com_eib = DecLiqComboBox()
        self.cb_com_eib.currentIndexChanged.connect(lambda idx: self._appliquer_port_eib())
        lay_com.addWidget(self.cb_com_eib, 1, 1)

        # Seringue 1 [q1 Liquides]
        self.lbl_cfg_p1 = QLabel(f"<b>{tr('pump1_full_name')} :</b>")
        lay_com.addWidget(self.lbl_cfg_p1, 2, 0)
        self.cb_com_p1 = DecLiqComboBox()
        self.cb_com_p1.currentIndexChanged.connect(lambda idx: self._appliquer_port_pompe(1))
        self.btn_id_p1 = QPushButton(f"{tr('btn_flash_screen')} S1")
        self.btn_id_p1.clicked.connect(lambda: self.backend_pumps.identifier_pompe_physique(1))

        lay_p1 = QHBoxLayout()
        lay_p1.setContentsMargins(0, 0, 0, 0)
        lay_p1.setSpacing(8)
        lay_p1.addWidget(self.cb_com_p1, 1)
        lay_p1.addWidget(self.btn_id_p1, 0)
        lay_com.addLayout(lay_p1, 2, 1)

        # Seringue 2 [q2 Gaz]
        self.lbl_cfg_p2 = QLabel(f"<b>{tr('pump2_full_name')} :</b>")
        lay_com.addWidget(self.lbl_cfg_p2, 3, 0)
        self.cb_com_p2 = DecLiqComboBox()
        self.cb_com_p2.currentIndexChanged.connect(lambda idx: self._appliquer_port_pompe(2))
        self.btn_id_p2 = QPushButton(f"{tr('btn_flash_screen')} S2")
        self.btn_id_p2.clicked.connect(lambda: self.backend_pumps.identifier_pompe_physique(2))

        lay_p2 = QHBoxLayout()
        lay_p2.setContentsMargins(0, 0, 0, 0)
        lay_p2.setSpacing(8)
        lay_p2.addWidget(self.cb_com_p2, 1)
        lay_p2.addWidget(self.btn_id_p2, 0)
        lay_com.addLayout(lay_p2, 3, 1)

        lay_com.setColumnStretch(0, 0)
        lay_com.setColumnStretch(1, 1)
        lay.addWidget(self.grp_com)

        # 3. Base seringues et diamètres
        self.grp_seringues_cfg = QGroupBox(tr("grp_syringe_wp1"))
        lay_s_cfg = QGridLayout(self.grp_seringues_cfg)
        lay_s_cfg.setVerticalSpacing(8)
        lay_s_cfg.setHorizontalSpacing(10)
        lay_s_cfg.setColumnStretch(0, 0)
        lay_s_cfg.setColumnStretch(1, 1)
        lay_s_cfg.setColumnStretch(2, 0)

        modeles_dispos = get_tous_les_modeles()

        for row, (pid, nom_label, defaut_modele) in enumerate([
            (1, "Seringue 1 [q₁ Liquides] :", "Hamilton Gastight 1 mL"),
            (2, "Seringue 2 [q₂ Gaz] :", "Air-Tite Norm-Ject 50 mL")
        ]):
            lbl = QLabel(f"<b>{nom_label}</b>")
            cb_mod = DecLiqComboBox()
            cb_mod.addItems(modeles_dispos)

            sp_d = DecLiqDoubleSpinBox()
            sp_d.setRange(0.05, 60.0)
            sp_d.setDecimals(3)
            sp_d.setSingleStep(0.05)
            sp_d.setSuffix(" mm")
            sp_d.setMinimumWidth(155)

            idx_def = cb_mod.findText(defaut_modele)
            if idx_def >= 0:
                cb_mod.setCurrentIndex(idx_def)
            diam_init = get_diametre(defaut_modele, 4.608)
            sp_d.setValue(diam_init if diam_init else 4.608)
            sp_d.setEnabled(False)

            cb_mod.currentIndexChanged.connect(lambda idx, p=pid, cb=cb_mod, sp=sp_d: self._on_modele_seringue_change(p, cb, sp))
            sp_d.valueChanged.connect(lambda val, p=pid, cb=cb_mod: self._on_diametre_custom_change(p, cb, val))

            lay_s_cfg.addWidget(lbl, row, 0)
            lay_s_cfg.addWidget(cb_mod, row, 1)
            lay_s_cfg.addWidget(sp_d, row, 2)

            self.widgets_cfg_seringues[pid] = {
                "lbl": lbl,
                "cb": cb_mod,
                "spin": sp_d
            }

        self.btn_lire_pompes = QPushButton(tr("btn_align_gui"))
        self.btn_lire_pompes.clicked.connect(self._synchroniser_manuellement_pompes)
        lay_s_cfg.addWidget(self.btn_lire_pompes, 2, 0, 1, 3)

        lay.addWidget(self.grp_seringues_cfg)
        self.recharger_ports_com()

        # 4. Langue de l'interface
        self.grp_lang = QGroupBox(tr("grp_lang"))
        lay_lang = QHBoxLayout(self.grp_lang)
        self.rad_fr = QRadioButton(tr("lang_fr"))
        self.rad_en = QRadioButton(tr("lang_en"))
        self.grp_btn_lang = QButtonGroup(self)
        self.grp_btn_lang.addButton(self.rad_fr, 0)
        self.grp_btn_lang.addButton(self.rad_en, 1)
        self.grp_btn_lang.idClicked.connect(lambda idx: self.changer_langue("fr" if idx == 0 else "en"))
        lay_lang.addWidget(self.rad_fr)
        lay_lang.addWidget(self.rad_en)
        lay_lang.addStretch()
        lay.addWidget(self.grp_lang)

        # 5. Thème graphique et échelle
        self.grp_t = QGroupBox(tr("grp_theme"))
        lay_t = QHBoxLayout(self.grp_t)
        self.rad_dark = QRadioButton(tr("theme_dark"))
        self.rad_light = QRadioButton(tr("theme_light"))
        self.grp_theme = QButtonGroup(self)
        self.grp_theme.addButton(self.rad_dark, 1)
        self.grp_theme.addButton(self.rad_light, 0)
        self.grp_theme.idClicked.connect(lambda idx: self.appliquer_theme(idx == 1))
        lay_t.addWidget(self.rad_dark)
        lay_t.addWidget(self.rad_light)
        lay_t.addStretch()
        lay.addWidget(self.grp_t)

        self.grp_z = QGroupBox(tr("grp_scale"))
        lay_z = QHBoxLayout(self.grp_z)
        self.lbl_scale = QLabel(tr("scale_lbl"))
        self.cb_zoom = DecLiqComboBox()
        self.cb_zoom.addItems(["80 % (Compact)", "100 % (Standard)", "120 % (Confort)", "140 % (Grand écran)"])
        self.cb_zoom.currentIndexChanged.connect(self.changer_taille_interface)
        lay_z.addWidget(self.lbl_scale)
        lay_z.addWidget(self.cb_zoom)
        lay_z.addStretch()
        lay.addWidget(self.grp_z)

        # 6. Séquenceur et performances
        self.grp_a = QGroupBox(tr("grp_anim"))
        lay_a = QVBoxLayout(self.grp_a)
        self.chk_anim = QCheckBox(tr("chk_anim"))
        self.chk_anim.toggled.connect(self.changer_animation)
        lay_a.addWidget(self.chk_anim)
        lay.addWidget(self.grp_a)

        self.grp_s = QGroupBox(tr("grp_seq_opt"))
        lay_s = QVBoxLayout(self.grp_s)
        self.chk_clr = QCheckBox(tr("chk_auto_clear"))
        self.chk_clr.toggled.connect(self._toggle_auto_clear)
        lay_s.addWidget(self.chk_clr)
        lay.addWidget(self.grp_s)

        lay.addStretch()

    def _synchroniser_manuellement_pompes(self):
        for pid in (1, 2):
            self.backend_pumps.synchroniser_depuis_ecran(pid)

    def _on_modele_seringue_change(self, pid: int, cb: DecLiqComboBox, spin: DecLiqDoubleSpinBox):
        modele = cb.currentText()
        if modele == OPTION_PERSONNALISEE:
            spin.setEnabled(True)
            self.backend_pumps.definir_seringue(pid, modele, diametre_libre=spin.value())
        else:
            spin.setEnabled(False)
            diam = get_diametre(modele)
            if diam:
                spin.blockSignals(True)
                spin.setValue(diam)
                spin.blockSignals(False)
            self.backend_pumps.definir_seringue(pid, modele)

        self.settings.setValue(f"syringe_model_p{pid}", modele)
        self.settings.setValue(f"syringe_diam_p{pid}", spin.value())

    def _on_diametre_custom_change(self, pid: int, cb: DecLiqComboBox, val: float):
        if cb.currentText() == OPTION_PERSONNALISEE:
            self.backend_pumps.definir_seringue(pid, OPTION_PERSONNALISEE, diametre_libre=val)
            self.settings.setValue(f"syringe_diam_p{pid}", val)

    def recharger_ports_com(self):
        ports_detectes = scanner_ports_systeme()

        for cb, nom_defaut in [
            (self.cb_com_eib, "COM3"),
            (self.cb_com_p1, "[Désactivé / Aucun]"),
            (self.cb_com_p2, "[Désactivé / Aucun]")
        ]:
            cb.blockSignals(True)
            anc_val = cb.currentText()
            cb.clear()
            cb.addItem("[Désactivé / Aucun]")
            cb.addItem("[Virtuel / Simulation]")
            for p in ports_detectes:
                cb.addItem(p)

            idx = cb.findText(anc_val)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            else:
                idx_def = cb.findText(nom_defaut, Qt.MatchFlag.MatchStartsWith)
                cb.setCurrentIndex(idx_def if idx_def >= 0 else 0)
            cb.blockSignals(False)

        self.ajouter_log(f"🔍 Scan des ports : {len(ports_detectes)} port(s) identifié(s).")

    def _appliquer_port_eib(self, *args):
        choix = self.cb_com_eib.currentText().strip()
        if not choix or "[Désactivé" in choix:
            self.backend.deconnecter()
            self._styliser_badge(self.badge_eib, "neutre", tr("badge_disabled"))
            self.lbl_detail_eib.setText("—")
        elif "[Virtuel" in choix or "Simulation" in choix:
            self.backend.mode_simulation = True
            self.backend.connected = True
            self.backend.analyser_materiel()
            self.maj_statut_connexion_labsmith(True)
            self.ajouter_log("🧪 Vannes EIB200 configurées en Mode Virtuel (Simulation).")
        else:
            port_brut = choix.split()[0]
            self.backend.connecter(port_brut)

    def _appliquer_port_pompe(self, pid: int, *args):
        cb = self.cb_com_p1 if pid == 1 else self.cb_com_p2
        choix = cb.currentText().strip()
        if not choix or "[Désactivé" in choix or "Aucun" in choix:
            self.backend_pumps.configurer_pompe(pid, None, active=False)
            self.maj_statut_pompe(pid, {"connecte": False, "virtuel": False, "port": "", "sn": ""})
        elif "[Virtuel" in choix or "Simulation" in choix:
            self.backend_pumps.configurer_pompe(pid, "VIRTUAL", active=True)
            self.maj_statut_pompe(pid, {"connecte": True, "virtuel": True, "port": "", "sn": ""})
        else:
            port_brut = choix.split()[0]
            self.maj_statut_pompe(pid, {"connecte": False, "virtuel": False, "port": port_brut, "sn": ""})
            self.backend_pumps.configurer_pompe(pid, port_brut, active=True)

    # =========================================================================
    # SURVEILLANCE WATCHDOG
    # =========================================================================
    def _surveiller_connexions_materielles(self):
        for pid in (1, 2):
            self.backend_pumps.surveiller_statut_moteur(pid)

        if not SERIAL_LIST_OK:
            return

        try:
            ports_info = serial.tools.list_ports.comports()
            noms_ports_actifs = {p.device.upper().strip() for p in ports_info if p.device}

            if self.backend.connected and not self.backend.mode_simulation:
                port_eib_nom = f"COM{self.backend.com_index}".upper()
                if port_eib_nom not in noms_ports_actifs:
                    self.backend.connected = False
                    self.backend.connexion_ok.emit(False)
                    self.ajouter_log(f"⚠️ Câble débranché : Contrôleur EIB200 ({port_eib_nom}) déconnecté !")

            for pid in (1, 2):
                p = self.backend_pumps.pompes.get(pid)
                if p and p.connecte and not p.mode_virtuel and p.port:
                    if p.port.upper().strip() not in noms_ports_actifs:
                        self.backend_pumps.configurer_pompe(pid, None, active=False)
                        self.ajouter_log(f"⚠️ Câble débranché : {p.nom} ({p.port}) déconnectée !")
        except Exception:
            pass

    def maj_statut_connexion_labsmith(self, ok: bool):
        self._statut_eib_ok = ok
        if self.backend.mode_simulation:
            self._styliser_badge(self.badge_eib, "ambre", tr("badge_virtual"))
            self.lbl_detail_eib.setText(tr("info_simulation"))
        elif ok:
            com_txt = f"COM{self.backend.com_index}" if self.backend.com_index else "COM"
            self._styliser_badge(self.badge_eib, "vert", tr("badge_online"))
            self.lbl_detail_eib.setText(com_txt)
        else:
            self._styliser_badge(self.badge_eib, "rouge", tr("badge_offline"))
            self.lbl_detail_eib.setText("—")
        self.vue_synoptique.update()

    def maj_statut_pompe(self, pid: int, infos: dict = None):
        """Met à jour l'état consolidé sans perdre le port, le S/N ni verrouiller le mode virtuel."""
        if infos is None:
            infos = {}

        if not hasattr(self, "_statut_pompes") or self._statut_pompes is None:
            self._statut_pompes = {1: {}, 2: {}}
        if pid not in self._statut_pompes or not isinstance(self._statut_pompes[pid], dict):
            self._statut_pompes[pid] = {}

        pompe_obj = None
        if hasattr(self, "backend_pumps") and hasattr(self.backend_pumps, "pompes"):
            pompe_obj = self.backend_pumps.pompes.get(pid)

        cache = self._statut_pompes[pid]

        # 1. Port matériel
        port_nom = infos.get("port")
        if port_nom is None and pompe_obj:
            port_nom = getattr(pompe_obj, "port", "")
        if port_nom is None:
            port_nom = cache.get("port", "")

        # 2. Mode Virtuel (détection stricte)
        if "virtuel" in infos:
            est_virtuel = bool(infos["virtuel"])
        elif "mode_virtuel" in infos:
            est_virtuel = bool(infos["mode_virtuel"])
        elif port_nom and port_nom.startswith("COM"):
            est_virtuel = False
        elif pompe_obj is not None:
            est_virtuel = getattr(pompe_obj, "mode_virtuel", False) or (getattr(pompe_obj, "port", "") == "VIRTUAL")
        else:
            est_virtuel = False

        if port_nom == "VIRTUAL":
            port_nom = ""

        # 3. État de connexion
        connecte = infos.get("connecte")
        if connecte is None and pompe_obj:
            connecte = getattr(pompe_obj, "connecte", False)
        if connecte is None:
            connecte = cache.get("connecte", False)

        # 4. Numéro de série
        sn = infos.get("sn")
        if sn is None and pompe_obj:
            sn = getattr(pompe_obj, "sn", "")
        if sn is None:
            sn = cache.get("sn", "")

        # 5. État moteur
        en_marche = infos.get("en_marche")
        if en_marche is None and pompe_obj:
            en_marche = getattr(pompe_obj, "en_marche", False)
        if en_marche is None:
            en_marche = cache.get("en_marche", False)

        # Enregistrement consolidé
        self._statut_pompes[pid] = {
            "connecte": bool(connecte),
            "virtuel": bool(est_virtuel),
            "en_marche": bool(en_marche),
            "port": str(port_nom) if port_nom else "",
            "sn": str(sn) if sn else "",
            "modele_seringue": infos.get("modele_seringue") or getattr(pompe_obj, "modele_seringue", cache.get("modele_seringue")),
            "diametre": infos.get("diametre") or getattr(pompe_obj, "diametre", cache.get("diametre"))
        }

        badge = self.badge_p1 if pid == 1 else self.badge_p2
        lbl_detail = self.lbl_detail_p1 if pid == 1 else self.lbl_detail_p2

        # 1. Mise à jour Badge + Détail matériel
        if not connecte and not est_virtuel:
            self._styliser_badge(badge, "neutre", tr("badge_disabled"))
            lbl_detail.setText("—")
        elif est_virtuel:
            self._styliser_badge(badge, "ambre", tr("badge_virtual"))
            lbl_detail.setText(tr("info_simulation"))
        else:
            self._styliser_badge(badge, "vert", tr("badge_online_fem"))
            sn_txt = f" [S/N: {sn}]" if sn else ""
            lbl_detail.setText(f"{port_nom}{sn_txt}")

        # 2. Pilotage des commandes manuelles
        w = getattr(self, "widgets_pompes", {}).get(pid)
        if w:
            actif = bool(connecte or est_virtuel)
            if "unite" in w:
                w["unite"].setEnabled(not en_marche and actif)
            if "debit" in w:
                w["debit"].setEnabled(actif)
            if "sens" in w:
                w["sens"].setEnabled(actif)
            if "btn_toggle" in w:
                w["btn_toggle"].setEnabled(actif)
                if en_marche:
                    w["btn_toggle"].setText(tr("btn_stop_pump"))
                    self.pompes_en_marche.add(pid)
                    if not self.timer_pulse_pompes.isActive():
                        self.timer_pulse_pompes.start()
                else:
                    w["btn_toggle"].setText(tr("btn_launch"))
                    w["btn_toggle"].setStyleSheet("")
                    self.pompes_en_marche.discard(pid)
                    if not self.pompes_en_marche and self.timer_pulse_pompes.isActive():
                        self.timer_pulse_pompes.stop()

        # 3. Synchronisation de la configuration seringue dans l'onglet Options
        if hasattr(self, "widgets_cfg_seringues") and pid in self.widgets_cfg_seringues:
            w_cfg = self.widgets_cfg_seringues[pid]
            mod_nom = self._statut_pompes[pid].get("modele_seringue")
            diam_nom = self._statut_pompes[pid].get("diametre")

            if mod_nom and w_cfg["cb"].currentText() != mod_nom:
                w_cfg["cb"].blockSignals(True)
                idx_mod = w_cfg["cb"].findText(mod_nom)
                if idx_mod >= 0:
                    w_cfg["cb"].setCurrentIndex(idx_mod)
                    w_cfg["spin"].setEnabled(False)
                else:
                    idx_custom = w_cfg["cb"].findText(OPTION_PERSONNALISEE)
                    w_cfg["cb"].setCurrentIndex(idx_custom)
                    w_cfg["spin"].setEnabled(True)
                w_cfg["cb"].blockSignals(False)

            if diam_nom and abs(w_cfg["spin"].value() - diam_nom) > 0.01:
                w_cfg["spin"].blockSignals(True)
                w_cfg["spin"].setValue(diam_nom)
                w_cfg["spin"].blockSignals(False)

        # 4. Rafraîchissement synoptique
        if hasattr(self, "vue_synoptique") and self.vue_synoptique:
            self.vue_synoptique.update()

    # =========================================================================
    # INTERNATIONALISATION & THÈMES
    # =========================================================================
    def changer_langue(self, code_langue: str):
        set_langue(code_langue)
        self.settings.setValue("language", code_langue)
        self.actualiser_textes_langue()

        if self._statut_eib_ok is not None:
            self.maj_statut_connexion_labsmith(self._statut_eib_ok)
        for pid in (1, 2):
            if self._statut_pompes.get(pid):
                self.maj_statut_pompe(pid, self._statut_pompes[pid])

    def actualiser_textes_langue(self):
        self.tabs.setTabText(0, tr("tab_manuel"))
        self.tabs.setTabText(1, tr("tab_sequence"))
        self.tabs.setTabText(2, tr("tab_options"))

        self.grp_com.setTitle(tr("grp_hardware_cfg"))
        self.btn_rescan.setText(tr("btn_scan_com"))
        self.btn_id_p1.setText(f"{tr('btn_flash_screen')} S1")
        self.btn_id_p2.setText(f"{tr('btn_flash_screen')} S2")
        self.grp_seringues_cfg.setTitle(tr("grp_syringe_wp1"))
        self.btn_lire_pompes.setText(tr("btn_align_gui"))

        self.lbl_logs_header.setText(f"<b>{tr('console_title')}</b>")
        self.btn_clear.setText(tr("btn_clear"))
        self.btn_export.setText(tr("btn_export"))
        self.grp_dispositifs.setTitle(tr("grp_devices"))

        # Actualisation des étiquettes et des titres
        if hasattr(self, "lbl_titre_eib"):
            self.lbl_titre_eib.setText(f"<b>{tr('dev_valves_eib')}</b>")
        if hasattr(self, "lbl_titre_p1"):
            self.lbl_titre_p1.setText(f"<b>{tr('dev_pump_1')}</b>")
        if hasattr(self, "lbl_titre_p2"):
            self.lbl_titre_p2.setText(f"<b>{tr('dev_pump_2')}</b>")

        if hasattr(self, "lbl_cfg_eib"):
            self.lbl_cfg_eib.setText(f"<b>{tr('dev_valves_eib')}</b>")
        if hasattr(self, "lbl_cfg_p1"):
            self.lbl_cfg_p1.setText(f"<b>{tr('pump1_full_name')} :</b>")
        if hasattr(self, "lbl_cfg_p2"):
            self.lbl_cfg_p2.setText(f"<b>{tr('pump2_full_name')} :</b>")

        self.grp_v.setTitle(tr("grp_view"))
        self.rad_classique.setText(tr("view_simple"))
        self.rad_graphique.setText(tr("view_synoptic"))

        self.grp_lang.setTitle(tr("grp_lang"))
        self.rad_fr.setText(tr("lang_fr"))
        self.rad_en.setText(tr("lang_en"))

        self.grp_t.setTitle(tr("grp_theme"))
        self.rad_dark.setText(tr("theme_dark"))
        self.rad_light.setText(tr("theme_light"))

        self.grp_z.setTitle(tr("grp_scale"))
        self.lbl_scale.setText(tr("scale_lbl"))
        
        idx_zoom = self.cb_zoom.currentIndex()
        self.cb_zoom.blockSignals(True)
        self.cb_zoom.clear()
        self.cb_zoom.addItems([tr("zoom_80"), tr("zoom_100"), tr("zoom_120"), tr("zoom_140")])
        self.cb_zoom.setCurrentIndex(idx_zoom)
        self.cb_zoom.blockSignals(False)

        self.grp_a.setTitle(tr("grp_anim"))
        self.chk_anim.setText(tr("chk_anim"))

        self.grp_s.setTitle(tr("grp_seq_opt"))
        self.chk_clr.setText(tr("chk_auto_clear"))

        if hasattr(self, "panel_sequenceur"):
            self.panel_sequenceur.retraduire()

        self.actualiser_tout()

    def _toggle_auto_clear(self, chk):
        self.panel_sequenceur.auto_clear = chk
        self.settings.setValue("auto_clear", chk)

    def changer_mode_vue(self, idx):
        self.pile_vues_manuel.setCurrentIndex(idx)
        self.settings.setValue("mode_vue", idx)
        if idx == 0:
            self.actualiser_vue_simple()
        else:
            self.vue_synoptique.update()

    def changer_animation(self, act):
        self.vue_synoptique.set_animations_actives(act)
        self.panel_sequenceur.set_animations_actives(act)
        self.settings.setValue("animations", act)

    def changer_taille_interface(self, idx):
        facteurs = [0.80, 1.0, 1.20, 1.40]
        polices = [8, 10, 12, 14]
        self.facteur_zoom = facteurs[idx]
        self.taille_police = polices[idx]

        self.vue_synoptique.set_echelle_ui(self.facteur_zoom)
        self.appliquer_theme(self.mode_sombre)
        self.settings.setValue("zoom_index", idx)

    def appliquer_theme(self, sombre: bool):
        self.mode_sombre = sombre
        self.vue_synoptique.set_mode_sombre(sombre)
        self.settings.setValue("theme_sombre", sombre)
        self.setStyleSheet(get_stylesheet(sombre, getattr(self, "taille_police", 10)))
        self.actualiser_vue_simple()

    def charger_parametres(self):
        lang = self.settings.value("language", "fr", type=str)
        set_langue(lang)
        (self.rad_fr if lang == "fr" else self.rad_en).setChecked(True)

        sombre = self.settings.value("theme_sombre", True, type=bool)
        (self.rad_dark if sombre else self.rad_light).setChecked(True)

        zoom_idx = self.settings.value("zoom_index", 1, type=int)
        if 0 <= zoom_idx < self.cb_zoom.count():
            self.cb_zoom.setCurrentIndex(zoom_idx)
            self.changer_taille_interface(zoom_idx)
        else:
            self.appliquer_theme(sombre)

        mode_vue = self.settings.value("mode_vue", 1, type=int)
        (self.rad_classique if mode_vue == 0 else self.rad_graphique).setChecked(True)
        self.pile_vues_manuel.setCurrentIndex(mode_vue)

        anim = self.settings.value("animations", True, type=bool)
        self.chk_anim.setChecked(anim)
        self.vue_synoptique.set_animations_actives(anim)
        self.panel_sequenceur.set_animations_actives(anim)

        ac = self.settings.value("auto_clear", False, type=bool)
        self.chk_clr.setChecked(ac)
        self.panel_sequenceur.auto_clear = ac

        split_sizes = self.settings.value("splitter_sizes")
        if split_sizes:
            try:
                self.splitter.setSizes([int(s) for s in split_sizes])
            except Exception:
                pass

        geom = self.settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)

        for pid in (1, 2):
            w = self.widgets_cfg_seringues.get(pid)
            if not w:
                continue
            def_m = "Hamilton Gastight 1 mL" if pid == 1 else "Air-Tite Norm-Ject 50 mL"
            mod_sauve = self.settings.value(f"syringe_model_p{pid}", def_m, type=str)
            diam_sauve = self.settings.value(f"syringe_diam_p{pid}", 0.0, type=float)

            idx = w["cb"].findText(mod_sauve)
            if idx >= 0:
                w["cb"].blockSignals(True)
                w["cb"].setCurrentIndex(idx)
                w["cb"].blockSignals(False)

            if mod_sauve == OPTION_PERSONNALISEE:
                w["spin"].setEnabled(True)
                if diam_sauve > 0:
                    w["spin"].setValue(diam_sauve)
                self.backend_pumps.definir_seringue(pid, mod_sauve, diametre_libre=w["spin"].value())
            else:
                w["spin"].setEnabled(False)
                diam = get_diametre(mod_sauve)
                if diam:
                    w["spin"].setValue(diam)
                self.backend_pumps.definir_seringue(pid, mod_sauve)

        self.actualiser_textes_langue()

    # =========================================================================
    # ACTIONS MANUELLES VANNES (GRILLE CLASSIQUE)
    # =========================================================================
    def construire_interface_dynamique(self, infos):
        while self.layout_modules_labsmith.count():
            item = self.layout_modules_labsmith.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.boutons_manuel_av201.clear()
        self.labels_etat_av201.clear()
        self.boutons_manuel_av801.clear()
        self.labels_etat_av801.clear()

        for addr, details in infos.items():
            nom, typ = details["nom"], details["type"]
            grp = QGroupBox(f"Module : {nom} (0x{addr:02X})")
            lay_g = QVBoxLayout(grp)

            if typ == "AV801":
                c = details["canal_selecteur"]
                lay_top = QHBoxLayout()
                lbl_st = QLabel(f"<b>[ {tr('port_unknown')} ]</b>")
                lbl_st.setStyleSheet("color: #c77dff; font-weight: bold;")
                self.labels_etat_av801[addr] = lbl_st
                lay_top.addWidget(QLabel("<b>AV801 (Port 3)</b>"))
                lay_top.addStretch()
                lay_top.addWidget(lbl_st)
                lay_g.addLayout(lay_top)

                grid = QGridLayout()
                for p in range(1, 9):
                    btn = QPushButton(f"Port {p}")
                    btn.clicked.connect(lambda chk, a=addr, cn=c, pt=p: self.action_manuel_8ports(a, cn, pt))
                    self.boutons_manuel_av801[(addr, p)] = btn
                    r, col = divmod(p - 1, 4)
                    grid.addWidget(btn, r, col)
                lay_g.addLayout(grid)
            else:
                lay_glob = QHBoxLayout()
                for et, cle_txt in [(1, "all_s1"), (2, "all_stop"), (3, "all_s3")]:
                    b = QPushButton(tr(cle_txt))
                    b.clicked.connect(lambda chk, a=addr, e=et: self.action_manuel_tous(a, e))
                    lay_glob.addWidget(b)
                lay_g.addLayout(lay_glob)

                grid = QGridLayout()
                for ch in range(1, 5):
                    lbl_st = QLabel("[ ? ]")
                    lbl_st.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.labels_etat_av201[(addr, ch)] = lbl_st

                    grid.addWidget(QLabel(f"<b>{tr('channel')} {ch} :</b>"), ch - 1, 0)
                    grid.addWidget(lbl_st, ch - 1, 1)
                    for et, cle_txt in [(1, "out_1"), (2, "all_stop"), (3, "out_3")]:
                        b = QPushButton(tr(cle_txt).replace("⏵ ", "").replace("⏹ ", ""))
                        b.clicked.connect(lambda chk, a=addr, cn=ch, e=et: self.action_manuel_vanne(a, cn, e))
                        self.boutons_manuel_av201[(addr, ch, et)] = b
                        grid.addWidget(b, ch - 1, et + 1)
                lay_g.addLayout(grid)

            self.layout_modules_labsmith.addWidget(grp)

        self.actualiser_tout()

    def actualiser_vue_simple(self):
        for addr, lbl in self.labels_etat_av801.items():
            p = self.backend.derniers_ports_av801.get(addr, None)
            lbl.setText(f"<b>[ {tr('port_active', port=p) if p else tr('port_unknown')} ]</b>")
            lbl.setStyleSheet(f"color: {'#c77dff' if p else '#8d99ae'}; font-weight: bold;")
            for pt in range(1, 9):
                b = self.boutons_manuel_av801.get((addr, pt))
                if b:
                    b.setStyleSheet("background-color: #3c096c; border: 2px solid #c77dff; color: #fff; font-weight: bold;" if p == pt else "")

        for (addr, ch), lbl in self.labels_etat_av201.items():
            pos = self.backend.dernieres_pos_av201.get((addr, ch), None)
            est_d = (addr == 0x08)
            txts = {1: "[ S1 ]", 2: "[ STOP ]", 3: "[ S3 ]"}
            colors = {1: "#fbbf24" if est_d else "#00f5d4", 2: "#ff4d6d", 3: "#e0aaff" if est_d else "#52b788"}

            lbl.setText(f"<b>{txts.get(pos, '[ ? ]')}</b>")
            lbl.setStyleSheet(f"color: {colors.get(pos, '#8d99ae')}; font-weight: bold;")

            for et in (1, 2, 3):
                b = self.boutons_manuel_av201.get((addr, ch, et))
                if b:
                    if pos == et:
                        bgs = {1: "#78350f" if est_d else "#005f73", 2: "#780000", 3: "#4a044e" if est_d else "#1b4332"}
                        bds = {1: "#fbbf24" if est_d else "#00f5d4", 2: "#ff4d6d", 3: "#e0aaff" if est_d else "#52b788"}
                        b.setStyleSheet(f"background-color: {bgs[et]}; border: 2px solid {bds[et]}; color: #fff; font-weight: bold;")
                    else:
                        b.setStyleSheet("")

    def actualiser_tout(self):
        self.actualiser_vue_simple()
        self.vue_synoptique.update()

    def action_manuel_vanne(self, addr, canal, etat):
        self.backend.regler_vanne_individuelle(addr, canal, etat)
        self.actualiser_tout()

    def action_manuel_tous(self, addr, etat):
        self.backend.regler_toutes_vannes(addr, etat)
        self.actualiser_tout()

    def action_manuel_8ports(self, addr, canal, port):
        self.backend.regler_vanne_8ports(addr, canal, port)
        self.actualiser_tout()

    def ajouter_log(self, txt):
        t = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.console_log.append(f"[{t}] {txt}")

    def exporter_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("btn_export"), "decliq_logs.txt", "Text (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.console_log.toPlainText())
                self.ajouter_log(f"💾 Logs exportés : {path}")
            except Exception as e:
                self.ajouter_log(f"❌ Erreur export : {e}")

    def closeEvent(self, event):
        self.timer_watchdog.stop()
        self.settings.setValue("splitter_sizes", [str(s) for s in self.splitter.sizes()])
        self.settings.setValue("geometry", self.saveGeometry())

        self.panel_sequenceur.arreter_sequence()
        self.backend_pumps.deconnecter_tout()
        self.backend.deconnecter()

        for th in (self.thread_labsmith, self.thread_pumps):
            th.quit()
            if not th.wait(1500):
                th.terminate()

        event.accept()


if __name__ == "__main__":
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("liphy.decliq.app.1.0")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(ressource_path("icon.svg")))
    fen = DecLiqFrontEnd()
    fen.show()
    sys.exit(app.exec())