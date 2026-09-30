"""
ui_components.py - Composants d'interface réutilisables pour DecLiq (LIPhy).
Centralise les widgets graphiques vectoriels, les champs de saisie tolérants,
les poignées de drag-and-drop du séquenceur et le dialogue de consigne de débit.
"""

from PyQt6.QtWidgets import (
    QWidget, QDoubleSpinBox, QFrame, QAbstractButton, QApplication, 
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QMimeData, QRectF
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QCursor, QDrag, QPixmap, 
    QKeyEvent, QPainterPath
)
from i18n import tr


class DecLiqDoubleSpinBox(QDoubleSpinBox):
    """
    QDoubleSpinBox d'instrumentation :
    - Tolérance virgule/point : accepte '.' et ',' indifféremment (clavier, pavé num, copier-coller).
    - Protection molette : ignore le scroll si le champ n'a pas le focus actif.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.text() in ('.', ','):
            self.lineEdit().insert(self.locale().decimalPoint())
            return
        super().keyPressEvent(event)

    def validate(self, input_str: str, pos: int):
        sep = self.locale().decimalPoint()
        alt_sep = '.' if sep == ',' else ','
        normalized = input_str.replace(alt_sep, sep)
        state, _, _ = super().validate(normalized, pos)
        return (state, input_str, pos)

    def fixup(self, input_str: str) -> str:
        sep = self.locale().decimalPoint()
        alt_sep = '.' if sep == ',' else ','
        return super().fixup(input_str.replace(alt_sep, sep))

    def valueFromText(self, text: str) -> float:
        propre = text.replace(self.suffix(), "").replace(self.prefix(), "").strip()
        propre = propre.replace(",", ".")
        try:
            return float(propre)
        except ValueError:
            return 0.0


class DecLiqComboBox(QComboBox):
    """
    Menu déroulant d'instrumentation :
    - Molette inactive tant que le menu est fermé (sécurité anti-déréglage sur le banc).
    - Molette active dans la liste déroulante une fois ouverte.
    - Affordance visuelle : séparateur vertical et chevron vectoriel rétroéclairé.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.view() and self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        w_btn = 26.0

        # Trait séparateur délimitant le bouton
        col_bordure = QColor("#24334a") if self.isEnabled() else QColor("#1e293b")
        p.setPen(QPen(col_bordure, 1))
        p.drawLine(int(w - w_btn), 5, int(w - w_btn), h - 5)

        # Chevron indicateur
        cx = w - (w_btn / 2.0)
        cy = h / 2.0

        if not self.isEnabled():
            col_fleche = QColor("#475569")
        elif self.underMouse() or self.hasFocus():
            col_fleche = QColor("#00f5d4")
        else:
            col_fleche = QColor("#94a3b8")

        pen = QPen(col_fleche, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        d = 3.5
        path = QPainterPath()
        path.moveTo(cx - d, cy - 2.0)
        path.lineTo(cx, cy + 2.5)
        path.lineTo(cx + d, cy - 2.0)
        p.drawPath(path)


class FlowRateDialog(QDialog):
    """Dialogue modal de consigne de débit pour les pousse-seringues."""
    def __init__(self, nom_seringue: str, debit_actuel: float, unite_actuelle: str, en_marche: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg_flow_title", nom=nom_seringue, default=f"Consigne — {nom_seringue}"))
        self.setFixedWidth(320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl_txt = tr("dlg_flow_lbl", nom=nom_seringue, default=f"Débit pour {nom_seringue} :")
        layout.addWidget(QLabel(f"<b>{lbl_txt}</b>"))

        h_lay = QHBoxLayout()
        self.sp_debit = DecLiqDoubleSpinBox()
        self.sp_debit.setRange(0.001, 50000.0)
        self.sp_debit.setValue(debit_actuel)
        self.sp_debit.setDecimals(3)
        self.sp_debit.setSingleStep(0.05)

        self.cb_unite = DecLiqComboBox()
        self.cb_unite.addItems(["µL/min", "mL/min", "nL/min", "µL/h", "mL/h"])
        idx_u = self.cb_unite.findText(unite_actuelle)
        if idx_u >= 0:
            self.cb_unite.setCurrentIndex(idx_u)
        
        # Sécurité synoptique : unité figée si la pompe tourne déjà
        self.cb_unite.setEnabled(not en_marche)
        
        self.cb_unite.currentIndexChanged.connect(self._adapter_spinbox)
        self._adapter_spinbox()

        h_lay.addWidget(self.sp_debit)
        h_lay.addWidget(self.cb_unite)
        layout.addLayout(h_lay)

        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _adapter_spinbox(self):
        u = self.cb_unite.currentText()
        if u == "µL/min":
            self.sp_debit.setRange(0.001, 1000.0)
            self.sp_debit.setDecimals(3)
            self.sp_debit.setSingleStep(0.05)
        elif u == "mL/min":
            self.sp_debit.setRange(0.001, 100.0)
            self.sp_debit.setDecimals(3)
            self.sp_debit.setSingleStep(0.1)
        elif u == "nL/min":
            self.sp_debit.setRange(0.1, 50000.0)
            self.sp_debit.setDecimals(1)
            self.sp_debit.setSingleStep(10.0)
        elif u == "µL/h":
            self.sp_debit.setRange(0.1, 20000.0)
            self.sp_debit.setDecimals(2)
            self.sp_debit.setSingleStep(1.0)
        elif u == "mL/h":
            self.sp_debit.setRange(0.001, 60.0)
            self.sp_debit.setDecimals(4)
            self.sp_debit.setSingleStep(0.01)

    def get_valeurs(self) -> tuple[float, str]:
        return self.sp_debit.value(), self.cb_unite.currentText()


class DragHandle(QWidget):
    """Poignée de préhension texturée (3 barres de grip) pour réordonner les étapes."""
    def __init__(self, parent_card):
        super().__init__()
        self.parent_card = parent_card
        self.setFixedSize(28, 34)
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        self.setToolTip(tr("tip_drag", default="Glisser-déposer pour réordonner"))
        self._drag_start_pos = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()

        survol = self.underMouse()
        if survol:
            painter.setBrush(QBrush(QColor(0, 180, 216, 40)))
            painter.setPen(QPen(QColor(0, 180, 216, 100), 1))
            painter.drawRoundedRect(QRectF(2, 2, r.width() - 4, r.height() - 4), 3, 3)

        painter.setBrush(QBrush(QColor("#00f5d4") if survol else QColor("#5c677d")))
        painter.setPen(Qt.PenStyle.NoPen)

        w_bar = 14
        h_bar = 2.2
        x_bar = (r.width() - w_bar) / 2
        y_start = (r.height() - (3 * h_bar + 2 * 3.5)) / 2

        for i in range(3):
            y = y_start + i * (h_bar + 3.5)
            painter.drawRoundedRect(QRectF(x_bar, y, w_bar, h_bar), 1.0, 1.0)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self._drag_start_pos:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self.parent_card)
        mime = QMimeData()
        mime.setData("application/x-decliq-step", b"step")

        idx_actuel = self.parent_card.parent_panel.layout_blocs.indexOf(self.parent_card)
        mime.setText(str(idx_actuel))
        drag.setMimeData(mime)

        carte_pixmap = self.parent_card.grab()
        pixmap_transparent = QPixmap(carte_pixmap.size())
        pixmap_transparent.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap_transparent)
        painter.setOpacity(0.75)
        painter.drawPixmap(0, 0, carte_pixmap)
        painter.end()

        drag.setPixmap(pixmap_transparent)
        drag.setHotSpot(event.pos())

        self.parent_card.parent_panel.conteneur.commencer_drag()
        drag.exec(Qt.DropAction.MoveAction)
        self.parent_card.parent_panel.conteneur.terminer_drag()
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))


