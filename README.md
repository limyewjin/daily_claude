# Daily Claude

Daily Claude is a Python-based automation tool designed to generate daily brief emails. It aggregates various data sources including weather forecasts, cryptocurrency prices, front page news analysis, word of the day, daily quotes, and stock market summaries, then sends a concise and informative email report.

## Features

- **Weather Information**: Retrieves weather forecasts, including hazards and detailed forecasts.
- **Cryptocurrency Prices**: Fetches and formats cryptocurrency prices.
- **Front Page News Analysis**: Analyzes front page news from specified newspapers.
- **Stock Market Summaries**: Provides summaries of stock market data.
- **Word of the Day**: Fetches and displays a word of the day with its definition and example usage.
- **Daily Quotes**: Retrieves and displays a daily quote.

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/limyewjin/daily_claude.git
   cd daily_claude
   ```

2. Install the required dependencies:

  ```bash
  pip install -r requirements.txt
  ```

3. Set up environment variables:

  Create a .env file in the root directory and add the required API keys and configurations:

  ```
  ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key
  ANTHROPIC_API_KEY=your_anthropic_api_key
  INCLUDE=crypto_price.yml:frontpage.yml:weather.yml:word_of_day.yml:daily_quote.yml:stock_market.yml
  ```

## Usage
Run the script using Python:

  ```bash
  python main.py --loglevel INFO
  ```

## Configuration
Modules are configured using YAML files located in the modules directory. Each module has its own YAML configuration file. For example, `crypto_price.yml` might look like:

  ```yaml
  crypto_ids:
    - bitcoin
    - ethereum
  currency: usd
  options:
    max_coins: 10
    include_24h_change: true
    include_market_cap: true
  cache_ttl: 3600
  ```

## Contributing
Feel free to submit issues and pull requests. Contributions are welcome!
