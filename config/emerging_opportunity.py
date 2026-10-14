"""Official equity sectors and separately identified thematic baskets."""
from pathlib import Path

EQUITY_SECTORS = [
    'Automobile and Auto Components', 'Capital Goods', 'Chemicals', 'Construction',
    'Construction Materials', 'Consumer Durables', 'Consumer Services', 'Diversified',
    'Fast Moving Consumer Goods', 'Financial Services', 'Forest Materials', 'Healthcare',
    'Information Technology', 'Media, Entertainment & Publication', 'Metals & Mining',
    'Oil, Gas & Consumable Fuels', 'Power', 'Realty', 'Services', 'Telecommunication',
    'Textiles', 'Utilities',
]
SECTORS = {s: s.lower().replace(',','').replace('&','and').replace(' ', '_') for s in EQUITY_SECTORS}
SECTORS['AI Catalysts'] = 'ai_catalysts'
AI_CONSTITUENTS = 'https://www.niftyindices.com/IndexConstituent/ind_niftyAICatalystslist.csv'
AI_PAGE = 'https://www.niftyindices.com/indices/equity/thematic-indices/nifty-ai-catalysts'
BASE_STORE = Path(__file__).resolve().parents[1] / 'data/stores/india/emerging_opportunity'


def sector_store(sector):
    return BASE_STORE / SECTORS[sector]
