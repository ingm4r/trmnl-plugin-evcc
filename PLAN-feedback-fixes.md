# Feedback Fixes — Mode Badge & SOC Progress Bar

**Grundregel:** Maximal TRMNL Framework-Klassen nutzen, Custom CSS nur wo das Framework keine Lösung bietet.

## TRMNL Framework Klassen (verfügbar, bereits im Einsatz)

**Layout:** `flex`, `flex--between`, `flex--center-y`, `flex--col`, `grid`, `grid--cols-2`
**Spacing:** `gap--xsmall`, `gap--small`, `gap--medium`, `p--small`, `no-shrink`
**Typography:** `title`, `title--small`, `value`, `value--small`, `value--xsmall`, `value--large`, `label`, `label--small`, `description`
**Components:** `tag`, `tag--black`, `progress-bar`, `progress-bar--small` (mit `.track` + `.fill`), `divider`, `title_bar`
**Text:** `text--center`

Referenz: https://trmnl.com/framework/docs

---

## Issue 1: Mode Badge — `tag`/`tag--black` überall verwenden

**Problem:** `full.liquid` verwendet Custom CSS (`.evcc-mode`, `.evcc-mode--active`), die anderen Templates verwenden `tag`/`tag--black` inkonsistent, `quadrant` zeigt gar keinen Mode.

**Analyse:** Das Framework bietet folgende relevante Klassen:
- `label` — Basis-Textklasse für Tags/Badges
- `label--small` — kleinere Variante
- `label--inverted` — invertiert (schwarzer Hintergrund, weißer Text) → perfekt für aktiven Lademodus
- `label--outline` — umrandet → gut für inaktiven Modus
Das Framework hat KEIN dokumentiertes `tag--black`. Die bisherige Nutzung von `tag`/`tag--black` ist vermutlich undokumentiert/legacy. Wir sollten auf die dokumentierten `label`-Varianten umstellen.

**Änderungen:**

### Einheitliches Markup (alle Templates):
```liquid
<span class="label label--small{% if lp.charging %} label--inverted{% else %} label--outline{% endif %}">{{ lp_mode }}</span>
```
- Aktiv (charging) → `label--inverted` (schwarz/weiß, auffällig)
- Inaktiv → `label--outline` (umrandet, dezent)

### full.liquid
- Custom CSS **entfernen**: `.evcc-mode`, `.evcc-mode--active`
- Zeile ~93: Markup ersetzen (s. oben)

### half_horizontal.liquid
- Z.83 (connected): `tag`/`tag--black` → `label label--small` + `label--inverted`/`label--outline`
- Z.116 (disconnected): `description` → `label label--small label--outline`

### half_vertical.liquid
- Z.65 (connected): `tag`/`tag--black` → `label label--small` + `label--inverted`/`label--outline`
- Z.107 (disconnected): `description` → `label label--small label--outline`

### quadrant.liquid
- Mode-Label hinter Loadpoint-Titel hinzufügen:
  ```liquid
  <span class="description flex flex--center-y gap--xsmall">
    {{ icon_car }} {{ lp.title | default: "Loadpoint" | truncate: 14 }}
    <span class="label label--small{% if lp.charging %} label--inverted{% else %} label--outline{% endif %}">{{ lp.mode_label | default: "off" }}</span>
  </span>
  ```

---

## Issue 2: SOC Progress Bar im Full Template reparieren

**Problem:** Im `full.liquid` nutzt der SOC-Balken Framework-Klasse `progress-bar progress-bar--small` mit einem absolut positionierten `.evcc-marker` für das Limit. Der Marker rendert als vertikaler Strich im Textflow statt über dem Balken → `38% |80%` statt einem sauberen Progressbar.

**Analyse:** Das `half_vertical` Template hat einen funktionierenden SOC-Balken, aber mit **Custom CSS** (`evcc-soc-bar`, `evcc-soc-fill`, `evcc-soc-limit`). Das `full` Template nutzt die Framework-Klasse `progress-bar`, aber der Limit-Marker ist nicht Framework-kompatibel.

**Lösung:** Den SOC-Block im `full.liquid` an das funktionierende Pattern aus `half_vertical` angleichen, aber wo möglich Framework-Klassen behalten. Da das Framework keinen Progress-Bar-Marker unterstützt, ist Custom CSS für den Limit-Marker unvermeidbar.

