#!/usr/bin/env bash
#
# restyle_figures.sh -- enlarge Figure 1, 3 and 5 text without breaking layout.
#
# Run from the directory holding 4.plotting_manuscript_uncertainity.py:
#     bash restyle_figures.sh --check    # report matches, write nothing
#     bash restyle_figures.sh            # back up, patch, syntax-check
#
# Idempotent. Restores the backup automatically if the result won't compile.
#
set -uo pipefail

F="${F:-4.plotting_manuscript_uncertainity.py}"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

[ -f "$F" ] || { echo "[error] $F not found in $PWD"; exit 1; }

hits=0; misses=0

# rep <description> <sed-expression> <grep-pattern-for-old> <grep-pattern-for-new>
rep() {
  local desc="$1" expr="$2" old="$3" new="$4"
  if grep -qF -- "$new" "$F"; then
    echo "  [already] $desc"
  elif grep -qF -- "$old" "$F"; then
    hits=$((hits+1))
    echo "  [apply]   $desc"
    [ "$CHECK" -eq 0 ] && sed -i "$expr" "$F"
  else
    misses=$((misses+1))
    echo "  [MISS]    $desc"
  fi
}

if [ "$CHECK" -eq 0 ]; then
  BAK="$F.$(date +%Y%m%d_%H%M%S).bak"
  cp "$F" "$BAK"
  echo "[info] backup: $BAK"
fi

echo
echo "-- canvas sizes ---------------------------------------------------------"
rep "Fig 1 figsize -> (20, 14)" \
    's/figsize=(17\.5, 12\.25)/figsize=(20, 14)/' \
    'figsize=(17.5, 12.25)' 'figsize=(20, 14)'
rep "Fig 5 figsize -> (20, 14)" \
    's/figsize=(30, 21)/figsize=(20, 14)/' \
    'figsize=(30, 21)' 'figsize=(20, 14)'
rep "Fig 3 figsize -> (20, 7.2)" \
    's/figsize=(18, 6\.5)/figsize=(20, 7.2)/' \
    'figsize=(18, 6.5)' 'figsize=(20, 7.2)'

echo
echo "-- Fig 1 / 5 layout -----------------------------------------------------"
rep "wider maps (width_ratios 2.1 -> 2.6)" \
    's/width_ratios=\[2\.1, 1\.0\]/width_ratios=[2.6, 1.0]/' \
    'width_ratios=[2.1, 1.0]' 'width_ratios=[2.6, 1.0]'
rep "more room below panels (bottom 0.11 -> 0.17)" \
    's/^        bottom=0\.11,$/        bottom=0.17,/' \
    '        bottom=0.11,' '        bottom=0.17,'
rep "headroom for panel titles (top 0.97 -> 0.94)" \
    's/^        top=0\.97,$/        top=0.94,/' \
    '        top=0.97,' '        top=0.94,'
rep "column gap (wspace 0.18 -> 0.22)" \
    's/^        wspace=0\.18,$/        wspace=0.22,/' \
    '        wspace=0.18,' '        wspace=0.22,'
rep "panel b legend -> lower right, single column" \
    's/        title="Five-GCM mean and min–max",/        title="Five-GCM mean and min–max",\n        title_fontsize=FS["small"],\n        loc="lower right",\n        ncol=1,/' \
    '        title="Five-GCM mean and min–max",' '        title_fontsize=FS["small"],'
rep "loss\/gain arrows lower + sized" \
    's/^        -0\.10,$/        -0.17,/' \
    '        -0.10,' '        -0.17,'
rep "panel d x-range padding (12 -> 20)" \
    's/float(dr_summary\["max"\]\.max()) + 12\.0/float(dr_summary["max"].max()) + 20.0/' \
    'float(dr_summary["max"].max()) + 12.0' 'float(dr_summary["max"].max()) + 20.0'
rep "driver legend 6 cols -> 3" \
    's/^        ncol=6,$/        ncol=3,/' \
    '        ncol=6,' '        ncol=3,'
rep "driver legend anchor 0.01 -> 0.005" \
    's/bbox_to_anchor=(0\.5, 0\.01),/bbox_to_anchor=(0.5, 0.005),/' \
    'bbox_to_anchor=(0.5, 0.01),' 'bbox_to_anchor=(0.5, 0.005),'

