"""
synoptic_painter.py - Moteur de tracé vectoriel P&ID pour DecLiq (LIPhy).
- Seringues Hamilton Gastight et raccords Luer-Lock PEEK.
- Réservoir borosilicaté avec tube plongeur descendant jusqu'au fond.
- Vannes AV201 3-voies, commandes groupées ALL et sélecteur rotatif AV801.
- Internationalisation intégrale (titres, sens, états et réservoir).
"""
import math
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, 
                         QPolygonF, QLinearGradient, QPainterPath)

from theme_manager import COL_LIQ, COL_GAZ, COL_MILIEU, COL_AV801, get_synoptic_palette
from i18n import tr


def dessiner_cartouche_seringue(p: QPainter, pid: int, x: float, y_center: float, w: float, h_bar: float, 
                               scale: float, etat_pompe: dict, zones: dict, mode_sombre: bool, 
                               animations_actives: bool, phase_flux: float):
    p.save()
    pal = get_synoptic_palette(mode_sombre)
    connecte = etat_pompe.get("connecte", False)
    en_marche = etat_pompe.get("en_marche", False)
    debit = etat_pompe.get("debit", 0.25)
    unite = etat_pompe.get("unite", "µL/min")
    sens = etat_pompe.get("sens", "withdraw")

    col = COL_LIQ if pid == 1 else COL_GAZ
    y_cyl = y_center - (h_bar / 2.0)

    # 1. En-tête résolu à la volée selon la langue active
    p.setFont(QFont("Segoe UI", max(7, int(8.2 * scale)), QFont.Weight.Bold))
    p.setPen(QPen(col if connecte else pal["texte_desactif"]))
    nom_affiche = tr(f"pump_{pid}_short", default=etat_pompe.get("nom", f"Seringue {pid}"))
    p.drawText(QRectF(x, y_cyl - int(20 * scale), w, int(16 * scale)), 
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, nom_affiche)

    # 2. Dimensions seringue Hamilton
    x_plunger_head = x + int(2 * scale)
    x_flange = x + int(14 * scale)
    x_cyl_left = x_flange + int(4 * scale)
    w_luer = int(8 * scale)
    x_tip = x + w
    x_cyl_right = x_tip - w_luer
    w_barrel = x_cyl_right - x_cyl_left
    x_seal = x_cyl_left + int(28 * scale)

    # Tige et poussoir
    p.setPen(QPen(QColor("#94a3b8"), max(1, int(1.8 * scale))))
    p.drawLine(QPointF(x_plunger_head + int(3 * scale), y_center), QPointF(x_seal, y_center))
    p.setBrush(QBrush(QColor("#cbd5e1")))
    p.setPen(QPen(QColor("#64748b"), 1))
    p.drawRoundedRect(QRectF(x_plunger_head, y_center - (h_bar * 0.45), int(3 * scale), h_bar * 0.9), 1, 1)

    # Collerette
    p.setBrush(QBrush(QColor(148, 163, 184, 85)))
    p.setPen(QPen(QColor("#64748b"), 1))
    p.drawRoundedRect(QRectF(x_flange, y_center - (h_bar * 0.65), int(4 * scale), h_bar * 1.3), 1.5, 1.5)

    # Corps cylindrique en verre
    r_barrel = QRectF(x_cyl_left, y_cyl, w_barrel, h_bar)
    grad_verre = QLinearGradient(x_cyl_left, y_cyl, x_cyl_left, y_cyl + h_bar)
    if mode_sombre:
        grad_verre.setColorAt(0.0, QColor(30, 41, 59, 160))
        grad_verre.setColorAt(0.5, QColor(15, 23, 42, 190))
        grad_verre.setColorAt(1.0, QColor(30, 41, 59, 160))
    else:
        grad_verre.setColorAt(0.0, QColor(241, 245, 249, 180))
        grad_verre.setColorAt(0.5, QColor(255, 255, 255, 220))
        grad_verre.setColorAt(1.0, QColor(241, 245, 249, 180))

    p.setBrush(QBrush(grad_verre))
    p.setPen(QPen(col if (connecte and en_marche) else pal["neutre"], 1.3 if (connecte and en_marche) else 1.0))
    p.drawRoundedRect(r_barrel, 2, 2)

    if connecte:
        c_fluid = col.darker(145) if mode_sombre else col.lighter(130)
        p.setBrush(QBrush(c_fluid))
        p.setPen(Qt.PenStyle.NoPen)

        path_fluide = QPainterPath()
        path_fluide.moveTo(x_seal, y_cyl + 1.5)
        path_fluide.quadTo(x_seal + int(2.5 * scale), y_center, x_seal, y_cyl + h_bar - 1.5)
        path_fluide.lineTo(x_cyl_right, y_cyl + h_bar - 1.5)
        path_fluide.lineTo(x_cyl_right, y_cyl + 1.5)
        path_fluide.closeSubpath()
        p.drawPath(path_fluide)

        # Joint PTFE
        p.setBrush(QBrush(QColor("#0f172a")))
        p.setPen(QPen(QColor("#334155"), 0.8))
        p.drawRoundedRect(QRectF(x_seal - int(6 * scale), y_cyl + 1.2, int(6 * scale), h_bar - 2.4), 1.2, 1.2)
        p.setPen(QPen(QColor("#475569"), 1))
        p.drawLine(QPointF(x_seal - int(3 * scale), y_cyl + 2), QPointF(x_seal - int(3 * scale), y_cyl + h_bar - 2))

        # Graduations
        p.setPen(QPen(QColor(255, 255, 255, 80) if mode_sombre else QColor(0, 0, 0, 80), 1))
        for i in range(1, 6):
            gx = x_cyl_left + i * (w_barrel / 6.0)
            if gx > x_seal:
                p.drawLine(QPointF(gx, y_cyl + 1.5), QPointF(gx, y_cyl + 5))
                p.drawLine(QPointF(gx, y_cyl + h_bar - 5), QPointF(gx, y_cyl + h_bar - 1.5))

        # Reflet spéculaire
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 45)))
        p.drawRoundedRect(QRectF(x_cyl_left + 1, y_cyl + 2, w_barrel - 2, int(3 * scale)), 1, 1)

        # Bulles de flux
        if en_marche and animations_actives:
            p.save()
            nb_p = 3
            l_fluide = x_cyl_right - x_seal - int(8 * scale)
            r_part = max(1.5, 2.2 * scale)
            for i in range(nb_p):
                frac = (phase_flux + i / nb_p) % 1.0
                px = (x_cyl_right - int(4 * scale) - frac * l_fluide) if (sens == "withdraw") else (x_seal + int(4 * scale) + frac * l_fluide)
                p.setBrush(QBrush(QColor(255, 255, 255, 225)))
                p.setPen(QPen(col.lighter(130), 0.8))
                p.drawEllipse(QPointF(px, y_center), r_part, r_part)
            p.restore()
    else:
        p.setFont(QFont("Segoe UI", max(6, int(7.5 * scale)), QFont.Weight.Normal))
        p.setPen(QPen(pal["texte_desactif"]))
        p.drawText(r_barrel, Qt.AlignmentFlag.AlignCenter, "OFF")

    # 3. Embout PEEK
    h_cone = h_bar * 0.40
    r_cone = QPolygonF([
        QPointF(x_cyl_right, y_center - (h_bar * 0.28)),
        QPointF(x_cyl_right + w_luer * 0.5, y_center - (h_cone * 0.5)),
        QPointF(x_tip, y_center - int(1.8 * scale)),
        QPointF(x_tip, y_center + int(1.8 * scale)),
        QPointF(x_cyl_right + w_luer * 0.5, y_center + (h_cone * 0.5)),
        QPointF(x_cyl_right, y_center + (h_bar * 0.28))
    ])
    p.setBrush(QBrush(QColor("#475569")))
    p.setPen(QPen(QColor("#334155"), 1))
    p.drawPolygon(r_cone)

    # 4. Commandes Ligne 1 : Sens
    r_sens = zones.get((pid, "btn_sens"))
    if r_sens:
        est_aspir = (sens == "withdraw")
        bg_sens = QColor("#082f49" if est_aspir else "#451a03") if mode_sombre else QColor("#e0f2fe" if est_aspir else "#ffedd5")
        b_sens = col if est_aspir else QColor("#f59e0b")
        p.setBrush(QBrush(bg_sens if connecte else pal["fond"]))
        p.setPen(QPen(b_sens if connecte else pal["neutre"], 1.2 if connecte else 1.0))
        p.drawRoundedRect(r_sens, 3, 3)
        p.setFont(QFont("Segoe UI", max(6, int(6.8 * scale)), QFont.Weight.Bold))
        p.setPen(QPen(b_sens if connecte else pal["texte_desactif"]))
        p.drawText(r_sens, Qt.AlignmentFlag.AlignCenter, tr("sens_wdr") if est_aspir else tr("sens_inf"))

    # 5. Commandes Ligne 1 : Débit
    r_badge = zones.get((pid, "badge_debit"))
    if r_badge:
        p.setBrush(QBrush(QColor(15, 23, 42, 200) if mode_sombre else QColor(241, 245, 249)))
        p.setPen(QPen(col if connecte else pal["neutre"], 1.0))
        p.drawRoundedRect(r_badge, 3, 3)
        p.setFont(QFont("Segoe UI", max(6, int(7.0 * scale)), QFont.Weight.Bold if en_marche else QFont.Weight.Normal))
        c_txt = QColor("#10b981") if en_marche else (pal["texte_titre"] if connecte else pal["texte_desactif"])
        p.setPen(QPen(c_txt))
        txt_debit = f"{debit:g} {unite}" if connecte else "--"
        p.drawText(r_badge, Qt.AlignmentFlag.AlignCenter, txt_debit)

    # 6. Commandes Ligne 2 : Run / Stop
    r_btn = zones.get((pid, "btn_toggle"))
    if r_btn:
        if not connecte:
            bg_btn, b_btn, txt_b, c_btn_txt = pal["fond"], pal["neutre"], tr("btn_offline"), pal["texte_desactif"]
        elif en_marche:
            bg_btn, b_btn, txt_b, c_btn_txt = QColor("#7f1d1d"), QColor("#ef4444"), tr("btn_stop"), QColor("#ffffff")
        else:
            bg_btn, b_btn, txt_b, c_btn_txt = QColor("#064e3b"), QColor("#10b981"), tr("btn_run"), QColor("#ffffff")

        p.setBrush(QBrush(bg_btn))
        p.setPen(QPen(b_btn, 1.4 if connecte else 1.0))
        p.drawRoundedRect(r_btn, 4, 4)
        p.setFont(QFont("Segoe UI", max(6, int(7.5 * scale)), QFont.Weight.Bold))
        p.setPen(QPen(c_btn_txt))
        p.drawText(r_btn, Qt.AlignmentFlag.AlignCenter, txt_b)

    p.restore()


