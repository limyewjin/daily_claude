import argparse
import os
import yaml
import hashlib
import json
import logging
import time
import re
import random
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from PIL import Image
import io
import base64
import traceback


from api import generate_anthropic_response, send_email, fetch_crypto_data, get_url
from frontpage import fetch_paper
from weather import extract_weather_info

# Set up logging
parser = argparse.ArgumentParser()
parser.add_argument('--loglevel', default='WARNING', help='Set the logging level')
args = parser.parse_args()
log_level = args.loglevel.upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Set up Jinja2 environment
template_env = Environment(loader=FileSystemLoader('templates'))

def load_module(module_name):
    try:
        with open(f"modules/{module_name}", 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logging.error(f"Module file modules/{module_name} not found")
        return None

def get_cache_path(module_name, data_hash=None):
    cache_dir = "cache"
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    if data_hash:
        return os.path.join(cache_dir, f"{module_name}_{data_hash}.json")
    return os.path.join(cache_dir, f"{module_name}_cache.json")

def is_cache_valid(cache_path, ttl=None):
    if not os.path.exists(cache_path):
        return False
    try:
        print(f"loading {cache_path}")
        with open(cache_path, "r") as cache_file:
            cache_data = json.load(cache_file)
        if ttl is None:
            return True
        cache_time = datetime.fromtimestamp(cache_data['timestamp'])
        return datetime.now() - cache_time < timedelta(seconds=ttl)
    except Exception as e:
        print(f"is_cache_valid exception: {e}")
        return False

def process_module(module_name, config):
    logging.info(f"Processing module: {module_name}")
    
    if module_name == 'crypto_price.yml':
        cache_path = get_cache_path(module_name)
        ttl = config.get('cache_ttl', 3600)  # Default TTL of 1 hour if not specified

        if is_cache_valid(cache_path, ttl):
            with open(cache_path, 'r') as cache_file:
                return json.load(cache_file)['data']

        crypto_ids = config.get('crypto_ids', [])
        currency = config.get('currency', 'usd')
        options = config.get('options', {})

        # Fetch crypto data with specified options
        crypto_data = fetch_crypto_data(
            crypto_ids,
            vs_currency=currency,
            order='market_cap_desc',
            per_page=options.get('max_coins', 100),
            price_change_percentage='24h' if options.get('include_24h_change') else None
        )

        # Filter and format the data based on options
        formatted_data = []
        for crypto in crypto_data:
            crypto_info = {
                'name': crypto['name'],
                'current_price': crypto['current_price'],
                'symbol': crypto['symbol']
            }
            if options.get('include_24h_change'):
                crypto_info['price_change_24h'] = crypto['price_change_percentage_24h']
            if options.get('include_market_cap'):
                crypto_info['market_cap'] = crypto['market_cap']
            formatted_data.append(crypto_info)

        # Cache the new data
        cache_data = {
            'timestamp': time.time(),
            'data': formatted_data
        }
        with open(cache_path, 'w') as cache_file:
            json.dump(cache_data, cache_file)

        return formatted_data

    elif module_name == 'frontpage.yml':
        newspapers = config.get('newspapers', [])
        frontpages = {}
        for prefix in newspapers:
            result = fetch_paper(prefix)
            if result:
                with open(result, 'rb') as f:
                    frontpage_data = f.read()

                # Generate a hash of the image data
                data_hash = hashlib.md5(frontpage_data).hexdigest()
                cache_path = get_cache_path(prefix, data_hash)

                # Check if we have a cached analysis
                if is_cache_valid(cache_path):
                    with open(cache_path, 'r') as cache_file:
                        analysis = json.load(cache_file)
                else:
                    # If not cached, call Anthropic API
                    prompt = """Please analyze this newspaper front page and provide a summary of the main headlines and stories. Focus on the most prominent news items and their significance. Format your response using HTML tags as follows:

<h4>Top Story</h4>
<p>[Brief summary of the most prominent story, its significance, and any key details]</p>

<h4>Other Major Headlines</h4>
<ul>
  <li><strong>[Headline 1]:</strong> [Brief summary]</li>
  <li><strong>[Headline 2]:</strong> [Brief summary]</li>
  <li><strong>[Headline 3]:</strong> [Brief summary]</li>
</ul>

<h4>Notable Trends or Themes</h4>
<p>[Brief analysis of any overarching themes or trends visible in today's news]</p>

Please ensure your response is concise, informative, and uses proper HTML formatting. The HTML should be valid and ready to be inserted directly into an email template."""
                    response = generate_anthropic_response(
                        [{'role': 'user',
                          'content': [
                            {
                              'type': 'image',
                              'source': {
                                'type': 'base64',
                                'media_type': 'image/jpeg',
                                'data': base64.b64encode(frontpage_data).decode('ascii'),
                              }
                            },
                            {
                              'type': 'text',
                              'text': prompt,
                            },
                          ]
                        }])
                    
                    analysis = response[0].text
                    
                    # Cache the analysis
                    with open(cache_path, 'w') as cache_file:
                        json.dump(analysis, cache_file)
                
                frontpages[prefix] = {
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'analysis': analysis
                }
        
        return frontpages

    elif module_name == 'weather.yml':
        cache_path = get_cache_path(module_name)
        ttl = config.get('cache_duration', 3600)  # Default TTL of 1 hour if not specified

        if is_cache_valid(cache_path, ttl):
            with open(cache_path, 'r') as cache_file:
                return json.load(cache_file)['data']

        location = config.get('location', {})
        lat = location.get('latitude', 37.3193)  # Default to Cupertino if not specified
        lon = location.get('longitude', -122.0293)
        weather_url = f"https://forecast.weather.gov/MapClick.php?lat={lat}&lon={lon}"
        
        weather_text = get_url(weather_url)
        weather_results = extract_weather_info(weather_text)
        
        # Add location name to the results if provided
        if 'name' in location:
            weather_results['location_name'] = location['name']

        options = config.get('options', {})
        if not options.get('include_top_news', True):
            weather_results.pop('top_news', None)
        if not options.get('include_hazards', True):
            weather_results.pop('hazards', None)
        
        forecast_days = options.get('forecast_days', 5)
        weather_results['detailed_forecast'] = dict(list(weather_results['detailed_forecast'].items())[:forecast_days*2])

        # Cache the new data
        cache_data = {
            'timestamp': time.time(),
            'data': weather_results
        }
        with open(cache_path, 'w') as cache_file:
            json.dump(cache_data, cache_file)

        return weather_results

    elif module_name == 'word_of_day.yml':
        cache_path = get_cache_path(module_name)
        ttl = config.get('cache_duration', 86400)  # Default TTL of 24 hours

        if is_cache_valid(cache_path, ttl):
            with open(cache_path, 'r') as cache_file:
                return json.load(cache_file)['data']

        api_url = config['api']['url']
        
        # Get a random word from a predefined list or another source
        word = random.choice(['serendipity', 'ephemeral', 'eloquent', 'resilient', 'innovative'])
        
        response = requests.get(f"{api_url}{word}")
        if response.status_code == 200:
            data = response.json()[0]
            word_data = {
                'word': data['word'],
                'definition': data['meanings'][0]['definitions'][0]['definition'],
                'example': data['meanings'][0]['definitions'][0].get('example', 'N/A')
            }
            
            # Cache the new data
            cache_data = {
                'timestamp': time.time(),
                'data': word_data
            }
            with open(cache_path, 'w') as cache_file:
                json.dump(cache_data, cache_file)
            
            return word_data
        else:
            logging.error(f"Failed to fetch word of the day: {response.status_code}")
            return None

    elif module_name == 'daily_quote.yml':
        cache_path = get_cache_path(module_name)
        ttl = config.get('cache_duration', 86400)  # Default TTL of 24 hours

        if is_cache_valid(cache_path, ttl):
            with open(cache_path, 'r') as cache_file:
                return json.load(cache_file)['data']

        api_url = config['api']['url']
        
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            quote_data = {
                'content': data['content'],
                'author': data['author']
            }
            
            # Cache the new data
            cache_data = {
                'timestamp': time.time(),
                'data': quote_data
            }
            with open(cache_path, 'w') as cache_file:
                json.dump(cache_data, cache_file)
            
            return quote_data
        else:
            logging.error(f"Failed to fetch daily quote: {response.status_code}")
            return None

    elif module_name == 'stock_market.yml':
        cache_path = get_cache_path(module_name)
        ttl = config.get('cache_duration', 3600)  # Default TTL of 1 hour

        if is_cache_valid(cache_path, ttl):
            with open(cache_path, 'r') as cache_file:
                return json.load(cache_file)['data']

        api_url = config['api']['url']
        api_key = os.environ["ALPHA_VANTAGE_API_KEY"]
        symbols = config.get('symbols', ['^GSPC', '^DJI', '^IXIC'])
        
        stock_data = {}
        for symbol in symbols:
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': symbol,
                'apikey': api_key
            }
            response = requests.get(api_url, params=params)
            if response.status_code == 200:
                print(response.json())
                data = response.json()['Global Quote']
                stock_data[symbol] = {
                    'price': float(data['05. price']),
                    'change': float(data['09. change']),
                    'change_percent': data['10. change percent']
                }
            else:
                logging.error(f"Failed to fetch stock data for {symbol}: {response.status_code}")
        
        if stock_data:
            # Cache the new data
            cache_data = {
                'timestamp': time.time(),
                'data': stock_data
            }
            with open(cache_path, 'w') as cache_file:
                json.dump(cache_data, cache_file)
            
            return stock_data
        else:
            logging.error("Failed to fetch any stock market data")
            return None

    else:
        # For other modules, you might use Claude to process the data
        module_data = f"Data for {module_name}: {config}"
        prompt = f"Please summarize the following data for the daily brief: {module_data}"
        return generate_anthropic_response([{"role": "user", "content": prompt}])

