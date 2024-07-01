import anthropic
import argparse
import http.client
import logging
import html2text
import requests
import re
import json
import os
from retrying import retry
from playwright.sync_api import sync_playwright

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
load_dotenv()
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Set up logging
parser = argparse.ArgumentParser()
parser.add_argument('--loglevel', default='WARNING', help='Set the logging level')
args = parser.parse_args()
log_level = args.loglevel.upper()
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')


@retry(stop_max_attempt_number=3, wait_exponential_multiplier=100, wait_exponential_max=1000)
# Define a decorator to handle retrying on specific exceptions
def generate_anthropic_response(messages, temperature=0.0, max_tokens=4096, model="claude-3-5-sonnet-20240620"):
  try:
    response = anthropic_client.messages.create(
      model=model,
      max_tokens=max_tokens,
      temperature=temperature,
      messages=messages)
    return response.content
  except Exception as e:
    print(f"Unexpected error: {e}")
    raise

def navigate(url):
    try:
      with sync_playwright() as p:
          browser = p.firefox.launch()
          page = browser.new_page()
          page.goto(url)
          page.wait_for_load_state()
          page.wait_for_timeout(5000)
          text = page.content()
          return text.replace("<|endoftext|>", "<endoftext>")
      return None
    except Exception as e:
      return str(e)

def navigate_and_screenshot(url, screenshot_path="screenshot.png", width=1280, height=720):
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch()
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.goto(url)
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(5000)  # Optional: Adjust the timeout as needed
            page.screenshot(path=screenshot_path)
            text = page.content()
            browser.close()
            return text.replace("", "<endoftext>")
    except Exception as e:
        return str(e)

def get_url(url):
    html = navigate(url)
    if html is None: return None
    h = html2text.HTML2Text()
    return h.handle(html)

def send_email(subject, body):
    sender_email = os.environ["SENDER_EMAIL"]
    receiver_email = os.environ["RECEIVER_EMAIL"]
    password = os.environ["SMTP_PASSWORD"]
    smtp_server = os.environ["SMTP_SERVER"]
    smtp_port = int(os.environ["SMTP_PORT"])

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    # Attach body to the email
    message.attach(MIMEText(body, "html"))
  
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, password)
            server.send_message(message)
            logging.info("Email sent successfully")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        # Print the email body for debugging
        logging.debug(f"Email body: {body}")
        raise

def fetch_crypto_data(crypto_ids, vs_currency='usd', order='market_cap_desc', per_page=100, price_change_percentage='24h'):
    base_url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": vs_currency,
        "ids": ",".join(crypto_ids),
        "order": order,
        "per_page": per_page,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": price_change_percentage
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        return response.json()
    except requests.RequestException as e:
        print(f"An error occurred while fetching crypto data: {e}")
        return None
