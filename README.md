# DecLiq — Logiciel de Contrôle Banc Microfluidique

Plateforme d'automatisation fluidique pour l'étude de la décontamination par ménisque liquide/air (LIPhy / CNRS).

## Matériel piloté
- Contrôleur de vannes : LabSmith EIB200 (via liaison série USB)
- Vannes : 8x AV201 (3-voies) + 1x AV801 (sélecteur 8-ports) sur manifolds 4VM02
- Pousse-seringues : 2x KD Scientific Legato 110

## Installation
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python frontend_gui.py