def dessiner_reservoir_verre(p: QPainter, x: float, y_cap_top: float, w: float, h: float, scale: float, mode_sombre: bool):
    p.save()
    pal = get_synoptic_palette(mode_sombre)
    h_cap = int(8 * scale)
    y_corps = y_cap_top + h_cap
    h_corps = h - h_cap

    r_corps = QRectF(x, y_corps, w, h_corps)
    grad_verre = QLinearGradient(x, y_corps, x + w, y_corps)
    if mode_sombre:
        grad_verre.setColorAt(0.0, QColor(30, 41, 59, 160))
        grad_verre.setColorAt(0.3, QColor(255, 255, 255, 30))
        grad_verre.setColorAt(0.6, QColor(15, 23, 42, 190))
        grad_verre.setColorAt(1.0, QColor(30, 41, 59, 160))
    else:
        grad_verre.setColorAt(0.0, QColor(241, 245, 249, 180))
        grad_verre.setColorAt(0.3, QColor(255, 255, 255, 220))
        grad_verre.setColorAt(0.6, QColor(241, 245, 249, 190))
        grad_verre.setColorAt(1.0, QColor(226, 232, 240, 180))

    p.setBrush(QBrush(grad_verre))
    p.setPen(QPen(COL_MILIEU.lighter(105) if mode_sombre else pal["neutre"], 1.3))
    p.drawRoundedRect(r_corps, 3, 3)

    # Fluide
    y_liq = y_corps + int(h_corps * 0.28)
    c_liq = COL_MILIEU.darker(135) if mode_sombre else COL_MILIEU.lighter(125)
    p.setBrush(QBrush(c_liq))
    p.setPen(Qt.PenStyle.NoPen)

    path_liq = QPainterPath()
    path_liq.moveTo(x + 1.5, y_liq)
    path_liq.quadTo(x + (w / 2.0), y_liq + int(2.5 * scale), x + w - 1.5, y_liq)
    path_liq.lineTo(x + w - 1.5, y_corps + h_corps - 1.5)
    path_liq.lineTo(x + 1.5, y_corps + h_corps - 1.5)
    path_liq.closeSubpath()
    p.drawPath(path_liq)

    # Graduations
    p.setPen(QPen(QColor(255, 255, 255, 75) if mode_sombre else QColor(0, 0, 0, 75), 1))
    for i in range(1, 5):
        gy = y_corps + i * (h_corps / 5.0)
        p.drawLine(QPointF(x + w - int(6 * scale), gy), QPointF(x + w - int(2 * scale), gy))

    # Reflet
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(255, 255, 255, 40)))
    p.drawRoundedRect(QRectF(x + int(3 * scale), y_corps + 2, int(3 * scale), h_corps - 4), 1, 1)

    # Bouchon bleu
    w_cap = w + int(4 * scale)
    r_cap = QRectF(x - int(2 * scale), y_cap_top, w_cap, h_cap)
    grad_cap = QLinearGradient(r_cap.left(), y_cap_top, r_cap.right(), y_cap_top)
    grad_cap.setColorAt(0.0, QColor("#0369a1"))
    grad_cap.setColorAt(0.5, QColor("#0ea5e9"))
    grad_cap.setColorAt(1.0, QColor("#0369a1"))
    p.setBrush(QBrush(grad_cap))
    p.setPen(QPen(QColor("#38bdf8"), 1))
    p.drawRoundedRect(r_cap, 2, 2)

    # Raccord PEEK
    x_dip = x + (w // 2.0)
    p.setBrush(QBrush(QColor("#475569")))
    p.setPen(QPen(QColor("#334155"), 1))
    p.drawRect(QRectF(x_dip - int(3 * scale), y_cap_top - int(3 * scale), int(6 * scale), int(3 * scale)))

    # Tube plongeur jusqu'au fond
    y_fond = y_corps + h_corps - int(2 * scale)
    p.setPen(QPen(QColor(255, 255, 255, 220), max(1.5, int(1.8 * scale)), Qt.PenStyle.SolidLine))
    p.drawLine(QPointF(x_dip, y_cap_top), QPointF(x_dip, y_fond))

    p.setFont(QFont("Segoe UI", max(7, int(8.5 * scale)), QFont.Weight.Bold))
    p.setPen(QPen(COL_MILIEU))
    p.drawText(QRectF(x - 20, y_corps + h_corps + int(4 * scale), w + 40, int(14 * scale)), 
               Qt.AlignmentFlag.AlignCenter, tr("reservoir"))
    p.restore()


def dessiner_vanne(p: QPainter, r_box: QRectF, etat: int, label: str, addr: int, scale: float, 
                   zones_vannes: dict, is_all: bool, mode_sombre: bool):
    p.save()
    est_d = (addr == 0x08)
    pal = get_synoptic_palette(mode_sombre)
    f_btn = max(6, int((8.0 if is_all else 8.5) * scale))

    for target in [1, 2, 3]:
        cle_z = (addr, "ALL" if is_all else int(label[-1]), target)
        rz = zones_vannes.get(cle_z)
        if not rz:
            continue
        actif = (etat == target)
        if actif:
            if target == 1:
                bg, fg = (QColor("#78350f"), QColor("#fbbf24")) if est_d else (QColor("#005f73"), QColor("#00f5d4"))
            elif target == 2:
                bg, fg = QColor("#780000"), QColor("#ff4d6d")
            else:
                bg, fg = (QColor("#4a044e"), QColor("#e0aaff")) if est_d else (QColor("#1b4332"), QColor("#52b788"))
            bordure = fg
        else:
            bg = pal.get("cadre_vanne", QColor("#162032") if mode_sombre else QColor("#e2e8f0"))
            fg = pal.get("texte_desactif", QColor("#94a3b8") if mode_sombre else QColor("#475569"))
            bordure = QColor("#2a374d") if mode_sombre else QColor("#cbd5e1")

        p.setBrush(QBrush(bg))
        p.setPen(QPen(bordure, 1.5 if actif else 1.0, Qt.PenStyle.SolidLine if (actif or not is_all) else Qt.PenStyle.DashLine))
        p.drawRoundedRect(rz.adjusted(1, 1, -1, -1), 3, 3)

        p.setFont(QFont("Segoe UI", f_btn, QFont.Weight.Bold if actif else QFont.Weight.Normal))
        p.setPen(QPen(fg))
        p.drawText(rz, Qt.AlignmentFlag.AlignCenter, "S1" if target == 1 else ("STOP" if target == 2 else "S3"))

    if is_all:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(COL_LIQ if not est_d else COL_AV801, 1, Qt.PenStyle.DotLine))
        p.drawRoundedRect(r_box.adjusted(-2, -2, 2, 2), 4, 4)

    f_lbl = max(7, int((8.5 if is_all else 9.5) * scale))
    p.setFont(QFont("Segoe UI", f_lbl, QFont.Weight.Bold))
    c_lbl = (COL_LIQ if not est_d else COL_AV801) if is_all else (pal.get("texte_titre", QColor("#e2e8f0")) if etat is not None else pal.get("texte_desactif", QColor("#94a3b8")))
    txt_l = label if (is_all or etat is not None) else f"{label} (?)"
    p.setPen(QPen(c_lbl))
    p.drawText(QRectF(r_box.center().x() - 40, r_box.top() - int(16 * scale), 80, int(15 * scale)), Qt.AlignmentFlag.AlignCenter, txt_l)
    p.restore()


