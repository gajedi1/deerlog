import os
import logging
import json
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response
from werkzeug.exceptions import HTTPException
from google_play_scraper import search, app as get_app_details

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Initialize Flask app
flask_app = Flask(__name__)

# Configure logging
log_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
log_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
log_handler.setLevel(logging.INFO)
flask_app.logger.addHandler(log_handler)
flask_app.logger.setLevel(logging.INFO)
flask_app.logger.info('App startup')

def log_search(app_name, result):
    """Log search attempts and their results"""
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = {
        'timestamp': timestamp,
        'query': app_name,
        'result': result
    }
    flask_app.logger.info(f"Search: {app_name} - Result: {result.get('title', 'Error')}")
    return log_entry

def get_app_data(app_name):
    try:
        if not app_name or not isinstance(app_name, str):
            raise ValueError("Invalid app name provided")
            
        flask_app.logger.info(f"Searching for app: {app_name}")
        print(f"Searching for '{app_name}' on Google Play Store...")
        
        try:
            # Search with more results to find better matches
            results = search(
                app_name,
                lang='en',
                country='us',
                n_hits=5  # Get more results to find the best match
            )
        except Exception as e:
            flask_app.logger.error(f"Search error for '{app_name}': {str(e)}")
            return {
                "error": f"Failed to search for app: {str(e)}",
                "title": app_name,
                "developer": "N/A",
                "installs": "N/A",
                "realInstalls": None,
                "score": "N/A",
                "ratings": 0
            }
        
        if not results:
            return {
                "error": f"No results found for '{app_name}'.",
                "title": app_name,
                "developer": "N/A",
                "installs": "N/A",
                "realInstalls": None,
                "score": "N/A",
                "ratings": 0
            }
        
        try:
            # Find the best matching app by title similarity
            best_match = None
            best_score = -1
            app_name_lower = app_name.lower()
            
            for app in results:
                title = str(app.get('title', '')).strip()
                if not title:
                    continue
                    
                title_lower = title.lower()
                
                # Calculate a simple matching score
                score = 0
                if app_name_lower == title_lower:
                    score = 100  # Exact match
                elif app_name_lower in title_lower:
                    score = 80 + (len(app_name_lower) / len(title_lower)) * 10  # Partial match
                
                # If this is a better match, update best_match
                if score > best_score:
                    best_score = score
                    best_match = app
            
            if not best_match:
                best_match = results[0]  # Fallback to first result if no good match found
                
            app_id = best_match.get('appId')
            if not app_id:
                raise ValueError("No app ID found in search results")
                
            app_title = best_match.get('title', app_name)
            print(f"Found best matching app: {app_title} (ID: {app_id})")
            
            try:
                app_details = get_app_details(
                    app_id,
                    lang='en',
                    country='us'
                )
                
                installs = app_details.get('installs', 'Not available')
                real_installs = app_details.get('realInstalls')
                score = app_details.get('score', 'N/A')
                ratings = app_details.get('ratings', 0) or 0
                
                return {
                    "title": app_details.get('title', app_title),
                    "developer": app_details.get('developer', 'N/A'),
                    "installs": installs,
                    "realInstalls": real_installs,
                    "score": score,
                    "ratings": ratings
                }
                
            except Exception as e:
                error_msg = f"Error getting app details: {str(e)}"
                flask_app.logger.error(error_msg)
                return {
                    "error": error_msg,
                    "title": app_title,
                    "developer": best_match.get('developer', 'N/A'),
                    "installs": "N/A",
                    "realInstalls": None,
                    "score": "N/A",
                    "ratings": 0
                }
                
        except Exception as e:
            error_msg = f"Error processing search results: {str(e)}"
            flask_app.logger.error(error_msg)
            return {
                "error": error_msg,
                "title": app_name,
                "developer": "N/A",
                "installs": "N/A",
                "realInstalls": None,
                "score": "N/A",
                "ratings": 0
            }
            
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        flask_app.logger.error(error_msg)
        return {
            "error": error_msg,
            "title": app_name if isinstance(app_name, str) else "Unknown App",
            "developer": "N/A",
            "installs": "N/A",
            "realInstalls": None,
            "score": "N/A",
            "ratings": 0
        }

@flask_app.route('/')
def index():
    return render_template('index.html')

