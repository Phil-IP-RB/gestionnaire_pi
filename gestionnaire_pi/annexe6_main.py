"""
/*************************
 Annexe6_Main
*************************/
"""
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsProject, QgsFeatureRequest

from .annexe6_processing import (
    process_data,
    generate_csv_files,
    update_tr_numbers,
    cleanup_rubber_bands,
)
from .annexe6_ui import ModificationDialog, ValidationDialog


class Annexe6Processor:
    def __init__(self, iface):
        self.iface = iface

    # ------------------------------------------------------------------
    #  run_custom
    # ------------------------------------------------------------------
    def run_custom(self, line_layer_name, detection_zone_layer_name,
                   folio_layer_name, output_folder):
        """
        Lance le traitement Annexe 6.

        • Si la couche Zones ne contient aucune entité (type = 0) ⇒
          on montre un message et on quitte immédiatement : aucune
          fenêtre de statistiques, aucun CSV.
        """
        project = QgsProject.instance()

        # 1. Récupération des couches ------------------------------------
        try:
            detection_zone_layer = project.mapLayersByName(
                detection_zone_layer_name)[0]
        except IndexError:
            QMessageBox.warning(
                None,
                "Erreur",
                "La couche des zones n'a pas été trouvée."
            )
            return

        line_layer = project.mapLayersByName(line_layer_name)[0]
        folio_layer = project.mapLayersByName(folio_layer_name)[0]

        # 2. Contrôle bloquant : zéro zone -------------------------------
        if detection_zone_layer.featureCount() == 0:
            QMessageBox.warning(
                None,
                "Zones de détection manquantes",
                ("Aucune zone de détection n'est présente.\n"
                 "Tracez ou chargez les zones avant de relancer le traitement.")
            )
            return  #  ← rien d’autre ne s’exécute

        # 3. Passage en édition pour permettre les suppressions ----------
        if not detection_zone_layer.isEditable():
            detection_zone_layer.startEditing()

        deleted_features = []

        # ------------------------------------------------------------------
        # 4. Boucle de traitement / validation utilisateur
        # ------------------------------------------------------------------
        while True:
            total_zones, length_c, length_b, corrections, folios, raccords = process_data(
                line_layer, detection_zone_layer, folio_layer, output_folder, deleted_features
            )

            # Zones sans classe C à corriger
            zones_to_review = [
                z for z in detection_zone_layer.getFeatures(
                    QgsFeatureRequest().setFilterExpression("type = 0"))
                if not any(
                    l['classe'] == 'C' and l.geometry().intersects(z.geometry())
                    for l in line_layer.getFeatures())
            ]

            # Boîte de validation ---------------------------------------
            dlg = ValidationDialog(total_zones,
                                   round(length_c, 1),
                                   round(length_b, 1))
            dlg.set_modify_enabled(bool(zones_to_review))

            result = dlg.exec_()

            # ------------------------------------------------------------
            # 4.a  L’utilisateur a cliqué « Annuler »
            # ------------------------------------------------------------
            if result == dlg.Rejected:
                if dlg.was_modify_clicked():
                    # Ouvre la boîte de modification des zones
                    if zones_to_review:
                        mod_dlg = ModificationDialog(
                            zones_to_review, self.iface,
                            deleted_features, detection_zone_layer)
                        mod_dlg.exec_()
                    cleanup_rubber_bands(self.iface.mapCanvas())
                    continue  # → recalcul
                else:
                    # Annulation simple
                    if detection_zone_layer.isEditable():
                        detection_zone_layer.rollBack()
                    QMessageBox.information(None, "Annulé", "Traitement annulé.")
                    break

            # ------------------------------------------------------------
            # 4.b  L’utilisateur a validé
            # ------------------------------------------------------------
            if detection_zone_layer.isEditable():
                detection_zone_layer.commitChanges()

            # Renumérotation éventuelle des TR après suppressions
            if deleted_features:
                mapping = update_tr_numbers(detection_zone_layer, deleted_features)

                # MAJ zone
                detection_zone_layer.startEditing()
                for zone in detection_zone_layer.getFeatures(
                        QgsFeatureRequest().setFilterExpression("type = 0")):
                    if zone['id'] in mapping:
                        zone['id'] = mapping[zone['id']]
                        detection_zone_layer.updateFeature(zone)
                detection_zone_layer.commitChanges()

                # MAJ folios
                folio_layer.startEditing()
                for folio in folio_layer.getFeatures():
                    if folio['id_tr']:
                        old = folio['id_tr'].split(' + ')
                        folio['id_tr'] = ' + '.join(mapping.get(n, n) for n in old)
                        folio_layer.updateFeature(folio)
                folio_layer.commitChanges()

            # Recalcul final après corrections ---------------------------
            total_zones, length_c, length_b, corrections, folios, raccords = process_data(
                line_layer, detection_zone_layer, folio_layer, output_folder, []
            )

            # Génération des CSV ----------------------------------------
            if generate_csv_files(corrections, folios, raccords,
                                  folio_layer, output_folder):
                QMessageBox.information(None, "Succès",
                                        "Le traitement est terminé.")
            break
