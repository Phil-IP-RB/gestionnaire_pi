# -*- coding: utf-8 -*-
"""
Logique métier de création de lot (modeler)
"""
from qgis.core import QgsProcessingFeedback, Qgis
import processing

def create_lot(iface, insee, line_layers, output_folder, styles_folder):
    """
    Lance le traitement de création de lot en utilisant le modèle graphique Principale.model3
    via le provider de modèles.
    """
    # 1) Construction des paramètres
    params = {
        'INSEE_CODE': insee,
        'LINE_LAYERS': [layer.id() for layer in line_layers],
        'OUTPUT_FOLDER': output_folder,
        'STYLES_FOLDER': styles_folder,
    }

    # 2) Exécution du modèle via son ID (enregistré par le provider)
    feedback = QgsProcessingFeedback()
    processing.run('model:Principale', params, feedback=feedback)

    # 3) Notification à l'utilisateur
    iface.messageBar().pushMessage(
        "Création lot",
        "Lot P.I. créé avec succès",
        level=Qgis.Success
    )