def generate_report(modules):
    report_data = {}
    for module in modules:
        config = load_module(module)
        if config:
            module_data = process_module(module, config)
            report_data[module] = module_data
    return report_data

def create_email_body(report_data):
    template = template_env.get_template('email_template.html')
    try:
        current_datetime = datetime.now()
        context = {
            'date': current_datetime.strftime('%Y-%m-%d'),
            'time': current_datetime.strftime('%H:%M:%S'),
            'report_data': report_data
        }
        email_body = template.render(context)
        logging.info(f"Email body created, length: {len(email_body)}")
        logging.debug(f"Email body preview: {email_body[:500]}...")  # Log the first 500 characters
        return email_body
    except Exception as e:
        logging.error(f"Failed to create email body: {str(e)}")
        logging.debug(f"report_data: {report_data}")  # Log the entire report_data for debugging
        raise

def generate_overview(report_data):
    # Prepare a summary of the report data
    summary = "Today's report includes:\n"

    if 'weather.yml' in report_data:
        weather_data = report_data['weather.yml']
        location = weather_data.get('location', 'the specified location')
        summary += f"- Weather information for {location}\n"
        
        if 'hazards' in weather_data and weather_data['hazards']:
            hazards = [re.sub('<[^<]+?>', '', hazard) for hazard in weather_data['hazards']]
            summary += f"  - Hazardous conditions: {', '.join(hazards)}\n"
        
        if 'detailed_forecast' in weather_data:
            today_forecast = next(iter(weather_data['detailed_forecast'].values()), "No forecast available")
            today_forecast = re.sub('<[^<]+?>', '', today_forecast)  # Remove HTML tags
            summary += f"  - Today's forecast: {today_forecast}\n"
    
        weather_data = report_data['weather.yml']
        location = weather_data.get('location', 'the specified location')
        summary += f"- Weather information for {location}\n"
        
        if 'hazards' in weather_data and weather_data['hazards']:
            hazards = [re.sub('<[^<]+?>', '', hazard) for hazard in weather_data['hazards']]
            summary += f"  - Hazardous conditions: {', '.join(hazards)}\n"
        
        if 'detailed_forecast' in weather_data:
            today_forecast = next(iter(weather_data['detailed_forecast'].values()), "No forecast available")
            today_forecast = re.sub('<[^<]+?>', '', today_forecast)  # Remove HTML tags
            summary += f"  - Today's forecast: {today_forecast}\n"
    if 'crypto_price.yml' in report_data:
        crypto_summary = ", ".join([f"{c['name']}: ${c['current_price']:.2f}" for c in report_data['crypto_price.yml'][:3]])
        summary += f"- Cryptocurrency prices (including {crypto_summary})\n"
    
    if 'frontpage.yml' in report_data:
        newspapers = ", ".join(report_data['frontpage.yml'].keys())
        summary += f"- Front page news analysis from {newspapers}\n"

    if 'stock_market.yml' in report_data:
        stock_data = report_data['stock_market.yml']
        stock_summary = ", ".join([f"{symbol}: {data['change_percent']}" for symbol, data in stock_data.items()])
        summary += f"- Stock market summary ({stock_summary})\n"

    if 'word_of_day.yml' in report_data:
        word_data = report_data['word_of_day.yml']
        summary += f"- Word of the Day: {word_data['word']}\n"

    if 'daily_quote.yml' in report_data:
        quote_data = report_data['daily_quote.yml']
        summary += f"- Daily Quote by {quote_data['author']}\n"

    prompt = f"""Create a concise overview of today's report, highlighting the most important points and any notable trends or connections between different areas. The overview should be engaging and informative, suitable as the opening of a daily brief email for busy professionals.

Start the overview directly with the content, without any introductory phrases like "Here's an overview" or "Today's overview". The tone should be professional and insightful.

Summary of report contents:
{summary}

Format your response in HTML, using appropriate tags for structure and emphasis. The overview should be about 2-3 paragraphs long."""

    overview = generate_anthropic_response([{'role': 'user', 'content': prompt}])
    return overview[0].text

def main():
  try:
    # Load included modules from .env
    included_modules = os.getenv('INCLUDE', '').split(':')
    
    # Generate report data
    report_data = generate_report(included_modules)

    # Generate overview
    overview = generate_overview(report_data)
    
    # Add overview to report data
    report_data['overview'] = overview

    # Create email body
    email_body = create_email_body(report_data)
    
    # Send email
    subject = f"Your Daily Brief for {datetime.now().strftime('%Y-%m-%d')}"
    send_email(subject, email_body)
    logging.info("Daily brief email sent successfully")
  except Exception as e:
    logging.error(f"Failed to generate or send daily brief: {str(e)}")
    logging.error(traceback.format_exc())  # This will print the full stack trace

if __name__ == "__main__":
    main()
