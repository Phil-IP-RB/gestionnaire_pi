import os
import csv
import re
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsFeatureRequest, 
    QgsSpatialIndex, QgsField, QgsWkbTypes, QgsCoordinateReferenceSystem
)
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QVariant          
from typing import List, Tuple


def clean_value(value):
    return '' if value in (None, 'null', 'NULL') else str(value)


def sort_by_tr(feature):
    id_tr = clean_value(feature['id_tr'])
    if id_tr:
        first_id = id_tr.split(" + ")[0]
        match = re.search(r'\d+', first_id)
        if match:
            return int(match.group())
    return float('inf')
    
def group_raccord_with_folios_and_tr(folios, raccords):
    grouped_features = []
    valid_folios = [
        f for f in folios
        if f['type'] == 'vrai' and clean_value(f['id_tr']).strip()
    ]
    for folio in valid_folios:
        grouped_features.append(folio)
        folio_geom = folio.geometry()
        to_remove = []
        for raccord in raccords:
            if raccord.geometry().distance(folio_geom) <= 10:
                grouped_features.append(raccord)
                to_remove.append(raccord)
        for r in to_remove:
            raccords.remove(r)
    return grouped_features

def process_data(line_layer: QgsVectorLayer, detection_zone_layer: QgsVectorLayer, 
                folio_layer: QgsVectorLayer, output_folder: str, zones_to_exclude: List[QgsFeature] = None) -> Tuple[int, float, float, List[QgsFeature], List[QgsFeature], List[QgsFeature]]:
    
    # Création d'un index spatial pour optimiser les requêtes
    line_index = QgsSpatialIndex()
    for f in line_layer.getFeatures():
        line_index.addFeature(f)

    # Premier traitement : découpage avec les zones de détection
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

    # Création de la couche intermédiaire
    intermediate_layer = QgsVectorLayer(f"LineString?crs={line_layer.crs().authid()}", 
                                      "Tronçons Coupés Zones", "memory")
    intermediate_layer.dataProvider().addAttributes(line_layer.fields())
    intermediate_layer.updateFields()
    intermediate_layer.dataProvider().addFeatures(clipped_features)

    # Ajout du champ longueur si nécessaire
    if intermediate_layer.fields().indexFromName('longueur') == -1:
        intermediate_layer.startEditing()
        intermediate_layer.addAttribute(QgsField('longueur', QVariant.Double))
        intermediate_layer.commitChanges()

    # Deuxième traitement : découpage avec les folios
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

    # Création de la couche finale
    final_layer = QgsVectorLayer(f"LineString?crs={intermediate_layer.crs().authid()}", 
                                "Tronçons Coupés Folios", "memory")
    final_layer.dataProvider().addAttributes(intermediate_layer.fields())
    final_layer.updateFields()
    final_layer.dataProvider().addFeatures(final_features)

    # Calcul des longueurs
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

    # Calcul des statistiques
    excluded_ids = {f.id() for f in zones_to_exclude} if zones_to_exclude else set()
    valid_zones = [f.geometry() for f in detection_zone_layer.getFeatures(QgsFeatureRequest().setFilterExpression("type = 0")) 
                  if f.id() not in excluded_ids]
    total_zones = len(valid_zones)
    
    # Calcul des longueurs totales par classe
    length_c = length_b = length_w = 0
    
    # Pour chaque folio de type 'vrai'
    for folio_feature in folio_layer.getFeatures():
        if folio_feature['type'] == 'vrai':
            folio_geom = folio_feature.geometry()
            # Pour chaque feature dans la couche finale
            for final_feature in final_layer.getFeatures():
                if final_feature.geometry().within(folio_geom):
                    if final_feature['classe'] == 'C':
                        length_c += final_feature.geometry().length()
                    elif final_feature['classe'] == 'B':
                        length_b += final_feature.geometry().length()
                    elif final_feature['classe'] == 'W':
                        length_w += final_feature.geometry().length()

    # Mise à jour des champs du folio
    field_names = ['id_tr', 'lg_res_clc', 'lg_res_clb']
    field_types = [QVariant.String, QVariant.Double, QVariant.Double]
    
    folio_layer.startEditing()
    for name, type_ in zip(field_names, field_types):
        if folio_layer.fields().indexFromName(name) == -1:
            folio_layer.addAttribute(QgsField(name, type_))
    folio_layer.updateFields()

    correction_features = []
    folios_features = []
    raccord_features = []
    
    for folio_feature in folio_layer.getFeatures():
        folio_geom = folio_feature.geometry()
        ids = []
        lg_res_clc_sum = lg_res_clb_sum = 0

        # Collecte des IDs des zones de détection
        for zone_feature in detection_zone_layer.getFeatures(QgsFeatureRequest().setFilterExpression("type = 0")):
            if zone_feature.geometry().intersects(folio_geom):
                ids.append(str(zone_feature['id']))

        # Mise à jour des attributs et calcul des longueurs
        id_tr_value = ' + '.join(ids)
        folio_feature['id_tr'] = id_tr_value

        # Calcul des longueurs uniquement pour les folios valides (type 'vrai' et avec zones de détection)
        if folio_feature['type'] == 'vrai' and id_tr_value:
            for final_feature in final_layer.getFeatures():
                if final_feature.geometry().within(folio_geom):
                    if final_feature['classe'] == 'C':
                        lg_res_clc_sum += final_feature.geometry().length()
                    else:
                        lg_res_clb_sum += final_feature.geometry().length()
            
            folio_feature['lg_res_clc'] = round(lg_res_clc_sum, 1)
            folio_feature['lg_res_clb'] = round(lg_res_clb_sum, 1)
        else:
            # Mettre les longueurs à 0 pour les folios non valides
            folio_feature['lg_res_clc'] = 0
            folio_feature['lg_res_clb'] = 0

        if folio_feature['type'] == 'correction':
            correction_features.append(folio_feature)
        elif folio_feature['type'] == 'faux':
            pass
        elif folio_feature['type'] == 'raccord':
            raccord_features.append(folio_feature)
        elif folio_feature['type'] == 'vrai':
            # Seulement ajouter les folios 'vrai' s'ils ont un id_tr non vide
            if id_tr_value.strip():
                # (Optionnel) Calcul des longueurs si nécessaire pour les folios valides
                lg_res_clc_sum = lg_res_clb_sum = 0
                for final_feature in final_layer.getFeatures():
                    if final_feature.geometry().within(folio_geom):
                        if final_feature['classe'] == 'C':
                            lg_res_clc_sum += final_feature.geometry().length()
                        elif final_feature['classe'] == 'B':
                            lg_res_clb_sum += final_feature.geometry().length()
                folio_feature['lg_res_clc'] = round(lg_res_clc_sum, 1)
                folio_feature['lg_res_clb'] = round(lg_res_clb_sum, 1)
                folios_features.append(folio_feature)
            else:
                # Ignorer le folio de type 'vrai' sans id_tr
                continue

        folio_layer.updateFeature(folio_feature)
    folio_layer.commitChanges()

    return total_zones, length_c, length_b, length_w, correction_features, folios_features, raccord_features