echo
echo "-- Fig 3 layout ---------------------------------------------------------"
rep "left margin for realm labels (0.12 -> 0.20)" \
    's/^        left=0\.12,$/        left=0.20,/' \
    '        left=0.12,' '        left=0.20,'
rep "bottom margin for legend (0.21 -> 0.28)" \
    's/^        bottom=0\.21,$/        bottom=0.28,/' \
    '        bottom=0.21,' '        bottom=0.28,'
rep "lollipop legend anchor 0.008 -> 0.005" \
    's/bbox_to_anchor=(0\.5, 0\.008),/bbox_to_anchor=(0.5, 0.005),/' \
    'bbox_to_anchor=(0.5, 0.008),' 'bbox_to_anchor=(0.5, 0.005),'
rep "proportional title size" \
    's/fontsize=FS\["title"\] + 2,/fontsize=FS["title"] * 1.15,/' \
    'fontsize=FS["title"] + 2,' 'fontsize=FS["title"] * 1.15,'
rep "proportional axis size" \
    's/fontsize=FS\["axis"\] + 1,/fontsize=FS["axis"] * 1.05,/' \
    'fontsize=FS["axis"] + 1,' 'fontsize=FS["axis"] * 1.05,'
rep "proportional tick size" \
    's/fontsize=FS\["tick"\] + 1,/fontsize=FS["tick"] * 1.05,/g' \
    'fontsize=FS["tick"] + 1,' 'fontsize=FS["tick"] * 1.05,'
rep "tick labelsize proportional" \
    's/labelsize=FS\["tick"\] + 1,/labelsize=FS["tick"] * 1.05,/' \
    'labelsize=FS["tick"] + 1,' 'labelsize=FS["tick"] * 1.05,'

echo
echo "-- Fig 3 shared x-label (python, multi-line) ----------------------------"
if [ "$CHECK" -eq 1 ]; then
  grep -q 'fig.supxlabel' "$F" \
    && echo "  [already] single shared x-label" \
    || echo "  [apply]   replace 4 repeated x-labels with one fig.supxlabel"
else
python3 - "$F" <<'PYEOF'
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()

if "fig.supxlabel" in s:
    print("  [already] single shared x-label")
else:
    old = re.compile(
        r'        ax\.set_xlabel\(\n'
        r'            "Net area change \(10³ km²\)",\n'
        r'            fontsize=FS\["axis"\][^\n]*\n'
        r'            fontweight="bold",\n'
        r'        \)\n'
    )
    s2, n = old.subn('        ax.set_xlabel("")\n', s)
    if n == 0:
        print("  [MISS]    per-panel x-label block not found, do this one by hand")
    else:
        anchor = '    fig.savefig(\n        OUT / "figure3_lollipop_net_change.png",'
        ins = (
            '    fig.supxlabel(\n'
            '        "Net area change (10³ km²)",\n'
            '        fontsize=FS["axis"] * 1.1,\n'
            '        fontweight="bold",\n'
            '        y=0.10,\n'
            '    )\n\n'
        )
        if anchor in s2:
            s2 = s2.replace(anchor, ins + anchor, 1)
            open(p, "w", encoding="utf-8").write(s2)
            print(f"  [apply]   removed {n} repeated x-labels, added one fig.supxlabel")
        else:
            print("  [MISS]    savefig anchor not found, nothing written")
PYEOF
fi

echo
if [ "$CHECK" -eq 1 ]; then
  echo "--check: $hits change(s) pending, $misses pattern(s) not found. Nothing written."
  exit 0
fi

echo "-- syntax check ---------------------------------------------------------"
if python3 -m py_compile "$F" 2>/dev/null; then
  echo "  [ok] compiles"
  rm -rf __pycache__
else
  echo "  [FAIL] does not compile, restoring backup"
  python3 -m py_compile "$F"
  cp "$BAK" "$F"
  exit 2
fi

cat <<'MSG'

Regenerate and inspect:
    python 4.plotting_manuscript_uncertainity.py --figures 1 3 5 --skip-unit-check

Check specifically:
  - Fig 1: maps larger, panel b legend clear of the bars, arrows clear of the
    six-item legend, panel d percentages inside the axes.
  - Fig 3: "Australasian & Oceanian" no longer clipped, one x-label only.

To revert, copy the .bak listed above back over the script.
MSG