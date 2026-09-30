"""
synoptic_widget.py - Widget synoptique compact pour DecLiq (LIPhy).
- Gestionnaire d'événements (clics, survol, molette).
- Centrage dynamique de la géométrie WP1 (880x580).
- Rendu délégué à synoptic_painter.py et saisie via FlowRateDialog (ui_components.py).
"""
import math
import time
from PyQt6.QtWidgets import QWidget, QDialog
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QCursor

from theme_manager import COL_LIQ, COL_GAZ, COL_MILIEU, COL_AV801, COL_STOP, get_synoptic_palette
from ui_components import FlowRateDialog
import synoptic_painter as sp
from i18n import tr


class SynopticWidget(QWidget):
    demande_toggle_pompe = pyqtSignal(int)
    demande_reglage_pompe = pyqtSignal(int, float, str)
    demande_sens_pompe = pyqtSignal(int, str)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.setMinimumSize(740, 480)
        self.setMouseTracking(True)

        self.echelle_ui = 1.0
        self.mode_sombre = True
        self.animations_actives = True

        self.geo = {}
        self.zones_clic_vannes = {}
        self.zones_clic_selecteur = {}
        self.zones_clic_pompes = {}

        self.etats_pompes = {
            1: {"connecte": False, "en_marche": False, "debit": 0.25, "unite": "µL/min", "sens": "withdraw", "nom": "Seringue 1 [q₁]"},
            2: {"connecte": False, "en_marche": False, "debit": 1.00, "unite": "µL/min", "sens": "withdraw", "nom": "Seringue 2 [q₂]"}
        }

        # Cinématique AV801 & AV201
        self.av801_angle_actuel = None
        self.av801_angle_cible = None
        self.av801_en_rotation = False
        self.av801_vitesse = 260.0

        self.transitions_vannes = {}
        self.etats_connus_vannes = {}
        self.port_connu_av801 = None

        self.phase_flux = {1: 0.0, 2: 0.0}
        self.timer_anim = QTimer(self)
        self.timer_anim.setInterval(25)  # 40 FPS
        self.timer_anim.timeout.connect(self._tick_animation)
        self.dernier_tick = time.time()

        self._recalculer_geometrie()

    def maj_etat_pompe(self, pump_id: int, infos: dict):
        if pump_id in self.etats_pompes:
            self.etats_pompes[pump_id].update(infos)
            self._ajuster_timer_animation()
            self.update()

    def set_mode_sombre(self, sombre: bool):
        self.mode_sombre = sombre
        self.update()

    def set_echelle_ui(self, facteur: float):
        self.echelle_ui = max(0.7, min(1.8, facteur))
        self._recalculer_geometrie()
        self.update()

    def set_animations_actives(self, active: bool):
        self.animations_actives = active
        if not active:
            self.transitions_vannes.clear()
            self.av801_en_rotation = False
            self.av801_angle_actuel = self.av801_angle_cible
            self.timer_anim.stop()
        else:
            self._ajuster_timer_animation()
        self.update()

    def _ajuster_timer_animation(self):
        pompe_en_cours = any(p["en_marche"] and p["connecte"] for p in self.etats_pompes.values())
        besoin = self.animations_actives and (pompe_en_cours or self.av801_en_rotation or bool(self.transitions_vannes))
        if besoin and not self.timer_anim.isActive():
            self.dernier_tick = time.time()
            self.timer_anim.start()
        elif not besoin and self.timer_anim.isActive():
            self.timer_anim.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalculer_geometrie()

    def _recalculer_geometrie(self):
        w, h = self.width(), self.height()
        scale = max(0.70, min(1.50, min(w / 880.0, h / 580.0) * self.echelle_ui))

        w_v, h_v = int(74 * scale), int(72 * scale)
        dec_port = h_v // 3
        h_v_all, r_sel = int(64 * scale), int(40 * scale)
        w_ser, h_bar = int(126 * scale), int(22 * scale)
        l_stub, d_bus = int(22 * scale), int(20 * scale)
        gap_pdms, w_pdms = int(28 * scale), int(58 * scale)
        w_res, h_res = int(40 * scale), int(54 * scale)

        pas_y = h_v + int(24 * scale)
        gap_all = int(34 * scale)
        h_content = int(16 * scale) + h_v_all + gap_all + int(14 * scale) + (3 * pas_y) + h_v + int(24 * scale)
        margin_y = max(int(14 * scale), (h - h_content) // 2)

        y_all = margin_y + int(14 * scale) + (h_v_all // 2)
        y_top = y_all + (h_v_all // 2) + gap_all + int(14 * scale) + (h_v // 2)
        y_canaux = [y_top + i * pas_y for i in range(4)]

        dist_sel = int(98 * scale)
        r_total_av801 = r_sel + int(38 * scale)
        w_content = w_ser + l_stub + d_bus + l_stub + w_v + gap_pdms + w_pdms + gap_pdms + w_v + l_stub + d_bus + dist_sel + r_total_av801
        margin_x = max(int(18 * scale), (w - w_content) // 2)

        x_ser = margin_x
        x_tip = x_ser + w_ser
        x_bus_g_b = x_tip + l_stub
        x_bus_g_v = x_bus_g_b + d_bus
        x_vg_left = x_bus_g_v + l_stub
        x_vg = x_vg_left + (w_v // 2)
        x_vg_right = x_vg_left + w_v

        x_p_in = x_vg_right + gap_pdms
        x_p_out = x_p_in + w_pdms
        x_vd_left = x_p_out + gap_pdms
        x_vd = x_vd_left + (w_v // 2)
        x_vd_right = x_vd_left + w_v

        x_bus_d_b = x_vd_right + l_stub
        x_bus_d_v = x_bus_d_b + d_bus
        cx_8p = x_bus_d_v + dist_sel
        x_tampon = cx_8p - int(10 * scale)

        y_ser1 = (y_canaux[0] + y_canaux[1]) // 2
        y_ser2 = (y_canaux[2] + y_canaux[3]) // 2
        y_av801 = (y_canaux[2] + y_canaux[3]) // 2

        self.geo = {
            "scale": scale, "ep": max(1, int(2 * scale)),
            "w_v": w_v, "h_v": h_v, "h_v_all": h_v_all, "dec_port": dec_port,
            "x_ser": x_ser, "w_ser": w_ser, "h_bar": h_bar, "x_tip": x_tip,
            "x_bus_g_b": x_bus_g_b, "x_bus_g_v": x_bus_g_v,
            "x_vg_left": x_vg_left, "x_vg": x_vg, "x_vg_right": x_vg_right,
            "x_p_in": x_p_in, "x_p_out": x_p_out,
            "x_vd_left": x_vd_left, "x_vd": x_vd, "x_vd_right": x_vd_right,
            "x_bus_d_b": x_bus_d_b, "x_bus_d_v": x_bus_d_v, "x_tampon": x_tampon,
            "y_canaux": y_canaux, "y_ser1": y_ser1, "y_ser2": y_ser2,
            "y_all": y_all, "y_av801": y_av801, "r_sel": r_sel, "cx_8p": cx_8p,
            "w_res": w_res, "h_res": h_res,
        }

        self.zones_clic_vannes.clear()
        self.zones_clic_selecteur.clear()
        self.zones_clic_pompes.clear()

        # Enregistrement des boutons pompes
        for pid in (1, 2):
            y_s = y_ser1 if pid == 1 else y_ser2
            y_cyl = y_s - (h_bar // 2)
            h_r1, h_r2, esp = int(22 * scale), int(24 * scale), int(5 * scale)
            y_r1 = y_cyl + h_bar + int(12 * scale)
            y_r2 = y_r1 + h_r1 + esp
            w_demi = (w_ser - esp) // 2

            self.zones_clic_pompes[(pid, "corps")] = QRectF(x_ser, y_cyl, w_ser, h_bar)
            self.zones_clic_pompes[(pid, "btn_sens")] = QRectF(x_ser, y_r1, w_demi, h_r1)
            self.zones_clic_pompes[(pid, "badge_debit")] = QRectF(x_ser + w_demi + esp, y_r1, w_demi, h_r1)
            self.zones_clic_pompes[(pid, "btn_toggle")] = QRectF(x_ser, y_r2, w_ser, h_r2)

        # Enregistrement des zones vannes
        for addr, x_c in [(0x05, x_vg), (0x08, x_vd)]:
            r_box = QRectF(x_c - (w_v // 2), y_all - (h_v_all // 2), w_v, h_v_all)
            h_part = r_box.height() / 3.0
            for i, et in enumerate([1, 2, 3]):
                self.zones_clic_vannes[(addr, "ALL", et)] = QRectF(r_box.left(), r_box.top() + i * h_part, w_v, h_part)

        for ch in range(1, 5):
            y = y_canaux[ch - 1]
            for addr, x_c in [(0x05, x_vg), (0x08, x_vd)]:
                r_box = QRectF(x_c - (w_v // 2), y - (h_v // 2), w_v, h_v)
                h_part = r_box.height() / 3.0
                for i, et in enumerate([1, 2, 3]):
                    self.zones_clic_vannes[(addr, ch, et)] = QRectF(r_box.left(), r_box.top() + i * h_part, w_v, h_part)

        r_pc, r_pas = r_sel + int(26 * scale), int(12 * scale)
        for p in range(1, 9):
            rad = math.radians(-130.0 + (p - 1) * (260.0 / 7.0))
            px, py = cx_8p + int(r_pc * math.cos(rad)), y_av801 + int(r_pc * math.sin(rad))
            self.zones_clic_selecteur[p] = QRectF(px - r_pas, py - r_pas, r_pas * 2, r_pas * 2)

    def _synchroniser_materiel(self):
        port_b = self.backend.derniers_ports_av801.get(0x09, None)
        if port_b != self.port_connu_av801:
            if port_b is not None:
                cible = (-130.0 + (port_b - 1) * (260.0 / 7.0)) % 360.0
                if self.animations_actives and self.port_connu_av801 is not None and self.av801_angle_actuel is not None:
                    self.av801_angle_cible = cible
                    self.av801_en_rotation = True
                    self.dernier_tick = time.time()
                    if not self.timer_anim.isActive():
                        self.timer_anim.start()
                else:
                    self.av801_angle_actuel = self.av801_angle_cible = cible
                    self.av801_en_rotation = False
            else:
                self.av801_angle_actuel = self.av801_angle_cible = None
                self.av801_en_rotation = False
            self.port_connu_av801 = port_b

        for cle, pos_b in self.backend.dernieres_pos_av201.items():
            pos_act = self.etats_connus_vannes.get(cle, None)
            if pos_b != pos_act:
                if self.animations_actives and pos_act in (1, 3) and pos_b in (1, 3) and pos_act != pos_b:
                    self.transitions_vannes[cle] = {
                        "depart": pos_act, "cible": pos_b,
                        "t_debut": time.time(), "duree_stop": 0.20, "duree_totale": 0.45
                    }
                    self.dernier_tick = time.time()
                    if not self.timer_anim.isActive():
                        self.timer_anim.start()
                self.etats_connus_vannes[cle] = pos_b

    def _tick_animation(self):
        now = time.time()
        dt = now - self.dernier_tick
        self.dernier_tick = now

        for pid in (1, 2):
            p_info = self.etats_pompes[pid]
            if p_info["en_marche"] and p_info["connecte"]:
                debit = p_info.get("debit", 0.25)
                vitesse = max(0.4, min(2.5, 0.4 + 0.3 * math.log10(max(0.01, debit * 10.0))))
                self.phase_flux[pid] = (self.phase_flux[pid] + dt * vitesse) % 1.0

        if self.av801_en_rotation and self.av801_angle_actuel is not None:
            pas = self.av801_vitesse * dt
            delta = (self.av801_angle_cible - self.av801_angle_actuel) % 360.0
            if delta <= pas or delta < 1.0:
                self.av801_angle_actuel = self.av801_angle_cible
                self.av801_en_rotation = False
            else:
                self.av801_angle_actuel = (self.av801_angle_actuel + pas) % 360.0

        termines = [k for k, v in self.transitions_vannes.items() if (now - v["t_debut"]) >= v["duree_totale"]]
        for k in termines:
            del self.transitions_vannes[k]

        self._ajuster_timer_animation()
        self.update()

    def _etat_visuel(self, cle):
        if cle in self.transitions_vannes:
            tr_v = self.transitions_vannes[cle]
            if (time.time() - tr_v["t_debut"]) < tr_v["duree_stop"]:
                return 2
            return tr_v["cible"]
        return self.backend.dernieres_pos_av201.get(cle, None)

    def paintEvent(self, event):
        self._synchroniser_materiel()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        g = self.geo
        pal = get_synoptic_palette(self.mode_sombre)
        p.fillRect(0, 0, self.width(), self.height(), pal["fond"])

        scale, ep = g["scale"], g["ep"]
        r_bridge, r_dot = int(5 * scale), max(2.5, 3.0 * scale)

        # 1. Pousse-seringues
        for pid in (1, 2):
            sp.dessiner_cartouche_seringue(
                p, pid, g["x_ser"], g["y_ser1"] if pid == 1 else g["y_ser2"],
                g["w_ser"], g["h_bar"], scale, self.etats_pompes[pid],
                self.zones_clic_pompes, self.mode_sombre, self.animations_actives, self.phase_flux[pid]
            )

        # 2. Tuyauteries Aval (Gauche)
        p1, p2 = self.etats_pompes[1], self.etats_pompes[2]
        c_l1 = COL_LIQ if p1["connecte"] else pal["neutre"]
        st_l1 = Qt.PenStyle.SolidLine if p1["connecte"] else Qt.PenStyle.DashLine
        c_l2 = COL_GAZ if p2["connecte"] else pal["neutre"]
        st_l2 = Qt.PenStyle.SolidLine if p2["connecte"] else Qt.PenStyle.DashLine

        p.setPen(QPen(c_l1, ep, st_l1))
        p.drawLine(g["x_tip"], g["y_ser1"], g["x_bus_g_b"], g["y_ser1"])
        p.drawLine(g["x_bus_g_b"], g["y_canaux"][0] - g["dec_port"], g["x_bus_g_b"], g["y_canaux"][3] - g["dec_port"])
        if p1["connecte"]:
            p.setBrush(QBrush(c_l1))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(g["x_bus_g_b"], g["y_ser1"]), r_dot, r_dot)

        p.setPen(QPen(c_l2, ep, st_l2))
        p.drawLine(g["x_tip"], g["y_ser2"], g["x_bus_g_b"] - r_bridge, g["y_ser2"])
        p.drawArc(QRectF(g["x_bus_g_b"] - r_bridge, g["y_ser2"] - r_bridge, 2 * r_bridge, 2 * r_bridge), 0, 180 * 16)
        p.drawLine(g["x_bus_g_b"] + r_bridge, g["y_ser2"], g["x_bus_g_v"], g["y_ser2"])
        p.drawLine(g["x_bus_g_v"], g["y_canaux"][0] + g["dec_port"], g["x_bus_g_v"], g["y_canaux"][3] + g["dec_port"])
        if p2["connecte"]:
            p.setBrush(QBrush(c_l2))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(g["x_bus_g_v"], g["y_ser2"]), r_dot, r_dot)

        for ch in range(1, 5):
            y_s1, y_s3 = g["y_canaux"][ch - 1] - g["dec_port"], g["y_canaux"][ch - 1] + g["dec_port"]
            p.setPen(QPen(c_l1, ep, st_l1))
            if p1["connecte"]:
                p.setBrush(QBrush(c_l1))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(g["x_bus_g_b"], y_s1), r_dot, r_dot)
                p.setPen(QPen(c_l1, ep, st_l1))

            if ch == 1:
                p.drawLine(g["x_bus_g_b"], y_s1, g["x_vg_left"], y_s1)
            else:
                p.drawLine(g["x_bus_g_b"], y_s1, g["x_bus_g_v"] - r_bridge, y_s1)
                p.drawArc(QRectF(g["x_bus_g_v"] - r_bridge, y_s1 - r_bridge, 2 * r_bridge, 2 * r_bridge), 0, 180 * 16)
                p.drawLine(g["x_bus_g_v"] + r_bridge, y_s1, g["x_vg_left"], y_s1)

            p.setPen(QPen(c_l2, ep, st_l2))
            p.drawLine(g["x_bus_g_v"], y_s3, g["x_vg_left"], y_s3)
            if p2["connecte"]:
                p.setBrush(QBrush(c_l2))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(g["x_bus_g_v"], y_s3), r_dot, r_dot)

        # 3. Tuyauteries Amont (Droite)
        port_8p = self.backend.derniers_ports_av801.get(0x09, None)
        y_d1_s1, y_d4_s1 = g["y_canaux"][0] - g["dec_port"], g["y_canaux"][3] - g["dec_port"]
        y_top_cap = g["y_ser1"] - (g["h_res"] // 2)

        sp.dessiner_reservoir_verre(p, g["x_tampon"] - (g["w_res"] // 2), y_top_cap, g["w_res"], g["h_res"], scale, self.mode_sombre)

        p.setPen(QPen(COL_MILIEU, ep, Qt.PenStyle.SolidLine))
        p.drawLine(QPointF(g["x_tampon"], y_top_cap), QPointF(g["x_tampon"], y_d1_s1))
        p.drawLine(QPointF(g["x_tampon"], y_d1_s1), QPointF(g["x_bus_d_b"], y_d1_s1))
        p.drawLine(QPointF(g["x_bus_d_b"], y_d1_s1), QPointF(g["x_bus_d_b"], y_d4_s1))

        sp.dessiner_av801(p, g["cx_8p"], g["y_av801"], g["r_sel"], port_8p, scale, pal, 
                          self.zones_clic_selecteur, self.av801_angle_actuel, self.av801_en_rotation)

        p.setPen(QPen(COL_AV801, ep, Qt.PenStyle.SolidLine))
        p.drawLine(QPointF(g["cx_8p"] - g["r_sel"], g["y_av801"]), QPointF(g["x_bus_d_v"], g["y_av801"]))
        p.drawLine(QPointF(g["x_bus_d_v"], g["y_canaux"][0] + g["dec_port"]), QPointF(g["x_bus_d_v"], g["y_canaux"][3] + g["dec_port"]))
        p.setBrush(QBrush(COL_AV801))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(g["x_bus_d_v"], g["y_av801"]), r_dot, r_dot)

        for ch in range(1, 5):
            y_s1, y_s3 = g["y_canaux"][ch - 1] - g["dec_port"], g["y_canaux"][ch - 1] + g["dec_port"]
            p.setPen(QPen(COL_MILIEU, ep, Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(g["x_vd_right"], y_s1), QPointF(g["x_bus_d_b"], y_s1))
            p.setBrush(QBrush(COL_MILIEU))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(g["x_bus_d_b"], y_s1), r_dot, r_dot)

            p.setPen(QPen(COL_AV801, ep, Qt.PenStyle.SolidLine))
            p.setBrush(QBrush(COL_AV801))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(g["x_bus_d_v"], y_s3), r_dot, r_dot)
            p.setPen(QPen(COL_AV801, ep, Qt.PenStyle.SolidLine))

            if ch == 4:
                p.drawLine(QPointF(g["x_vd_right"], y_s3), QPointF(g["x_bus_d_v"], y_s3))
            else:
                p.drawLine(QPointF(g["x_vd_right"], y_s3), QPointF(g["x_bus_d_b"] - r_bridge, y_s3))
                p.drawArc(QRectF(g["x_bus_d_b"] - r_bridge, y_s3 - r_bridge, 2 * r_bridge, 2 * r_bridge), 0, 180 * 16)
                p.drawLine(QPointF(g["x_bus_d_b"] + r_bridge, y_s3), QPointF(g["x_bus_d_v"], y_s3))

        # 4. Commandes groupées ALL
        pref_g, pref_d = tr("prefix_left"), tr("prefix_right")
        eg = [self.backend.dernieres_pos_av201.get((0x05, ch)) for ch in range(1, 5)]
        pos_g_all = eg[0] if len(set(eg)) == 1 and eg[0] is not None else None
        sp.dessiner_vanne(p, QRectF(g["x_vg"] - (g["w_v"] // 2), g["y_all"] - (g["h_v_all"] // 2), g["w_v"], g["h_v_all"]),
                         pos_g_all, f"{pref_g} ALL", 0x05, scale, self.zones_clic_vannes, True, self.mode_sombre)

        ed = [self.backend.dernieres_pos_av201.get((0x08, ch)) for ch in range(1, 5)]
        pos_d_all = ed[0] if len(set(ed)) == 1 and ed[0] is not None else None
        sp.dessiner_vanne(p, QRectF(g["x_vd"] - (g["w_v"] // 2), g["y_all"] - (g["h_v_all"] // 2), g["w_v"], g["h_v_all"]),
                         pos_d_all, f"{pref_d} ALL", 0x08, scale, self.zones_clic_vannes, True, self.mode_sombre)

        p.setPen(QPen(pal["neutre"], 1, Qt.PenStyle.DashLine))
        p.drawLine(g["x_vg"], g["y_all"] + (g["h_v_all"] // 2), g["x_vg"], g["y_canaux"][0] - (g["h_v"] // 2) - int(16 * scale))
        p.drawLine(g["x_vd"], g["y_all"] + (g["h_v_all"] // 2), g["x_vd"], g["y_canaux"][0] - (g["h_v"] // 2) - int(16 * scale))

        # 5. Puce PDMS
        h_puce = (g["y_canaux"][3] - g["y_canaux"][0]) + int(34 * scale)
        r_p = QRectF(g["x_p_in"], g["y_canaux"][0] - int(17 * scale), g["x_p_out"] - g["x_p_in"], h_puce)
        p.setBrush(QBrush(pal["fond_puce"]))
        p.setPen(QPen(pal["bord_puce"], 1, Qt.PenStyle.DashLine))
        p.drawRoundedRect(r_p, 4, 4)
        p.setFont(QFont("Segoe UI", max(6, int(7 * scale)), QFont.Weight.Bold))
        p.setPen(QPen(QColor("#457b9d")))
        p.drawText(r_p.adjusted(0, 4, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "PDMS")

        # 6. Microcanaux continus & Vannes unitaires
        c_pointille = QColor("#64748b") if self.mode_sombre else QColor("#94a3b8")
        pen_pointille = QPen(c_pointille, max(1.2, 1.8 * scale), Qt.PenStyle.DotLine)

        for ch in range(1, 5):
            y = g["y_canaux"][ch - 1]
            pos_g, pos_d = self._etat_visuel((0x05, ch)), self._etat_visuel((0x08, ch))

            r_vg = QRectF(g["x_vg"] - (g["w_v"] // 2), y - (g["h_v"] // 2), g["w_v"], g["h_v"])
            r_vd = QRectF(g["x_vd"] - (g["w_v"] // 2), y - (g["h_v"] // 2), g["w_v"], g["h_v"])
            sp.dessiner_vanne(p, r_vg, pos_g, f"{pref_g}{ch}", 0x05, scale, self.zones_clic_vannes, False, self.mode_sombre)
            sp.dessiner_vanne(p, r_vd, pos_d, f"{pref_d}{ch}", 0x08, scale, self.zones_clic_vannes, False, self.mode_sombre)

            # Segment G -> Puce
            p.setPen(QPen(COL_LIQ if pos_g == 1 else COL_GAZ, max(1, int(2.2 * scale)), Qt.PenStyle.SolidLine) if pos_g in (1, 3) 
                     else (QPen(COL_STOP, max(1, int(1.8 * scale)), Qt.PenStyle.DotLine) if pos_g == 2 else pen_pointille))
            p.drawLine(g["x_vg_right"], y, g["x_p_in"], y)

            # Segment Puce -> D
            p.setPen(QPen(COL_MILIEU if pos_d == 1 else COL_AV801, max(1, int(2.2 * scale)), Qt.PenStyle.SolidLine) if pos_d in (1, 3) 
                     else (QPen(COL_STOP, max(1, int(1.8 * scale)), Qt.PenStyle.DotLine) if pos_d == 2 else pen_pointille))
            p.drawLine(g["x_p_out"], y, g["x_vd_left"], y)

            # Traversée PDMS
            if pos_g in (1, 3) and pos_d in (1, 3):
                cf = COL_MILIEU if pos_d == 1 else COL_AV801
                p.setPen(QPen(cf, max(1, int(2.5 * scale)), Qt.PenStyle.SolidLine))
                p.drawLine(g["x_p_in"], y, g["x_p_out"], y)

                pid_actif = 1 if pos_g == 1 else 2
                pompe = self.etats_pompes[pid_actif]
                dir_gauche = (pompe["sens"] == "withdraw")

                if pompe["en_marche"] and pompe["connecte"] and self.animations_actives:
                    sp.dessiner_bulles_flux(p, g["x_p_in"], g["x_p_out"], y, cf, scale, self.phase_flux[pid_actif], dir_gauche)
                else:
                    sp.dessiner_fleche_repos(p, (g["x_p_in"] + g["x_p_out"]) // 2, y, cf, scale, dir_gauche)
            elif pos_g == 2 or pos_d == 2:
                p.setPen(QPen(COL_STOP, max(1, int(1.8 * scale)), Qt.PenStyle.DotLine))
                p.drawLine(g["x_p_in"], y, g["x_p_out"], y)
            else:
                p.setPen(pen_pointille)
                p.drawLine(g["x_p_in"], y, g["x_p_out"], y)

    # =========================================================================
    # ACTIONS UTILISATEUR (SOURIS / MOLETTE)
    # =========================================================================
    def _action_toggle_sens(self, pid: int):
        p_info = self.etats_pompes.get(pid, {})
        if not p_info.get("connecte", False):
            return
        nouveau = "infuse" if p_info.get("sens", "withdraw") == "withdraw" else "withdraw"
        p_info["sens"] = nouveau

        bp = getattr(self.backend, "pumps", None)
        if bp:
            if p_info.get("en_marche", False):
                bp.demarrer(pid, p_info.get("debit", 0.25), p_info.get("unite", "µL/min"), nouveau)
            else:
                p = bp.pompes.get(pid)
                if p:
                    p.sens = nouveau
                    bp._notifier_etat(p)
        self.demande_sens_pompe.emit(pid, nouveau)
        self.update()

    def _action_toggle_pompe(self, pid: int):
        bp = getattr(self.backend, "pumps", None)
        p_info = self.etats_pompes.get(pid, {})
        if not p_info.get("connecte", False):
            return
        if bp:
            if p_info.get("en_marche", False):
                bp.arreter(pid)
            else:
                bp.demarrer(pid, p_info.get("debit", 0.25), p_info.get("unite", "µL/min"), p_info.get("sens", "withdraw"))
        self.demande_toggle_pompe.emit(pid)

    def _action_regler_debit(self, pid: int):
        p_info = self.etats_pompes.get(pid, {})
        if not p_info.get("connecte", False):
            return
        
        en_marche = p_info.get("en_marche", False)
        dlg = FlowRateDialog(
            tr(f"pump_{pid}_short", default=p_info["nom"]), 
            p_info.get("debit", 0.25), 
            p_info.get("unite", "µL/min"), 
            en_marche=en_marche, 
            parent=self
        )
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            nouveau_debit, nouvelle_unite = dlg.get_valeurs()
            p_info["debit"] = nouveau_debit
            p_info["unite"] = nouvelle_unite
            bp = getattr(self.backend, "pumps", None)
            if bp:
                if en_marche:
                    # Ajustement à chaud via la méthode dédiée sans couper le flux
                    if hasattr(bp, "regler_debit_seul"):
                        bp.regler_debit_seul(pid, nouveau_debit, nouvelle_unite)
                    else:
                        bp.demarrer(pid, nouveau_debit, nouvelle_unite, p_info.get("sens", "withdraw"))
                else:
                    p = bp.pompes.get(pid)
                    if p:
                        p.debit = nouveau_debit
                        p.unite_debit = nouvelle_unite
                        bp._notifier_etat(p)
            self.demande_reglage_pompe.emit(pid, nouveau_debit, nouvelle_unite)
            self.update()

    def wheelEvent(self, event):
        pos = event.position()
        for pid in (1, 2):
            r_c = self.zones_clic_pompes.get((pid, "corps"))
            r_b = self.zones_clic_pompes.get((pid, "badge_debit"))
            if (r_c and r_c.contains(pos)) or (r_b and r_b.contains(pos)):
                p_info = self.etats_pompes.get(pid, {})
                if not p_info.get("connecte", False):
                    return
                unite = p_info.get("unite", "µL/min")
                pas = 0.05 if unite == "µL/min" else (10.0 if unite == "nL/min" else (1.0 if unite == "µL/h" else 0.01))
                delta = 1 if event.angleDelta().y() > 0 else -1
                nouveau = max(0.001, round(p_info.get("debit", 0.25) + delta * pas, 4))
                p_info["debit"] = nouveau
                bp = getattr(self.backend, "pumps", None)
                if bp:
                    if p_info.get("en_marche", False):
                        bp.demarrer(pid, nouveau, unite, p_info.get("sens", "withdraw"))
                    else:
                        p = bp.pompes.get(pid)
                        if p:
                            p.debit = nouveau
                            bp._notifier_etat(p)
                self.demande_reglage_pompe.emit(pid, nouveau, unite)
                self.update()
                event.accept()
                return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        pos = event.position()

        for pid in (1, 2):
            if self.zones_clic_pompes.get((pid, "btn_sens"), QRectF()).contains(pos):
                self._action_toggle_sens(pid)
                return
            if self.zones_clic_pompes.get((pid, "btn_toggle"), QRectF()).contains(pos) or self.zones_clic_pompes.get((pid, "corps"), QRectF()).contains(pos):
                self._action_toggle_pompe(pid)
                return
            if self.zones_clic_pompes.get((pid, "badge_debit"), QRectF()).contains(pos):
                self._action_regler_debit(pid)
                return

        for pt, r in self.zones_clic_selecteur.items():
            if r.contains(pos):
                c = self.backend.ROLES_BANC.get(0x09, {}).get("canal_selecteur", 1)
                self.backend.regler_vanne_8ports(0x09, c, pt)
                self.update()
                return

        for (addr, canal, etat_cible), r in self.zones_clic_vannes.items():
            if r.contains(pos):
                if canal == "ALL":
                    self.backend.regler_toutes_vannes(addr, etat_cible)
                else:
                    self.backend.regler_vanne_individuelle(addr, canal, etat_cible)
                self.update()
                return

    def mouseMoveEvent(self, event):
        pos = event.position()
        survol = any(r.contains(pos) for r in self.zones_clic_pompes.values()) or \
                 any(r.contains(pos) for r in self.zones_clic_vannes.values()) or \
                 any(r.contains(pos) for r in self.zones_clic_selecteur.values())
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor if survol else Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)