"""
/*************************
 annexe6_processing
*************************/
"""
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsSpatialIndex,
    QgsFeatureRequest
)
from qgis.PyQt.QtCore import QVariant
from qgis.gui import QgsRubberBand

import os
import csv

from .annexe6_ui import ValidationDialog

def process_data(line_layer, detection_zone_layer, folio_layer, output_folder, zones_to_exclude=None):
    line_index = QgsSpatialIndex()
    for f in line_layer.getFeatures():
        line_index.addFeature(f)

    clipped_features = []
    excluded_ids = {f.id() for f in zones_to_exclude} if zones_to_exclude else set()
    for zone_feature in detection_zone_layer.getFeatures(QgsFeatureRequest().setFilterExpression("type = 0")):
        if zone_feature.id() in excluded_ids:
            continue
        zone_geom = zone_feature.geometry()
        for fid in line_index.intersects(zone_geom.boundingBox()):
            line_feature = line_layer.getFeature(fid)
            if line_feature.geometry().intersects(zone_geom):
                clipped_geom = line_feature.geometry().intersection(zone_geom)
                new_feature = QgsFeature(line_feature)
                new_feature.setGeometry(clipped_geom)
                clipped_features.append(new_feature)

    intermediate_layer = QgsVectorLayer(f"LineString?crs={line_layer.crs().authid()}", "Tronçons Zones", "memory")
    intermediate_layer.dataProvider().addAttributes(line_layer.fields())
    intermediate_layer.updateFields()
    intermediate_layer.dataProvider().addFeatures(clipped_features)

    if intermediate_layer.fields().indexFromName('longueur') == -1:
        intermediate_layer.startEditing()
        intermediate_layer.addAttribute(QgsField('longueur', QVariant.Double))
        intermediate_layer.commitChanges()

    final_features = []
    folio_index = QgsSpatialIndex()
    for f in folio_layer.getFeatures():
        if f['type'] != 'raccord':
            folio_index.addFeature(f)

    for int_feature in intermediate_layer.getFeatures():
        int_geom = int_feature.geometry()
        for fid in folio_index.intersects(int_geom.boundingBox()):
            folio_feature = folio_layer.getFeature(fid)
            if folio_feature['type'] == 'vrai' and int_geom.intersects(folio_feature.geometry()):
                final_geom = int_geom.intersection(folio_feature.geometry())
                new_feature = QgsFeature(int_feature)
                new_feature.setGeometry(final_geom)
                final_features.append(new_feature)

    final_layer = QgsVectorLayer(f"LineString?crs={intermediate_layer.crs().authid()}", "Tronçons Folios", "memory")
    final_layer.dataProvider().addAttributes(intermediate_layer.fields())
    final_layer.updateFields()
    final_layer.dataProvider().addFeatures(final_features)

    longueur_field_index = final_layer.fields().indexFromName('longueur')
    final_layer.startEditing()
    features_to_delete = []
    for feature in final_layer.getFeatures():
        length = round(feature.geometry().length(), 1)
        if length == 0:
            features_to_delete.append(feature.id())
        else:
            feature.setAttribute(longueur_field_index, length)
            final_layer.updateFeature(feature)
    for feature_id in features_to_delete:
        final_layer.deleteFeature(feature_id)
    final_layer.commitChanges()

    valid_zones = [f for f in detection_zone_layer.getFeatures(QgsFeatureRequest().setFilterExpression("type = 0"))
                   if f.id() not in excluded_ids]
    total_zones = len(valid_zones)
    length_c = length_b = 0

    for final_feature in final_layer.getFeatures():
        classe = final_feature['classe']
        if classe == 'C':
            length_c += final_feature.geometry().length()
        elif classe == 'B':
            length_b += final_feature.geometry().length()

    correction_features = [f for f in folio_layer.getFeatures() if f['type'] == 'correction']
    folios_features = [f for f in folio_layer.getFeatures() if f['type'] == 'vrai']
    raccord_features = [f for f in folio_layer.getFeatures() if f['type'] == 'raccord']

    return total_zones, length_c, length_b, correction_features, folios_features, raccord_features

