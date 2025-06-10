# ---------------------------------------------------------------------------
#  Gestionnaire PI – génération Annexe 6
#  Version : 2025-06 – « longueurs sans doublons »
# ---------------------------------------------------------------------------

import os
import csv
import re
from typing import List, Tuple

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsFeatureRequest,
    QgsSpatialIndex, QgsField, QgsGeometry
)
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QVariant

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def clean_value(value):
    """Normalise les champs vides ou 'null'."""
    return '' if value in (None, 'null', 'NULL') else str(value)


def is_duplicate(geom, geom_list):
    """Test topologique : True si geom occupe déjà l’espace d’un élément de geom_list."""
    for g in geom_list:
        if geom.equals(g):
            return True
    return False


def sort_by_tr(feature):
    """Ordre dans l’Annexe 6 : par premier numéro de TR dans id_tr."""
    id_tr = clean_value(feature['id_tr'])
    if id_tr:
        match = re.search(r'\d+', id_tr.split(' + ')[0])
        if match:
            return int(match.group())
    return float('inf')


def group_raccord_with_folios_and_tr(folios, raccords):
    """
    Associe chaque raccord au folio 'vrai' (≤10 m) le plus proche
    afin de l’afficher juste après ce folio dans l’Annexe 6.
    """
    grouped = []
    valid_folios = [f for f in folios
                    if f['type'] == 'vrai' and clean_value(f['id_tr']).strip()]

    for folio in valid_folios:
        grouped.append(folio)
        fgeom = folio.geometry()
        to_remove = []
        for rac in raccords:
            if rac.geometry().distance(fgeom) <= 10:
                grouped.append(rac)
                to_remove.append(rac)
        for r in to_remove:
            raccords.remove(r)
    return grouped

# ---------------------------------------------------------------------------
# Traitement principal
# ---------------------------------------------------------------------------

