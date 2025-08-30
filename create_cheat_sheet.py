#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#
# python create_cheat_sheet.py \
#   --export export_from_40k_app.txt \
#   --yaml-dir data \
#   --out cheat_sheet_ultramarines.html


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from collections import defaultdict
from pathlib import Path
import re
import os
import glob
import html
from difflib import get_close_matches

try:
    import yaml  # type: ignore
except ImportError:
    raise SystemExit("PyYAML requis. Installe: pip install pyyaml")


# -----------------------------
# Stratagems
# -----------------------------
def load_stratagems(yaml_path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    return data.get("stratagems", [])


def normalize_timing(s: dict) -> tuple[str, str, str]:
    phase = s.get("phase", "command")
    step = s.get("step", "start")
    who = s.get("player", "you")  # you|opponent|any
    # Optionnel: harmoniser quelques steps vers ceux de ta grille
    alias = {
        "after_enemy_selects_targets": "start",
        "after_enemy_resolves_attacks": "end",
        "after_enemy_ends_move": "start",
        "after_enemy_declares_charge": "declare",
        "after_enemy_ends_charge_move": "move",
        "reinforcements": "start",
        "any": "start",
    }
    step = alias.get(step, step)
    # préfix utile pour visuel
    prefix = {"you": "🟦", "opponent": "🟥", "any": "🟨"}[who]
    label = f"{prefix} Strat · "
    return phase, step, label


def add_stratagems_to_timeline(
    timeline: dict, strats: list[dict], detachment_name: str
):
    for st in strats:
        if detachment_name not in st.get("detachment", []):
            continue
        for w in st.get("when", []):
            phase, step, label = normalize_timing(w)
            box = f"{label}{st['name']} ({st['cp']}CP) — {st.get('effect','')}"
            timeline.setdefault(phase, {}).setdefault(step, []).append(box)
    return timeline


def strat_items_by_phase(
    strats: list[dict], detachment_name: str | None = None
) -> dict[str, list[str]]:
    """
    Regroupe les stratagèmes par phase en <li> prêts à insérer.
    Utilise normalize_timing(w) que tu as déjà.
    """
    bucket: dict[str, list[str]] = defaultdict(list)
    for st in strats or []:
        # filtre détachement si fourni (accepte "All" si tu l'utilises)
        if detachment_name and (
            detachment_name not in st.get("detachment", [])
            and "All" not in st.get("detachment", [])
        ):
            continue

        name = st.get("name", "—")
        cp = st.get("cp", "?")
        effect = st.get("effect", "")

        for w in st.get("when", []):
            phase, step, label = normalize_timing(w)  # <- ton helper existant
            line = (
                "<li>"
                + label
                + "<b>"
                + html.escape(name)
                + "</b> ("
                + str(cp)
                + "CP) — ["
                + html.escape(step)
                + "] "
                + html.escape(effect)
                + "</li>"
            )
            bucket[phase].append(line)
    return bucket


# -----------------------------
# Parsing de l'export 40k App
# -----------------------------

UNIT_LINE_RE = re.compile(r"^([^\n(]+?)\s*\((\d+)\s*points?\)\s*$", re.IGNORECASE)
SECTION_RE = re.compile(r"^[A-Z][A-Z\s/’'–-]+$")

FORMAT_RE = re.compile(
    r"^(Combat Patrol|Incursion|Strike Force|Onslaught)\s*\((\d+)\s*points?\)\s*$",
    re.IGNORECASE,
)


def normalize_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[\u2019’']", "", s)
    s = re.sub(r"[^a-z0-9+&/ -]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_export_txt(path: str):
    """
    Retourne:
      - army: dict meta (title, points_total, faction, chapter, detachment, format, format_points)
      - units: dict key -> {display, count, points_each, section}
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    lines = [l.rstrip() for l in text.splitlines() if l is not None]

    army = {
        "title": None,
        "points_total": None,
        "faction": None,
        "chapter": None,
        "detachment": None,
        "format": None,
        "format_points": None,
    }
    units = {}
    current_section = None

    # Titre (ex: "test (995 points)")
    if lines:
        first = lines[0].strip()
        if first:
            army["title"] = re.sub(r"\s*\(.*$", "", first).strip() or first
            mpts = re.search(r"\((\d+)\s*points?\)", first, re.I)
            if mpts:
                army["points_total"] = int(mpts.group(1))

    # Méta
    for l in lines[:30]:
        if "Space Marines" in l:
            army["faction"] = "Space Marines"
        if "Ultramarines" in l:
            army["chapter"] = "Ultramarines"
        if "Gladius Task Force" in l:
            army["detachment"] = "Gladius Task Force"
        fm = FORMAT_RE.match(l.strip())
        if fm:
            army["format"] = fm.group(1).title()
            army["format_points"] = int(fm.group(2))

    # Unités
    for i, l in enumerate(lines):
        s = l.strip()
        if not s:
            continue
        if SECTION_RE.match(s):
            current_section = s.strip().upper()
            continue

        # ignorer explicitement quelques lignes d'en-tête
        if i == 0:  # première ligne = titre "test (995 points)" -> pas une unité
            continue
        if FORMAT_RE.match(s):  # "Incursion (1000 points)" -> format, pas une unité
            continue
        if s in {
            "Space Marines",
            "Ultramarines",
            "Gladius Task Force",
            "Anvil Siege Force",
            "Ironstorm Spearhead",
            "Firestorm Assault Force",
            "Stormlance Task Force",
            "Vanguard Spearhead",
            "1st Company Task Force",
            "Librarius Conclave",
        }:
            continue

        m = UNIT_LINE_RE.match(s)
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
# Chargement YAML
# -----------------------------


def load_units_from_yaml_dir(yaml_dir: str):
    units_by_key = {}
    faction_helpers = None

    for path in sorted(glob.glob(os.path.join(yaml_dir, "*.yaml"))):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

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
                if isinstance(u, dict) and u.get("name"):
                    units_by_key[normalize_name(u["name"])] = u

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


def fuzzy_find(key: str, units_by_key: dict, cutoff: float = 0.72):
    if key in units_by_key:
        return key, 1.0
    choices = list(units_by_key.keys())
    match = get_close_matches(key, choices, n=1, cutoff=cutoff)
    if match:
        return match[0], 0.9
    return None, 0.0


# -----------------------------
# Rendu HTML
# -----------------------------

CSS = """
<style>
  @page { size: A4; margin: 10mm; }
  html, body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; color: #0e1326; }
  h1 { font-size: 18px; margin: 0 0 6px; }
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
  .phase { font-weight:700; margin-top:6px; }
  .small { font-size:10px; color:#6b7280;}
  .right { text-align:right; }
  .warn { color:#b91c1c; font-weight:600; }
  .phaseboard { break-inside: avoid; border:1px solid #e5e7eb; border-radius:8px; padding:8px; margin:8px 0 12px;}
  .phaseboard .colwrap { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }
  .phaseboard .box { border:1px solid #eef2f7; border-radius:6px; padding:6px; }
  .phaseboard ul { margin:4px 0 2px 16px; }
</style>
"""

PHASE_ORDER = [
    ("command", "Phase de Commandement"),
    ("movement", "Phase de Mouvement"),
    ("shooting", "Phase de Tir"),
    ("charge", "Phase de Charge"),
    ("fight", "Phase de Combat"),
    ("end", "Fin de tour"),
]


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
            + ", ".join(html.escape(x.get("name", "—")) for x in ranged[:limit_each])
        )
    if melee:
        lines.append(
            "<b>CaC</b> : "
            + ", ".join(html.escape(x.get("name", "—")) for x in melee[:limit_each])
        )
    return "<br>".join(lines) if lines else "<span class='small'>—</span>"


def render_abilities(u, limit=3):
    ab = u.get("abilities") or {}
    unit_ab = ab.get("unit") or []
    items = []
    for x in unit_ab[:limit]:
        nm = x.get("name", "—")
        tx = x.get("text", "")
        items.append(
            f"<li><b>{html.escape(nm)}.</b> {html.escape(tx)}</li>"
            if tx
            else f"<li><b>{html.escape(nm)}</b></li>"
        )
    return (
        "<ul>" + "".join(items) + "</ul>" if items else "<span class='small'>—</span>"
    )


def collect_phase_tips_for_unit(faction_helpers, u):
    """Retourne dict phase -> [bullets] pour une unité."""
    tips = ((u.get("play_tips") or {}).get("phases")) or {}
    out = {}
    for key, _label in PHASE_ORDER:
        bullets = []
        sp = tips.get(key)
        if isinstance(sp, dict):
            for step, arr in sp.items():
                if arr:
                    for t in arr:
                        bullets.append(f"[{step}] {t}")
        elif isinstance(sp, list):
            bullets.extend(sp)
        if bullets:
            out[key] = bullets
    return out


def build_phase_board(faction_helpers, matched_units, strats):
    """Construit la Timeline globale par phase (génériques + spécifiques par unité)."""
    gen = (faction_helpers or {}).get("generic_reminders") or {}
    blocks = []

    # 2 colonnes visuelles: 3 phases par colonne
    colA = []
    colB = []

    for idx, (key, label) in enumerate(PHASE_ORDER):
        items = []
        # génériques
        gen_list = gen.get(key) or []
        if gen_list:
            items.append("<li><b>Rappels généraux :</b></li>")
            items.extend(f"<li class='small'>{html.escape(x)}</li>" for x in gen_list)

        # spécifiques par unité
        for mu in matched_units:
            u = mu.get("unit")
            if not u:
                continue
            unit_tips = collect_phase_tips_for_unit(faction_helpers, u)
            bullets = unit_tips.get(key)
            if not bullets:
                continue
            uname = u.get("name", mu["display"])
            for b in bullets:
                items.append(f"<li><b>{html.escape(uname)}</b> — {html.escape(b)}</li>")

        # stratagems
        items.extend(strats.get(key, []))

        alt_item = "<li class='small'>&mdash;</li>"  # ← ASCII safe (— devient &mdash;)
        items_html = "".join(items) if items else alt_item

        html_box = (
            "<div class='box'><div class='phase'>"
            + html.escape(label)
            + "</div><ul>"
            + items_html
            + "</ul></div>"
        )
        (colA if idx < 3 else colB).append(html_box)

    return f"""
<div class="phaseboard">
  <h2>Timeline par phase</h2>
  <div class="colwrap">
    <div>{''.join(colA)}</div>
    <div>{''.join(colB)}</div>
  </div>
</div>"""


def generate_html(army, matched_units, faction_helpers, outfile, strats):
    subtitle_bits = []
    if army.get("format"):
        p = (
            f"{army['format']} ({army['format_points']} pts)"
            if army.get("format_points")
            else army["format"]
        )
        subtitle_bits.append(p)
    if army.get("detachment"):
        subtitle_bits.append(f"Détachement : {army['detachment']}")
    if army.get("points_total"):
        subtitle_bits.append(f"Total liste : {army['points_total']} pts")

    head = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>{html.escape(army.get('title') or 'Cheat Sheet')}</title>
{CSS}
</head><body>
<h1>{html.escape(army.get('title') or 'Cheat Sheet')}</h1>
<div class="meta">{' · '.join(html.escape(x) for x in subtitle_bits if x)}</div>
"""

    # Timeline globale en tête
    head += build_phase_board(faction_helpers, matched_units, strats)

    head += '<div class="grid">'

    # Cartes unités
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
  <div class="small">Vérifie l'orthographe de la fiche ou complète les YAML.</div>
</div>"""
            )
            continue

        name = u.get("name", mu["display"])
        role = u.get("role", "")
        badges = []
        if role:
            badges.append(role)
        kws = u.get("keywords") or []
        if "Ultramarines" in kws:
            badges.append("Ultramarines")
        if count > 1:
            badges.append(f"x{count}")

        stats = render_stats(u)
        weapons = render_weapons(u)
        abilities = render_abilities(u)

        # mini recap par phase pour la carte (facultatif mais utile)
        mini_phase = collect_phase_tips_for_unit(faction_helpers, u)
        mini_html = []
        for k, label in PHASE_ORDER:
            if k in mini_phase:
                mini_html.append(
                    f"<div class='small'><b>{label}:</b> "
                    + " | ".join(html.escape(x) for x in mini_phase[k][:2])
                    + "</div>"
                )
        mini_block = "".join(mini_html) if mini_html else "<div class='small'>—</div>"

        pills = " ".join(f"<span class='pill'>{html.escape(t)}</span>" for t in badges)

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
  <div class="phases"><b>Cette unité — moments clés</b>{mini_block}</div>
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


def run(export_path: str, yaml_dir: str, out_file: str) -> str:
    army, listed = parse_export_txt(export_path)
    units_by_key, faction_helpers = load_units_from_yaml_dir(yaml_dir)

    matched = []
    section_order = {
        "CHARACTERS": 0,
        "BATTLELINE": 1,
        "DEDICATED TRANSPORTS": 2,
        "OTHER DATASHEETS": 3,
    }
    for key, info in listed.items():
        mkey, score = fuzzy_find(key, units_by_key, cutoff=0.72)
        unit = units_by_key.get(mkey) if mkey else None
        matched.append(
            {
                "query_key": key,
                "display": info["display"],
                "count": info["count"],
                "points_each": info["points_each"],
                "section": info.get("section") or "",
                "unit": unit,
                "match_score": score,
            }
        )
    matched.sort(
        key=lambda x: (
            section_order.get((x["section"] or "").upper(), 9),
            -(x["match_score"] or 0),
        )
    )

    # Stratagems
    strats = []
    strat_yaml_path = Path(yaml_dir, "stratagems.yaml")
    strats = load_stratagems(strat_yaml_path)

    strats = strat_items_by_phase(strats, army["detachment"])

    outfile = generate_html(army, matched, faction_helpers, out_file, strats)
    return outfile


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fiche mémo A4 (HTML) depuis export 40k")
    ap.add_argument("--export", required=True, help="export_from_40k_app.txt")
    ap.add_argument("--yaml-dir", required=True, help="Dossier des ultramarines_*.yaml")
    ap.add_argument(
        "--out", default="cheat_sheet_ultramarines.html", help="HTML de sortie"
    )
    args = ap.parse_args(argv)
    out = run(args.export, args.yaml_dir, args.out)
    print(f"✅ Fiche générée: {out}")


if __name__ == "__main__":
    main()
