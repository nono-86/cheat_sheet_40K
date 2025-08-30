#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#
# python create_cheat_sheet.py \
#   --export export_from_40k_app.txt \
#   --yaml-dir space_marines \
#   --out cheat_sheet_ultramarines.html


import argparse
import re
import os
import glob
import html
from difflib import get_close_matches

# Dépendance standard unique
try:
    import yaml
except ImportError:
    raise SystemExit(
        "Le module 'yaml' (PyYAML) est requis.\n" "Installe-le avec: pip install pyyaml"
    )

# -----------------------------
# Parsing de l'export 40k App
# -----------------------------

UNIT_LINE_RE = re.compile(r"^([^\n(]+?)\s*\((\d+)\s*points?\)\s*$", re.IGNORECASE)
SECTION_RE = re.compile(r"^[A-Z][A-Z\s/’'-]+$")


def normalize_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[\u2019’']", "", s)  # enlever apostrophes
    s = re.sub(r"[^a-z0-9+&/ -]", " ", s)  # nettoyer ponctuation exotique
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_export_txt(path: str):
    """
    Retourne:
      - army: dict méta (faction, détachement, format…)
      - units: dict name -> {"count": n, "points_each": x, "section": "CHARACTERS"/...}
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    lines = [l.rstrip() for l in text.splitlines()]
    army = {
        "title": None,
        "faction": None,
        "chapter": None,
        "detachment": None,
        "format": None,
    }
    units = {}
    current_section = None

    # Métadonnées simples (tolérant)
    for i, l in enumerate(lines[:20]):
        if i == 0 and l.strip():
            army["title"] = l.strip()
        elif "Space Marines" in l:
            army["faction"] = "Space Marines"
        elif "Ultramarines" in l:
            army["chapter"] = "Ultramarines"
        elif "Gladius Task Force" in l:
            army["detachment"] = "Gladius Task Force"
        elif "Incursion" in l or "Combat Patrol" in l or "Strike Force" in l:
            army["format"] = l.strip()

    # Extraire unités
    for l in lines:
        if not l.strip():
            continue
        if SECTION_RE.match(l.strip()):
            current_section = l.strip()
            continue
        m = UNIT_LINE_RE.match(l.strip())
        if m:
            name = m.group(1).strip()
            pts = int(m.group(2))
            key = normalize_name(name)
            if key not in units:
                units[key] = {
                    "display": name,
                    "count": 0,
                    "points_each": pts,
                    "section": current_section,
                }
            units[key]["count"] += 1

    return army, units


# -----------------------------
# Chargement des YAML
# -----------------------------


def load_units_from_yaml_dir(yaml_dir: str):
    """
    Concatène toutes les listes 'units:' trouvées dans les fichiers .yaml du dossier.
    Retourne:
      - units_by_key: dict normalisé -> fiche unité (dict)
      - faction_helpers: le premier bloc faction_helpers trouvé (ou défaut)
    """
    units_by_key = {}
    faction_helpers = None

    for path in sorted(glob.glob(os.path.join(yaml_dir, "*.yaml"))):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # top-level helpers
        if (
            faction_helpers is None
            and isinstance(data, dict)
            and "faction_helpers" in data
        ):
            faction_helpers = data["faction_helpers"]

        if (
            isinstance(data, dict)
            and "units" in data
            and isinstance(data["units"], list)
        ):
            for u in data["units"]:
                if not isinstance(u, dict):
                    continue
                name = u.get("name")
                if not name:
                    continue
                key = normalize_name(name)
                units_by_key[key] = u

    # défaut minimal si non trouvé
    if faction_helpers is None:
        faction_helpers = {
            "turn_start": ["Déclarer/mettre à jour les effets de détachement/faction."],
            "generic_reminders": {
                "command": ["Gagner CP ; tests d’ébranlement ; poser auras/buffs."],
                "movement": ["Mesurer menaces ; garder couvert/lignes de vue."],
                "shooting": ["Choisir cibles intelligemment."],
                "charge": ["Penser multi-charge ; garder 1 CP pour relance critique."],
                "fight": [
                    "Activer dans le bon ordre ; pile-in/consolidation pour voler OC."
                ],
                "end": ["Compter OC ; scorer primaires/secondaires ; valider actions."],
            },
        }
    return units_by_key, faction_helpers


def fuzzy_find(name_key: str, units_by_key: dict, cutoff: float = 0.75):
    if name_key in units_by_key:
        return name_key, 1.0
    choices = list(units_by_key.keys())
    match = get_close_matches(name_key, choices, n=1, cutoff=cutoff)
    if match:
        return match[0], 0.9
    return None, 0.0


# -----------------------------
# Rendu HTML compact A4
# -----------------------------

CSS = """
<style>
  @page { size: A4; margin: 10mm; }
  html, body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; color: #0e1326; }
  h1 { font-size: 18px; margin: 0 0 8px; }
  h2 { font-size: 14px; margin: 10px 0 6px; border-bottom: 1px solid #ddd; padding-bottom: 4px;}
  .meta { font-size: 11px; margin-bottom: 8px; color: #374151; }
  .grid { column-count: 2; column-gap: 14px; }
  .card { break-inside: avoid; border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px; margin: 0 0 10px; }
  .unithead { display:flex; justify-content:space-between; align-items:baseline; }
  .name { font-weight: 700; font-size: 13px; }
  .tag { font-size: 10px; background:#edf2ff; color:#1d4ed8; padding:2px 6px; border-radius: 999px; margin-left:6px;}
  .stats { font-size: 11px; margin: 4px 0 6px; color:#111827;}
  .stats b { font-weight:700; }
  .weapons, .abilities, .phases { font-size: 11px; margin: 4px 0; }
  .weapons ul, .abilities ul, .phases ul { margin: 2px 0 2px 16px; padding: 0; }
  .pill { display:inline-block; font-size:10px; padding:1px 6px; border:1px solid #e5e7eb; border-radius:999px; margin:1px 4px 1px 0; color:#111827;}
  .phase { font-weight:600; margin-top:4px; }
  .small { font-size:10px; color:#6b7280;}
  .right { text-align:right; }
  .warn { color:#b91c1c; font-weight:600; }
</style>
"""


def render_stats(u):
    base = u.get("base") or {}

    def g(k, default="–"):
        return base.get(k, default)

    parts = [
        f"M {g('M')}",
        f"T {g('T')}",
        f"Sv {g('Sv')}",
        f"W {g('W')}",
        f"Ld {g('Ld')}",
        f"OC {g('OC')}",
    ]
    if base.get("Inv"):
        parts.append(f"Inv {base['Inv']}")
    if base.get("FnP"):
        parts.append(f"FnP {base['FnP']}")
    return "  |  ".join(parts)


def render_weapons(u, limit_each=2):
    lines = []
    w = u.get("weapons") or {}
    ranged = w.get("ranged") or []
    melee = w.get("melee") or []

    if ranged:
        lines.append(
            "<b>Tir</b> : "
            + ", ".join([html.escape(x.get("name", "—")) for x in ranged[:limit_each]])
        )
    if melee:
        lines.append(
            "<b>CaC</b> : "
            + ", ".join([html.escape(x.get("name", "—")) for x in melee[:limit_each]])
        )
    return "<br>".join(lines) if lines else "<span class='small'>—</span>"


def render_abilities(u, limit=3):
    ab = u.get("abilities") or {}
    unit_ab = ab.get("unit") or []
    items = []
    for x in unit_ab[:limit]:
        nm = x.get("name", "—")
        tx = x.get("text", "")
        if tx:
            items.append(f"<li><b>{html.escape(nm)}.</b> {html.escape(tx)}</li>")
        else:
            items.append(f"<li><b>{html.escape(nm)}</b></li>")
    if not items:
        return "<span class='small'>—</span>"
    return "<ul>" + "".join(items) + "</ul>"


def collect_phase_tips(faction_helpers, u):
    # Rappels génériques
    gen = (faction_helpers or {}).get("generic_reminders") or {}
    # Spécifiques unité
    tips = ((u.get("play_tips") or {}).get("phases")) or {}

    def phase_block(phase_key, label):
        # agrège génériques + spécifiques (par sous-étape si présent)
        bullets = []
        gen_list = gen.get(phase_key) or []
        bullets.extend(gen_list)
        # spécifiques
        sp = tips.get(phase_key) or {}
        if isinstance(sp, dict):
            # concat toutes sous-étapes
            for step, arr in sp.items():
                if not arr:
                    continue
                bullets.append(f"[{step}] " + " / ".join(arr))
        elif isinstance(sp, list):
            bullets.extend(sp)

        if not bullets:
            return ""
        items = "".join(f"<li>{html.escape(x)}</li>" for x in bullets)
        return f"<div class='phase'>{label}</div><ul>{items}</ul>"

    order = [
        ("command", "Phase de Commandement"),
        ("movement", "Mouvement"),
        ("shooting", "Tir"),
        ("charge", "Charge"),
        ("fight", "CàC"),
        ("end", "Fin de tour"),
    ]
    out = [phase_block(k, lab) for k, lab in order]
    return "".join([x for x in out if x])


def generate_html(army, matched_units, faction_helpers, outfile):
    head = f"""
<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>{html.escape(army.get('title') or 'Cheat Sheet')}</title>
{CSS}
</head><body>
<h1>Cheat Sheet — {html.escape(army.get('chapter') or army.get('faction') or '')}</h1>
<div class="meta">
  {html.escape(army.get('format') or '')} · Détachement: {html.escape(army.get('detachment') or '—')}
</div>
<div class="grid">
"""
    cards = []
    for mu in matched_units:
        u = mu["unit"]
        count = mu["count"]
        score = mu["match_score"]
        if u is None:
            cards.append(
                f"""
<div class="card">
  <div class="unithead">
    <div class="name">{html.escape(mu['display'])}</div>
    <div class="warn small">Non trouvé dans YAML</div>
  </div>
  <div class="small">Astuce: vérifie l'orthographe de la fiche ou complète les YAML.</div>
</div>"""
            )
            continue

        name = u.get("name", mu["display"])
        role = u.get("role", "")
        head_badges = []
        if role:
            head_badges.append(role)
        kws = u.get("keywords") or []
        if "Ultramarines" in kws:
            head_badges.append("Ultramarines")
        if count > 1:
            head_badges.append(f"x{count}")

        stats = render_stats(u)
        weapons = render_weapons(u)
        abilities = render_abilities(u)
        phases = collect_phase_tips(faction_helpers, u)

        pills = " ".join(
            f"<span class='pill'>{html.escape(t)}</span>" for t in head_badges
        )

        cards.append(
            f"""
<div class="card">
  <div class="unithead">
    <div class="name">{html.escape(name)}</div>
    <div class="small right">match {int(score*100)}%</div>
  </div>
  <div>{pills}</div>
  <div class="stats"><b>Profil</b> — {stats}</div>
  <div class="weapons"><b>Armes</b><br>{weapons}</div>
  <div class="abilities"><b>Capacités</b>{abilities}</div>
  <div class="phases"><b>Rappels par phase</b>{phases or "<div class='small'>—</div>"}</div>
</div>
"""
        )

    tail = "</div></body></html>"
    html_str = head + "\n".join(cards) + tail
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(html_str)
    return outfile


# -----------------------------
# Main
# -----------------------------


def main():
    ap = argparse.ArgumentParser(
        description="Génère une fiche mémo A4 à partir d'un export 40k App + YAMLs."
    )
    ap.add_argument(
        "--export",
        required=True,
        help="Chemin du fichier texte exporté depuis l'app 40k.",
    )
    ap.add_argument(
        "--yaml-dir", required=True, help="Dossier contenant les ultramarines_*.yaml"
    )
    ap.add_argument(
        "--out", default="cheat_sheet_ultramarines.html", help="Fichier HTML de sortie."
    )
    args = ap.parse_args()

    army, list_units = parse_export_txt(args.export)
    units_by_key, faction_helpers = load_units_from_yaml_dir(args.yaml_dir)

    matched = []
    for key, info in list_units.items():
        mkey, score = fuzzy_find(key, units_by_key, cutoff=0.70)
        unit = units_by_key.get(mkey) if mkey else None
        matched.append(
            {
                "query_key": key,
                "display": info["display"],
                "count": info["count"],
                "points_each": info["points_each"],
                "section": info["section"],
                "unit": unit,
                "match_score": score,
            }
        )

    outfile = generate_html(army, matched, faction_helpers, args.out)
    print(f"✅ Fiche générée: {outfile}")
    print(
        "Ouvre le HTML et imprime en A4 (de préférence en mode Portrait, sans marges supplémentaires)."
    )


if __name__ == "__main__":
    main()