def process_data(
    line_layer,
    detection_zone_layer,
    folio_layer,
    output_folder,
    zones_to_exclude=None
):
    """
    Calcul précis des longueurs par folio.
    - Portion exclusive : longueur entière pour le folio.
    - Portion commune à k folios : longueur / k pour chacun.
    Retourne le tuple :
      total_zones, length_c, length_b, length_w, corrections, folios_vrais, raccords
    """

    # ------------------------------------------------------------------ #
    # 0. S’assurer que les champs de longueur existent                   #
    # ------------------------------------------------------------------ #
    new_fields = []
    if 'lg_res_clc' not in folio_layer.fields().names():
        new_fields.append(QgsField('lg_res_clc', QVariant.Double))
    if 'lg_res_clb' not in folio_layer.fields().names():
        new_fields.append(QgsField('lg_res_clb', QVariant.Double))
    if new_fields:
        folio_layer.startEditing()
        folio_layer.dataProvider().addAttributes(new_fields)
        folio_layer.updateFields()
        folio_layer.commitChanges()

    # ------------------------------------------------------------------ #
    # 1. Séparer les folios par type et indexer les "vrai"               #
    # ------------------------------------------------------------------ #
    type_field = 'type'
    vrais, raccords, corrections = [], [], []
    folio_index = QgsSpatialIndex()
    folio_geom_by_id = {}

    for f in folio_layer.getFeatures():
        t = str(f[type_field]).lower()
        if t == 'vrai':
            vrais.append(f)
            folio_index.addFeature(f)           # API >= 3.30
            folio_geom_by_id[f.id()] = f.geometry()
        elif t == 'raccord':
            raccords.append(f)
        elif t == 'correction':
            corrections.append(f)

    # dictionnaires cumul longueur
    clc = {f.id(): 0.0 for f in vrais}
    clb = {f.id(): 0.0 for f in vrais}

    # ------------------------------------------------------------------ #
    # 1.b  Union des zones de détection                                 #
    # ------------------------------------------------------------------ #
    exclude_ids = {f.id() for f in zones_to_exclude} if zones_to_exclude else set()
    zone_geoms = [z.geometry() for z in detection_zone_layer.getFeatures()
                  if z['type'] == 0 and z.id() not in exclude_ids]
    zone_union = QgsGeometry.unaryUnion(zone_geoms) if zone_geoms else None

    # ------------------------------------------------------------------ #
    # 2. Parcours de tous les segments                                   #
    # ------------------------------------------------------------------ #
    length_c = length_b = 0.0
    seen_wkb = set()
    class_field = 'classe'

    for seg in line_layer.getFeatures():
        g_raw = seg.geometry()
        if g_raw is None or g_raw.isEmpty():
            continue

        # -- on garde uniquement la portion dans la zone de détection --
        if zone_union:
            if not g_raw.intersects(zone_union):          # totalement hors zone
                continue
            g_seg = g_raw.intersection(zone_union)        # portion à l'intérieur
            if g_seg.isEmpty():
                continue
        else:
            g_seg = g_raw
        wkb = g_seg.asWkb()
        if wkb in seen_wkb:                      # doublon strict
            continue
        seen_wkb.add(wkb)

        seg_class = str(seg[class_field]).strip().upper()
        seg_len   = g_seg.length()

        # --- Totaux globaux ---
        if seg_class == 'C':
            length_c += seg_len
        elif seg_class in ('B', 'W'):
            length_b += seg_len     # W inclus

        # --- Folios candidats ---
        cand_ids = folio_index.intersects(g_seg.boundingBox())
        if not cand_ids:
            continue  # pas de folio 'vrai' concerné

        # Liste des sous-segments : [(geom, owners_set)]
        subsegments = [(g_seg, set())]

        # Découpe progressive par chaque folio intersecté
        for fid in cand_ids:
            f_geom = folio_geom_by_id[fid]
            if not g_seg.intersects(f_geom):
                continue

            new_subs = []
            for geom_part, owners in subsegments:
                if geom_part.intersects(f_geom):
                    overlap = geom_part.intersection(f_geom)
                    reste   = geom_part.difference(f_geom)

                    if not overlap.isEmpty():
                        new_subs.append((overlap, owners | {fid}))
                    if not reste.isEmpty():
                        new_subs.append((reste, owners))
                else:
                    new_subs.append((geom_part, owners))
            subsegments = new_subs

        # Attribution des longueurs par sous-segment
        for geom_part, owners in subsegments:
            if not owners:
                continue   # portion hors folio 'vrai'
            L_part = geom_part.length()
            share  = L_part / len(owners)
            for fid in owners:
                if seg_class == 'C':
                    clc[fid] += share
                elif seg_class in ('B', 'W'):
                    clb[fid] += share

    # ------------------------------------------------------------------ #
    # 3. Écriture des valeurs dans la couche folio                       #
    # ------------------------------------------------------------------ #
    folio_layer.startEditing()
    idx_clc = folio_layer.fields().indexFromName('lg_res_clc')
    idx_clb = folio_layer.fields().indexFromName('lg_res_clb')

    for f in vrais:
        fid = f.id()
        f[idx_clc] = round(clc[fid], 1)
        f[idx_clb] = round(clb[fid], 1)
        folio_layer.updateFeature(f)

    for f in raccords:                 # champs vides sur les raccords
        f[idx_clc] = None
        f[idx_clb] = None
        folio_layer.updateFeature(f)

    folio_layer.commitChanges()

    # ------------------------------------------------------------------ #
    # 4. Valeurs de retour                                               #
    # ------------------------------------------------------------------ #
    total_zones = len(vrais) + len(raccords)
    return (total_zones,
            round(length_c, 1),
            round(length_b, 1),
            0.0,
            corrections,
            vrais,
            raccords)

# ---------------------------------------------------------------------------
#  Fonctions annexes : numérotation TR, export CSV, nettoyage bandes
#  (inchangées sauf nettoyage mineur)
# ---------------------------------------------------------------------------

