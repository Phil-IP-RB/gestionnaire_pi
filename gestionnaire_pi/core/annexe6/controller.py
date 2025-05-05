"""
/*************************
 Annexe6_Main
*************************/
"""
from qgis.PyQt.QtWidgets import QMessageBox
from PyQt5.QtCore import Qt
from qgis.core import QgsProject, QgsFeatureRequest

from gestionnaire_pi.core.annexe6.service import (
    process_data,
    generate_csv_files,
    update_tr_numbers,
    cleanup_rubber_bands,
)
from gestionnaire_pi.ui.annexe6_dialogs import ModificationDialog, ValidationDialog


class Annexe6Processor:
    def __init__(self, iface):
        self.iface = iface

    # ------------------------------------------------------------------
    #  run_custom
    # ------------------------------------------------------------------
    def run_custom(
        self,
        line_layer_name: str,
        detection_zone_layer_name: str,
        folio_layer_name: str,
        output_folder: str,
    ):
        """
        Lance le traitement Annexe 6.

        • Si la couche Zones ne contient aucune entité (type = 0) ⇒
          message et arrêt immédiat (pas de stats, pas de CSV).
        """
        project = QgsProject.instance()

        # 1. Récupération des couches ------------------------------------
        try:
            detection_zone_layer = project.mapLayersByName(
                detection_zone_layer_name
            )[0]
        except IndexError:
            QMessageBox.warning(
                None,
                "Erreur",
                "La couche des zones n'a pas été trouvée.",
            )
            return

        line_layer = project.mapLayersByName(line_layer_name)[0]
        folio_layer = project.mapLayersByName(folio_layer_name)[0]

        # 2. Contrôle bloquant : zéro zone -------------------------------
        if detection_zone_layer.featureCount() == 0:
            QMessageBox.warning(
                None,
                "Zones de détection manquantes",
                (
                    "Aucune zone de détection n'est présente.\n"
                    "Tracez ou chargez les zones avant de relancer le traitement."
                ),
            )
            return

        # 3. Passage en édition pour autoriser les suppressions ----------
        if not detection_zone_layer.isEditable():
            detection_zone_layer.startEditing()

        deleted_features = []

        # ------------------------------------------------------------------
        # 4. Boucle principale de traitement / validation
        # ------------------------------------------------------------------
        while True:
            total_zones, length_c, length_b, corrections, folios, raccords = process_data(
                line_layer,
                detection_zone_layer,
                folio_layer,
                output_folder,
                deleted_features,
            )

            zones_to_review = [
                z
                for z in detection_zone_layer.getFeatures(
                    QgsFeatureRequest().setFilterExpression("type = 0")
                )
                if not any(
                    l["classe"] == "C" and l.geometry().intersects(z.geometry())
                    for l in line_layer.getFeatures()
                )
            ]

            dlg = ValidationDialog(
                total_zones, round(length_c, 1), round(length_b, 1)
            )
            dlg.set_modify_enabled(bool(zones_to_review))

            result = dlg.exec_()

            # -------- 4.a  L’utilisateur a choisi « Annuler » -----------
            if result == dlg.Rejected:
                # ---------------- MODIFIER ----------------
                if dlg.was_modify_clicked() and zones_to_review:
                    # Ouvre la boîte de modification NON‑MODALE
                    mod_dlg = ModificationDialog(
                        zones_to_review,
                        self.iface,
                        deleted_features,
                        detection_zone_layer,
                    )
                    mod_dlg.setModal(False)
                    mod_dlg.setWindowModality(Qt.NonModal)
                    mod_dlg.setAttribute(Qt.WA_DeleteOnClose)

                    # on garde la fenêtre de sialog au premier plan
                    mod_dlg.setWindowFlags(mod_dlg.windowFlags() | Qt.WindowStaysOnTopHint)

                    # Callback : au fermeture => nettoyage + relance run_custom
                    def _after_mod(_result):
                        cleanup_rubber_bands(self.iface.mapCanvas())
                        deleted_features.extend(mod_dlg.get_deleted_features())
                        # Relance exactement le même traitement
                        self.run_custom(
                            line_layer_name,
                            detection_zone_layer_name,
                            folio_layer_name,
                            output_folder,
                        )

                    mod_dlg.finished.connect(_after_mod)
                    mod_dlg.show()
                    return  # on sort : la suite s'exécutera dans le rappel
                # --------------- ANNULER SIMPLE -------------
                else:
                    if detection_zone_layer.isEditable():
                        detection_zone_layer.rollBack()
                    QMessageBox.information(
                        None, "Annulé", "Traitement annulé."
                    )
                    break

            # -------- 4.b  L’utilisateur a validé ------------------------
            if detection_zone_layer.isEditable():
                detection_zone_layer.commitChanges()

            # Renumérotation des TR après suppressions -------------------
            if deleted_features:
                mapping = update_tr_numbers(
                    detection_zone_layer, deleted_features
                )

                # MAJ Zones
                detection_zone_layer.startEditing()
                for zone in detection_zone_layer.getFeatures(
                    QgsFeatureRequest().setFilterExpression("type = 0")
                ):
                    if zone["id"] in mapping:
                        zone["id"] = mapping[zone["id"]]
                        detection_zone_layer.updateFeature(zone)
                detection_zone_layer.commitChanges()

                # MAJ Folios
                folio_layer.startEditing()
                for folio in folio_layer.getFeatures():
                    if folio["id_tr"]:
                        old_names = folio["id_tr"].split(" + ")
                        folio["id_tr"] = " + ".join(
                            mapping.get(n, n) for n in old_names
                        )
                        folio_layer.updateFeature(folio)
                folio_layer.commitChanges()

            # Recalcul final après corrections ---------------------------
            total_zones, length_c, length_b, corrections, folios, raccords = process_data(
                line_layer,
                detection_zone_layer,
                folio_layer,
                output_folder,
                [],
            )

            # Génération des CSV ----------------------------------------
            if generate_csv_files(
                corrections, folios, raccords, folio_layer, output_folder
            ):
                QMessageBox.information(
                    None, "Succès", "Le traitement est terminé."
                )
            break
