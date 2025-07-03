# ---------------------------------------------------------------------------
#  Gestionnaire PI – génération Annexe 6
#  Version : 2025-06 – « longueurs sans doublons »
#  Correctif 2025-06-25c :
#      * total_zones = nombre de zones de détection (et non de folios)
#      * sécurisation de la conversion float pour l'export CSV
#      * création automatique du dossier de sortie s'il n'existe pas
#      * attribution automatique du champ id_tr (TRn ou "TRn + TRm"…)
#      * exclusion des folios "vrai" sans zone de détection (id_tr vide)
#      * Code INSEE préfixé par apostrophe pour Excel
#      * FIX QGIS 3.28 : construction de QgsSpatialIndex sans argument, puis addFeatures()
# ---------------------------------------------------------------------------

import os
import csv
import re
from typing import List

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsSpatialIndex,
    QgsField, QgsGeometry
)
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QVariant

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def clean_value(value):
    """Normalise les champs vides ou 'null'."""
    return '' if value in (None, 'null', 'NULL') else str(value)


def sort_by_tr(feature):
    """Ordre d'export : premier numéro TR dans id_tr (numérique)."""
    id_tr = clean_value(feature['id_tr'])
    if id_tr:
        m = re.search(r"\d+", id_tr.split(" + ")[0])
        if m:
            return int(m.group())
    return float('inf')


def group_raccord_with_folios_and_tr(folios, raccords):
    """Place chaque raccord juste après le folio « vrai » (≤10 m) le plus proche."""
    grouped = []
    valid_folios = [f for f in folios if f['type'] == 'vrai' and clean_value(f['id_tr']).strip()]
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
    return grouped + raccords  # ajoute les raccords orphelins en fin

# ---------------------------------------------------------------------------
# Traitement principal
# ---------------------------------------------------------------------------