def generate_csv_files(correction_features, folios_features, raccord_features, folio_layer, output_folder):
    try:
        correction_path = os.path.join(output_folder, "corrections.csv")
        folios_path = os.path.join(output_folder, "Annexe_6.csv")
        atlas_path = os.path.join(output_folder, "Export_atlas.csv")

        for path in [correction_path, folios_path, atlas_path]:
            if os.path.exists(path):
                os.remove(path)

        def clean_value(value):
            return '' if value in (None, 'null', 'NULL', QVariant(), QVariant.Null) else str(value)

        def safe_str(value):
            try:
                if value is None or value in ('null', 'NULL', QVariant(), QVariant.Null):
                    return ""
                return str(value).strip()
            except Exception:
                return ""

        def sort_by_tr(feature):
            import re
            id_tr = feature['id_tr']
            if id_tr:
                first_id = id_tr.split(" + ")[0]
                match = re.search(r'\d+', first_id)
                if match:
                    return int(match.group())
            return float('inf')

        folios_features.sort(key=sort_by_tr)
        correction_features.sort(key=sort_by_tr)

        def group_raccords(folios, raccords):
            grouped = []
            valid_folios = [f for f in folios if f['type'] == 'vrai' and safe_str(f['id_tr'])[:10]]
            for folio in valid_folios:
                grouped.append(folio)
                folio_geom = folio.geometry()
                close_raccords = [r for r in raccords if r.geometry().distance(folio_geom) <= 10]
                grouped.extend(close_raccords)
                for r in close_raccords:
                    raccords.remove(r)
            return grouped

        grouped_folios = group_raccords(folios_features, raccord_features)

        folio_csv_fields = {
            "Commune": "commune_no",
            "Code INSEE": "commune_in",
            "Rue concernée": "voie_princ",
            "Plan": "plan_nom",
            "Code qualité du plan": "qualite_li",
            "Identifiant du tronçon à détecter (facultatif)": "id_tr",
            "Linéaire réseaux cartographié en classe PI (mètre)": "lg_res_clc",
            "Matière réseaux cartographié en PI": "mat_pi",
            "Lignéaire réseaux cartographié en classe B (mètre)": "lg_res_clb",
            "Matière réseaux cartographié en classe B": "mat_b",
            "Caracteristiques réseau du tronçon (facultatif)": "carac_res",
            "Quintile du plan": "cdp_lib",
            "Commentaire précision commande": "commentair"
        }

        def find_matching_field(attr, feature_fields):
            for field_name in feature_fields:
                if attr[:10] == field_name[:10]:
                    return field_name
            return None

        with open(folios_path, 'w', newline='', encoding='utf-8') as csvfile:
            csvfile.write('\ufeff')
            writer = csv.writer(csvfile, delimiter=';')
            writer.writerow(folio_csv_fields.keys())
            for f in grouped_folios:
                row = []
                for field, attr in folio_csv_fields.items():
                    match_field = find_matching_field(attr, f.fields().names())
                    raw = f[match_field] if match_field else ""
                    val = safe_str(raw)
                    if attr == "plan_nom":
                        val = "'" + val
                    if field == "Commentaire précision commande":
                        val_lower = val.lower() if isinstance(val, str) else ""
                        if f['type'] == 'raccord':
                            val = "Folio raccord"
                        elif f['type'] == 'vrai' and val_lower in ["folio raccord", "raccord"]:
                            val = ""
                    row.append(val)
                writer.writerow(row)

        with open(correction_path, 'w', newline='', encoding='utf-8') as csvfile:
            csvfile.write('\ufeff')
            writer = csv.writer(csvfile, delimiter=';')
            fields = [f.name() for f in folio_layer.fields()]
            writer.writerow(fields)
            for f in correction_features:
                writer.writerow([clean_value(f[field]) for field in fields])

        export_fields = [
            "Nom du plan", "Norme", "Code INSEE", "Statut du plan", "Etat du géoréférencement",
            "Demande d'opération", "Numéro du lot", "Numéro de commande", "Numéro de la tranche",
            "Nom du prestataire en charge du géoréférencement", "Nom du prestataire en charge du contrôle",
            "Date de verrouillage prévue", "Date de verrouillage effective", "Date d'intégration prévue",
            "Date d'intégration réalisée"
        ]

        with open(atlas_path, 'w', newline='', encoding='utf-8') as csvfile:
            csvfile.write('\ufeff')
            writer = csv.writer(csvfile, delimiter=';')
            writer.writerow(export_fields)
            for f in grouped_folios:
                writer.writerow([clean_value(f['plan_nom'])] + [''] * 14)

        return True

    except Exception as e:
        QMessageBox.critical(None, "Erreur CSV", f"Erreur lors de la génération des fichiers CSV : {str(e)}")
        return False

def update_tr_numbers(detection_zone_layer, deleted_features):
    mapping = {}
    current_id = 1
    for feature in detection_zone_layer.getFeatures():
        if feature not in deleted_features:
            old_id = feature["id"]
            new_id = f"TR{current_id:02d}"
            mapping[old_id] = new_id
            current_id += 1
    return mapping

def cleanup_rubber_bands(canvas):
    for item in canvas.scene().items():
        if isinstance(item, QgsRubberBand):
            try:
                item.setToGeometry(None, None)
            except:
                item.hide()
