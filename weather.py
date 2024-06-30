import re
import markdown2

def extract_weather_info(text):
    def escape_regex(text):
        return re.escape(text).replace(r'\ ', ' ')

    weather_info = {}
    
    # Extract top news
    top_news_start = r'\(/bundles/templating/images/top_news/important\.png\)'
    top_news_end = r'\[Read More'
    top_news_pattern = f"{top_news_start}(.*?){top_news_end}"
    top_news_match = re.search(top_news_pattern, text, re.DOTALL | re.IGNORECASE)
    if top_news_match:
        top_news = top_news_match.group(1).strip()
        # Remove any remaining HTML tags
        top_news = re.sub(r'<.*?>', '', top_news)
        # Remove extra whitespace
        top_news = re.sub(r'\s+', ' ', top_news).strip()
        top_news = re.sub(r'\[(.*?)\]\((.*?)\)', lambda match: f'[{match.group(1)}](https://forecast.weather.gov/{match.group(2)})', top_news)
        weather_info['top_news'] = markdown2.markdown(top_news)
        if weather_info['top_news'].startswith('<h1>'): weather_info['top_news'] = weather_info['top_news'][len('<h1>'):]
        if weather_info['top_news'].endswith('</h1>'): weather_info['top_news'] = weather_info['top_news'][:-len('</h1>')]
    
    # Extract hazardous weather conditions
    hazard_start = escape_regex("### Hazardous Weather Conditions")
    hazard_end = escape_regex("Current conditions at")
    hazard_pattern = f"{hazard_start}(.*?){hazard_end}"
    hazard_match = re.search(hazard_pattern, text, re.DOTALL)
    if hazard_match:
        hazards = hazard_match.group(1).strip()
        hazard_items = [h.strip() for h in re.split(r'\*+', hazards) if h.strip()]
        weather_info['hazards'] = []
        for hazard in hazard_items:
            # Fix URLs in the hazard text
            hazard = re.sub(r'\[(.*?)\]\((.*?)\)', lambda match: f'[{match.group(1)}](https://forecast.weather.gov/{match.group(2)})', hazard)
            weather_info['hazards'].append(markdown2.markdown(hazard))
    
    # Extract detailed forecast
    forecast_start = "## Detailed Forecast"
    forecast_end = "## Additional Forecasts and Information"
    forecast_pattern = f"{escape_regex(forecast_start)}(.*?){escape_regex(forecast_end)}"
    forecast_match = re.search(forecast_pattern, text, re.DOTALL)
    
    if forecast_match:
        forecast_text = forecast_match.group(1).strip()
        # Split the forecast into days
        day_forecasts = re.split(r'\*\*(.*?)\*\*', forecast_text)[1:]  # Skip the first empty element
        weather_info['detailed_forecast'] = {}
        for i in range(0, len(day_forecasts), 2):
            day = day_forecasts[i].strip()
            forecast = day_forecasts[i+1].strip() if i+1 < len(day_forecasts) else ""
            weather_info['detailed_forecast'][day] = markdown2.markdown(forecast)
    
    return weather_info