def update_tr_numbers(detection_zone_layer, deleted_features):
    remaining = [z for z in detection_zone_layer.getFeatures("type = 0")
                 if z.id() not in {f.id() for f in deleted_features}]
    remaining.sort(key=lambda x: int(re.search(r'\d+', x['id']).group()))
    return {zone['id']: f'TR{idx}' for idx, zone in enumerate(remaining, 1)}


def generate_csv_files(corrections, folios, raccords, folio_layer, output_folder):
    try:
        paths = {
            'correction': os.path.join(output_folder, 'corrections.csv'),
            'folios':     os.path.join(output_folder, 'Annexe_6.csv'),
            'atlas':      os.path.join(output_folder, 'Export_atlas.csv')
        }
        for p in paths.values():
            if os.path.exists(p):
                os.remove(p)

        folios.sort(key=sort_by_tr)
        corrections.sort(key=sort_by_tr)
        grouped = group_raccord_with_folios_and_tr(folios[:], raccords[:])

        # ---------- Annexe 6 ------------------------------------------------
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

        with open(paths['folios'], 'w', newline='', encoding='utf-8') as f:
            f.write('\ufeff')  # BOM pour Excel
            w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_MINIMAL)
            w.writerow(folio_csv_fields.keys())

            for feat in grouped:
                row = []
                for label, field in folio_csv_fields.items():
                    raw = feat[field] if field in feat.fields().names() else ''
                    val = ''

                    if field in ('lg_res_clc', 'lg_res_clb'):
                        if feat['type'] == 'vrai' and raw not in ('', None):
                            val = f"{float(raw):.1f}"
                        else:
                            val = ''
                    elif field == 'plan_nom':
                        val = f"'{clean_value(raw)}" if raw else ''
                    else:
                        val = clean_value(raw)

                    if label == 'Commentaire précision commande':
                        if feat['type'] == 'raccord':
                            val = 'Folio raccord'
                        elif feat['type'] == 'vrai':
                            orig = clean_value(raw)
                            val = '' if orig.lower() in ('folio raccord', 'raccord') else orig

                    row.append(val)
                w.writerow(row)

        # ---------- corrections.csv ----------------------------------------
        with open(paths['correction'], 'w', newline='', encoding='utf-8') as f:
            f.write('\ufeff')
            w = csv.writer(f, delimiter=';')
            fields = [fld.name() for fld in folio_layer.fields()]
            w.writerow(fields)
            for feat in corrections:
                w.writerow([clean_value(feat[f]) for f in fields])

        # ---------- Export_atlas.csv ---------------------------------------
        atlas_fields = [
            'Nom du plan', 'Norme', 'Code INSEE', 'Statut du plan',
            'Etat du géoréférencement', 'Demande d\'opération', 'Numéro du lot',
            'Numéro de commande', 'Numéro de la tranche',
            'Nom du prestataire en charge du géoréférencement',
            'Nom du prestataire en charge du contrôle',
            'Date de verrouillage prévue', 'Date de verrouillage effective',
            'Date d\'intégration prévue', 'Date d\'intégration réalisée',
        ]
        with open(paths['atlas'], 'w', newline='', encoding='utf-8') as f:
            f.write('\ufeff')
            w = csv.writer(f, delimiter=';')
            w.writerow(atlas_fields)
            for feat in grouped:
                w.writerow([clean_value(feat['plan_nom'])] + [''] * 14)

        return True
    except Exception as e:
        QMessageBox.critical(None, 'Erreur', f'Erreur génération CSV : {e}')
        return False

def cleanup_rubber_bands(canvas):
    """Supprime toutes les QgsRubberBand du canvas actif."""
    from qgis.gui import QgsRubberBand
    for item in list(canvas.scene().items()):
        if isinstance(item, QgsRubberBand):
            canvas.scene().removeItem(item)
            del item