class ActionButton(QAbstractButton):
    """Bouton vectoriel anti-aliasé pour dupliquer ('dup') ou supprimer ('del') une étape."""
    def __init__(self, mode="dup", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setFixedSize(28, 28)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(tr("tip_dup", default="Dupliquer l'étape") if mode == "dup" else tr("tip_del", default="Supprimer l'étape"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()

        if self.isDown():
            bg = QColor("#1e293b" if self.mode == "dup" else "#4a121a")
            border = QColor("#00b4d8" if self.mode == "dup" else "#ff4d6d")
        elif self.underMouse():
            bg = QColor("#1f2937" if self.mode == "dup" else "#3f131a")
            border = QColor("#00b4d8" if self.mode == "dup" else "#ff4d6d")
        else:
            bg = QColor("#161a22")
            border = QColor("#2b3240")

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.2 if self.underMouse() else 1.0))
        painter.drawRoundedRect(QRectF(1, 1, r.width() - 2, r.height() - 2), 4, 4)

        if self.mode == "dup":
            c_icon = QColor("#00f5d4" if self.underMouse() else "#8d99ae")
            painter.setPen(QPen(c_icon, 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(7, 6, 9, 11), 1, 1)
            painter.setBrush(QBrush(bg))
            painter.drawRoundedRect(QRectF(10, 9, 9, 11), 1, 1)
        else:
            c_icon = QColor("#ff4d6d" if self.underMouse() else "#8d99ae")
            painter.setPen(QPen(c_icon, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            d = 9.0
            painter.drawLine(int(d), int(d), int(r.width() - d), int(r.height() - d))
            painter.drawLine(int(r.width() - d), int(d), int(d), int(r.height() - d))
        painter.end()


class DropIndicator(QFrame):
    """Ligne lumineuse intercalée dynamiquement pendant le déplacement."""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(4)
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 transparent, stop:0.2 #00f5d4, stop:0.8 #00f5d4, stop:1 transparent);
                border-radius: 2px;
                margin: 1px 12px;
            }
        """)