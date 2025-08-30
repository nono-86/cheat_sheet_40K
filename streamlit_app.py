import re
import io
import sys
import yaml
import tempfile
from pathlib import Path
from typing import Dict, Any, List
import streamlit as st
from jinja2 import Template

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
from create_cheat_sheet import run

# --------------------------- CONFIG ---------------------------------
DEFAULT_YAML_DIR = Path(__file__).parent / "data"
FACTION = "Adeptus Astartes"
CHAPTER = "Ultramarines"
DETACHMENT_DEFAULT = "Gladius Task Force"

# Quelques alias pratiques (ajoute ici si une unité n'est pas matchée)
ALIASES = {
    "assault intercessors with jump pack": "Assault Intercessors with Jump Packs",
    "captain with jump pack": "Captain with Jump Pack",
    "intercessor squad": "Intercessor Squad",
    "bladeguard veteran squad": "Bladeguard Veteran Squad",
    "ballistus dreadnought": "Ballistus Dreadnought",
    "terminator squad": "Terminator Squad",
}

# ------------------------ UTILS : PARSE / LOAD ----------------------


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s*\(.*?\)", "", s)  # retire parenthèses
    s = s.replace("with jump packs", "with jump pack")
    s = s.replace("w/ jump packs", "with jump pack")
    s = s.replace(" w/", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_yaml_files(files: List[io.BytesIO]) -> Dict[str, Any]:
    """Charge un corpus YAML à partir d'objets uploadés."""
    phases, faction_helpers, units = None, None, []
    for f in files:
        data = yaml.safe_load(f.read().decode("utf-8"))
        if phases is None and "phases" in data:
            phases = data["phases"]
        if faction_helpers is None and "faction_helpers" in data:
            faction_helpers = data["faction_helpers"]
        if "units" in data:
            units.extend(data["units"])
    if phases is None:
        phases = {"order": [], "steps": {}}
    if faction_helpers is None:
        faction_helpers = {}
    return {"units": units, "phases": phases, "faction_helpers": faction_helpers}


def load_yaml_dir(directory: Path) -> Dict[str, Any]:
    files = sorted(directory.glob("ultramarines_*.yaml"))
    uploads = []
    for f in files:
        uploads.append(io.BytesIO(f.read_bytes()))
    return load_yaml_files(uploads)


def build_units_index(all_units: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx = {norm(u["name"]): u for u in all_units}
    for k, v in ALIASES.items():
        if norm(v) in idx and k not in idx:
            idx[k] = idx[norm(v)]
    return idx


def parse_export_text(txt: str) -> Dict[str, Any]:
    lines = [l.strip() for l in txt.splitlines()]
    head = [l for l in lines if l][:5]
    meta = {
        "list_name": head[0] if len(head) > 0 else "Ma liste",
        "faction": head[1] if len(head) > 1 else FACTION,
        "chapter": head[2] if len(head) > 2 else CHAPTER,
        "format": head[3] if len(head) > 3 else "Incursion",
        "detachment": head[4] if len(head) > 4 else DETACHMENT_DEFAULT,
    }
    units = []
    for l in lines:
        if re.search(r"\(\d+\s*points?\)\s*$", l):
            units.append({"name": re.sub(r"\s*\(\d+\s*points?\)\s*$", "", l).strip()})
    return {"meta": meta, "units": units}


def collect_phase_tips(
    phases: Dict[str, Any],
    faction_helpers: Dict[str, Any],
    selected_units: List[Dict[str, Any]],
) -> Dict[str, Dict[str, List[str]]]:
    result = {}
    order = phases.get("order", [])
    steps = phases.get("steps", {})
    for phase in order:
        result[phase] = {s: [] for s in steps.get(phase, [])}

    # Faction helpers génériques
    gen = faction_helpers.get("generic_reminders", {})
    for phase, payload in gen.items():
        if isinstance(payload, list):
            if phase in result and result[phase]:
                bucket = (
                    "start"
                    if "start" in result[phase]
                    else list(result[phase].keys())[0]
                )
                result[phase][bucket].extend(payload)
        elif isinstance(payload, dict):
            for stp, msgs in payload.items():
                if phase in result and stp in result[phase]:
                    result[phase][stp].extend(msgs)

    # Play tips par unité
    for u in selected_units:
        tips = (u.get("play_tips") or {}).get("phases", {})
        for phase, stepdict in tips.items():
            if phase not in result:
                continue
            for stp, msgs in stepdict.items():
                if stp in result[phase] and msgs:
                    result[phase][stp].extend([f"[{u['name']}] {m}" for m in msgs])
    return result


# -------------------------- HTML TEMPLATE ---------------------------

HTML_TPL = Template(
    r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>{{ meta.list_name }} — Cheat Sheet</title>
<style>
:root { --ink:#0b2e54; --muted:#6b7280; }
@page { size:A4; margin:12mm; }
@media print { .noprint { display:none !important; } body { margin:0; } }
body { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color:#111; }
h1 { font-size:22px; margin:0 0 4px; color:var(--ink); }
h2 { font-size:16px; margin:18px 0 6px; color:var(--ink); }
h3 { font-size:14px; margin:12px 0 6px; color:var(--ink); }
.muted { color:var(--muted); }
.card { border:1px solid #e5e7eb; border-radius:10px; padding:10px 12px; margin-bottom:8px; }
.grid { display:grid; grid-template-columns: 1fr 1fr; gap:12px; }
.pill { display:inline-block; padding:3px 8px; border:1px solid #cbd5e1; border-radius:999px; font-size:12px; color:#334155; }
.kvs { font-size:12px; color:#374151; }
ul { margin:6px 0 8px 18px; } li{ margin:3px 0; }
.phase-table{ width:100%; border-collapse:separate; border-spacing:0 6px; }
.phase-name{ width:140px; font-weight:600; vertical-align:top; }
.step{ margin-bottom:4px; }
.warn{ color:#b45309; }
</style>
</head>
<body>
  <div class="noprint" style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
    <div>
      <h1>{{ meta.list_name }}</h1>
      <div class="muted">{{ meta.format }} — {{ meta.chapter }} — {{ meta.detachment }}</div>
    </div>
  </div>

  {% if faction_helpers.turn_start %}
  <div class="card">
    <h2>Début de tour</h2>
    <ul>{% for t in faction_helpers.turn_start %}<li>{{ t }}</li>{% endfor %}</ul>
  </div>
  {% endif %}

  <div class="card">
    <h2>Timeline — Phases & Rappels</h2>
    <table class="phase-table">
      {% for phase in phases.order %}
        <tr>
          <td class="phase-name">{{ phase|capitalize }}</td>
          <td>
            {% set steps = phases.steps.get(phase, []) %}
            {% for st in steps %}
              {% set tips = phase_tips.get(phase, {}).get(st, []) %}
              {% if tips %}
                <div class="step"><span class="pill">{{ st }}</span>
                  <ul>{% for tip in tips %}<li>{{ tip }}</li>{% endfor %}</ul>
                </div>
              {% endif %}
            {% endfor %}
          </td>
        </tr>
      {% endfor %}
    </table>
  </div>

  <div class="grid">
    {% for u in units %}
      <div class="card">
        <h3>{{ u.name }}</h3>
        {% if u.role %}<div class="kvs">{{ u.role }}</div>{% endif %}
        {% if u.base %}<div class="kvs">
          M {{u.base.M}} • T {{u.base.T}} • Sv {{u.base.Sv}} • W {{u.base.W}} • Ld {{u.base.Ld}} • OC {{u.base.OC}}
          {% if u.base.Inv %} • Inv {{u.base.Inv}}{% endif %}{% if u.base.FnP %} • FnP {{u.base.FnP}}{% endif %}
        </div>{% endif %}

        {% if u.weapons and u.weapons.ranged %}
          <h4>Armes de tir</h4>
          <ul>
            {% for w in u.weapons.ranged %}
            <li><b>{{w.name}}</b> — {{w.range}}, A {{w.A}}, BS {{w.BS}}, S {{w.S}}, AP {{w.AP}}, D {{w.D}}
              {% if w.keywords %}<span class="muted">({{ w.keywords|join(", ") }})</span>{% endif %}</li>
            {% endfor %}
          </ul>
        {% endif %}

        {% if u.weapons and u.weapons.melee %}
          <h4>Armes de CàC</h4>
          <ul>
            {% for w in u.weapons.melee %}
            <li><b>{{w.name}}</b> — A {{w.A}}, WS {{w.WS}}, S {{w.S}}, AP {{w.AP}}, D {{w.D}}
              {% if w.keywords %}<span class="muted">({{ w.keywords|join(", ") }})</span>{% endif %}</li>
            {% endfor %}
          </ul>
        {% endif %}

        {% if u.abilities and u.abilities.unit %}
          <h4>Rappels & règles</h4>
          <ul>{% for ab in u.abilities.unit %}<li><b>{{ab.name}}.</b> {{ab.text}}</li>{% endfor %}</ul>
        {% endif %}
      </div>
    {% endfor %}
  </div>

  {% if missing %}
    <div class="card warn"><b>Unités non trouvées dans les YAML :</b> {{ missing|join(", ") }}</div>
  {% endif %}
</body>
</html>
"""
)


def render_html(
    meta, phases, faction_helpers, selected_units, missing, phase_tips
) -> str:
    return HTML_TPL.render(
        meta=meta,
        phases=phases,
        faction_helpers=faction_helpers,
        units=selected_units,
        missing=missing,
        phase_tips=phase_tips,
    )


def save_uploaded_file(uploaded_file, dir: str | None = None) -> str:
    """Sauve un UploadedFile Streamlit sur le disque et renvoie le chemin absolu."""
    suffix = Path(uploaded_file.name).suffix or ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=dir) as tmp:
        tmp.write(uploaded_file.getbuffer())  # bytes
        tmp.flush()
        return tmp.name  # chemin du fichier temp


# ------------------------------ UI ----------------------------------

st.set_page_config(page_title="40k Cheat Sheet", layout="wide")
st.title("40k Cheat Sheet — Streamlit")

tab_input, tab_preview = st.tabs(["1) Entrée & YAML", "2) Aperçu / Export"])

with tab_input:
    st.subheader("Source YAML")
    src = st.radio(
        "Charger les données d’unités depuis…",
        ["Dossier local `space_marines/`", "Upload de fichiers YAML"],
        horizontal=True,
    )

    corpus = None
    if src == "Dossier local `space_marines/`":
        if DEFAULT_YAML_DIR.exists():
            corpus = load_yaml_dir(DEFAULT_YAML_DIR)
            st.success(
                f"{len(corpus['units'])} unités chargées depuis `{DEFAULT_YAML_DIR.name}/`."
            )
        else:
            st.warning(
                "Dossier `space_marines/` introuvable à côté de l'app. Utilise l’upload."
            )
    else:
        uploads = st.file_uploader(
            "Dépose plusieurs fichiers YAML (ultramarines_*.yaml)",
            type=["yaml", "yml"],
            accept_multiple_files=True,
        )
        if uploads:
            corpus = load_yaml_files(uploads)
            st.success(f"{len(corpus['units'])} unités chargées via upload.")

    st.subheader("Export 40k")
    col1, col2 = st.columns([2, 1])
    with col1:
        export_text = st.text_area(
            "Colle ici l’export depuis l’app 40k",
            height=240,
            placeholder="test (995 points)\n\nSpace Marines\nUltramarines\nIncursion (1000 points)\nGladius Task Force\n\nCHARACTERS\n\nCaptain with Jump Pack (75 points)\n  • ...",
        )
    with col2:
        txt_file = st.file_uploader("…ou uploade le .txt", type=["txt"])
        if txt_file and not export_text.strip():
            export_text = txt_file.read().decode("utf-8", errors="ignore")
            st.info("Texte rempli depuis le fichier uploadé.")

    if st.button("Générer la fiche"):
        # Chemin local : on sauve dans un temp file
        uploaded_path = save_uploaded_file(txt_file)  # <-- VOILÀ LE PATH
        st.session_state["uploaded_path"] = uploaded_path

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_out:
            out_html_path = tmp_out.name
        st.session_state["out_html_path"] = out_html_path

        run(uploaded_path, DEFAULT_YAML_DIR, out_html_path)
        html = Path(out_html_path).read_text(encoding="utf-8")

        st.session_state["preview_html"] = html  # stocke pour l'affichage persistant
        st.toast("Fiche générée ✅")

        # affiche le résultat tout de suite
        st.download_button(
            "Télécharger le HTML",
            data=html,
            file_name="cheat_sheet_40k.html",
            mime="text/html",
            key="dl_html",
        )
        st.components.v1.html(html, height=900, scrolling=True)

    # bouton pour repartir de zéro (ré-initialiser et relancer le script)
    if st.button("Nouvelle fiche"):
        for k in ("preview_html", "export_text", "parsed_list"):
            st.session_state.pop(k, None)
        st.rerun()  # Streamlit >= 1.27 (sinon: st.experimental_rerun())

with tab_preview:
    if "corpus" not in st.session_state or "export_text" not in st.session_state:
        st.info(
            "Charge les YAML et colle l’export dans l’onglet précédent, puis clique sur **Générer la cheat sheet**."
        )
    else:
        corpus = st.session_state["corpus"]
        parsed = parse_export_text(st.session_state["export_text"])

        units_index = build_units_index(corpus["units"])
        selected, missing = [], []
        for u in parsed["units"]:
            found = units_index.get(norm(u["name"]))
            if found:
                selected.append(found)
            else:
                missing.append(u["name"])

        phase_tips = collect_phase_tips(
            corpus["phases"], corpus["faction_helpers"], selected
        )
        html = render_html(
            parsed["meta"],
            corpus["phases"],
            corpus["faction_helpers"],
            selected,
            missing,
            phase_tips,
        )

        st.subheader("Aperçu")
        st.components.v1.html(html, height=900, scrolling=True)

        st.download_button(
            "Télécharger le HTML",
            data=html.encode("utf-8"),
            file_name=f"cheat_{parsed['meta']['list_name'].strip().replace(' ','_')}.html",
            mime="text/html",
            use_container_width=True,
        )
