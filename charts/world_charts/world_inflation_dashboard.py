"""Native dashboard charts from the edition's audited monthly CPI observations."""
import altair as alt
import pandas as pd


BLUE = "#1F5596"
ORANGE = "#C8620A"
LABELS = {"headline": "Headline CPI", "core": "Excluding food & energy"}

# ISO/OECD area codes. Euro-area membership is for the edition's as-of date.
# https://www.ecb.europa.eu/euro/changeover/bulgaria/html/index.en.html
EURO_AREA = frozenset("AUT BEL HRV CYP EST FIN FRA DEU GRC IRL ITA LVA LTU LUX MLT NLD PRT SVK SVN ESP".split())
REGIONS = {
    "Asia": frozenset("CHN IND IDN JPN KOR ISR SAU TUR HKG TWN SGP MYS THA PHL VNM KAZ".split()),
    "Europe": EURO_AREA | frozenset("EA BGR GBR CZE DNK HUN ISL NOR POL ROU SWE CHE TUR RUS UKR SRB".split()),
    "Euro area": EURO_AREA | {"EA"},
    "North America": frozenset({"USA", "CAN"}),
    "Latin America & Caribbean": frozenset("ARG BRA CHL COL CRI MEX PER ECU URY VEN PAN DOM".split()),
    "Africa": frozenset("ZAF EGY MAR TUN NGA".split()),
    "Oceania": frozenset({"AUS", "NZL"}),
}
SORT_OPTIONS = ("Default order", "Country A–Z", "Inflation: highest first", "Inflation: lowest first")


def region_codes(region, as_of):
    codes = REGIONS[region]
    if region == "Euro area" and as_of >= "2026-01-01":
        codes = codes | {"BGR"}
    return codes


def region_options(countries, as_of):
    """Only offer regions with panels in the selected edition."""
    present = {c["code"] for c in countries}
    options = ["All regions"] + [r for r in REGIONS if present & region_codes(r, as_of)]
    if present - set().union(*REGIONS.values()):
        options.append("Other regions")
    return options


def select_countries(countries, region="All regions", sort="Default order", as_of=""):
    """Filter/sort a copy, preserving the audited edition and global breadth."""
    if region == "All regions":
        selected = list(countries)
    elif region == "Other regions":
        known = set().union(*REGIONS.values())
        selected = [c for c in countries if c["code"] not in known]
    else:
        selected = [c for c in countries if c["code"] in region_codes(region, as_of)]
    if sort == "Country A–Z":
        selected.sort(key=lambda c: c["label"].casefold())
    elif sort in SORT_OPTIONS[2:]:
        direction = -1 if sort == "Inflation: highest first" else 1
        selected.sort(key=lambda c: (direction * c["series"]["headline"][-1]["value"],
                                     c["label"].casefold()))
    return selected


def panel(country, start_month, end_month):
    """Split each line at missing months; hover retains source classifications."""
    records = []
    for kind, label in LABELS.items():
        previous, segment = None, 0
        for row in country["series"][kind]:
            month = pd.Period(row["month"], freq="M")
            if previous is not None and month != previous + 1:
                segment += 1
            records.append({"date": month.to_timestamp().isoformat(), "rate": row["value"],
                            "series": label, "segment": f"{kind}-{segment}",
                            "classification": row["classification"]})
            previous = month
    base = alt.Chart(alt.Data(values=records)).encode(
        x=alt.X("date:T", title=None, scale=alt.Scale(domain=[
            pd.Period(start_month, freq="M").to_timestamp().isoformat(),
            pd.Period(end_month, freq="M").to_timestamp().isoformat()]),
            axis=alt.Axis(format="%Y", tickCount=3, grid=False, labelAngle=0)),
        y=alt.Y("rate:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(tickCount=4, gridColor="#E4E7EB", format="~g")),
        color=alt.Color("series:N", scale=alt.Scale(domain=list(LABELS.values()),
                                                  range=[BLUE, ORANGE]), legend=None),
        detail="segment:N",
        tooltip=[alt.Tooltip("date:T", title="Month", format="%b %Y"),
                 alt.Tooltip("series:N", title="Measure"),
                 alt.Tooltip("rate:Q", title="Inflation (% YoY)", format=".2f"),
                 alt.Tooltip("classification:N", title="COICOP")],
    )
    lines = base.mark_line(strokeWidth=2.3).encode(
        strokeDash=alt.StrokeDash("series:N", scale=alt.Scale(
            domain=list(LABELS.values()), range=[[1, 0], [6, 3]]), legend=None))
    # Transparent point targets provide precise monthly hover without clutter.
    points = base.mark_circle(size=65, opacity=0)
    return (lines + points).properties(height=190).configure_view(stroke=None).configure_axis(
        domain=False, ticks=False, labelFont="Inter", labelFontSize=11,
        labelColor="#4B5563", labelPadding=7)


def panel_notes(country):
    notes = []
    headline = country["series"]["headline"][-1]["month"]
    core = country["series"]["core"]
    if not core:
        notes.append(country.get("core_note") or "Core not available")
    elif core[-1]["month"] != headline:
        notes.append("Core through " + core[-1]["month"])
    for measure, month in country["transitions"].items():
        notes.append(f"{measure.capitalize()} classification join: {month}")
    return " · ".join(notes)