def update_tr_numbers(detection_zone_layer, deleted_features):
    """
    Met à jour la numérotation des zones TR après suppression.
    Retourne un mapping de l'ancien nom vers le nouveau.
    """
    remaining = []
    deleted_ids = {f.id() for f in deleted_features}
    for zone in detection_zone_layer.getFeatures(QgsFeatureRequest().setFilterExpression("type = 0")):
        if zone.id() not in deleted_ids:
            remaining.append(zone)
    remaining.sort(key=lambda x: int(re.search(r'\d+', x['id']).group()))
    mapping = {}
    for idx, zone in enumerate(remaining, start=1):
        mapping[zone['id']] = f'TR{idx}'
    return mapping


def generate_csv_files(correction_features, folios_features, raccord_features, folio_layer, output_folder):
    try:
        paths = {
            'correction': os.path.join(output_folder, 'corrections.csv'),
            'folios': os.path.join(output_folder, 'Annexe_6.csv'),
            'atlas': os.path.join(output_folder, 'Export_atlas.csv')
        }
        for p in paths.values():
            with open(p, 'a'): pass
            os.remove(p)

        folios_features.sort(key=sort_by_tr)
        correction_features.sort(key=sort_by_tr)
        grouped = group_raccord_with_folios_and_tr(folios_features[:], raccord_features[:])

        folio_csv_fields = {
            'Commune': 'commune_no',
            'Code INSEE': 'commune_in',
            'Rue concernée': 'voie_princ',
            'Plan': 'plan_nom',
            'Code qualité du plan': 'qualite_li',
            'Identifiant du tronçon à détecter (facultatif)': 'id_tr',
            'Linéaire réseaux cartographié en classe PI (mètre)': 'lg_res_clc',
            'Matière réseaux cartographié en PI': 'mat_pi',
            'Linéaire réseaux cartographié en classe B (mètre)': 'lg_res_clb',
            'Matière réseaux cartographié en classe B': 'mat_b',
            'Caracteristiques réseau du tronçon (facultatif)': 'carac_res',
            'Quintile du plan': 'cdp_lib',
            'Commentaire précision commande': 'commentair'
        }
        with open(paths['folios'], 'w', newline='', encoding='utf-8') as csvfile:
            csvfile.write('\ufeff')
            writer = csv.writer(csvfile, delimiter=';', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(folio_csv_fields.keys())
            for feat in grouped:
                row = []
                for fld in folio_csv_fields:
                    raw = feat[folio_csv_fields[fld]]
                    if folio_csv_fields[fld] == 'plan_nom':
                        val = "'" + str(raw) if raw else ''
                    else:
                        val = clean_value(raw)
                    if fld == 'Commentaire précision commande':
                        if feat['type'] == 'raccord':
                            val = 'Folio raccord'
                        elif feat['type'] == 'vrai':
                            orig = clean_value(raw)
                            val = '' if orig.lower() in ('folio raccord','raccord') else orig
                    row.append(val)
                writer.writerow(row)

        with open(paths['correction'], 'w', newline='', encoding='utf-8') as csvfile:
            csvfile.write('\ufeff')
            writer = csv.writer(csvfile, delimiter=';')
            fields = [f.name() for f in folio_layer.fields()]
            writer.writerow(fields)
            for feat in correction_features:
                writer.writerow([clean_value(feat[f]) for f in fields])

        atlas_fields = [
    'Nom du plan',
    'Norme',
    'Code INSEE',
    'Statut du plan',
    'Etat du géoréférencement',
    'Demande d\'opération',
    'Numéro du lot',
    'Numéro de commande',
    'Numéro de la tranche',
    'Nom du prestataire en charge du géoréférencement',
    'Nom du prestataire en charge du contrôle',
    'Date de verrouillage prévue',
    'Date de verrouillage effective',
    'Date d\'intégration prévue',
    'Date d\'intégration réalisée',
]   
        with open(paths['atlas'], 'w', newline='', encoding='utf-8') as csvfile:
            csvfile.write('\ufeff')
            writer = csv.writer(csvfile, delimiter=';')
            writer.writerow(atlas_fields)
            for feat in grouped:
                writer.writerow([clean_value(feat['plan_nom'])] + ['']*14)

        return True
    except Exception as e:
        QMessageBox.critical(None, 'Erreur', f'Erreur génération CSV: {e}')
        return False


# Nettoyage des rubber bands sur un canvas donné
def cleanup_rubber_bands(canvas):
    """
    Supprime toutes les instances de QgsRubberBand du scene du canvas.
    """
    from qgis.gui import QgsRubberBand
    for item in list(canvas.scene().items()):
        if isinstance(item, QgsRubberBand):
            canvas.scene().removeItem(item)
            del item
