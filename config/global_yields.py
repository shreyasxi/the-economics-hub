"""The approved 20-country universe; frequencies are source-specific."""
COUNTRIES = {
    "USA": ("United States", "North America"), "CAN": ("Canada", "North America"),
    "GBR": ("United Kingdom", "Europe"), "DEU": ("Germany", "Europe"),
    "FRA": ("France", "Europe"), "ITA": ("Italy", "Europe"),
    "ESP": ("Spain", "Europe"), "SWE": ("Sweden", "Europe"), "CHE": ("Switzerland", "Europe"),
    "NOR": ("Norway", "Europe"), "POL": ("Poland", "Europe"),
    "IND": ("India", "Asia"), "JPN": ("Japan", "Asia"), "KOR": ("South Korea", "Asia"),
    "COL": ("Colombia", "Latin America"), "CHL": ("Chile", "Latin America"), "MEX": ("Mexico", "Latin America"),
    "AUS": ("Australia", "Oceania"), "NZL": ("New Zealand", "Oceania"), "ZAF": ("South Africa", "Africa"),
}
STEM = "17b_macro_global_yields"
OECD_FLOW = "OECD.SDD.STES,DSD_STES@DF_FINMARK,"
OECD_KEY = "+".join(COUNTRIES) + ".M.IRLT.PA....."
OECD_URL = "https://sdmx.oecd.org/public/rest/data/" + OECD_FLOW + "/" + OECD_KEY
