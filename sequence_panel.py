"""
sequence_panel.py - Séquenceur de protocoles automatisés pour DecLiq (LIPhy).
- Gestion modulaire des blocs : AV201 (3-voies), AV801 (8-ports), Pousse-seringue et Pause.
- Défilement automatique et pulsation de la brique en cours d'exécution.
- Intégration de DecLiqComboBox (protection contre la molette et chevrons vectoriels).
- Import / Export au format JSON.
"""
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QScrollArea, QFrame, QLabel, QFileDialog
)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QTimer
from PyQt6.QtGui import QFont, QPainter, QPen, QBrush, QColor

from ui_components import (
    DecLiqDoubleSpinBox, DecLiqComboBox, DragHandle, 
    ActionButton, DropIndicator
)
from sequence_worker import SequenceWorker
from i18n import tr


class BlockCard(QFrame):
    """Carte représentant une étape élémentaire du protocole DecLiq."""
    def __init__(self, type_bloc: str, parent_panel, vals: dict = None):
        super().__init__()
        self.type_bloc = type_bloc
        self.parent_panel = parent_panel
        self.est_active = False

        if type_bloc == "AV201":
            self.col_accent = QColor("#00b4d8")
        elif type_bloc == "AV801":
            self.col_accent = QColor("#c77dff")
        elif type_bloc == "Pump":
            self.col_accent = QColor("#10b981")
        else:
            self.col_accent = QColor("#f59e0b")

        self.pulse_alpha = 255
        self.pulse_phase = 0
        self.timer_pulse = QTimer(self)
        self.timer_pulse.setInterval(60)
        self.timer_pulse.timeout.connect(self._animer_pulsation)

        self.init_card_ui(vals)

    def init_card_ui(self, vals: dict):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(10)

        self.handle = DragHandle(self)
        lay.addWidget(self.handle)

        self.lbl_num = QLabel("#00")
        self.lbl_num.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.lbl_num.setStyleSheet("color: #8d99ae; min-width: 30px;")
        lay.addWidget(self.lbl_num)

        # 1. Actionneurs 3-voies AV201
        if self.type_bloc == "AV201":
            lbl_type = QLabel("AV201")
            lbl_type.setToolTip("Actionneur 3-voies amont (0x05) ou aval (0x08)")
            lbl_type.setStyleSheet(f"""
                color: {self.col_accent.name()};
                background-color: rgba(0, 180, 216, 0.12);
                border: 1px solid {self.col_accent.name()};
                border-radius: 4px;
                font-weight: bold;
                padding: 3px 6px;
                min-width: 55px;
            """)

            cb_addr = DecLiqComboBox()
            for addr, cfg in self.parent_panel.backend.ROLES_BANC.items():
                if cfg["type"] == "AV201":
                    cb_addr.addItem(cfg["nom"], addr)
            if vals and "addr" in vals:
                idx = cb_addr.findData(vals["addr"])
                if idx >= 0:
                    cb_addr.setCurrentIndex(idx)

            cb_canal = DecLiqComboBox()
            cb_canal.addItems(["Canal 1", "Canal 2", "Canal 3", "Canal 4", "Tous (GLOBAL)"])
            if vals and "canal" in vals:
                c_val = vals["canal"]
                if c_val in ("ALL", 0):
                    cb_canal.setCurrentIndex(4)
                else:
                    cb_canal.setCurrentIndex(int(c_val) - 1)

            cb_act = DecLiqComboBox()
            cb_act.addItems([tr("out_1"), "STOP", tr("out_3")])
            if vals and "action" in vals:
                act = str(vals["action"])
                if "1" in act:
                    cb_act.setCurrentIndex(0)
                elif "STOP" in act or "Fermé" in act:
                    cb_act.setCurrentIndex(1)
                elif "3" in act:
                    cb_act.setCurrentIndex(2)

            self.w_addr, self.w_canal, self.w_action = cb_addr, cb_canal, cb_act
            lay.addWidget(lbl_type)
            lay.addWidget(cb_addr)
            lay.addWidget(cb_canal)
            lay.addWidget(cb_act)

        # 2. Sélecteur 8-ports AV801
        elif self.type_bloc == "AV801":
            lbl_type = QLabel("AV801")
            lbl_type.setToolTip("Sélecteur rotatif 8-ports (sens horaire)")
            lbl_type.setStyleSheet(f"""
                color: {self.col_accent.name()};
                background-color: rgba(199, 125, 255, 0.12);
                border: 1px solid {self.col_accent.name()};
                border-radius: 4px;
                font-weight: bold;
                padding: 3px 6px;
                min-width: 55px;
            """)

            cb_addr = DecLiqComboBox()
            for addr, cfg in self.parent_panel.backend.ROLES_BANC.items():
                if cfg["type"] == "AV801":
                    cb_addr.addItem(cfg["nom"], addr)
            if vals and "addr" in vals:
                idx = cb_addr.findData(vals["addr"])
                if idx >= 0:
                    cb_addr.setCurrentIndex(idx)

            cb_port = DecLiqComboBox()
            for p in range(1, 9):
                cb_port.addItem(f"Port {p}", p)
            if vals and "port" in vals:
                cb_port.setCurrentIndex(int(vals["port"]) - 1)

            self.w_addr, self.w_port = cb_addr, cb_port
            lay.addWidget(lbl_type)
            lay.addWidget(cb_addr)
            lay.addWidget(cb_port)

        # 3. Pousse-seringues
        elif self.type_bloc == "Pump":
            lbl_type = QLabel("POMPE")
            lbl_type.setToolTip("Consigne de débit, sens ou arrêt pour pousse-seringue")
            lbl_type.setStyleSheet(f"""
                color: {self.col_accent.name()};
                background-color: rgba(16, 185, 129, 0.12);
                border: 1px solid {self.col_accent.name()};
                border-radius: 4px;
                font-weight: bold;
                padding: 3px 6px;
                min-width: 55px;
            """)

            cb_pump = DecLiqComboBox()
            cb_pump.addItem("Seringue 1 [q₁]", 1)
            cb_pump.addItem("Seringue 2 [q₂]", 2)
            cb_pump.addItem(tr("seq_pump_target_all", default="Toutes (q₁ & q₂)"), 0)
            if vals and "pump_id" in vals:
                idx = cb_pump.findData(vals["pump_id"])
                if idx >= 0:
                    cb_pump.setCurrentIndex(idx)

            cb_action = DecLiqComboBox()
            cb_action.addItems(["Aspiration (withdraw)", "Infusion", "Arrêt (STOP)"])

            sp_debit = DecLiqDoubleSpinBox()
            sp_debit.setRange(0.001, 10000.0)
            sp_debit.setValue(0.25)
            sp_debit.setDecimals(3)
            sp_debit.setSingleStep(0.05)

            cb_unite = DecLiqComboBox()
            cb_unite.addItems(["µL/min", "mL/min", "nL/min", "µL/h", "mL/h"])
            cb_unite.currentIndexChanged.connect(lambda idx, sp=sp_debit, c=cb_unite: self._adapter_plage_debit(sp, c))

            def _gerer_changement_action(idx):
                est_stop = (idx == 2)
                sp_debit.setEnabled(not est_stop)
                cb_unite.setEnabled(not est_stop)

            cb_action.currentIndexChanged.connect(_gerer_changement_action)

            if vals and "action" in vals:
                act = str(vals["action"]).lower()
                if "stop" in act or "arr" in act:
                    cb_action.setCurrentIndex(2)
                elif "infuse" in act or "infusion" in act:
                    cb_action.setCurrentIndex(1)
                else:
                    cb_action.setCurrentIndex(0)

            _gerer_changement_action(cb_action.currentIndex())

            if vals:
                if "unite" in vals:
                    u_idx = cb_unite.findText(vals["unite"])
                    if u_idx >= 0:
                        cb_unite.setCurrentIndex(u_idx)
                if "debit" in vals:
                    try:
                        sp_debit.setValue(float(vals["debit"]))
                    except (ValueError, TypeError):
                        pass

            self.w_pump = cb_pump
            self.w_pump_action = cb_action
            self.w_debit = sp_debit
            self.w_unite_debit = cb_unite

            lay.addWidget(lbl_type)
            lay.addWidget(cb_pump)
            lay.addWidget(cb_action)
            lay.addWidget(sp_debit)
            lay.addWidget(cb_unite)

        # 4. Temporisation
        elif self.type_bloc == "Pause":
            lbl_type = QLabel("TEMPO")
            lbl_type.setToolTip("Temporisation (stabilisation, ménisque, incubation)")
            lbl_type.setStyleSheet(f"""
                color: {self.col_accent.name()};
                background-color: rgba(245, 158, 11, 0.12);
                border: 1px solid {self.col_accent.name()};
                border-radius: 4px;
                font-weight: bold;
                padding: 3px 6px;
                min-width: 55px;
            """)

            sp = DecLiqDoubleSpinBox()
            sp.setRange(0.01, 86400.0)
            sp.setDecimals(2)
            sp.setSingleStep(1.0)

            cb_u = DecLiqComboBox()
            cb_u.addItems([tr("unit_sec"), tr("unit_min"), tr("unit_h")])

            if vals and "duree" in vals:
                d = vals["duree"]
                if isinstance(d, dict):
                    sp.setValue(d.get("valeur", 5.0))
                    u_txt = d.get("unite", "Secondes (s)")
                    if "min" in u_txt.lower():
                        cb_u.setCurrentIndex(1)
                    elif "h" in u_txt.lower():
                        cb_u.setCurrentIndex(2)
                    else:
                        cb_u.setCurrentIndex(0)
                else:
                    sp.setValue(float(d))
            else:
                sp.setValue(5.0)

            self.w_duree, self.w_unite = sp, cb_u
            lay.addWidget(lbl_type)
            lay.addWidget(sp)
            lay.addWidget(cb_u)

        lay.addStretch()

        btn_dup = ActionButton("dup", self)
        btn_dup.clicked.connect(lambda: self.parent_panel.dupliquer_bloc(self))

        btn_del = ActionButton("del", self)
        btn_del.clicked.connect(lambda: self.parent_panel.supprimer_bloc(self))

        lay.addWidget(btn_dup)
        lay.addWidget(btn_del)

    def _adapter_plage_debit(self, spin: DecLiqDoubleSpinBox, combo: DecLiqComboBox):
        unite = combo.currentText()
        val = spin.value()
        if unite == "µL/min":
            spin.setRange(0.001, 1000.0)
            spin.setDecimals(3)
            spin.setSingleStep(0.05)
        elif unite == "mL/min":
            spin.setRange(0.001, 100.0)
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        if self.est_active:
            bg_color = QColor(16, 185, 129, 38)
            border_color = QColor(16, 185, 129, self.pulse_alpha)
            accent_color = QColor("#10b981")
            ep_border = 2.0
        else:
            bg_color = QColor(120, 130, 150, 18)
            border_color = QColor(120, 130, 150, 50)
            accent_color = self.col_accent
            ep_border = 1.0

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, ep_border))
        painter.drawRoundedRect(r, 6, 6)

        painter.setBrush(QBrush(accent_color))
        painter.setPen(Qt.PenStyle.NoPen)
        r_accent = QRectF(r.left(), r.top() + 1, 5, r.height() - 2)
        painter.drawRoundedRect(r_accent, 2.5, 2.5)
        painter.end()
        super().paintEvent(event)

    def set_actif(self, actif: bool, animer: bool):
        self.est_active = actif
        if actif:
            self.lbl_num.setStyleSheet("color: #10b981; font-weight: bold; min-width: 30px;")
            if animer:
                self.pulse_phase = 0
                self.timer_pulse.start()
            else:
                self.timer_pulse.stop()
                self.pulse_alpha = 255
                self.update()
        else:
            self.timer_pulse.stop()
            self.lbl_num.setStyleSheet("color: #8d99ae; min-width: 30px;")
            self.update()

    def _animer_pulsation(self):
        self.pulse_phase = (self.pulse_phase + 1) % 24
        self.pulse_alpha = int(120 + 135 * abs(12 - self.pulse_phase) / 12.0)
        self.update()


