from flask import Flask, render_template
from mcstatus import JavaServer
import requests
import pytz
from datetime import datetime, timezone, timedelta
import asyncio
import aiohttp
from RMVtransport import RMVtransport
import re


app = Flask(__name__)

# How often API requests are made, per minute
refreshrate = 5


# Replace with your Minecraft server IP and port
server_ip = "home.rexvizsla.com"
server_port = 25565

# Initialize a variable to store the last time weather and public transport data that was fetched
last_weather_fetch_time = None
last_public_transport_fetch_time = None
last_weather_data = None
last_public_transport_data = None

bus_connection = None
train_connection = None

# Replace with your location's latitude and longitude for accurate weather data
latitude = "50.81018545"
longitude = "8.8108746393"
api_key = "5b83a980a861513faaa8b9c1b65bf368"  # Get an API key from a weather data provider
timezone = pytz.timezone('Europe/Berlin')

# Replace with Station IDs
niederklein_allendorfer_strasse = "3010467"
marburg_hans_meerwein_strasse = "3010044"
alsfeld_bahnhof = "3011190"
marburg_bahnhof = "3010011"
stadtallendorf_bahnhof_bus = "3019875"
stadtallendorf_bahnhof = "3011076"
marburg_faehnrichsweg = "3010135"

def get_online_players():
    try:
        server = JavaServer.lookup(f"{server_ip}:{server_port}")
        status = server.status()
        players = status.players.sample
        online_players = ["No players online"] if players is None else [player.name for player in players]
        return online_players
    except Exception as e:
        return [f"Error: {str(e)}"]


def get_weather():
    global last_weather_data, last_weather_fetch_time
    if last_weather_fetch_time is None or (datetime.now(timezone) - last_weather_fetch_time) >= timedelta(minutes=refreshrate):
        try:
            # Get current time
            time = datetime.now(timezone)
            unix_time = time.timestamp()
            # Use a weather API to get real-world weather data for your location
            weather_api_url = f"https://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={api_key}&units=metric"
            response = requests.get(weather_api_url)
            weather_data = response.json()
            # Extract relevant weather information like temperature, conditions, etc.
            weather_info = """
            Location: {}, {}<br>
            Weather: {} - {}<br>
            Temperature: {:.2f}°C<br>
            Feels Like: {:.2f}°C<br>
            Min Temperature: {:.2f}°C<br>
            Max Temperature: {:.2f}°C<br>
            Pressure: {} hPa<br>
            Humidity: {}%<br>
            Wind Speed: {} m/s<br>
            Wind Direction: {}°<br>
            Cloud Cover: {}%<br>
            """.format(
                weather_data['name'],
                weather_data['sys']['country'],
                weather_data['weather'][0]['main'],
                weather_data['weather'][0]['description'],
                weather_data['main']['temp'],
                weather_data['main']['feels_like'],
                weather_data['main']['temp_min'],
                weather_data['main']['temp_max'],
                weather_data['main']['pressure'],
                weather_data['main']['humidity'],
                weather_data['wind']['speed'],
                weather_data['wind']['deg'],
                weather_data['clouds']['all']
            )
            if 'rain' in weather_data:
                weather_info += "Precipitation (1h): {} mm<br>".format(weather_data['rain']['1h'])
             # Update the last fetch time
            last_weather_fetch_time = datetime.now(timezone)
            last_weather_data = f"<h3>Real-world Weather:</h3><br>{weather_info}"
            return last_weather_data
        except Exception as e:
            return f"Error fetching weather data: {str(e)}"
    else:
        # If less than 5 minutes have passed, return the previous data
        if last_weather_data:
            return last_weather_data
        else:
            return "No weather data available"

