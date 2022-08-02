import requests
import re
import os
import smtplib
import config
import time
import sys
from email.message import EmailMessage
from dataclasses import dataclass
from hashlib import sha1

PRICE_MIN           = '400'
PRICE_MAX           = '700'
SEARCH_RADIUS       = '0'
SEARCH_QUERY        = 'Falkirk'
EXCLUDE_LOCATIONS   = ['Denny', "Bo'ness", "Bonnybridge", "Larbert", "Stenhousemuir"]

AGGREGATORS = {
    'Zoopla': {
        'search_endpoint': ('https://www.zoopla.co.uk/to-rent/property/falkirk-county/'
                            '?price_frequency=per_month'
                            '&results_sort=newest_listings'
                            f'&price_max={PRICE_MAX}'
                            f'&price_min={PRICE_MIN}'
                            f'&q={SEARCH_QUERY}'
                            f'&radius={SEARCH_RADIUS}'),
        'expr_property': r'(?<=typename":"Listing")(.*?)(?=isFavourite":false)',
        'expr_bedrooms': r'"content":([0-9]?),"iconId":"bed"',
        'expr_location': r',"address":"(.*?)",',
        'expr_price': r'"price":"£([0-9]+?) pcm"',
        'expr_details_url': (r'"listingId":"([0-9]+?)"', 'https://www.zoopla.co.uk/to-rent/details/')
    },
    
    'Rightmove': {
        'search_endpoint': ('https://www.rightmove.co.uk/property-to-rent/find.html'
                            '?locationIdentifier=REGION%5E501'
                            f'&maxPrice={PRICE_MAX}'
                            f'&minPrice={PRICE_MIN}'),
        'expr_property': r'(?<={"id":[0-9])(.*?)(?="hasBrandPlus")',
        'expr_bedrooms': r'"bedrooms":([0-9]?)',
        'expr_location': r'"displayAddress":"(.*?)"',
        'expr_price': r'"displayPrice":"£([0-9]+?) pcm"',
        'expr_details_url': (r'propertyUrl":"(.*?)#/\?', 'https://www.rightmove.co.uk')
    },
    
    'Clyde': {
        'search_endpoint': ('https://www.clydeproperty.co.uk/search/Falkirk,%20Stirlingshire:55.992735:-3.837275:'
                            f'{SEARCH_QUERY}:place:{SEARCH_QUERY}'
                            f'/any/{PRICE_MIN}/{PRICE_MAX}/any/any/any/any/any/2/1/date/'),
        'expr_property': r'(?<=property-search-item)(.*?)(?=fa-video-camera)',
        'expr_bedrooms': r'([0-9]?]?) Bedroom',
        'expr_location': r'(?<=property-name-title">)([a-zA-Z0-9\W]+?)(?=<\/label)',
        'expr_price': r';([0-9]+?) PCM',
        'expr_details_url': (r'href="(\/property\/.+?)"', 'https://www.clydeproperty.co.uk')
    },
    
    'SlaterHogg': {
        'search_endpoint': (f'https://www.slaterhogg.co.uk/falkirk/lettings'
                            f'/from-{PRICE_MIN}'
                            f'/up-to-{PRICE_MAX}'
                            '/most-recent-first'),
        'expr_property': r'(?<=url":")(.*?)(?="floorplans")',
        'expr_bedrooms': r'bedrooms":([0-9]?)',
        'expr_location': r'"displayAddress":"(.*?)"',
        'expr_price': r'"price":"£([0-9]+?) ',
        'expr_details_url': (r'(/properties/[0-9]+/lettings/[0-9]+)', 'https://www.slaterhogg.co.uk')
    },
    
    'CampbellDean': {
        'search_endpoint': ('https://campbellanddean.com/property-search/?department=residential-lettings'
                            f'&minimum_rent={PRICE_MIN}'
                            f'&maximum_rent={PRICE_MAX}&orderby=date'),
        'expr_property': r'(?<=department-residential-lettings)(.*?)(?=class="actions")',
        'expr_bedrooms': r'', # no bedrooms on overview page
        'expr_location': r'.+.jpg" alt="(.*?)"',
        'expr_price': r';([0-9]+) pcm',
        'expr_details_url': r'<h3><a href="(.*?)">.+<\/a><\/h3>'
    }
    
}

if len(sys.argv) > 1:
    DEBUG = True
else:
    DEBUG = False
    
@dataclass
class Property:
    aggregator: str
    location: str
    bedrooms: int
    price: float
    url: str
    sha1: str
    
    def __post_init__(self):
        """
        Create a SHA-1 hash of the property and cache it to avoid duplicate alerts
        from multiple aggregators. 
        """
        self.sha1 = sha1(self.bedrooms.encode('utf-8') +
                    self.location.encode('utf-8') +
                    self.price.encode('utf-8')).hexdigest()
    
    def sha1(self):
        return 


def fetch(url):
    if DEBUG:
        with open('test.html', 'r') as f:
            return f.read()
    
    resp = requests.get(url).text
    resp = resp.replace('\t', '')
    resp = resp.replace('\n', '')
    return resp

def extract_regex(regex, text):
    prepend = ''
        
    if isinstance(regex, tuple):
        prepend = regex[1]
        regex = regex[0]
        
    try:
        extracted = re.findall(regex, text)[0]
    except:
        extracted = 'Unknown'
        
    return prepend + extracted


def is_excluded_location(location):
    for loc in EXCLUDE_LOCATIONS:
        if loc.lower() in location.lower():
            return True
    
    return False


def normalise_location(location):
    location = location.lower()
    
    if ',' in location:
        return location.split(',')[0]
    
    location = location.replace(',', '')
    
    return location


def parse(response, config, agg_name):
    properties = []

    all_properties = re.findall(config['expr_property'], response)
    
    for prop in all_properties:
        location = extract_regex(config['expr_location'], prop)
        if is_excluded_location(location):
            continue

        location = normalise_location(location)
        bedrooms = extract_regex(config['expr_bedrooms'], prop)
        price = extract_regex(config['expr_price'], prop)
        url = extract_regex(config['expr_details_url'], prop)
        
        properties.append(Property(
            aggregator=agg_name,
            location=location,
            bedrooms=bedrooms,
            price=price,
            url=url
        ))
    
    return properties


def fetch_all_properties():
    properties = []
    
    for agg_name, config in AGGREGATORS.items():        
        try:
            resp = fetch(config['search_endpoint'])

            for p in parse(resp, config, agg_name):
                properties.append(p)
        except:
            print(f'Error fetching {config["search_endpoint"]}', file=sys.stderr)
        
    return properties


def send_notification(property):
    if DEBUG:
        return
    
    msg = EmailMessage()
    msg.set_content(f"""
    A new property has been added.
        URL: {property.url}
        Price: {property.price}
        Bedrooms: {property.bedrooms}
    """)
    msg['subject'] = 'New property added'
    msg['to'] = config.RECIPIENT
    msg['from'] = config.EMAIL_USERNAME
        
    server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
    server.starttls()
    server.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
    server.send_message(msg)
    server.quit()

        
if __name__ == '__main__':
    seen = []
    first_run = True
    
    if os.path.isfile('cache') and not DEBUG:
        first_run = False
        seen = [l.rstrip() for l in open('cache', 'r').readlines()]
        
    for p in fetch_all_properties():
        if p.sha1 in seen:
            continue
        
        seen.append(p.sha1)
        
        with open('cache', 'a+') as f:
            f.write(p.sha1 + "\n")
        
        print(p)
        
        if not first_run:
            send_notification(p)
            time.sleep(10)    