class SequenceContainer(QWidget):
    """Conteneur acceptant le glisser-déposer avec indicateur visuel."""
    def __init__(self, parent_panel):
        super().__init__()
        self.parent_panel = parent_panel
        self.setAcceptDrops(True)
        self.drop_indicator = DropIndicator()
        self.drop_indicator.hide()
        self._dernier_idx_cible = -1

    def commencer_drag(self):
        self._dernier_idx_cible = -1

    def terminer_drag(self):
        if self.drop_indicator.isVisible():
            self.drop_indicator.hide()
            self.parent_panel.layout_blocs.removeWidget(self.drop_indicator)
        self._dernier_idx_cible = -1

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-decliq-step"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat("application/x-decliq-step"):
            return

        event.acceptProposedAction()
        pos_y = event.position().y()
        layout = self.parent_panel.layout_blocs

        cartes = [layout.itemAt(i).widget() for i in range(layout.count() - 1)
                  if layout.itemAt(i).widget() and layout.itemAt(i).widget() != self.drop_indicator]

        idx_cible = len(cartes)
        for i, carte in enumerate(cartes):
            if pos_y < carte.geometry().center().y():
                idx_cible = i
                break

        if idx_cible != self._dernier_idx_cible:
            self._dernier_idx_cible = idx_cible
            if self.drop_indicator.isVisible():
                layout.removeWidget(self.drop_indicator)
            layout.insertWidget(idx_cible, self.drop_indicator)
            self.drop_indicator.show()

    def dragLeaveEvent(self, event):
        self.terminer_drag()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-decliq-step"):
            return

        layout = self.parent_panel.layout_blocs
        idx_cible = layout.indexOf(self.drop_indicator)
        self.terminer_drag()

        idx_source = int(event.mimeData().text())
        if idx_cible != -1 and idx_source != idx_cible:
            item = layout.takeAt(idx_source)
            if item and item.widget():
                pos_finale = idx_cible if idx_source > idx_cible else max(0, idx_cible - 1)
                layout.insertWidget(pos_finale, item.widget())
                self.parent_panel.renumeroter_blocs()

        event.acceptProposedAction()