def get_rmv(last_public_transport_data,last_public_transport_fetch_time):
    if last_public_transport_fetch_time is None or (datetime.now(timezone) - last_public_transport_fetch_time) >= timedelta(minutes=refreshrate):
        async def main():
            async with aiohttp.ClientSession():
                rmv = RMVtransport()
                try:
                    data = await rmv.get_departures(
                        station_id=marburg_hans_meerwein_strasse,
                        products=["Bus"], 
                        max_journeys=1,
                        direction_id=niederklein_allendorfer_strasse)
                    return str(data)
                except Exception as e:
                    print(str(e))

        async def main(station_id,products,max_journeys,direction_id,time=None):
            async with aiohttp.ClientSession():
                    rmv = RMVtransport()
                    try:
                        if time is None:
                            time = datetime.now(timezone).strftime("%H:%M")
                        data = await rmv.get_departures(
                            station_id=station_id,
                            products=products, 
                            max_journeys=max_journeys,
                            direction_id=direction_id,
                            time=time)
                        return str(data)
                    except Exception as e:
                        print(str(e))

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 1. Anfangsstation, 2. Verkehrsmittel, 3. Anzahl Ausgaben, 4. Fahrtrichtung, 5. (optional) Uhrzeit
        x35_connection = loop.run_until_complete(main(marburg_hans_meerwein_strasse,["Bus"],1,niederklein_allendorfer_strasse)) # X35 Richtung Niederklein
        trains_connection = loop.run_until_complete(main(marburg_bahnhof,["R"],2,stadtallendorf_bahnhof,"16:00")) # RB41 und RE30 um 16 Uhr Richtung Stadtallendorf
        bus_9_connection = loop.run_until_complete(main(marburg_hans_meerwein_strasse,["Bus"],1,marburg_faehnrichsweg)) # Buslinie 9 Richtung Erlenring

        # Update the last fetch time
        last_public_transport_fetch_time = datetime.now(timezone)
        last_public_transport_data = f"{x35_connection},{trains_connection},{bus_9_connection}"
        
        # Pretty print by deleting unnecessary information and fixing some things
        now = datetime.now()
        time_difference_rb41 = round((datetime(now.year, now.month, now.day, 16, 5) - now).total_seconds() / 60)
        time_difference_re30 = round((datetime(now.year, now.month, now.day, 16, 20) - now).total_seconds() / 60)
        pattern = re.compile(r'([a-zA-Z]+: [A-Z0-9]+ \(\d+\))\nRichtung: (.+)\nAbfahrt in (\d+) min.\nAbfahrt (\d+:\d+:\d+) \(\+(\d+)\)')
        matches = re.findall(pattern, last_public_transport_data)
        last_public_transport_data = "<h3>Public Transport Information:</h3><br>"
        for match in matches:
            if "RB: RB41 (12361308001)" and "16:05:00" in match:
                last_public_transport_data += f"{match[0]} Richtung: {match[1]}, Abfahrt in {time_difference_rb41} min. // {match[3]} (+{match[4]})<br><br>"
            elif "RE: RE30 (12513708003)" and "16:20:00" in match:
                last_public_transport_data += f"{match[0]} Richtung: {match[1]}, Abfahrt in {time_difference_re30} min. // {match[3]} (+{match[4]})<br><br>"
            else:
                last_public_transport_data += f"{match[0]} Richtung: {match[1]}, Abfahrt in {int(match[2]) + int(match[4])} min. // {match[3]} (+{match[4]})<br><br>"
        
        return last_public_transport_data,last_public_transport_fetch_time
        
    else:
        # If less than 5 minutes have passed, return the previous data
        if last_public_transport_data:
            return last_public_transport_data
        else:
            return "No public transport data available"
    

@app.route('/')
def index():
    online_players = get_online_players()
    real_world_weather = get_weather()
    public_transport = get_rmv(last_public_transport_data,last_public_transport_fetch_time)[0]
    return "Players Online:<br>" + '<br>'.join(online_players) + "<br><br>" + real_world_weather + "<br><br>" + public_transport

if __name__ == '__main__':
    app.run(debug=True, port=8080, host="0.0.0.0")