def dessiner_av801(p: QPainter, cx: float, cy: float, rayon: float, port_b: int, scale: float, 
                   pal: dict, zones_selecteur: dict, av801_angle_actuel: float, av801_en_rotation: bool):
    p.save()

    # 1. Liaisons radiales vers les 8 voies (tracées en premier, arrêtées au bord extérieur de la bulle)
    for pt, rp in zones_selecteur.items():
        rad = math.radians(-130.0 + (pt - 1) * (260.0 / 7.0))
        est_act = (not av801_en_rotation and port_b == pt)
        
        col_ligne = COL_AV801 if est_act else pal.get("neutre", QColor("#475569"))
        p.setPen(QPen(col_ligne, max(2, int(2.2 * scale)) if est_act else max(1, int(1.2 * scale)),
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))

        # Raccord tangentiel : du bord du cadran au bord intérieur du satellite
        r_sat = rp.width() / 2.0
        x_dial = cx + rayon * math.cos(rad)
        y_dial = cy + rayon * math.sin(rad)
        x_sat_in = rp.center().x() - r_sat * math.cos(rad)
        y_sat_in = rp.center().y() - r_sat * math.sin(rad)

        p.drawLine(QPointF(x_dial, y_dial), QPointF(x_sat_in, y_sat_in))

    # 2. Pastilles satellites 1 à 8 (opaques, masquant tout artefact sous-jacent)
    for pt, rp in zones_selecteur.items():
        est_act = (not av801_en_rotation and port_b == pt)
        bg = QColor("#3c096c") if est_act else pal.get("cadre_vanne", QColor("#162032"))
        border = COL_AV801 if est_act else pal.get("neutre", QColor("#475569"))

        p.setBrush(QBrush(bg))
        p.setPen(QPen(border, 2 if est_act else 1))
        p.drawEllipse(rp)

        p.setFont(QFont("Segoe UI", max(7, int(8.5 * scale)), QFont.Weight.Bold))
        p.setPen(QPen(border if est_act else pal.get("texte_titre", QColor("#e2e8f0"))))
        p.drawText(rp, Qt.AlignmentFlag.AlignCenter, str(pt))

    # 3. Cadran central AV801
    p.setBrush(QBrush(pal.get("fond", QColor("#0b101b"))))
    p.setPen(QPen(COL_AV801, 2))
    p.drawEllipse(QPointF(cx, cy), rayon, rayon)

    # 4. Aiguille indicatrice interne vers la voie sélectionnée
    ang = av801_angle_actuel if av801_angle_actuel is not None else ((-130.0 + (port_b - 1) * (260.0 / 7.0)) if port_b is not None else None)
    if ang is not None and port_b is not None:
        r = math.radians(ang)
        p.setPen(QPen(COL_AV801, max(2, int(2.5 * scale)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(cx + (rayon - 4) * math.cos(r), cy + (rayon - 4) * math.sin(r)))
        p.drawLine(QPointF(cx - rayon, cy), QPointF(cx, cy))

    # Libellé central
    p.setFont(QFont("Segoe UI", max(7, int(8.5 * scale)), QFont.Weight.Bold))
    p.setPen(QPen(pal.get("texte_titre", QColor("#e2e8f0"))))
    p.drawText(QRectF(cx - 30, cy - int(12 * scale), 60, int(14 * scale)), Qt.AlignmentFlag.AlignCenter, "AV801")

    p.setFont(QFont("Segoe UI", max(6, int(7.5 * scale))))
    p.setPen(QPen(COL_AV801 if port_b else pal.get("texte_desactif", QColor("#94a3b8"))))
    txt_p = tr("port_active", port=port_b) if port_b is not None else tr("port_unknown")
    p.drawText(QRectF(cx - 40, cy + 2, 80, int(14 * scale)), Qt.AlignmentFlag.AlignCenter, txt_p)

    p.restore()


def dessiner_bulles_flux(p: QPainter, x_in: float, x_out: float, y: float, col: QColor, 
                         scale: float, phase: float, vers_gauche: bool = True):
    p.save()
    longueur = x_out - x_in
    nb_bulles = 3
    r_bulle = max(2.0, 3.2 * scale)

    for i in range(nb_bulles):
        frac = (phase + i / nb_bulles) % 1.0
        bx = (x_out - frac * longueur) if vers_gauche else (x_in + frac * longueur)

        p.setBrush(QBrush(QColor(255, 255, 255, 220)))
        p.setPen(QPen(col.darker(120), 1.2))
        p.drawEllipse(QPointF(bx, y), r_bulle, r_bulle)

        p.setBrush(QBrush(QColor(255, 255, 255, 255)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(bx - 0.7 * scale, y - 0.7 * scale), r_bulle * 0.4, r_bulle * 0.4)

    p.restore()


def dessiner_fleche_repos(p: QPainter, x: float, y: float, col: QColor, scale: float, vers_gauche: bool = True):
    p.save()
    p.setBrush(QBrush(col))
    p.setPen(Qt.PenStyle.NoPen)
    d = int(4 * scale)
    if vers_gauche:
        p.drawPolygon(QPolygonF([QPointF(x + d, y - d), QPointF(x - d, y), QPointF(x + d, y + d)]))
    else:
        p.drawPolygon(QPolygonF([QPointF(x - d, y - d), QPointF(x + d, y), QPointF(x - d, y + d)]))
    p.restore()