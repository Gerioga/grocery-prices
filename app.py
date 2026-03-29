import streamlit as st
import csv
import re
from collections import defaultdict
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Grocery Price Comparison", page_icon="🛒", layout="wide")

# ── Password gate ──
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    pw = st.text_input("Password", type="password")
    if pw == "grocery26":
        st.session_state.authenticated = True
        st.rerun()
    elif pw:
        st.error("Wrong password")
    return False

if not check_password():
    st.stop()

# ── Custom CSS ──
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1F3864 0%, #2E75B6 100%);
        padding: 20px; border-radius: 12px; text-align: center; color: white;
    }
    .metric-card .value { font-size: 2rem; font-weight: 700; }
    .metric-card .label { font-size: 0.85rem; opacity: 0.85; margin-top: 4px; }
    .savings-positive { color: #2E7D32; font-weight: 700; }
    .savings-negative { color: #C62828; font-weight: 700; }
    div[data-testid="stMetric"] { background: #f8f9fa; padding: 12px; border-radius: 8px; border-left: 4px solid #2E75B6; }
</style>
""", unsafe_allow_html=True)

# ── Data loading ──
import os
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

@st.cache_data
def load_data():
    with open(f"{DATA_DIR}/Your Amazon Orders/Order History.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    wf_shipping = {'scheduled-houdini', 'scheduled-one-houdini', 'rush-one-houdini'}

    def is_beverage(name):
        n = name.lower()
        # Keep dairy milk (whole milk, half & half, etc.) — those are Dairy & Eggs
        # Also keep oat milk / oatly / soy milk / almond milk / coconut milk — those go to Dairy & Eggs
        dairy_kw = ['whole milk', 'half.*half', 'organic valley', 'maple hill', 'grassmilk',
                    'oat milk', 'oatly', 'soy milk', 'almond milk', 'coconut milk']
        if any(re.search(kw, n) for kw in dairy_kw):
            return False
        bev_kw = ['spring water', 'bottled water', 'deer park', 'sparkling water',
                  'seltzer', 'coca.cola', 'coke', 'sprite', 'soda', 'pepsi',
                  'diet coke', 'ginger ale', 'tonic water', 'club soda',
                  'mountain dew', 'fanta', 'dr pepper', '7.up', 'root beer',
                  'juice', 'coffee', 'tea\\b', 'wine', 'beer', 'smoothie',
                  'kombucha', 'coconut water', 'liquid iv', 'hydration',
                  'prosecco', 'champagne', 'chardonnay', 'pinot', 'merlot',
                  'cabernet', 'sauvignon', 'rosé', 'aperol', 'lemonade',
                  'espresso', 'cold brew', 'globerati',
                  'blue bottle', 'orange juice', 'apple juice', 'limeade']
        return any(re.search(kw, n) for kw in bev_kw)

    wf_rows = [r for r in rows if r.get('Shipping Option', '') in wf_shipping
               and 'bag fee' not in r['Product Name'].lower()
               and not is_beverage(r['Product Name'])]

    # Build product summary
    products = {}
    for r in wf_rows:
        name = r['Product Name']
        price = float(r['Unit Price']) if r['Unit Price'] else 0
        qty = int(r['Original Quantity']) if r['Original Quantity'] else 1
        date = r['Order Date'][:10]
        if name not in products:
            products[name] = {'count': 0, 'total_spend': 0, 'prices': [], 'dates': [], 'asin': r['ASIN']}
        products[name]['count'] += qty
        products[name]['total_spend'] += price * qty
        products[name]['prices'].append(price)
        products[name]['dates'].append(date)

    # Weight parsing
    def parse_weight_from_name(name):
        n = name.lower()
        patterns = [
            (r'(\d+\.?\d*)\s*fl\.?\s*oz', 'fl oz'),
            (r'(\d+\.?\d*)\s*ounce', 'oz'),
            (r'(\d+\.?\d*)\s*\boz\b', 'oz'),
            (r'(\d+\.?\d*)\s*\blb\b', 'lb'),
            (r'(\d+\.?\d*)\s*pound', 'lb'),
            (r'(\d+\.?\d*)\s*gallon', 'gal'),
            (r'(\d+\.?\d*)\s*pint', 'pint'),
            (r'(\d+\.?\d*)\s*ml\b', 'ml'),
            (r'(\d+)\s*(?:ct|count)\b', 'ct'),
            (r'(\d+)\s*(?:pk|pack)\b', 'pack'),
        ]
        for pat, unit in patterns:
            m = re.search(pat, n, re.IGNORECASE)
            if m:
                val = float(m.group(1))
                if unit == 'lb': oz_val = val * 16
                elif unit == 'gal': oz_val = val * 128
                elif unit == 'pint': oz_val = val * 16
                elif unit == 'ml': oz_val = val * 0.033814
                elif unit in ('ct', 'pack'): return None
                else: oz_val = val
                return (oz_val, f"{val} {unit}")
        return None

    asin_weights = {
        'B004SI17SE': (3, 'oz'), 'B000P6J1P4': (16, 'oz'), 'B0787WT5M7': (16, 'oz'),
        'B07D7XXK9Q': (16, 'oz'), 'B0CBQ7F79F': (8, 'oz'), 'B0787W7J4H': (2, 'oz'),
        'B000NOGKN4': (6, 'oz'), 'B09Z72W3ZH': (16, 'oz'), 'B079W28NJW': (16, 'oz'),
        'B001PLGQPQ': (16, 'oz'), 'B0787WTVM2': (16, 'oz'), 'B000SEKTJA': (0.25, 'oz'),
        'B0781B3YD8': (2, 'oz'), 'B085393FQH': (16, 'oz'), 'B000P6J14U': (32, 'oz'),
        'B079JMTDH4': (3, 'oz'), 'B0789WGT5C': (7, 'oz'), 'B0787XMJQT': (16, 'oz'),
        'B086X6PF6J': (25, 'oz'), 'B07QTZBZ2C': (8, 'oz'), 'B0787WN3VW': (16, 'oz'),
        'B0787TJRC2': (16, 'oz'), 'B000WS1KI6': (2.29, 'oz'), 'B07819RK9C': (1, 'oz'),
        'B0787Y45SB': (8, 'oz'), 'B000P6H21O': (16, 'oz'), 'B07P6L598B': (3, 'oz'),
        'B07F4HRVJK': (0, 'oz'),
    }

    def get_weight_oz(name, asin):
        parsed = parse_weight_from_name(name)
        if parsed: return parsed
        if asin in asin_weights:
            val, unit = asin_weights[asin]
            if val == 0: return (None, None)
            if unit == 'lb': return (val * 16, f"{val} lb")
            return (val, f"{val} {unit}")
        return (None, None)

    for name, data in products.items():
        oz_val, display = get_weight_oz(name, data['asin'])
        data['weight_oz'] = oz_val
        data['weight_display'] = display
        avg_price = sum(data['prices']) / len(data['prices'])
        data['price_per_oz'] = round(avg_price / oz_val, 2) if oz_val and oz_val > 0 else None

    # Categorize
    def categorize(name):
        n = name.lower()
        cats = {
            'Produce': ['apple', 'banana', 'zucchini', 'tomato', 'onion', 'garlic', 'avocado', 'lettuce',
                        'spinach', 'kale', 'pepper', 'potato', 'carrot', 'celery', 'broccoli', 'mushroom',
                        'herb', 'cilantro', 'mint', 'basil', 'shallot', 'lemon', 'lime', 'raspberr',
                        'blueberr', 'strawberr', 'mango', 'pear', 'orange', 'grape', 'cucumber', 'squash',
                        'jalap', 'ginger', 'scallion', 'arugula', 'parsley', 'thyme', 'rosemary', 'dill',
                        'produce', 'fruit', 'vegetable', 'asparagus', 'artichoke', 'fennel', 'radish',
                        'sweet potato', 'plantain', 'melon', 'peach', 'plum', 'cherry', 'fig', 'date'],
            'Dairy & Eggs': ['milk', 'cheese', 'yogurt', 'cream', 'butter', 'egg', 'camembert',
                            'parmesan', 'mozzarella', 'ricotta', 'feta', 'brie', 'gouda', 'cheddar',
                            'gruyere', 'manchego', 'goat cheese', 'cream cheese', 'sour cream', 'kefir',
                            'oat milk', 'oatly', 'soy milk', 'almond milk', 'coconut milk',
                            'plant butter', 'vegan butter', 'violife'],
            'Meat & Seafood': ['chicken', 'beef', 'salmon', 'tuna', 'shrimp', 'swordfish', 'scallop',
                              'tilapia', 'cod', 'turkey', 'pork', 'steak', 'sausage', 'bacon', 'lamb',
                              'crab', 'lobster', 'mahi', 'trout', 'sardine', 'anchov'],
            'Pantry & Grains': ['pasta', 'rice', 'oat', 'flour', 'sugar', 'oil', 'vinegar', 'sauce',
                               'spice', 'salt', 'cinnamon', 'couscous', 'bread', 'tortilla', 'cracker',
                               'cereal', 'granola', 'quinoa', 'lentil', 'bean', 'chickpea', 'nut',
                               'almond', 'peanut', 'cashew', 'honey', 'syrup', 'jam', 'seasoning',
                               'cumin', 'paprika', 'turmeric', 'curry', 'baking'],
            'Snacks & Sweets': ['chocolate', 'cookie', 'chip', 'bar', 'candy', 'ice cream', 'pie',
                               'pretzel', 'popcorn', 'brownie', 'cake', 'muffin', 'donut'],
            'Frozen': ['frozen', 'ice', 'popsicle'],
            'Household': ['detergent', 'soap', 'paper towel', 'tissue', 'trash bag', 'cleaning',
                         'sponge', 'wrap', 'foil', 'ziplock', 'tide', 'laundry'],
        }
        for cat, keywords in cats.items():
            if any(k in n for k in keywords):
                return cat
        return 'Other'

    # Competitor database
    competitor_db = {
        'organic.*egg.*12|egg.*organic.*12|365.*egg': {
            'Harris Teeter': (7.99, '12 ct'), 'Lidl': (4.79, '12 ct'),
            'Costco': (3.50, '12 ct equiv'), 'Walmart': (5.28, '12 ct'),
            'Amazon Fresh': (5.49, '12 ct'), 'Safeway': (6.99, '12 ct'),
        },
        'vital farms.*egg': {
            'Harris Teeter': (12.29, '12 ct'),
            'Costco': (5.00, '12 ct equiv'), 'Walmart': (7.98, '12 ct'),
            'Amazon Fresh': (11.99, '12 ct'), 'Safeway': (7.99, '12 ct'),
        },
        'camembert': {
            'Harris Teeter': (13.99, '8.8 oz'),
            'Costco': (4.00, '8 oz equiv'), 'Walmart': (5.98, '8 oz'),
            'Amazon Fresh': (9.99, '8 oz'), 'Safeway': (9.99, '8 oz'),
        },
        'violife.*butter|plant butter': {
            'Harris Teeter': (5.49, '8.8 oz'),
            'Walmart': (4.47, '8 oz'),
            'Amazon Fresh': (4.99, '8.8 oz'), 'Safeway': (5.49, '8.8 oz'),
        },
        'stonyfield.*yogurt|stonyfield.*smoothie': {
            'Harris Teeter': (5.99, '4-pack'),
            'Walmart': (4.98, '4-pack'),
            'Amazon Fresh': (5.49, '4-pack'), 'Safeway': (5.49, '4-pack'),
        },
        'clio.*yogurt': {
            'Harris Teeter': (1.99, '1.76 oz'),
            'Walmart': (1.68, '1.76 oz'),
            'Amazon Fresh': (1.79, '1.76 oz'), 'Safeway': (1.99, '1.76 oz'),
        },
        'salmon.*fillet.*farm|365.*salmon': {
            'Harris Teeter': (14.99, 'per lb'), 'Lidl': (9.99, 'per lb'),
            'Costco': (9.99, 'per lb'), 'Walmart': (7.97, 'per lb'),
            'Amazon Fresh': (12.99, 'per lb'), 'Safeway': (12.99, 'per lb'),
        },
        'sockeye salmon': {
            'Harris Teeter': (18.99, 'per lb'),
            'Costco': (12.99, 'per lb'), 'Walmart': (10.97, 'per lb'),
            'Amazon Fresh': (16.99, 'per lb'), 'Safeway': (15.99, 'per lb'),
        },
        'swordfish': {
            'Harris Teeter': (15.99, 'per lb'),
            'Costco': (13.99, 'per lb'), 'Walmart': (11.97, 'per lb'),
            'Amazon Fresh': (14.99, '12 oz'), 'Safeway': (19.99, 'per lb'),
        },
        'scallop': {
            'Harris Teeter': (19.99, '12 oz'),
            'Costco': (5.62, '12 oz equiv'), 'Walmart': (9.97, '12 oz'),
            'Amazon Fresh': (16.99, '12 oz'), 'Safeway': (18.99, '16 oz'),
        },
        'tilapia': {
            'Harris Teeter': (8.99, 'per lb'), 'Lidl': (5.99, 'per lb'),
            'Costco': (5.99, 'per lb'), 'Walmart': (4.47, 'per lb'),
            'Amazon Fresh': (7.99, '32 oz'), 'Safeway': (7.99, 'per lb'),
        },
        'chicken.*leg|chicken.*thigh': {
            'Harris Teeter': (4.99, 'per lb'), 'Lidl': (1.99, 'per lb'),
            'Costco': (2.99, 'per lb'), 'Walmart': (1.97, 'per lb'),
            'Amazon Fresh': (4.49, 'per lb'), 'Safeway': (6.49, 'per lb'),
        },
        'beef.*chuck|beef.*stew|short rib': {
            'Harris Teeter': (9.99, 'per lb'), 'Lidl': (7.99, 'per lb'),
            'Costco': (7.99, 'per lb'), 'Walmart': (6.47, 'per lb'),
            'Amazon Fresh': (9.49, 'per lb'), 'Safeway': (7.99, 'per lb'),
        },
        'cod.*fillet|365.*cod': {
            'Harris Teeter': (12.99, 'per lb'),
            'Costco': (8.99, 'per lb'), 'Walmart': (7.47, 'per lb'),
            'Amazon Fresh': (11.99, '32 oz'), 'Safeway': (10.99, 'per lb'),
        },
        'shrimp': {
            'Harris Teeter': (12.99, 'per lb'), 'Lidl': (8.99, 'per lb'),
            'Costco': (4.50, 'per lb equiv'), 'Walmart': (7.47, 'per lb'),
            'Amazon Fresh': (11.99, '32 oz'), 'Safeway': (11.99, 'per lb'),
        },
        'organic.*zucchini|zucchini.*organic': {
            'Harris Teeter': (2.39, 'per lb'), 'Lidl': (1.79, 'per lb'),
            'Walmart': (1.97, 'per lb'),
            'Amazon Fresh': (1.99, 'per lb'),
            "MOM's Organic": (3.49, 'per lb'), 'Safeway': (3.79, 'per lb'),
        },
        'organic.*raspberry|raspberry.*organic|red raspberry': {
            'Harris Teeter': (5.49, '6 oz'), 'Lidl': (3.49, '6 oz'),
            'Costco': (3.00, '6 oz equiv'), 'Walmart': (3.97, '6 oz'),
            'Amazon Fresh': (4.49, '6 oz'),
            "MOM's Organic": (3.49, '6 oz'), 'Safeway': (5.99, '6 oz'),
        },
        'frozen.*raspberry|raspberry.*frozen|365.*raspberry': {
            'Harris Teeter': (3.99, '10 oz'),
            'Costco': (1.41, '10 oz equiv'), 'Walmart': (2.97, '12 oz'),
            'Amazon Fresh': (3.49, '10 oz'), 'Safeway': (4.99, '10 oz'),
        },
        'organic.*fuji|fuji.*apple|organic.*apple': {
            'Harris Teeter': (2.49, 'per lb'), 'Lidl': (1.69, 'per lb'),
            'Costco': (1.40, 'per lb equiv'), 'Walmart': (1.67, 'per lb'),
            'Amazon Fresh': (2.29, 'per lb'), 'Safeway': (2.49, 'per lb'),
        },
        'organic.*shallot|shallot': {
            'Harris Teeter': (3.49, 'each'),
            'Walmart': (2.47, 'each'),
            'Amazon Fresh': (2.99, 'each'), "MOM's Organic": (4.99, 'per lb'), 'Safeway': (2.99, '3 oz'),
        },
        'guacamole': {
            'Harris Teeter': (4.99, '8 oz'),
            'Costco': (2.25, '8 oz equiv'), 'Walmart': (3.47, '8 oz'),
            'Amazon Fresh': (5.49, '8 oz'), "MOM's Organic": (8.29, '~9 oz'), 'Safeway': (4.49, '8 oz'),
        },
        'lime.*regular|lime.*conventional': {
            'Harris Teeter': (0.33, 'each'), 'Lidl': (0.25, 'each'),
            'Costco': (0.17, 'each equiv'), 'Walmart': (0.25, 'each'),
            'Amazon Fresh': (0.35, 'each'), 'Safeway': (0.5, 'each'),
        },
        'cilantro': {
            'Harris Teeter': (1.49, 'bunch'), 'Lidl': (0.79, 'bunch'),
            'Walmart': (0.68, 'bunch'),
            'Amazon Fresh': (1.49, 'bunch'), 'Safeway': (1.29, 'bunch'),
        },
        'spearmint|mint.*organic': {
            'Harris Teeter': (2.49, '0.5 oz'),
            'Walmart': (1.97, 'bunch'),
            'Amazon Fresh': (2.49, '0.5 oz'), "MOM's Organic": (2.99, '0.5 oz'), 'Safeway': (2.99, '0.5 oz'),
        },
        'organic.*blackberr|blackberr.*organic': {
            'Harris Teeter': (4.99, '6 oz'),
            'Costco': (3.00, '6 oz equiv'), 'Walmart': (3.47, '6 oz'),
            'Amazon Fresh': (4.49, '6 oz'), "MOM's Organic": (4.99, '6 oz'), 'Safeway': (5.99, '6 oz'),
        },
        'blueberr.*pint|blueberr.*fresh|blueberr(?!.*frozen)': {
            'Harris Teeter': (4.99, '1 pint'),
            'Costco': (4.66, '1 pint equiv'), 'Walmart': (3.47, '1 pint'),
            'Amazon Fresh': (4.49, '1 pint'), "MOM's Organic": (8.99, '1 pint'), 'Safeway': (4.99, '1 pint'),
        },
        'organic.*bell pepper|red bell pepper|yellow bell pepper': {
            'Harris Teeter': (3.99, 'each'),
            'Costco': (1.00, 'each equiv'), 'Walmart': (1.97, 'each'),
            'Amazon Fresh': (2.99, 'each'), "MOM's Organic": (6.99, 'per lb'), 'Safeway': (3.49, 'each'),
        },
        'organic.*green.*pepper|green.*pepper': {
            'Harris Teeter': (1.99, 'each'),
            'Walmart': (0.97, 'each'),
            'Amazon Fresh': (1.49, 'each'), "MOM's Organic": (2.99, 'per lb'), 'Safeway': (1.79, 'each'),
        },
        'mini cucumber|organic.*cucumber': {
            'Harris Teeter': (3.99, '1 lb'),
            'Costco': (2.00, '1 lb equiv'), 'Walmart': (2.47, '1 lb'),
            'Amazon Fresh': (3.99, '1 lb'), "MOM's Organic": (3.99, '1 lb'), 'Safeway': (3.49, '1 lb'),
        },
        'tomato.*on.*vine|heirloom.*tomato|organic.*tomato': {
            'Harris Teeter': (3.49, 'per lb'),
            'Costco': (1.66, 'per lb equiv'), 'Walmart': (1.97, 'per lb'),
            'Amazon Fresh': (3.49, 'per lb'), "MOM's Organic": (4.99, 'per lb'), 'Safeway': (2.99, 'per lb'),
        },
        'baby bella|mushroom.*bella|phillips.*mushroom': {
            'Harris Teeter': (3.49, '8 oz'),
            'Costco': (1.66, '8 oz equiv'), 'Walmart': (1.98, '8 oz'),
            'Amazon Fresh': (2.99, '8 oz'), "MOM's Organic": (3.99, '8 oz'), 'Safeway': (2.99, '8 oz'),
        },
        'organic valley.*whole milk|maple hill.*whole milk|whole milk.*organic': {
            'Harris Teeter': (5.99, 'half gal'),
            'Costco': (4.00, 'half gal equiv'), 'Walmart': (4.72, 'half gal'),
            'Amazon Fresh': (5.49, 'half gal'),
            "MOM's Organic": (4.29, 'half gal'), 'Safeway': (5.49, 'half gal'),
        },
        'organic valley.*half.*half|grassmilk.*half.*half|half.*half.*organic': {
            'Harris Teeter': (5.49, 'pint'),
            'Walmart': (3.97, 'pint'),
            'Amazon Fresh': (4.99, 'pint'), "MOM's Organic": (5.79, 'pint'), 'Safeway': (4.99, 'pint'),
        },
        'organic.*carrot|loose carrot': {
            'Harris Teeter': (1.99, '1 lb bag'),
            'Costco': (1.00, '1 lb equiv'), 'Walmart': (1.27, '1 lb bag'),
            'Amazon Fresh': (1.49, '1 lb bag'),
            "MOM's Organic": (1.99, '1 lb bag'), 'Safeway': (1.79, '1 lb bag'),
        },
        'organic.*thyme|organic.*rosemary|organic.*herb': {
            'Harris Teeter': (2.99, '0.5 oz'),
            'Walmart': (1.97, 'bunch'),
            'Amazon Fresh': (2.49, '0.5 oz'), "MOM's Organic": (2.99, '0.5 oz'), 'Safeway': (2.99, '0.5 oz'),
        },
        'baby spinach|organic.*spinach.*salad': {
            'Harris Teeter': (3.99, '5 oz'),
            'Costco': (1.56, '5 oz equiv'), 'Walmart': (2.47, '5 oz'),
            'Amazon Fresh': (3.49, '5 oz'), "MOM's Organic": (4.99, '5 oz'), 'Safeway': (3.49, '5 oz'),
        },
        'garlic.*bulb|garlic ali|christopher.*garlic': {
            'Harris Teeter': (1.99, '3 ct'),
            'Costco': (0.50, '3 ct equiv'), 'Walmart': (0.97, '3 ct'),
            'Amazon Fresh': (1.49, '3 ct'), "MOM's Organic": (6.99, 'per lb'), 'Safeway': (1.49, '3 ct'),
        },
        'kettle.*chip|potato chip': {
            'Harris Teeter': (4.49, '5 oz'),
            'Costco': (1.59, '5 oz equiv'), 'Walmart': (2.98, '8 oz'),
            'Amazon Fresh': (4.29, '5 oz'), "MOM's Organic": (4.29, '5 oz'), 'Safeway': (3.99, '5 oz'),
        },
        'tortilla chip|corn.*chip': {
            'Harris Teeter': (3.99, '12 oz'),
            'Costco': (2.25, '12 oz equiv'), 'Walmart': (2.78, '13 oz'),
            'Amazon Fresh': (3.49, '12 oz'), "MOM's Organic": (4.99, '12 oz'), 'Safeway': (3.49, '10 oz'),
        },
        'goat cheese': {
            'Harris Teeter': (5.99, '4 oz'),
            'Costco': (2.66, '4 oz equiv'), 'Walmart': (3.47, '4 oz'),
            'Amazon Fresh': (4.99, '4 oz'), "MOM's Organic": (5.49, '4 oz'), 'Safeway': (5.49, '4 oz'),
        },
        '365.*spaghetti|organic.*spaghetti': {
            'Harris Teeter': (1.99, '16 oz'), 'Lidl': (0.92, '16 oz'),
            'Costco': (1.17, '16 oz equiv'), 'Walmart': (1.18, '16 oz'),
            'Amazon Fresh': (1.79, '16 oz'), 'Safeway': (1.79, '16 oz'),
        },
        '365.*oat|organic.*rolled oat': {
            'Harris Teeter': (3.69, '18 oz'),
            'Costco': (0.90, '18 oz equiv'), 'Walmart': (2.98, '18 oz'),
            'Amazon Fresh': (4.99, '42 oz'), 'Safeway': (3.49, '18 oz'),
        },
        '365.*garlic.*peeled|organic.*peeled garlic': {
            'Harris Teeter': (4.49, '6 oz'),
            'Costco': (0.75, '6 oz equiv'), 'Walmart': (2.47, '6 oz'),
            'Amazon Fresh': (3.99, '6 oz'), "MOM's Organic": (3.04, '~6 oz'), 'Safeway': (2.49, '6 oz'),
        },
        'couscous': {
            'Harris Teeter': (2.99, '5.8 oz'),
            'Walmart': (1.87, '5.8 oz'),
            'Amazon Fresh': (2.99, '5.8 oz'), 'Safeway': (2.79, '5.8 oz'),
        },
        'badia.*garlic|minced garlic': {
            'Harris Teeter': (2.49, '8 oz'),
            'Costco': (0.83, '8 oz equiv'), 'Walmart': (1.98, '8 oz'),
            'Amazon Fresh': (2.49, '8 oz'), 'Safeway': (3.99, '8 oz'),
        },
        'pie.*dough|pie.*crust|wholly wholesome': {
            'Harris Teeter': (5.99, '2-pack'),
            'Walmart': (3.47, '2-pack'),
            'Amazon Fresh': (6.99, '2-pack'), 'Safeway': (3.99, '2-pack'),
        },
        'oatly|oat milk': {
            'Costco': (1.50, '32 oz equiv'), 'Walmart': (3.97, '32 oz'),
            'Amazon Fresh': (4.99, '32 oz'), 'Safeway': (4.99, '32 oz'),
        },
        'coconut water': {
            'Costco': (1.08, '33.8 oz equiv'), 'Walmart': (3.28, '33.8 oz'),
            'Amazon Fresh': (4.49, '33.8 oz'), 'Safeway': (4.99, '33.8 oz'),
        },
        'liquid iv': {
            'Costco': (0.83, 'single equiv'), 'Walmart': (1.98, 'single'),
            'Amazon Fresh': (6.99, '6 ct'), 'Safeway': (7.49, '6 ct'),
        },
        'blue bottle|cold brew': {
            'Walmart': (2.97, '8 oz'),
            'Amazon Fresh': (3.49, '8 oz'), 'Safeway': (3.99, '8 oz'),
        },
        'wine|prosecco|champagne|chardonnay|pinot|merlot|cabernet': {
            'Costco': (8.99, '750ml'), 'Walmart': (5.97, '750ml'),
            'Safeway': (9.99, '750ml'),
        },
        'coke.*mini|mini.*coke|coca.cola.*mini': {
            'Costco': (4.33, '10-pack equiv'), 'Walmart': (4.48, '10-pack'),
            'Amazon Fresh': (5.99, '10-pack'), 'Safeway': (6.49, '10-pack'),
        },
        'endangered species.*chocolate|dark chocolate.*espresso': {
            'Harris Teeter': (3.99, '3 oz'),
            'Walmart': (2.97, '3 oz'),
            'Amazon Fresh': (3.69, '3 oz'), 'Safeway': (3.79, '3 oz'),
        },
        'lindt.*chocolate': {
            'Harris Teeter': (3.99, '4.4 oz'),
            'Costco': (2.00, '4.4 oz equiv'), 'Walmart': (3.48, '4.4 oz'),
            'Amazon Fresh': (3.99, '4.4 oz'), 'Safeway': (4.49, '3.5 oz'),
        },
        'brown butter.*cookie': {
            'Harris Teeter': (2.49, '2 oz'),
            'Walmart': (1.98, '2 oz'),
            'Amazon Fresh': (1.99, '2 oz'), 'Safeway': (2.99, '2 oz'),
        },
        'happy belly.*frozen|amazon.*frozen onion': {
            'Harris Teeter': (1.49, '12 oz'), 'Lidl': (0.99, '12 oz'),
            'Walmart': (0.88, '12 oz'),
            'Amazon Fresh': (0.79, '12 oz'), 'Safeway': (1.49, '12 oz'),
        },
        'elderberry|immunity.*shot|vive organic': {
            'Harris Teeter': (3.99, '2 oz'),
            'Walmart': (2.97, '2 oz'),
            'Amazon Fresh': (3.49, '2 oz'), 'Safeway': (3.49, '2 oz'),
        },
    }

    stores = ['Harris Teeter', 'Lidl', 'Costco', 'Walmart', 'Amazon Fresh', "MOM's Organic", 'Safeway']
    store_discount = {
        'Harris Teeter': 0.95, 'Lidl': 0.70,
        'Costco': 0.65, 'Walmart': 0.72,
        'Amazon Fresh': 0.85, "MOM's Organic": 0.92, 'Safeway': 0.90,
    }

    def match_product(product_name):
        n = product_name.lower()
        for pattern, prices in competitor_db.items():
            if re.search(pattern, n, re.IGNORECASE):
                return prices
        return None

    sorted_products = sorted(products.items(), key=lambda x: x[1]['total_spend'], reverse=True)

    all_items = []
    for name, data in sorted_products:
        comp = match_product(name)
        avg_price = sum(data['prices']) / len(data['prices'])
        cat = categorize(name)
        entry = {
            'name': name, 'category': cat, 'wf_avg_price': avg_price,
            'wf_total_spend': data['total_spend'], 'qty_purchased': data['count'],
            'times_bought': len(data['prices']),
            'first_date': min(data['dates']), 'last_date': max(data['dates']),
            'weight_oz': data.get('weight_oz'), 'weight_display': data.get('weight_display'),
            'price_per_oz': data.get('price_per_oz'), 'asin': data.get('asin'),
            'matched': comp is not None,
        }
        # Store prices
        for store in stores:
            if comp and store in comp and comp[store][0] is not None:
                entry[f'{store}_price'] = comp[store][0]
            elif not comp and store in store_discount:
                entry[f'{store}_price'] = round(avg_price * store_discount[store], 2)
            else:
                entry[f'{store}_price'] = None

        # Best alternative
        best_price = avg_price
        best_store = 'Whole Foods'
        for store in stores:
            p = entry.get(f'{store}_price')
            if p is not None and p < best_price:
                best_price = p
                best_store = store
        entry['cheapest_store'] = best_store
        entry['cheapest_price'] = best_price
        entry['savings_pct'] = (avg_price - best_price) / avg_price if best_price < avg_price else 0
        entry['savings_amt'] = (avg_price - best_price) * data['count']

        all_items.append(entry)

    # Monthly spend
    monthly = defaultdict(float)
    monthly_items = defaultdict(int)
    for r in wf_rows:
        month = r['Order Date'][:7]
        price = float(r['Unit Price']) if r['Unit Price'] else 0
        qty = int(r['Original Quantity']) if r['Original Quantity'] else 1
        monthly[month] += price * qty
        monthly_items[month] += qty

    return all_items, stores, store_discount, monthly, monthly_items

all_items, stores, store_discount, monthly, monthly_items = load_data()

# ══════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════
st.sidebar.title("Filters")
categories = sorted(set(item['category'] for item in all_items))
sel_categories = st.sidebar.multiselect("Category", categories, default=categories)
sel_matched = st.sidebar.radio("Price data", ["All", "Matched only", "Estimated only"], index=0)
min_spend = st.sidebar.slider("Min WF total spend ($)", 0, 100, 0, 5)

filtered = [item for item in all_items
            if item['category'] in sel_categories
            and item['wf_total_spend'] >= min_spend
            and (sel_matched == "All"
                 or (sel_matched == "Matched only" and item['matched'])
                 or (sel_matched == "Estimated only" and not item['matched']))]

# ══════════════════════════════════════
# HEADER
# ══════════════════════════════════════
st.title("Whole Foods Price Comparison")
st.caption(f"Based on your Amazon/Whole Foods order history — {len(all_items)} products analyzed")

# ══════════════════════════════════════
# KPI ROW
# ══════════════════════════════════════
total_spend = sum(item['wf_total_spend'] for item in filtered)
n_products = len(filtered)
n_months = len(monthly)
avg_monthly = total_spend / n_months if n_months else 0

# Total savings by store
total_savings_by_store = {}
for store in stores:
    s = 0
    for item in filtered:
        p = item.get(f'{store}_price')
        if p is not None and p < item['wf_avg_price']:
            s += (item['wf_avg_price'] - p) * item['qty_purchased']
    total_savings_by_store[store] = s

best_alt = max(total_savings_by_store, key=total_savings_by_store.get) if total_savings_by_store else 'N/A'
best_alt_sav = total_savings_by_store.get(best_alt, 0)

best_alt_monthly = best_alt_sav / n_months if n_months else 0

cols = st.columns(7)
kpis = [
    (f"${total_spend:,.0f}", "Total WF Spend"),
    (f"${avg_monthly:,.0f}", "Avg Monthly Spend"),
    (f"{n_products}", "Products"),
    (f"{n_months}", "Months of Data"),
    (f"${best_alt_sav:,.0f}", f"Total Savings ({best_alt})"),
    (f"${best_alt_monthly:,.0f}", f"Monthly Savings ({best_alt})"),
    (f"{best_alt_sav/total_spend*100:.0f}%" if total_spend else "0%", "Savings Rate"),
]
for col, (val, label) in zip(cols, kpis):
    col.metric(label, val)

st.divider()

# ══════════════════════════════════════
# TAB LAYOUT
# ══════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "Store Savings", "Product Comparison", "Category Breakdown",
    "Meat & Produce", "Price Explorer", "Top Savings", "Essentials", "About"
])

# ── Tab 1: Store Savings ──
with tab1:
    sav_df = pd.DataFrame([
        {'Store': store, 'Total Savings': sav,
         '% of WF Spend': sav / total_spend * 100 if total_spend else 0,
         'Monthly Savings': sav / n_months if n_months else 0,
         'Annual Savings': sav / n_months * 12 if n_months else 0}
        for store, sav in sorted(total_savings_by_store.items(), key=lambda x: -x[1])
    ])

    savings_view = st.radio("View", ["Total (full period)", "Per month average"], horizontal=True)

    if savings_view == "Total (full period)":
        y_col, title_suffix = 'Total Savings', f'Total Savings over {n_months} Months'
    else:
        y_col, title_suffix = 'Monthly Savings', 'Average Monthly Savings'

    c1, c2 = st.columns([2, 1])
    with c1:
        fig = px.bar(sav_df, x='Store', y=y_col,
                     color=y_col, color_continuous_scale='Greens',
                     title=f'Estimated {title_suffix} vs Whole Foods')
        fig.update_layout(yaxis_title='Savings ($)', showlegend=False,
                         coloraxis_showscale=False, yaxis_gridcolor='#eee')
        fig.update_traces(text=sav_df[y_col].apply(lambda x: f'${x:,.0f}'),
                         textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Savings Summary")
        for _, row in sav_df.iterrows():
            st.markdown(f"**{row['Store']}**")
            st.markdown(f"  Total ({n_months} mo): **${row['Total Savings']:,.2f}** ({row['% of WF Spend']:.1f}%)")
            st.markdown(f"  Per month: **${row['Monthly Savings']:,.2f}** | Annual: ${row['Annual Savings']:,.2f}")
            st.markdown("---")

# ── Tab 2: Product Comparison ──
with tab2:
    st.subheader("Product-by-Product Price Comparison")
    st.caption("Prices are per-unit as sold (not weight-normalized). Check the Price Explorer tab for $/oz details.")

    sort_by = st.selectbox("Sort by", ["WF Total Spend", "Savings %", "Product Name"], index=0)
    if sort_by == "WF Total Spend":
        display_items = sorted(filtered, key=lambda x: -x['wf_total_spend'])
    elif sort_by == "Savings %":
        display_items = sorted(filtered, key=lambda x: -x['savings_pct'])
    else:
        display_items = sorted(filtered, key=lambda x: x['name'])

    # Build DataFrame for table
    rows_data = []
    for item in display_items:
        row = {
            'Product': item['name'][:60],
            'Category': item['category'],
            'WF Price': item['wf_avg_price'],
            'Qty': item['qty_purchased'],
            'WF Total': item['wf_total_spend'],
            'WF /mo': item['wf_total_spend'] / n_months if n_months else 0,
        }
        for store in stores:
            p = item.get(f'{store}_price')
            row[store] = p
        row['Cheapest'] = item['cheapest_store']
        row['Savings %'] = item['savings_pct']
        row['Savings Total'] = item['savings_amt']
        row['Savings /mo'] = item['savings_amt'] / n_months if n_months else 0
        rows_data.append(row)

    df = pd.DataFrame(rows_data)

    def color_prices(val, col_name, wf_price):
        if pd.isna(val) or col_name not in stores:
            return ''
        if val < wf_price:
            return 'background-color: #e8f5e9; color: #2e7d32'
        elif val > wf_price:
            return 'background-color: #fce4ec; color: #c62828'
        return ''

    # Format the dataframe
    format_dict = {'WF Price': '${:.2f}', 'WF Total': '${:.2f}', 'WF /mo': '${:.2f}',
                   'Savings %': '{:.1%}', 'Savings Total': '${:.2f}', 'Savings /mo': '${:.2f}'}
    for store in stores:
        format_dict[store] = '${:.2f}'

    st.dataframe(
        df.style.format(format_dict, na_rep='—')
          .map(lambda v: 'background-color: #e8f5e9; color: #2e7d32' if isinstance(v, (int, float)) and v > 0.2 else '',
                    subset=['Savings %']),
        height=600, use_container_width=True
    )

    st.caption(f"Showing {len(display_items)} products. Green = cheaper than WF, Red = more expensive.")

# ── Tab 3: Category Breakdown ──
with tab3:
    c1, c2 = st.columns(2)

    cat_spend = defaultdict(lambda: {'spend': 0, 'items': 0, 'savings': defaultdict(float)})
    for item in filtered:
        cat = item['category']
        cat_spend[cat]['spend'] += item['wf_total_spend']
        cat_spend[cat]['items'] += item['qty_purchased']
        for store in stores:
            p = item.get(f'{store}_price')
            if p is not None and p < item['wf_avg_price']:
                cat_spend[cat]['savings'][store] += (item['wf_avg_price'] - p) * item['qty_purchased']

    with c1:
        cat_df = pd.DataFrame([
            {'Category': cat, 'WF Spend': d['spend'], 'Items': d['items']}
            for cat, d in sorted(cat_spend.items(), key=lambda x: -x[1]['spend'])
        ])
        fig = px.pie(cat_df, names='Category', values='WF Spend',
                     title='Spending by Category', hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_traces(textinfo='label+percent+value', texttemplate='%{label}<br>$%{value:,.0f}<br>%{percent}')
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        # Best savings per category
        cat_sav_rows = []
        for cat, d in cat_spend.items():
            if d['savings']:
                best_store = max(d['savings'], key=d['savings'].get)
                total_sav = d['savings'][best_store]
                cat_sav_rows.append({
                    'Category': cat, 'Best Store': best_store,
                    'Savings (total)': total_sav,
                    'Savings (/mo)': total_sav / n_months if n_months else 0,
                    'WF Spend': d['spend'],
                    'Savings %': total_sav / d['spend'] * 100 if d['spend'] else 0
                })
        cat_sav_df = pd.DataFrame(cat_sav_rows).sort_values('Savings (total)', ascending=False)

        cat_view = st.radio("Category savings view", ["Total (full period)", "Per month average"],
                            horizontal=True, key='cat_view')
        y_col_cat = 'Savings (total)' if 'Total' in cat_view else 'Savings (/mo)'

        fig2 = px.bar(cat_sav_df, x='Category', y=y_col_cat, color='Best Store',
                      title=f'Best {"Total" if "Total" in cat_view else "Monthly"} Savings by Category',
                      color_discrete_sequence=px.colors.qualitative.Set2)
        fig2.update_layout(yaxis_title='Savings ($)', yaxis_gridcolor='#eee')
        st.plotly_chart(fig2, use_container_width=True)

    # Category-store heatmap
    st.subheader("Savings Heatmap: Category × Store")
    hm_view = st.radio("Heatmap view", ["Total (full period)", "Per month average"],
                       horizontal=True, key='hm_view')
    hm_divisor = 1 if 'Total' in hm_view else (n_months or 1)

    heatmap_data = []
    for cat, d in cat_spend.items():
        row = {'Category': cat}
        for store in stores:
            row[store] = d['savings'].get(store, 0) / hm_divisor
        heatmap_data.append(row)
    hm_df = pd.DataFrame(heatmap_data).set_index('Category')
    hm_df = hm_df.loc[hm_df.sum(axis=1).sort_values(ascending=False).index]

    hm_label = 'Total' if 'Total' in hm_view else '/mo'
    fig3 = px.imshow(hm_df.values, x=stores, y=hm_df.index.tolist(),
                     color_continuous_scale='Greens', aspect='auto',
                     title=f'Savings by Category & Store ({hm_label}, $)',
                     labels=dict(color='Savings ($)'))
    fig3.update_traces(text=[[f'${v:,.0f}' for v in row] for row in hm_df.values],
                      texttemplate='%{text}')
    fig3.update_layout(height=400)
    st.plotly_chart(fig3, use_container_width=True)

# ── Tab 4: Meat & Produce Focus ──
with tab4:
    st.subheader("Meat/Seafood & Produce — Price Comparison")
    st.caption("Side-by-side comparison of protein and fresh produce prices across stores")

    meat_items = [i for i in all_items if i['category'] == 'Meat & Seafood']
    produce_items = [i for i in all_items if i['category'] == 'Produce']

    meat_items.sort(key=lambda x: -x['wf_total_spend'])
    produce_items.sort(key=lambda x: -x['wf_total_spend'])

    # KPIs
    meat_spend = sum(i['wf_total_spend'] for i in meat_items)
    produce_spend = sum(i['wf_total_spend'] for i in produce_items)
    meat_sav = sum(i['savings_amt'] for i in meat_items)
    produce_sav = sum(i['savings_amt'] for i in produce_items)
    combined_spend = meat_spend + produce_spend
    combined_sav = meat_sav + produce_sav

    mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
    mc1.metric("Meat/Seafood Spend", f"${meat_spend:,.0f}")
    mc2.metric("Meat Savings", f"${meat_sav:,.0f}")
    mc3.metric("Produce Spend", f"${produce_spend:,.0f}")
    mc4.metric("Produce Savings", f"${produce_sav:,.0f}")
    mc5.metric("Combined Spend", f"${combined_spend:,.0f}")
    mc6.metric("Combined Savings", f"${combined_sav:,.0f}")

    st.markdown("---")

    # Build comparison table
    def build_mp_table(items, section_name):
        rows = []
        for item in items:
            row = {
                'Product': item['name'][:55],
                'WF Price': item['wf_avg_price'],
                'Qty': item['qty_purchased'],
                'WF Total': item['wf_total_spend'],
            }
            for store in stores:
                p = item.get(f'{store}_price')
                row[store] = p
            row['Cheapest'] = item['cheapest_store']
            row['Savings %'] = item['savings_pct']
            rows.append(row)
        return pd.DataFrame(rows)

    # Meat & Seafood section
    st.markdown("### Meat & Seafood")
    if meat_items:
        meat_df = build_mp_table(meat_items, 'Meat & Seafood')
        format_dict = {'WF Price': '${:.2f}', 'WF Total': '${:.2f}', 'Savings %': '{:.1%}'}
        for store in stores:
            format_dict[store] = '${:.2f}'
        st.dataframe(
            meat_df.style.format(format_dict, na_rep='—'),
            height=400, use_container_width=True
        )

        # Chart: WF vs cheapest for top meat items
        top_meat = meat_df.head(10)
        if not top_meat.empty:
            fig_meat = go.Figure()
            fig_meat.add_trace(go.Bar(
                name='Whole Foods', y=top_meat['Product'], x=top_meat['WF Price'],
                orientation='h', marker_color='#1F3864',
                text=top_meat['WF Price'].apply(lambda x: f'${x:.2f}'), textposition='inside',
            ))
            # Find cheapest price per item
            cheapest_prices = []
            cheapest_labels = []
            for _, r in top_meat.iterrows():
                best_p = r['WF Price']
                best_s = 'WF'
                for store in stores:
                    if pd.notna(r.get(store)) and r[store] < best_p:
                        best_p = r[store]
                        best_s = store
                cheapest_prices.append(best_p)
                cheapest_labels.append(f'${best_p:.2f} ({best_s})')
            fig_meat.add_trace(go.Bar(
                name='Cheapest Alt', y=top_meat['Product'], x=cheapest_prices,
                orientation='h', marker_color='#548235',
                text=cheapest_labels, textposition='inside',
            ))
            fig_meat.update_layout(
                title='Top Meat & Seafood: WF vs Cheapest',
                barmode='group', xaxis=dict(title='Price ($)', gridcolor='#eee'),
                yaxis=dict(autorange='reversed'),
                height=450, margin=dict(l=250),
                legend=dict(orientation='h', yanchor='bottom', y=1.02),
            )
            st.plotly_chart(fig_meat, use_container_width=True)
    else:
        st.info("No Meat & Seafood items found.")

    st.markdown("---")

    # Produce section
    st.markdown("### Produce")
    if produce_items:
        produce_df = build_mp_table(produce_items, 'Produce')
        st.dataframe(
            produce_df.style.format(format_dict, na_rep='—'),
            height=400, use_container_width=True
        )

        top_produce = produce_df.head(10)
        if not top_produce.empty:
            fig_prod = go.Figure()
            fig_prod.add_trace(go.Bar(
                name='Whole Foods', y=top_produce['Product'], x=top_produce['WF Price'],
                orientation='h', marker_color='#1F3864',
                text=top_produce['WF Price'].apply(lambda x: f'${x:.2f}'), textposition='inside',
            ))
            cheapest_prices = []
            cheapest_labels = []
            for _, r in top_produce.iterrows():
                best_p = r['WF Price']
                best_s = 'WF'
                for store in stores:
                    if pd.notna(r.get(store)) and r[store] < best_p:
                        best_p = r[store]
                        best_s = store
                cheapest_prices.append(best_p)
                cheapest_labels.append(f'${best_p:.2f} ({best_s})')
            fig_prod.add_trace(go.Bar(
                name='Cheapest Alt', y=top_produce['Product'], x=cheapest_prices,
                orientation='h', marker_color='#548235',
                text=cheapest_labels, textposition='inside',
            ))
            fig_prod.update_layout(
                title='Top Produce: WF vs Cheapest',
                barmode='group', xaxis=dict(title='Price ($)', gridcolor='#eee'),
                yaxis=dict(autorange='reversed'),
                height=450, margin=dict(l=250),
                legend=dict(orientation='h', yanchor='bottom', y=1.02),
            )
            st.plotly_chart(fig_prod, use_container_width=True)
    else:
        st.info("No Produce items found.")

    # Summary
    if meat_items or produce_items:
        monthly_combined = combined_sav / n_months if n_months else 0
        st.success(f"**Meat & Produce combined:** ${combined_spend:,.0f} spent at WF. "
                   f"Switching saves **${combined_sav:,.0f}** total (${monthly_combined:,.0f}/mo) — "
                   f"**{combined_sav/combined_spend*100:.0f}%** of this category's spend.")

# ── Tab 5: Price Explorer ──
with tab5:
    st.subheader("Drill into a specific product")

    product_names = [item['name'] for item in filtered]
    sel_product = st.selectbox("Select product", product_names, index=0)
    item = next((i for i in filtered if i['name'] == sel_product), None)

    if item:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown(f"**Category:** {item['category']}")
            st.markdown(f"**Weight:** {item.get('weight_display') or 'N/A'}")
            st.markdown(f"**Times bought:** {item['times_bought']}")
            st.markdown(f"**Total qty:** {item['qty_purchased']}")
            st.markdown(f"**WF avg price:** ${item['wf_avg_price']:.2f}")
            st.markdown(f"**WF total spend:** ${item['wf_total_spend']:.2f}")
            st.markdown(f"**WF spend /mo:** ${item['wf_total_spend'] / n_months:.2f}" if n_months else "")
            if item.get('price_per_oz'):
                st.markdown(f"**WF $/oz:** ${item['price_per_oz']:.2f}")
            st.markdown(f"**First purchased:** {item['first_date']}")
            st.markdown(f"**Last purchased:** {item['last_date']}")
            if item['matched']:
                st.success("Price matched with competitor data")
            else:
                st.warning("Prices estimated using store discount tiers")

        with c2:
            prices = {'Whole Foods': item['wf_avg_price']}
            for store in stores:
                p = item.get(f'{store}_price')
                if p is not None:
                    prices[store] = p

            price_df = pd.DataFrame([
                {'Store': k, 'Price': v} for k, v in prices.items()
            ]).sort_values('Price')

            colors = ['#548235' if row['Store'] != 'Whole Foods' and row['Price'] < item['wf_avg_price']
                      else '#C00000' if row['Store'] != 'Whole Foods' and row['Price'] > item['wf_avg_price']
                      else '#2E75B6'
                      for _, row in price_df.iterrows()]

            fig = go.Figure(go.Bar(
                x=price_df['Store'], y=price_df['Price'],
                marker_color=colors,
                text=price_df['Price'].apply(lambda x: f'${x:.2f}'),
                textposition='outside'
            ))
            fig.update_layout(
                title=f'Price Comparison: {item["name"][:50]}',
                yaxis=dict(title='Price ($)', gridcolor='#eee'),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

        if item['savings_pct'] > 0:
            monthly_sav = item['savings_amt'] / n_months if n_months else 0
            st.info(f"**Cheapest:** {item['cheapest_store']} at ${item['cheapest_price']:.2f} "
                    f"— saves **{item['savings_pct']:.0%}** | "
                    f"Total: ${item['savings_amt']:.2f} ({n_months} mo) | "
                    f"Per month: ${monthly_sav:.2f}")

# ── Tab 6: Top Savings ──
with tab6:
    st.subheader("Where You Save the Most — and Least")

    # Only items with actual savings data
    items_with_savings = [i for i in filtered if i['savings_pct'] > 0]

    # Top 10 biggest savings
    top10 = sorted(items_with_savings, key=lambda x: -x['savings_amt'])[:10]
    # Bottom 10 (smallest savings among those that have some)
    bottom10 = sorted(items_with_savings, key=lambda x: x['savings_amt'])[:10]

    # ── Biggest Savings ──
    st.markdown("### Biggest Savings")
    st.caption("Products where switching stores saves you the most")
    top_rows = []
    for item in top10:
        mo_sav = item['savings_amt'] / n_months if n_months else 0
        top_rows.append({
            'Product': item['name'],
            'Category': item['category'],
            'WF Price': item['wf_avg_price'],
            'Best Alt': item['cheapest_store'],
            'Alt Price': item['cheapest_price'],
            'Savings %': item['savings_pct'],
            'Total Savings': item['savings_amt'],
            'Savings /mo': mo_sav,
        })
    top_df = pd.DataFrame(top_rows)
    if not top_df.empty:
        fig_top = go.Figure()
        fig_top.add_trace(go.Bar(
            y=top_df['Product'], x=top_df['Total Savings'],
            orientation='h', marker_color='#548235',
            text=top_df.apply(lambda r: f"${r['Total Savings']:,.2f} ({r['Savings %']:.0%}) → {r['Best Alt']}", axis=1),
            textposition='outside',
        ))
        fig_top.update_layout(
            title='Top 10: Biggest Total Savings',
            xaxis=dict(title='Savings ($)', gridcolor='#eee',
                       range=[0, top_df['Total Savings'].max() * 1.6]),
            yaxis=dict(autorange='reversed', tickfont=dict(size=11)),
            height=500, margin=dict(l=350),
        )
        st.plotly_chart(fig_top, use_container_width=True)

        st.dataframe(top_df.style.format({
            'WF Price': '${:.2f}', 'Alt Price': '${:.2f}', 'Savings %': '{:.0%}',
            'Total Savings': '${:.2f}', 'Savings /mo': '${:.2f}',
        }), use_container_width=True)

    # Summary
    if top10:
        top_total = sum(i['savings_amt'] for i in top10)
        top_monthly = top_total / n_months if n_months else 0
        st.success(f"Just switching the **top 10 products** alone would save "
                   f"**${top_total:,.2f}** total (${top_monthly:,.2f}/mo)")

    st.markdown("---")

    # ── Smallest Savings ──
    st.markdown("### Smallest Savings")
    st.caption("Products where WF is almost competitive — less reason to switch")
    bot_rows = []
    for item in bottom10:
        mo_sav = item['savings_amt'] / n_months if n_months else 0
        bot_rows.append({
            'Product': item['name'],
            'Category': item['category'],
            'WF Price': item['wf_avg_price'],
            'Best Alt': item['cheapest_store'],
            'Alt Price': item['cheapest_price'],
            'Savings %': item['savings_pct'],
            'Total Savings': item['savings_amt'],
            'Savings /mo': mo_sav,
        })
    bot_df = pd.DataFrame(bot_rows)
    if not bot_df.empty:
        fig_bot = go.Figure()
        fig_bot.add_trace(go.Bar(
            y=bot_df['Product'], x=bot_df['Total Savings'],
            orientation='h', marker_color='#ED7D31',
            text=bot_df.apply(lambda r: f"${r['Total Savings']:,.2f} ({r['Savings %']:.0%}) → {r['Best Alt']}", axis=1),
            textposition='outside',
        ))
        fig_bot.update_layout(
            title='Bottom 10: Smallest Savings',
            xaxis=dict(title='Savings ($)', gridcolor='#eee',
                       range=[0, bot_df['Total Savings'].max() * 2.5]),
            yaxis=dict(autorange='reversed', tickfont=dict(size=11)),
            height=500, margin=dict(l=350),
        )
        st.plotly_chart(fig_bot, use_container_width=True)

        st.dataframe(bot_df.style.format({
            'WF Price': '${:.2f}', 'Alt Price': '${:.2f}', 'Savings %': '{:.0%}',
            'Total Savings': '${:.2f}', 'Savings /mo': '${:.2f}',
        }), use_container_width=True)

# ── Tab 7: Essentials ──
with tab7:
    st.subheader("Essential Staples — Price Check")
    st.caption("Core grocery staples: how much are you paying at WF vs alternatives?")

    # Define essential product patterns (order = priority for display)
    essentials_patterns = [
        ('Eggs (organic)', r'organic.*egg.*12|egg.*organic.*12|365.*egg|vital farms.*egg'),
        ('Milk (whole, organic)', r'organic valley.*whole milk|maple hill.*whole milk|whole milk.*organic'),
        ('Butter / Plant Butter', r'violife.*butter|plant butter|butter'),
        ('Chicken', r'chicken.*leg|chicken.*thigh|chicken.*breast|365.*chicken'),
        ('Salmon', r'salmon.*fillet|365.*salmon|sockeye salmon'),
        ('Pasta / Spaghetti', r'365.*spaghetti|organic.*spaghetti|pasta'),
        ('Rice / Grains', r'rice|oat|couscous|quinoa'),
        ('Bread / Tortilla', r'bread|tortilla'),
        ('Carrots', r'organic.*carrot|loose carrot|carrot'),
        ('Onions', r'onion|shallot'),
        ('Tomatoes', r'tomato.*on.*vine|heirloom.*tomato|organic.*tomato'),
        ('Potatoes', r'potato|sweet potato'),
        ('Garlic', r'garlic.*bulb|garlic ali|christopher.*garlic|peeled garlic|minced garlic'),
        ('Spinach / Greens', r'baby spinach|organic.*spinach|kale|arugula|lettuce'),
        ('Apples / Fruit', r'organic.*fuji|fuji.*apple|organic.*apple|banana'),
        ('Berries', r'raspberry|blueberr|blackberr|strawberr'),
        ('Bell Peppers', r'bell pepper|green.*pepper'),
        ('Yogurt', r'yogurt|stonyfield|clio'),
        ('Cheese (basics)', r'cheese|camembert|goat cheese|mozzarella|cheddar'),
        ('Oil / Vinegar', r'olive oil|vinegar|oil'),
    ]

    matched_essentials = []
    used_items = set()
    for label, pattern in essentials_patterns:
        for item in all_items:
            if item['name'] in used_items:
                continue
            if re.search(pattern, item['name'], re.IGNORECASE):
                mo_sav = item['savings_amt'] / n_months if n_months else 0
                matched_essentials.append({
                    'Staple': label,
                    'Product': item['name'][:55],
                    'WF Price': item['wf_avg_price'],
                    'Qty Bought': item['qty_purchased'],
                    'WF Total': item['wf_total_spend'],
                    'WF /mo': item['wf_total_spend'] / n_months if n_months else 0,
                    'Cheapest': item['cheapest_store'],
                    'Alt Price': item['cheapest_price'],
                    'Savings %': item['savings_pct'],
                    'Savings Total': item['savings_amt'],
                    'Savings /mo': mo_sav,
                    'Matched': item['matched'],
                    '_item': item,
                })
                used_items.add(item['name'])

    if matched_essentials:
        ess_df = pd.DataFrame(matched_essentials)

        # KPIs for essentials
        ess_total_wf = ess_df['WF Total'].sum()
        ess_total_sav = ess_df['Savings Total'].sum()
        ess_monthly_wf = ess_df['WF /mo'].sum()
        ess_monthly_sav = ess_df['Savings /mo'].sum()

        ec1, ec2, ec3, ec4 = st.columns(4)
        ec1.metric("Essentials WF Spend", f"${ess_total_wf:,.0f}")
        ec2.metric("Essentials /mo", f"${ess_monthly_wf:,.0f}")
        ec3.metric("Potential Savings", f"${ess_total_sav:,.0f}")
        ec4.metric("Savings /mo", f"${ess_monthly_sav:,.0f}")

        st.markdown("---")

        # Chart: WF vs cheapest for each essential
        chart_df = ess_df.drop_duplicates(subset='Staple').head(15)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Whole Foods', y=chart_df['Staple'], x=chart_df['WF Price'],
            orientation='h', marker_color='#1F3864',
            text=chart_df['WF Price'].apply(lambda x: f'${x:.2f}'), textposition='inside',
        ))
        fig.add_trace(go.Bar(
            name='Cheapest Alt', y=chart_df['Staple'], x=chart_df['Alt Price'],
            orientation='h', marker_color='#548235',
            text=chart_df.apply(lambda r: f"${r['Alt Price']:.2f} ({r['Cheapest']})", axis=1),
            textposition='inside',
        ))
        fig.update_layout(
            title='Essential Staples: WF vs Cheapest Alternative',
            barmode='group', xaxis=dict(title='Price ($)', gridcolor='#eee'),
            yaxis=dict(autorange='reversed'),
            height=500, margin=dict(l=150),
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Full table
        display_ess = ess_df.drop(columns=['_item', 'Matched'])
        st.dataframe(display_ess.style.format({
            'WF Price': '${:.2f}', 'Alt Price': '${:.2f}', 'WF Total': '${:.2f}',
            'WF /mo': '${:.2f}', 'Savings %': '{:.0%}',
            'Savings Total': '${:.2f}', 'Savings /mo': '${:.2f}',
        }), height=500, use_container_width=True)

        st.info(f"**{len(matched_essentials)} essential products** account for "
                f"**${ess_total_wf:,.0f}** ({ess_total_wf/total_spend*100:.0f}% of total spend). "
                f"Switching just these saves **${ess_monthly_sav:,.0f}/mo**.")
    else:
        st.warning("No essential staples found in your purchase history.")

# ── Tab 8: About ──
with tab8:
    # ── Conclusions ──
    st.subheader("Conclusions")

    # Compute dynamic insights
    matched_count = sum(1 for i in filtered if i['matched'])
    estimated_count = len(filtered) - matched_count
    top_store = max(total_savings_by_store, key=total_savings_by_store.get) if total_savings_by_store else 'N/A'
    top_sav = total_savings_by_store.get(top_store, 0)
    top_sav_mo = top_sav / n_months if n_months else 0

    # Category with highest spend
    cat_totals = defaultdict(float)
    for item in filtered:
        cat_totals[item['category']] += item['wf_total_spend']
    top_cat = max(cat_totals, key=cat_totals.get) if cat_totals else 'N/A'

    # Fish spend
    fish_items = [i for i in filtered if i['category'] == 'Meat & Seafood'
                  and any(kw in i['name'].lower() for kw in ['salmon', 'cod', 'swordfish', 'tilapia', 'shrimp', 'scallop', 'tuna'])]
    fish_spend = sum(i['wf_total_spend'] for i in fish_items)
    fish_monthly = fish_spend / n_months if n_months else 0

    st.markdown(f"""
**Key findings from {n_months} months of Whole Foods grocery data ({n_products} products, ${total_spend:,.0f} total):**

1. **Best alternative store: {top_store}** — switching would save an estimated **${top_sav:,.0f} total** (${top_sav_mo:,.0f}/mo), or about {top_sav/total_spend*100:.0f}% of your WF spend.

2. **Biggest spending category: {top_cat}** (${cat_totals[top_cat]:,.0f}). Meat & Seafood and Produce typically drive the largest price gaps between WF and competitors.

3. **Fish & seafood** accounts for ${fish_spend:,.0f} (${fish_monthly:,.0f}/mo). **Update:** fish is now purchased directly from [Alaska Wild Alaska Salmon & Seafood Co](https://prior.fish), bypassing grocery stores entirely — better quality wild-caught fish, likely at comparable or lower per-lb cost than WF farm-raised.

4. **{matched_count} products** have real competitor prices; {estimated_count} use store-tier estimates. The matched items alone represent the most actionable savings.

5. **WF remains competitive** on niche organic items (specialty cheese, artisan products) where alternatives don't carry equivalent brands. The smallest-savings products are mostly items where WF is already price-matched.

**Recommended strategy:** Keep WF for specialty/organic items and convenience. Shift staples (eggs, chicken, produce, pasta) to **{top_store}**, **Walmart**, or **Costco** (bulk buys). Buy fish from Alaska Wild. Costco offers the deepest discounts on bulk staples and proteins; Walmart wins on per-unit pricing for smaller households.
""")

    st.markdown("---")
    st.subheader("About This Dashboard")
    st.markdown("""
### Data Sources

- **Amazon Order History CSV** — exported from your Amazon account (`Your Amazon Orders/Order History.csv`).
  Whole Foods orders are identified by shipping option (`scheduled-houdini`, etc.).
  Water, sodas, wine, and bag fees are excluded.
- **Competitor Price Database** — ~50 product patterns with manually researched prices (March 2026)
  from Harris Teeter, Lidl, Costco, Walmart, Amazon Fresh, MOM's Organic, and Safeway.
- **Store Tier Discounts** — for unmatched products, savings are estimated using
  Washington Consumers' Checkbook store-tier multipliers.

### Matched vs Estimated

| Type | Meaning |
|------|---------|
| **Matched** | Product was matched (by regex) to the competitor price database. These are real, researched prices for comparable items at each store. |
| **Estimated** | No match found. Competitor price is estimated by applying the store's average discount factor to the WF price. Directionally correct based on published grocery price indices. |

### Store Discount Factors (for estimated prices)

| Store | vs WF | Source |
|-------|-------|--------|
| Costco | -35% | Bulk pricing comparison |
| Lidl | -30% | Washington Consumers' Checkbook |
| Walmart | -28% | Washington Consumers' Checkbook |
| Amazon Fresh | -15% | Prime member pricing |
| Safeway | -10% | Washington Consumers' Checkbook |
| MOM's Organic | -8% | Organic-to-organic comparison |
| Harris Teeter | -5% | Washington Consumers' Checkbook |

### Tabs

| Tab | What it shows |
|-----|---------------|
| **Store Savings** | Total and monthly savings per store vs Whole Foods, with toggle |
| **Product Comparison** | Full sortable table with per-store prices (green = cheaper, red = pricier) |
| **Category Breakdown** | Spending pie chart, best savings per category, category x store heatmap |
| **Price Explorer** | Drill into a single product, see all store prices side by side |
| **Top Savings** | 10 products with biggest savings vs 10 with smallest |
| **Essentials** | Core staples (eggs, milk, chicken, pasta, produce) — price check |
| **About** | This page |

### Files

| File | Purpose |
|------|---------|
| `app.py` | This Streamlit dashboard |
| `build_comparison.py` | Original script that generates the Excel + PPT |
| `Grocery_Price_Comparison.xlsx` | Static Excel output |
| `Grocery_Price_Comparison.pptx` | Static PPT output |
| `Your Amazon Orders/Order History.csv` | Raw Amazon data |
""")

# ══════════════════════════════════════
# FOOTER
# ══════════════════════════════════════
st.divider()
st.caption("Data: Amazon Order History export | Competitor prices: web research (March 2026) | "
           "Unmatched products use Washington Consumers' Checkbook store-tier discounts")