**Änderungen in full.liquid:**

### CSS (Style-Block):
```
ENTFERNEN:
  .evcc-mode { ... }
  .evcc-mode--active { ... }
  .evcc-soc-bar { flex: 1; min-width: 0; }
  .evcc-marker { position: absolute; top: -2px; width: 3px; height: 12px; background: black; }
  .evcc-soc-progress { position: relative; overflow: visible; }

ERSETZEN DURCH:
  .evcc-soc-bar { width: 100%; height: 10px; background: #e5e5e5; border: 1px solid #999; overflow: hidden; position: relative; }
  .evcc-soc-fill { height: 100%; background: black; }
  .evcc-soc-limit { position: absolute; top: 0; bottom: 0; width: 2px; background: #666; }
```

### SOC-Block (Zeilen 113-126):
```
VORHER:
  <div class="flex flex--center-y gap--small">
    <span class="value value--small">{{ v_soc }}%</span>
    <div class="evcc-soc-bar">
      <div class="progress-bar progress-bar--small evcc-soc-progress">
        <div class="track">
          <div class="fill" style="width: {{ v_soc }}%;"></div>
        </div>
        {% if l_soc > 0 and l_soc < 100 %}
        <div class="evcc-marker" style="left: {{ l_soc }}%;"></div>
        {% endif %}
      </div>
    </div>
    {% if l_soc > 0 and l_soc < 100 %}<span class="value value--small">{{ l_soc }}%</span>{% endif %}
  </div>

NACHHER (wie half_vertical, funktioniert):
  <div class="evcc-soc-bar">
    <div class="evcc-soc-fill" style="width: {{ v_soc }}%;"></div>
    {% if l_soc > 0 and l_soc < 100 %}
    <div class="evcc-soc-limit" style="left: {{ l_soc }}%;"></div>
    {% endif %}
  </div>
  <div class="flex flex--between">
    <span class="value value--small">{{ v_soc }}%</span>
    {% if l_soc > 0 and l_soc < 100 %}<span class="description">Limit: {{ l_soc }}%</span>{% endif %}
  </div>
```

**Begründung:** Framework `progress-bar` unterstützt keinen Limit-Marker. Das Custom-CSS Pattern aus `half_vertical` funktioniert nachweislich (laut Feedback-Screenshot) und ist minimal (3 Zeilen CSS). Die Werte (SOC + Limit) stehen als Text unter dem Balken statt inline daneben → sauberer.

---

## Zusammenfassung: Custom CSS nach dem Fix

### full.liquid (vorher 7 Custom-Regeln → nachher 4)
```css
.evcc-full { ... }         /* Layout-Container — kein Framework-Äquivalent für feste Höhe */
.evcc-card { ... }         /* Card-Styling — Framework hat kein card-Component */
.evcc-soc-bar { ... }      /* SOC-Balken — Framework progress-bar hat keinen Marker */
.evcc-soc-fill { ... }     /* SOC-Füllung */
.evcc-soc-limit { ... }    /* Limit-Marker — Framework-inkompatibel */
```

### Entfernt aus full.liquid:
```
.evcc-mode        → ersetzt durch Framework label label--outline
.evcc-mode--active → ersetzt durch Framework label label--inverted
.evcc-soc-progress → nicht mehr nötig
.evcc-marker       → ersetzt durch .evcc-soc-limit (konsistent mit half_vertical)
```

---

## Shared CSS (optional, Phase 2)

Aktuell hat jedes Template eigene Custom-CSS-Definitionen für `.evcc-card`, `.evcc-soc-bar` etc. In einem zweiten Schritt könnten diese in `src/shared.liquid` ausgelagert werden ({% render 'shared' %}), um Duplikation zu vermeiden. Das `shared.liquid` existiert bereits, wird aber aktuell nicht für CSS genutzt.

---

## Umsetzungsreihenfolge

1. **Issue 2** — SOC Bar in `full.liquid` fixen (CSS + HTML-Block)
2. **Issue 1** — Mode Badge: Custom CSS in `full.liquid` entfernen, `tag`/`tag--black` überall einheitlich
3. **Testen** mit `trmnlp serve` und Beispieldaten aus `examples/`
4. **Commit & Push** → Forgejo + GitHub
