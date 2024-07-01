"""
Daily Brief Package

This package provides functionality for generating and sending daily briefing emails.
It includes modules for fetching various types of data (weather, crypto prices, news headlines),
analyzing traffic conditions, and composing email reports.

Main components:
- Data fetching and processing (api, frontpage, weather)
- Report generation and email sending (main)
- Utility functions for web scraping and API interactions

For detailed usage instructions, refer to the project documentation.
"""

# Import main function from main.py
from .main import main, generate_report, create_email_body

# Import functions from api.py
from .api import (
    generate_anthropic_response,
    send_email,
    fetch_crypto_data,
    get_url,
    navigate_and_screenshot
)

# Import function from frontpage.py
from .frontpage import fetch_paper

# Import function from weather.py
from .weather import extract_weather_info

# Version of the package
__version__ = '0.1.0'

# All modules that should be imported when `from package import *` is used
__all__ = [
    'main',
    'generate_report',
    'create_email_body',
    'generate_anthropic_response',
    'send_email',
    'fetch_crypto_data',
    'get_url',
    'navigate_and_screenshot',
    'fetch_paper',
    'extract_weather_info'
]
