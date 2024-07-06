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


from api import generate_anthropic_response, send_email, fetch_crypto_data, get_url, navigate_and_screenshot
from frontpage import fetch_paper
from weather import extract_weather_info

# Set up logging
parser = argparse.ArgumentParser()
parser.add_argument(
    '--loglevel',
    default='WARNING',
    help='Set the logging level')
args = parser.parse_args()
log_level = args.loglevel.upper()
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s')

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


def get_cache_path(module_name):
    cache_dir = "cache"
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    return os.path.join(cache_dir, f"{module_name}_cache.json")


def is_cache_valid(cache_path, ttl=None, data_hash=None):
    if not os.path.exists(cache_path):
        return False
    try:
        print(f"loading {cache_path}")
        with open(cache_path, "r") as cache_file:
            cache_data = json.load(cache_file)
        if data_hash is not None:
            return data_hash == cache_data['data_hash']
        else:
            if ttl is None:
                return True
            cache_time = datetime.fromtimestamp(cache_data['timestamp'])
            return datetime.now() - cache_time < timedelta(seconds=ttl)
    except Exception as e:
        print(f"is_cache_valid exception: {e}")
        return False


def process_module(module_name, config):
    logging.info(f"Processing module: {module_name}")

    common = {}
    common['include_in_summary'] = config.get('include_in_summary', False)

    if module_name == 'crypto_price.yml':
        cache_path = get_cache_path(module_name)
        # Default TTL of 1 hour if not specified
        ttl = config.get('cache_ttl', 3600)

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
            per_page=options.get(
                'max_coins',
                100),
            price_change_percentage='24h' if options.get('include_24h_change') else None)

        # Filter and format the data based on options
        formatted_data = {}
        crypto_list = []
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
            crypto_list.append(crypto_info)
        formatted_data['crypto_list'] = crypto_list

        # Cache the new data
        formatted_data.update(common)
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
                cache_path = get_cache_path(prefix)

                # Check if we have a cached analysis
                if is_cache_valid(cache_path, data_hash=data_hash):
                    with open(cache_path, 'r') as cache_file:
                        data = json.load(cache_file)
                else:
                    # If not cached, call Anthropic API
                    prompt = """Please analyze this newspaper front page and provide a summary of the main headlines and stories. Focus on the most prominent news items and their significance. Format your response using HTML tags as follows:

<h4>Top Story</h4>
<p>[Brief summary of the <li><strong>most prominent story</strong></li>, its significance, and any key details. Remember to highlight the main story.]</p>

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
                    data = {
                        'data_hash': data_hash,
                        'analysis': analysis,
                    }
                    with open(cache_path, 'w') as cache_file:
                        json.dump(data, cache_file)

                frontpages[prefix] = {
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'analysis': data['analysis']
                }

        frontpages.update(common)
        return frontpages

    elif module_name == 'weather.yml':
        cache_path = get_cache_path(module_name)
        # Default TTL of 1 hour if not specified
        ttl = config.get('cache_duration', 3600)

        if is_cache_valid(cache_path, ttl):
            with open(cache_path, 'r') as cache_file:
                return json.load(cache_file)['data']

        location = config.get('location', {})
        # Default to Cupertino if not specified
        lat = location.get('latitude', 37.3193)
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
        weather_results['detailed_forecast'] = dict(
            list(weather_results['detailed_forecast'].items())[:forecast_days * 2])

        # Cache the new data
        weather_results.update(common)

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
        word = random.choice(
            ['serendipity', 'ephemeral', 'eloquent', 'resilient', 'innovative'])

        response = requests.get(f"{api_url}{word}")
        if response.status_code == 200:
            data = response.json()[0]
            word_data = {
                'word': data['word'],
                'definition': data['meanings'][0]['definitions'][0]['definition'],
                'example': data['meanings'][0]['definitions'][0].get(
                    'example',
                    'N/A')}

            # Cache the new data
            cache_data = {
                'timestamp': time.time(),
                'data': word_data
            }
            with open(cache_path, 'w') as cache_file:
                json.dump(cache_data, cache_file)

            word_data.update(common)
            return word_data
        else:
            logging.error(
                f"Failed to fetch word of the day: {response.status_code}")
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
            logging.error(
                f"Failed to fetch daily quote: {response.status_code}")
            return None

    elif module_name == 'traffic_analyzer.yml':
        options = config.get('options', {})

        if "days_to_run" in options:
            days_to_run = options["days_to_run"]
            dow = datetime.now().weekday()
            if dow not in days_to_run:
                logging.info(f"dow: {dow} not in days_to_run: {days_to_run}")
                return None

        cache_path = get_cache_path(module_name)
        ttl = config.get('cache_duration', 1800)  # Default TTL of 30 minutes

        if is_cache_valid(cache_path, ttl):
            with open(cache_path, 'r') as cache_file:
                return json.load(cache_file)['data']

        maps_url = config['maps_url']
        route_description = config['route_description']
        screenshot_config = config['screenshot']

        # Take screenshot
        screenshot_path = screenshot_config['filename']
        navigate_and_screenshot(
            maps_url,
            screenshot_path,
            screenshot_config['width'],
            screenshot_config['height'])

        # Analyze screenshot with Claude
        with open(screenshot_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('ascii')

        prompt = f"""You will be analyzing a traffic map based on a provided description. Your task is to provide a concise summary of the current traffic conditions, estimated travel time, and any notable delays or incidents.

