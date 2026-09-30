"""
theme_manager.py - Gestionnaire centralisé des thèmes et des styles pour DecLiq (LIPhy).
- Palette chromatique fluidique P&ID pour le synoptique vectoriel.
- Feuille de style QSS optimisée pour écran de contrôle de banc microfluidique.
- Typographie adaptative et élimination des artefacts de rastérisation Qt.
"""

from PyQt6.QtGui import QColor

# Couleurs normalisées des lignes fluidiques DecLiq
COL_LIQ = QColor("#00f5d4")      # Seringue 1 : Phase liquide / Inoculation (Cyan)
COL_GAZ = QColor("#10b981")      # Seringue 2 : Phase gazeuse / Bulles d'air (Émeraude)
COL_MILIEU = QColor("#fbbf24")   # Milieu de culture / Réservoir tampon (Ambre)
COL_AV801 = QColor("#c77dff")    # Sélecteur rotatif 8-ports (Violet néon)
COL_STOP = QColor("#ff4d6d")     # Voie fermée / STOP fluidique (Corail)


class SynopticPalette(dict):
    """Dictionnaire de palette tolérant aux clés manquantes pour éviter tout plantage."""
    def __init__(self, *args, sombre: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.sombre = sombre

    def __missing__(self, key):
        # Fallback clair et contrasté en mode sombre pour ne jamais perdre un texte
        return QColor("#94a3b8" if self.sombre else "#475569")


def get_synoptic_palette(sombre: bool = True) -> SynopticPalette:
    """Retourne la palette chromatique complète pour synoptic_widget et synoptic_painter."""
    if sombre:
        c_fond = QColor("#0b101b")
        c_surface = QColor("#131b2a")
        c_bordure = QColor("#24334a")
        c_canal = QColor("#1f2c42")
        c_neutre = QColor("#475569")
        c_cadre_vanne = QColor("#162032")
        c_texte_inactif = QColor("#94a3b8")
        c_texte_titre = QColor("#f1f5f9")
        c_fond_puce = QColor("#131d2e")
        c_bord_puce = QColor("#38bdf8")
        c_active = QColor("#00f5d4")
    else:
        c_fond = QColor("#f8fafc")
        c_surface = QColor("#ffffff")
        c_bordure = QColor("#cbd5e1")
        c_canal = QColor("#e2e8f0")
        c_neutre = QColor("#94a3b8")
        c_cadre_vanne = QColor("#e2e8f0")
        c_texte_inactif = QColor("#475569")
        c_texte_titre = QColor("#0f172a")
        c_fond_puce = QColor("#e0f2fe")
        c_bord_puce = QColor("#0284c7")
        c_active = QColor("#0284c7")

    return SynopticPalette({
        # Géométrie de base
        "fond": c_fond,
        "surface": c_surface,
        "bordure": c_bordure,
        "canal": c_canal,
        "neutre": c_neutre,

        # Vannes unitaires et commandes groupées
        "cadre_vanne": c_cadre_vanne,
        "texte_desactif": c_texte_inactif,
        "texte_titre": c_texte_titre,

        # Puce microfluidique PDMS
        "fond_puce": c_fond_puce,
        "bord_puce": c_bord_puce,

        # Lignes et réseaux fluidiques
        "actif": c_active,
        "liq": COL_LIQ,
        "gaz": COL_GAZ,
        "milieu": COL_MILIEU,
        "av801": COL_AV801,
        "stop": COL_STOP,
    }, sombre=sombre)


def get_stylesheet(sombre: bool = True, taille_police: int = 10) -> str:
    """Génère la feuille de style QSS globale de l'interface DecLiq."""
    if sombre:
        c_bg = "#0b101b"
        c_card = "#131b2a"
        c_border = "#24334a"
        c_border_hover = "#38bdf8"
        c_text = "#f1f5f9"
        c_text_muted = "#94a3b8"
        c_accent = "#00f5d4"
        c_input_bg = "#162032"
        c_btn_bg = "#1e293b"
        c_btn_hover = "#334155"
        c_scroll_track = "#0b101b"
        c_scroll_thumb = "#24334a"
    else:
        c_bg = "#f8fafc"
        c_card = "#ffffff"
        c_border = "#cbd5e1"
        c_border_hover = "#0284c7"
        c_text = "#0f172a"
        c_text_muted = "#64748b"
        c_accent = "#0284c7"
        c_input_bg = "#f1f5f9"
        c_btn_bg = "#e2e8f0"
        c_btn_hover = "#cbd5e1"
        c_scroll_track = "#f8fafc"
        c_scroll_thumb = "#cbd5e1"

    return f"""
    /* Configuration générale */
    QWidget {{
        background-color: {c_bg};
        color: {c_text};
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        font-size: {taille_police}pt;
    }}

    /* Étiquettes transparentes sans pavé de fond */
    QLabel {{
        background-color: transparent;
        background: transparent;
        color: {c_text};
        padding: 2px 4px;
    }}

    /* Onglets de navigation principaux */
    QTabWidget::pane {{
        border: 1px solid {c_border};
        background-color: {c_card};
        border-radius: 6px;
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: {c_bg};
        color: {c_text_muted};
        border: 1px solid {c_border};
        border-bottom: none;
        padding: 8px 18px;
        margin-right: 4px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: bold;
    }}

    QTabBar::tab:selected {{
        background-color: {c_card};
        color: {c_accent};
        border-color: {c_border};
        border-bottom: 2px solid {c_card};
    }}

    QTabBar::tab:hover:!selected {{
        background-color: {c_btn_bg};
        color: {c_text};
    }}

    /* Encadrés QGroupBox (Style Card instrumentale) */
    QGroupBox {{
        background-color: {c_card};
        border: 1px solid {c_border};
        border-radius: 6px;
        margin-top: 10px;
        padding: 28px 12px 12px 12px;
        font-weight: bold;
    }}

    QGroupBox::title {{
        subcontrol-origin: padding;
        subcontrol-position: top left;
        left: 12px;
        top: 8px;
        padding: 0px;
        color: {c_accent};
        background-color: transparent;
        background: transparent;
    }}

    /* Boutons standards */
    QPushButton {{
        background-color: {c_btn_bg};
        border: 1px solid {c_border};
        border-radius: 4px;
        color: {c_text};
        padding: 6px 14px;
        font-weight: 500;
    }}

    QPushButton:hover {{
        background-color: {c_btn_hover};
        border-color: {c_border_hover};
    }}

    QPushButton:pressed {{
        background-color: {c_input_bg};
        border-color: {c_accent};
    }}

    QPushButton:disabled {{
        background-color: transparent;
        border-color: {c_border};
        color: {c_text_muted};
    }}

    /* Champs de saisie numérique et spinboxes */
    QSpinBox, QDoubleSpinBox, QLineEdit {{
        background-color: {c_input_bg};
        border: 1px solid {c_border};
        border-radius: 4px;
        padding: 5px 8px;
        color: {c_text};
    }}

    QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{
        border-color: {c_border_hover};
    }}

    QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
        border: 1px solid {c_accent};
    }}

    /* Menus déroulants (QComboBox / DecLiqComboBox) */
    QComboBox {{
        background-color: {c_input_bg};
        border: 1px solid {c_border};
        border-radius: 4px;
        padding: 5px 30px 5px 10px;
        color: {c_text};
        min-height: 22px;
    }}

    QComboBox:hover {{
        border-color: {c_border_hover};
    }}

    QComboBox:focus {{
        border: 1px solid {c_accent};
    }}

    /* Neutralisation de la flèche native Windows */
    QComboBox::drop-down {{
        border: none;
        width: 0px;
        background: transparent;
    }}

    QComboBox::down-arrow {{
        image: none;
        width: 0px;
        height: 0px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {c_card};
        border: 1px solid {c_border};
        selection-background-color: {c_btn_hover};
        selection-color: {c_accent};
        color: {c_text};
        outline: none;
        padding: 4px;
    }}

    /* Cases à cocher (QCheckBox) */
    QCheckBox {{
        spacing: 8px;
        color: {c_text};
        background: transparent;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 3px;
        border: 1px solid {c_border};
        background-color: {c_input_bg};
    }}

    QCheckBox::indicator:hover {{
        border-color: {c_border_hover};
    }}

    QCheckBox::indicator:checked {{
        background-color: {c_accent};
        border-color: {c_accent};
    }}

    /* Boutons radio (QRadioButton) */
    QRadioButton {{
        spacing: 8px;
        color: {c_text};
        background: transparent;
    }}

    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 8px;
        border: 1px solid {c_border};
        background-color: {c_input_bg};
    }}

    QRadioButton::indicator:hover {{
        border-color: {c_border_hover};
    }}

    QRadioButton::indicator:checked {{
        background-color: {c_card};
        border: 5px solid {c_accent};
    }}

    /* Console de journalisation */
    QTextEdit {{
        background-color: {c_input_bg};
        border: 1px solid {c_border};
        border-radius: 4px;
        color: {c_text};
        font-family: 'Consolas', 'Cascadia Code', monospace;
        font-size: {max(8, taille_police - 1)}pt;
        padding: 6px;
    }}

    /* Barres de défilement (QScrollBar) */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 12px;
        margin: 2px 4px 2px 0px; /* Dégage 4 px à droite pour ne plus toucher le bord */
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical {{
        background-color: {c_scroll_thumb};
        min-height: 24px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {c_border_hover};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
        border: none;
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: transparent;
        height: 12px;
        margin: 0px 2px 4px 2px;
        border-radius: 4px;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {c_scroll_thumb};
        min-width: 24px;
        border-radius: 4px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {c_border_hover};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
        border: none;
        width: 0px;
    }}

    /* Séparateur de panneau (QSplitter) */
    QSplitter::handle:horizontal {{
        background-color: {c_border};
        margin: 0px 4px; /* Laisse 4 px de vide de chaque côté de la ligne séparatrice */
    }}

    QSplitter::handle:horizontal:hover {{
        background-color: {c_accent};
    }}
    """