@flask_app.route('/search', methods=['POST'])
@flask_app.route('/logs')
def view_logs():
    log_dir = os.path.join('logs', 'daily')
    log_files = []
    
    # Get all daily log files
    if os.path.exists(log_dir):
        log_files = sorted(
            [f for f in os.listdir(log_dir) if f.endswith('.json')],
            reverse=True
        )
    
    # Get app logs
    app_logs = []
    try:
        with open('logs/app.log', 'r') as f:
            app_logs = f.readlines()
    except FileNotFoundError:
        pass
    
    # Get daily log data
    daily_logs = {}
    for log_file in log_files:
        try:
            date_str = log_file.replace('.json', '')
            with open(os.path.join(log_dir, log_file), 'r') as f:
                daily_logs[date_str] = json.load(f)
        except Exception as e:
            flask_app.logger.error(f"Error reading log file {log_file}: {str(e)}")
    
    return render_template(
        'logs.html',
        app_logs=app_logs,
        daily_logs=daily_logs,
        log_files=log_files
    )

@flask_app.route('/clear_logs', methods=['POST'])
def clear_logs():
    try:
        open('logs/app.log', 'w').close()
        flask_app.logger.info("Logs cleared")
        return jsonify({"status": "success", "message": "Logs cleared"})
    except Exception as e:
        flask_app.logger.error(f"Error clearing logs: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@flask_app.errorhandler(HTTPException)
def handle_http_error(e):
    return jsonify({
        "error": e.description,
        "code": e.code
    }), e.code

@flask_app.errorhandler(Exception)
def handle_generic_error(e):
    flask_app.logger.error(f"Unhandled exception: {str(e)}")
    return jsonify({
        "error": "An internal server error occurred",
        "code": 500
    }), 500

@flask_app.route('/search', methods=['POST'])
def search_app():
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
            
        data = request.get_json()
        if not data or 'app_name' not in data:
            return jsonify({"error": "app_name is required"}), 400
            
        app_name = data['app_name'].strip()
        if not app_name:
            return jsonify({"error": "app_name cannot be empty"}), 400
            
        result = get_app_data(app_name)
        log_search(app_name, result)
        return jsonify(result)
        
    except Exception as e:
        flask_app.logger.error(f"Error in search_app: {str(e)}")
        return jsonify({
            "error": str(e) or "An error occurred while processing your request"
        }), 500

def scheduled_search():
    """Perform a scheduled search for Deerwalk"""
    with flask_app.app_context():
        try:
            flask_app.logger.info("Running scheduled search for 'Deerwalk'")
            result = get_app_data('Deerwalk')
            # Save the result to a daily log file
            log_dir = os.path.join('logs', 'daily')
            os.makedirs(log_dir, exist_ok=True)
            
            today = datetime.now(pytz.timezone('Asia/Kathmandu')).strftime('%Y-%m-%d')
            log_file = os.path.join(log_dir, f'{today}.json')
            
            # Read existing logs if any
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            else:
                logs = []
            
            # Add new log entry
            logs.append({
                'timestamp': datetime.now(pytz.timezone('Asia/Kathmandu')).isoformat(),
                'query': 'Deerwalk',
                'result': result
            })
            
            # Save back to file
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
                
            flask_app.logger.info(f"Saved Deerwalk search results to {log_file}")
            
        except Exception as e:
            flask_app.logger.error(f"Error in scheduled search: {str(e)}")

# Initialize scheduler
scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Kathmandu'))

# Schedule the job to run at 11:00 AM, 3:00 PM, and 6:00 PM Nepal time
scheduled_times = [
    {'id': 'morning_search', 'hour': 11, 'minute': 0, 'name': '11:00 AM'},
    {'id': 'afternoon_search', 'hour': 15, 'minute': 0, 'name': '3:00 PM'},
    {'id': 'evening_search', 'hour': 18, 'minute': 0, 'name': '6:00 PM'}
]

for time_slot in scheduled_times:
    scheduler.add_job(
        scheduled_search,
        CronTrigger(
            hour=time_slot['hour'],
            minute=time_slot['minute'],
            timezone='Asia/Kathmandu'
        ),
        id=time_slot['id'],
        name=f'Run Deerwalk search at {time_slot["name"]} NPT',
        replace_existing=True
    )

# Start the scheduler when the app starts
if not scheduler.running:
    scheduler.start()

# For production with gunicorn
app = flask_app

if __name__ == '__main__':
    # Run the scheduled search immediately for testing
    # Comment this out in production
    # scheduled_search()
    
    flask_app.run(debug=True)