<route_description>
{route_description}
</route_description>

Here's how to proceed:

1. Analyze the information provided in the image description. Pay attention to:
   - Overall traffic flow
   - Areas of congestion
   - Reported incidents or accidents
   - Estimated travel times for major routes

2. Formulate a concise summary of the traffic conditions. Your summary should include:
   - A general overview of the traffic situation
   - Specific areas experiencing heavy traffic or delays
   - Any notable incidents or accidents affecting traffic flow
   - Estimated travel times for key routes, if available

3. Format your response in HTML. Use appropriate HTML tags to structure your summary. For example:
   - Use <h2> for main section headings
   - Use <p> for paragraphs
   - Use <ul> or <ol> for lists of incidents or affected areas
   - Use <strong> to emphasize important information

4. Your response should be informative and easy to read. Focus on providing actionable information for drivers.

5. Do not describe the image itself or mention that you're analyzing an image description. Present the information as if you're a traffic reporter providing real-time updates.

Remember to provide a concise yet comprehensive summary of the traffic conditions based solely on the information given in the image description."""

        response = generate_anthropic_response(
            [{'role': 'user',
              'content': [
                  {
                      'type': 'image',
                      'source': {
                          'type': 'base64',
                          'media_type': 'image/png',
                          'data': image_data,
                      }
                  },
                  {
                      'type': 'text',
                      'text': prompt,
                  },
              ]
              }])

        traffic_analysis = response[0].text

        # Cache the analysis
        data = {
            'analysis': traffic_analysis,
            'maps_url': maps_url
        }
        data.update(common)
        cache_data = {
            'timestamp': time.time(),
            'data': data,
        }
        with open(cache_path, 'w') as cache_file:
            json.dump(cache_data, cache_file)

        return data

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
                logging.error(
                    f"Failed to fetch stock data for {symbol}: {response.status_code}")

        if stock_data:
            # Cache the new data
            cache_data = {
                'timestamp': time.time(),
                'data': stock_data
            }
            with open(cache_path, 'w') as cache_file:
                json.dump(cache_data, cache_file)

            stock_data.update(common)
            return stock_data
        else:
            logging.error("Failed to fetch any stock market data")
            return None

    else:
        # For other modules, you might use Claude to process the data
        module_data = f"Data for {module_name}: {config}"
        prompt = f"Please summarize the following data for the daily brief: {module_data}"
        response = generate_anthropic_response(
            [{"role": "user", "content": prompt}])
        data = {'text': response[0].text}
        data.update(common)
        return data


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
            'date': current_datetime.strftime('%A, %b %d, %Y'),
            'time': current_datetime.strftime('%H:%M:%S'),
            'report_data': report_data
        }
        email_body = template.render(context)
        logging.info(f"Email body created, length: {len(email_body)}")
        # Log the first 500 characters
        logging.debug(f"Email body preview: {email_body[:500]}...")
        return email_body
    except Exception as e:
        logging.error(f"Failed to create email body: {str(e)}")
        # Log the entire report_data for debugging
        logging.debug(f"report_data: {report_data}")
        raise


def generate_overview(report_data):
    # Prepare a summary of the report data
    summary = "Today's report includes:\n"

    for config in report_data:
        if report_data[config] is None:
            continue
        if 'include_in_summary' not in report_data[config] or not report_data[config]['include_in_summary']:
            continue

        if config == 'weather.yml':
            weather_data = report_data['weather.yml']
            location = weather_data.get(
                'location_name', 'the specified location')
            summary += f"- Weather information for {location}\n"

            if 'hazards' in weather_data and weather_data['hazards']:
                hazards = [re.sub('<[^<]+?>', '', hazard)
                           for hazard in weather_data['hazards']]
                summary += f"  - Hazardous conditions: {', '.join(hazards)}\n"

            if 'detailed_forecast' in weather_data:
                today_forecast = next(
                    iter(
                        weather_data['detailed_forecast'].values()),
                    "No forecast available")
                today_forecast = re.sub(
                    '<[^<]+?>', '', today_forecast)  # Remove HTML tags
                summary += f"  - Today's forecast: {today_forecast}\n"
        elif config == 'crypto_price.yml':
            crypto_summary = ", ".join(
                [f"{c['name']}: ${c['current_price']:.2f} price_change_24h: {c['price_change_24h']}" for c in report_data['crypto_price.yml']['crypto_list']])
            summary += f"- Cryptocurrency prices (including {crypto_summary})\n"
        elif config == 'frontpage.yml':
            newspapers = ", ".join([paper for paper in report_data['frontpage.yml'].keys(
            ) if paper != 'include_in_summary'])
            summary += f"- Front page news analysis from {newspapers}\n"
            for paper in report_data['frontpage.yml']:
                if paper == 'include_in_summary':
                    continue
                summary += f"  - {paper}: {report_data['frontpage.yml'][paper]}\n"
        elif config == 'stock_market.yml':
            stock_data = report_data['stock_market.yml']
            stock_summary = ", ".join(
                [f"{symbol}: {data['change_percent']}" for symbol, data in stock_data.items()])
            summary += f"- Stock market summary ({stock_summary})\n"
        elif config == 'word_of_day.yml':
            word_data = report_data['word_of_day.yml']
            summary += f"- Word of the Day: {word_data['word']}\n"
        elif config == 'daily_quote.yml':
            quote_data = report_data['daily_quote.yml']
            summary += f"- Daily Quote by {quote_data['author']}\n"
        elif config == 'traffic_analyzer.yml':
            traffic_data = report_data['traffic_analyzer.yml']
            summary += f"- Traffic analysis {traffic_data['analysis']}\n"
        else:
            data = report_data[config]
            summary += f"- Unnamed data {data}\n"

    prompt = f"""Create a concise overview of today's report, highlighting the most important points and any notable trends. The overview should be engaging, informative, and action-oriented, suitable as the opening of a daily brief email for busy professionals.

Start the overview directly with the content, without any introductory phrases. The tone should be professional and insightful. Focus on providing key takeaways that the reader can use to inform their day.

Limit the overview to 1-3 paragraphs. Avoid broad generalizations or philosophical musings about the interconnectedness of events. Instead, concentrate on specific, important information and its potential impact on the reader's day or decisions.

Summary of report contents:
{summary}

Format your response in HTML, using appropriate tags for structure and emphasis."""

    logging.debug(f"Prompt being sent: {prompt}")

    overview = generate_anthropic_response(
        [{'role': 'user', 'content': prompt}])
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
        formatted_date = datetime.now().strftime('%A, %b %d, %Y')
        subject = f"Your Daily Brief for {formatted_date}"
        send_email(subject, email_body)
        with open('body.html', 'w') as f:
            f.write(email_body)
        logging.info("Daily brief email sent successfully")
    except Exception as e:
        logging.error(f"Failed to generate or send daily brief: {str(e)}")
        # This will print the full stack trace
        logging.error(traceback.format_exc())


if __name__ == "__main__":
    main()