def process_data(
    line_layer: QgsVectorLayer,
    detection_zone_layer: QgsVectorLayer,
    folio_layer: QgsVectorLayer,
    output_folder: str,
    zones_to_exclude: List[QgsFeature] | None = None
):
    """Calcule les statistiques et met à jour les attributs.

    Retourne :
        total_zones, length_c, length_b, length_w, corrections, folios_export, raccords
    """

    # 0. Vérifie/ajoute les champs longueurs
    new_fields = []
    for fld in ("lg_res_clc", "lg_res_clb"):
        if fld not in folio_layer.fields().names():
            new_fields.append(QgsField(fld, QVariant.Double))
    if new_fields:
        folio_layer.startEditing()
        folio_layer.dataProvider().addAttributes(new_fields)
        folio_layer.updateFields()
        folio_layer.commitChanges()

    # 1. Récupère les folios par type + index spatial
    vrais, raccords, corrections = [], [], []
    folio_index = QgsSpatialIndex()
    folio_geom = {}
    for f in folio_layer.getFeatures():
        t = str(f['type']).lower()
        if t == 'vrai':
            vrais.append(f)
            folio_index.addFeature(f)
            folio_geom[f.id()] = f.geometry()
        elif t == 'raccord':
            raccords.append(f)
        elif t == 'correction':
            corrections.append(f)
    clc = {f.id(): 0.0 for f in vrais}
    clb = {f.id(): 0.0 for f in vrais}

    # 1.b Prépare les zones de détection
    exclude_ids = {f.id() for f in zones_to_exclude} if zones_to_exclude else set()
    zone_feats = [z for z in detection_zone_layer.getFeatures() if z['type'] == 0 and z.id() not in exclude_ids]
    zone_union = QgsGeometry.unaryUnion([z.geometry() for z in zone_feats]) if zone_feats else None

    # Index spatial compatible QGIS 3.28 : construction vide puis addFeatures
    zone_index = QgsSpatialIndex()
    zone_index.addFeatures(zone_feats)
    zone_geom_by_id = {z.id(): z.geometry() for z in zone_feats}
    # Libellés TRn
    sorted_zones = sorted(zone_feats, key=lambda z: int(re.search(r"\d+", str(z['id'])).group()) if re.search(r"\d+", str(z['id'])) else 0)
    zone_label = {z.id(): f"TR{idx}" for idx, z in enumerate(sorted_zones, 1)}

    # 2. Parcours des segments
    length_c = length_b = 0.0
    seen_wkb = set()
    for seg in line_layer.getFeatures():
        g_raw = seg.geometry()
        if not g_raw or g_raw.isEmpty():
            continue
        if zone_union and not g_raw.intersects(zone_union):
            continue
        g_seg = g_raw.intersection(zone_union) if zone_union else g_raw
        if g_seg.isEmpty():
            continue
        wkb = g_seg.asWkb()
        if wkb in seen_wkb:
            continue
        seen_wkb.add(wkb)

        seg_class = str(seg['classe']).strip().upper()
        seg_len = g_seg.length()
        if seg_class == 'C':
            length_c += seg_len
        elif seg_class in ('B', 'W'):
            length_b += seg_len

        cand_ids = folio_index.intersects(g_seg.boundingBox())
        if not cand_ids:
            continue
        subsegments = [(g_seg, set())]
        for fid in cand_ids:
            fol_geom = folio_geom[fid]
            if not g_seg.intersects(fol_geom):
                continue
            new_subs = []
            for geom_part, owners in subsegments:
                if geom_part.intersects(fol_geom):
                    overlap = geom_part.intersection(fol_geom)
                    rest = geom_part.difference(fol_geom)
                    if not overlap.isEmpty():
                        new_subs.append((overlap, owners | {fid}))
                    if not rest.isEmpty():
                        new_subs.append((rest, owners))
                else:
                    new_subs.append((geom_part, owners))
            subsegments = new_subs
        for geom_part, owners in subsegments:
            if not owners:
                continue
            share = geom_part.length() / len(owners)
            for fid in owners:
                if seg_class == 'C':
                    clc[fid] += share
                elif seg_class in ('B', 'W'):
                    clb[fid] += share

    # 3. Met à jour longueurs ET id_tr dans la couche folio
    folio_layer.startEditing()
    idx_clc = folio_layer.fields().indexFromName('lg_res_clc')
    idx_clb = folio_layer.fields().indexFromName('lg_res_clb')
    folios_export = []

    for f in vrais:
        fid = f.id()
        f[idx_clc] = round(clc[fid], 1)
        f[idx_clb] = round(clb[fid], 1)

        # Attribution id_tr
        intersect_labels = []
        for zid in zone_index.intersects(f.geometry().boundingBox()):
            if f.geometry().intersects(zone_geom_by_id[zid]):
                intersect_labels.append(zone_label[zid])
        intersect_labels = sorted(set(intersect_labels), key=lambda s: int(re.search(r"\d+", s).group()))
        f['id_tr'] = ' + '.join(intersect_labels) if intersect_labels else ''
        folio_layer.updateFeature(f)
        if intersect_labels:
            folios_export.append(f)

    for f in raccords:
        f[idx_clc] = None
        f[idx_clb] = None
        folio_layer.updateFeature(f)
    folio_layer.commitChanges()

    return (
        len(zone_feats),
        round(length_c, 1),
        round(length_b, 1),
        0.0,
        corrections,
        folios_export,
        raccords,
    )

# ---------------------------------------------------------------------------
# Fonctions annexes
# ---------------------------------------------------------------------------

def update_tr_numbers(detection_zone_layer: QgsVectorLayer, deleted_features: List[QgsFeature]):
    remaining = [z for z in detection_zone_layer.getFeatures("type = 0") if z.id() not in {f.id() for f in deleted_features}]
    remaining.sort(key=lambda x: int(re.search(r"\d+", str(x['id'])).group()))
    return {zone['id']: f"TR{idx}" for idx, zone in enumerate(remaining, 1)}

def generate_csv_files(corrections: List[QgsFeature],
                        folios: List[QgsFeature],
                        raccords: List[QgsFeature],
                        folio_layer: QgsVectorLayer,
                        output_folder: str) -> bool:
    try:
        # S’assure que le dossier existe
        os.makedirs(output_folder, exist_ok=True)

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
                            try:
                                # Remplacement virgule->point pour robustesse
                                raw_float = float(str(raw).replace(',', '.'))
                                val = f"{raw_float:.1f}"
                            except (ValueError, TypeError):
                                val = ''
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
            'Etat du géoréférencement', "Demande d'opération", 'Numéro du lot',
            'Numéro de commande', 'Numéro de la tranche',
            'Nom du prestataire en charge du géoréférencement',
            'Nom du prestataire en charge du contrôle',
            'Date de verrouillage prévue', 'Date de verrouillage effective',
            "Date d'intégration prévue", "Date d'intégration réalisée",
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
            # "del item" inutile : le garbage collector s'en chargera