class SequencePanel(QWidget):
    log_demande = pyqtSignal(str)
    effacer_log_demande = pyqtSignal()
    sequence_terminee = pyqtSignal()

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.worker = None
        self.auto_clear = False
        self.animations_actives = True
        self.init_ui()

    def set_animations_actives(self, active: bool):
        self.animations_actives = active

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Fichiers
        layout_io = QHBoxLayout()
        layout_io.setSpacing(8)
        self.btn_import = QPushButton(tr("btn_import_seq"))
        self.btn_import.clicked.connect(self.importer_sequence)
        self.btn_export = QPushButton(tr("btn_export_seq"))
        self.btn_export.clicked.connect(self.sauvegarder_sequence)
        layout_io.addWidget(self.btn_import)
        layout_io.addWidget(self.btn_export)
        layout.addLayout(layout_io)

        # Défilement
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: 1px solid rgba(120, 130, 150, 0.25); border-radius: 6px; }")

        self.conteneur = SequenceContainer(self)
        self.layout_blocs = QVBoxLayout(self.conteneur)
        self.layout_blocs.setSpacing(6)
        self.layout_blocs.setContentsMargins(6, 6, 6, 6)
        self.layout_blocs.addStretch()
        self.scroll.setWidget(self.conteneur)
        layout.addWidget(self.scroll)

        # Ajout
        layout_ajout = QHBoxLayout()
        layout_ajout.setSpacing(8)
        self.btn_av201 = QPushButton(tr("add_av201"))
        self.btn_av201.clicked.connect(lambda: self.ajouter_bloc("AV201"))
        self.btn_av801 = QPushButton(tr("add_av801"))
        self.btn_av801.clicked.connect(lambda: self.ajouter_bloc("AV801"))
        self.btn_pump = QPushButton("+ Pousse-seringue")
        self.btn_pump.clicked.connect(lambda: self.ajouter_bloc("Pump"))
        self.btn_pause = QPushButton(tr("add_tempo"))
        self.btn_pause.clicked.connect(lambda: self.ajouter_bloc("Pause"))
        layout_ajout.addWidget(self.btn_av201)
        layout_ajout.addWidget(self.btn_av801)
        layout_ajout.addWidget(self.btn_pump)
        layout_ajout.addWidget(self.btn_pause)
        layout.addLayout(layout_ajout)

        # Commandes de lancement
        layout_ctrl = QHBoxLayout()
        layout_ctrl.setSpacing(10)
        self.btn_run = QPushButton(tr("btn_run_seq"))
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #155724; 
                color: #d4edda; 
                border: 1px solid #28a745; 
                font-weight: bold; 
                padding: 9px; 
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #1e7e34; color: #ffffff; }
            QPushButton:disabled { background-color: #2b3038; border-color: #495057; color: #6c757d; }
        """)
        self.btn_run.clicked.connect(self.lancer_sequence)

        self.btn_stop = QPushButton(tr("btn_stop_seq"))
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #721c24; 
                color: #f8d7da; 
                border: 1px solid #dc3545; 
                font-weight: bold; 
                padding: 9px; 
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #bd2130; color: #ffffff; }
            QPushButton:disabled { background-color: #2b3038; border-color: #495057; color: #6c757d; }
        """)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.arreter_sequence)
        layout_ctrl.addWidget(self.btn_run)
        layout_ctrl.addWidget(self.btn_stop)
        layout.addLayout(layout_ctrl)

    def retraduire(self):
        self.btn_import.setText(tr("btn_import_seq"))
        self.btn_export.setText(tr("btn_export_seq"))
        self.btn_av201.setText(tr("add_av201"))
        self.btn_av801.setText(tr("add_av801"))
        self.btn_pause.setText(tr("add_tempo"))
        self.btn_run.setText(tr("btn_run_seq"))
        self.btn_stop.setText(tr("btn_stop_seq"))

        for i in range(self.layout_blocs.count() - 1):
            w = self.layout_blocs.itemAt(i).widget()
            if w and hasattr(w, "type_bloc") and w.type_bloc == "Pause":
                idx = w.w_unite.currentIndex()
                w.w_unite.clear()
                w.w_unite.addItems([tr("unit_sec"), tr("unit_min"), tr("unit_h")])
                w.w_unite.setCurrentIndex(idx)

    def definir_etape_active(self, index: int):
        total = self.layout_blocs.count() - 1
        for i in range(total):
            item = self.layout_blocs.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), BlockCard):
                card = item.widget()
                est_courante = (i == index)
                card.set_actif(est_courante, self.animations_actives)
                if est_courante:
                    self.scroll.ensureWidgetVisible(card, 15, 15)

    def ajouter_bloc(self, type_bloc: str, vals: dict = None):
        carte = BlockCard(type_bloc, self, vals)
        self.layout_blocs.insertWidget(self.layout_blocs.count() - 1, carte)
        self.renumeroter_blocs()

    def renumeroter_blocs(self):
        total = self.layout_blocs.count() - 1
        for i in range(total):
            item = self.layout_blocs.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), "lbl_num"):
                item.widget().lbl_num.setText(f"#{i + 1:02d}")

    def dupliquer_bloc(self, carte: BlockCard):
        tb = carte.type_bloc
        vals = {}
        if tb == "AV201":
            canal_idx = carte.w_canal.currentIndex()
            vals = {
                "addr": carte.w_addr.currentData(),
                "canal": "ALL" if canal_idx == 4 else (canal_idx + 1),
                "action": carte.w_action.currentText()
            }
        elif tb == "AV801":
            vals = {
                "addr": carte.w_addr.currentData(),
                "port": carte.w_port.currentData()
            }
        elif tb == "Pump":
            vals = {
                "pump_id": carte.w_pump.currentData(),
                "action": carte.w_pump_action.currentText(),
                "debit": carte.w_debit.value(),
                "unite": carte.w_unite_debit.currentText()
            }
        elif tb == "Pause":
            vals = {
                "duree": {
                    "valeur": carte.w_duree.value(),
                    "unite": carte.w_unite.currentText()
                }
            }

        idx = self.layout_blocs.indexOf(carte)
        nouvelle_carte = BlockCard(tb, self, vals)
        self.layout_blocs.insertWidget(idx + 1, nouvelle_carte)
        self.renumeroter_blocs()

    def supprimer_bloc(self, carte: BlockCard):
        carte.timer_pulse.stop()
        carte.setParent(None)
        carte.deleteLater()
        self.renumeroter_blocs()

    def extraire_etapes(self) -> list[dict]:
        etapes = []
        for i in range(self.layout_blocs.count() - 1):
            w = self.layout_blocs.itemAt(i).widget()
            if w and hasattr(w, "type_bloc"):
                tb = w.type_bloc
                if tb == "AV201":
                    c_idx = w.w_canal.currentIndex()
                    etapes.append({
                        "type": "AV201",
                        "addr": w.w_addr.currentData(),
                        "canal": "ALL" if c_idx == 4 else (c_idx + 1),
                        "action": w.w_action.currentText()
                    })
                elif tb == "AV801":
                    etapes.append({
                        "type": "AV801",
                        "addr": w.w_addr.currentData(),
                        "port": w.w_port.currentData()
                    })
                elif tb == "Pump":
                    etapes.append({
                        "type": "Pump",
                        "pump_id": w.w_pump.currentData(),
                        "action": w.w_pump_action.currentText(),
                        "debit": w.w_debit.value(),
                        "unite": w.w_unite_debit.currentText()
                    })
                elif tb == "Pause":
                    etapes.append({
                        "type": "Pause",
                        "duree": {
                            "valeur": w.w_duree.value(),
                            "unite": w.w_unite.currentText()
                        }
                    })
        return etapes

    def lancer_sequence(self):
        etapes = self.extraire_etapes()
        if not etapes:
            self.log_demande.emit("⚠️ Aucun bloc configuré dans le séquenceur.")
            return

        if self.auto_clear:
            self.effacer_log_demande.emit()

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.worker = SequenceWorker(self.backend, etapes)
        self.worker.log_seq.connect(self.log_demande.emit)
        self.worker.etape_en_cours.connect(self.definir_etape_active)
        self.worker.termine.connect(self._fin_sequence)
        self.worker.start()

    def arreter_sequence(self):
        if self.worker:
            self.worker.stop()

    def _fin_sequence(self, success: bool, msg: str):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.definir_etape_active(-1)
        self.sequence_terminee.emit()
        self.log_demande.emit(f"🏁 Fin du protocole : {msg}")

    def sauvegarder_sequence(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("btn_export_seq"), "protocole_decliq.json", "JSON (*.json)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.extraire_etapes(), f, indent=4)
                self.log_demande.emit(f"💾 Protocole enregistré : {path}")
            except Exception as e:
                self.log_demande.emit(f"❌ Erreur sauvegarde : {e}")

    def importer_sequence(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("btn_import_seq"), "", "JSON (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    etapes = json.load(f)

                while self.layout_blocs.count() > 1:
                    it = self.layout_blocs.takeAt(0)
                    if it.widget() and it.widget() != self.conteneur.drop_indicator:
                        if hasattr(it.widget(), "timer_pulse"):
                            it.widget().timer_pulse.stop()
                        it.widget().deleteLater()

                for et in etapes:
                    self.ajouter_bloc(et.get("type", "Pause"), et)

                self.renumeroter_blocs()
                self.log_demande.emit(f"📂 Protocole chargé ({len(etapes)} étapes) depuis : {path}")
            except Exception as e:
                self.log_demande.emit(f"❌ Erreur chargement : {e}")