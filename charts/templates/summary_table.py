"""
Economics Hub — Market Snapshot Table (Footer Fix)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from style.economics_hub_style import EconStyle

# Section Text Colors
SECTION_COLORS = {
    "equities":    "#0F172A",
    "crypto":      "#7C3AED",
    "fx":          "#059669",
    "yields":      "#B91C1C",
    "volatility":  "#6B21A8",
    "commodities": "#D97706",
}

# Highlight Colors
HIGHLIGHT_MAX = "#86efac"  # Green 300
HIGHLIGHT_MIN = "#fca5a5"  # Red 300
SECTION_BG    = "#F1F5F9"  # Slate 100

class SummaryTable:
    def __init__(self):
        self.rows = []
        self.fig = None

    def add_row(self, name, level, weekly_change, ytd_change="-", category="equities"):
        if ytd_change is None: ytd_change = "-"
        self.rows.append({"name": name, "level": level, "weekly": weekly_change,
                          "ytd": ytd_change, "category": category})

    def _parse_val(self, val_str):
        """Extract numeric value. Normalizes 'bps' to match '%' scale."""
        try:
            if not isinstance(val_str, str): return -999999
            if val_str == "-" or val_str is None: return None
            is_bps = "bps" in val_str
            clean = val_str.replace("%", "").replace("bps", "").replace(",", "").replace("+", "")
            val = float(clean)
            if is_bps:
                return val / 100
            return val
        except: return None

    def _get_extremes(self):
        w_vals = []
        y_vals = []
        for r in self.rows:
            w_vals.append(self._parse_val(str(r["weekly"])))
            y_vals.append(self._parse_val(str(r["ytd"])))

        def find_idx(lst, func):
            valid_vals = [x for x in lst if x is not None]
            if not valid_vals: return None
            target = func(valid_vals)
            return lst.index(target)

        return {
            "w_max": find_idx(w_vals, max),
            "w_min": find_idx(w_vals, min),
            "y_max": find_idx(y_vals, max),
            "y_min": find_idx(y_vals, min)
        }

    def _format_level(self, val):
        try:
            if isinstance(val, str): return val
            f_val = float(val)
            if f_val > 20000: return f"{f_val:,.0f}"
            if f_val > 1000:  return f"{f_val:,.0f}"
            if f_val > 100:   return f"{f_val:,.2f}"
            if f_val > 10:    return f"{f_val:,.2f}"
            return f"{f_val:,.4f}"
        except: return str(val)

    def _draw_highlight(self, ax, x, y, width, height, color):
        rect = mpatches.FancyBboxPatch(
            (x - width/2, y - height/2), width, height,
            boxstyle="round,pad=0.01,rounding_size=0.05",
            facecolor=color, edgecolor="none", zorder=0
        )
        ax.add_patch(rect)

    def _draw_section_bar(self, ax, y, height):
        rect = plt.Rectangle(
            (0, y - height/2), 10, height,
            facecolor=SECTION_BG, edgecolor="none", zorder=0
        )
        ax.add_patch(rect)

    def render(self, title="Market Snapshot", subtitle=None, source="Yahoo Finance"):
        n = len(self.rows)
        cats = []
        for r in self.rows:
            if r["category"] not in cats: cats.append(r["category"])

        extremes = self._get_extremes()

        # DIMENSIONS
        row_h = 0.25        
        cat_gap = 0.45       
        header_block = 1.4  
        
        # ═══ FOOTER FIX: compute exact content height ═══
        # Each category: cat_gap (0.45) + post-header gap (0.20)
        # Each row: row_h (0.25)
        content_below_header = (0.65 * len(cats)) + (row_h * n)
        footer_space = 0.95  # separator + text + bottom pad
        
        fig_h = header_block + content_below_header + footer_space

        self.fig, ax = EconStyle.create_figure(size=(7.0, fig_h))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, fig_h)
        ax.axis("off")

        cx = {"name": 0.5, "level": 5.2, "weekly": 7.5, "ytd": 9.5}

        # ── Title Block ──
        y = fig_h - 0.4
        ax.text(0.5, y, title.upper(), fontsize=20, fontweight="bold", 
                color="#000000", fontfamily="sans-serif", ha="left")
        
        y -= 0.25
        if subtitle:
            ax.text(0.5, y, subtitle, fontsize=10, color="#000000", ha="left")

        # ── Headers ──
        y -= 0.5
        headers = [("name", "ASSET"), ("level", "LEVEL"), ("weekly", "1W CHG"), ("ytd", "YTD")]
        for key, label in headers:
            ha = "left" if key == "name" else "right"
            ax.text(cx[key], y, label, fontsize=9, fontweight="bold", 
                    color="#000000", ha=ha, fontfamily="sans-serif")

        y -= 0.15
        ax.plot([0.5, 9.5], [y, y], color="#000000", linewidth=1.2)

        # ── Rows ──
        cur_cat = None
        for i, row in enumerate(self.rows):
            if row["category"] != cur_cat:
                cur_cat = row["category"]
                y -= cat_gap
                self._draw_section_bar(ax, y, 0.25)
                sec_col = SECTION_COLORS.get(cur_cat, "#000000")
                display_names = {
                    "crypto": "CRYPTO ASSETS",
                    "volatility": "VOLATILITY & SENTIMENT",
                }
                label = display_names.get(cur_cat, cur_cat.upper())
                ax.text(cx["name"], y, label, fontsize=9, fontweight="bold", 
                        color=sec_col, ha="left", va="center")
                y -= 0.20

            y -= row_h
            
            # Data
            ax.text(cx["name"], y, row["name"], fontsize=10, fontweight="medium", 
                    color="#000000", ha="left", va="center")
            ax.text(cx["level"], y, self._format_level(row["level"]), fontsize=10, 
                    color="#334155", ha="right", va="center")
            
            # Weekly
            w_str = str(row["weekly"])
            is_pos = "+" in w_str
            is_neg = "-" in w_str
            txt_col = "#065f46" if is_pos else ("#991b1b" if is_neg else "#000000")

            if i == extremes["w_max"]: self._draw_highlight(ax, cx["weekly"]-0.25, y, 1.4, row_h*0.85, HIGHLIGHT_MAX)
            elif i == extremes["w_min"]: self._draw_highlight(ax, cx["weekly"]-0.25, y, 1.4, row_h*0.85, HIGHLIGHT_MIN)

            ax.text(cx["weekly"], y, w_str, fontsize=10, fontweight="bold", color=txt_col, ha="right", va="center")
            
            # YTD
            y_str = str(row["ytd"])
            y_col = EconStyle.POSITIVE if "+" in y_str else (EconStyle.NEGATIVE if "-" in y_str else "#64748b")
            
            if i == extremes["y_max"]: self._draw_highlight(ax, cx["ytd"]-0.25, y, 1.4, row_h*0.85, HIGHLIGHT_MAX)
            elif i == extremes["y_min"]: self._draw_highlight(ax, cx["ytd"]-0.25, y, 1.4, row_h*0.85, HIGHLIGHT_MIN)

            ax.text(cx["ytd"], y, y_str, fontsize=10, color=y_col, ha="right", va="center")
            ax.plot([0.5, 9.5], [y - row_h/2, y - row_h/2], color="#e2e8f0", linewidth=0.8, linestyle=":")

        # ═══════════════════════════════════════════
        # FOOTER — positioned relative to last row
        # (NOT hardcoded at y=0.2 which caused the clash)
        # ═══════════════════════════════════════════
        footer_y = y - row_h/2 - 0.40
        
        ax.text(0.5, footer_y, f"Source: {source}", 
                fontsize=8, color="#666666", ha="left", va="bottom")
        
        ax.text(9.5, footer_y, EconStyle.WATERMARK_TEXT, 
                fontproperties=EconStyle._get_masthead_font(),
                fontsize=13, color="#1A1A1A", ha="right", va="bottom")

        EconStyle.finalize(self.fig, ax, source=None, tight=False)
        return self.fig

    def save(self, filepath):
        if self.fig is None: raise ValueError("Call render() first.")
        return EconStyle.save_chart(self.fig, filepath)
