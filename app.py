from flask import Flask, render_template, request, jsonify
import os
import logging
import atexit
from logging.handlers import RotatingFileHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from google_play_scraper import search, app as get_app_details

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# File handler for logs
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Play Store Scraper starting up...')

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Ensure scheduler shuts down properly
atexit.register(lambda: scheduler.shutdown())

def log_search_result(app_name, result):
    """Log search results to a file"""
    log_dir = os.path.join('logs', 'searches')
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = os.path.join(log_dir, f'search_{app_name.lower().replace(" ", "_")}_{timestamp}.json')
    
    with open(filename, 'w', encoding='utf-8') as f:
        import json
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'app_name': app_name,
            'result': result
        }, f, indent=2)

def scheduled_search(app_name):
    """Function to be called by the scheduler"""
    with app.app_context():
        try:
            app.logger.info(f"Running scheduled search for: {app_name}")
            result = get_app_info(app_name)
            log_search_result(app_name, result)
            app.logger.info(f"Completed scheduled search for: {app_name}")
        except Exception as e:
            app.logger.error(f"Error in scheduled search for {app_name}: {str(e)}")

def schedule_app_search(app_name, hour=0, minute=0):
    """Schedule a daily search for an app"""
    # Remove any existing jobs for this app
    for job in scheduler.get_jobs():
        if job.id == f'scheduled_search_{app_name}':
            job.remove()
    
    # Add the new job
    trigger = CronTrigger(hour=hour, minute=minute)
    scheduler.add_job(
        scheduled_search,
        trigger=trigger,
        args=[app_name],
        id=f'scheduled_search_{app_name}',
        name=f'Scheduled search for {app_name}',
        replace_existing=True
    )
    
    app.logger.info(f"Scheduled daily search for {app_name} at {hour:02d}:{minute:02d}")

def get_app_info(app_name):
    """Fetch app information from Google Play Store"""
    try:
        logger.info(f"Searching for app: {app_name}")
        
        # Search for the app
        results = search(app_name, n_hits=1, lang='en', country='us')
        
        if not results:
            logger.warning(f"No results found for: {app_name}")
            return {"error": "App not found on Google Play Store"}
        
        # Get app ID from search results
        app_id = results[0]['appId']
        logger.info(f"Found app ID: {app_id}")
        
        # Get detailed app information
        app_details = get_app_details(
            app_id,
            lang='en',
            country='us'
        )
        
        if not app_details:
            logger.error(f"No details found for app ID: {app_id}")
            return {"error": "Could not fetch app details"}
        
        # Format the response
        return {
            'success': True,
            'app': {
                'title': app_details.get('title', ''),
                'appId': app_id,
                'url': f"https://play.google.com/store/apps/details?id={app_id}",
                'icon': app_details.get('icon', ''),
                'developer': app_details.get('developer', ''),
                'score': app_details.get('score', 0),
                'ratings': app_details.get('ratings', 0),
                'installs': app_details.get('installs', ''),
                'price': app_details.get('price', 'Free'),
                'free': app_details.get('free', True),
                'description': app_details.get('description', ''),
                'genre': app_details.get('genre', ''),
                'version': app_details.get('version', ''),
                'updated': app_details.get('updated'),
                'size': app_details.get('size', ''),
                'contentRating': app_details.get('contentRating', '')
            }
        }
        
    except Exception as e:
        error_msg = f"Error fetching app data: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            'success': False,
            'error': 'Failed to fetch app data',
            'details': str(e) if app.debug else None
        }

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_app():
    """Handle app search requests"""
    try:
        data = request.get_json()
        if not data or 'app_name' not in data:
            return jsonify({
                'success': False,
                'error': 'App name is required'
            }), 400
        
        app_name = data['app_name'].strip()
        if not app_name:
            return jsonify({
                'success': False,
                'error': 'App name cannot be empty'
            }), 400
        
        result = get_app_info(app_name)
        
        # Log the search
        logger.info(f"Search completed for: {app_name}")
        
        if 'error' in result:
            return jsonify(result), 200
        
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred',
            'details': str(e) if app.debug else None
        }), 500

# Schedule default searches (example: Deerwalk at 10 AM and 2 PM daily)
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    # Schedule Deerwalk search at 10 AM and 2 PM daily
    schedule_app_search('Deerwalk', hour=10, minute=0)
    schedule_app_search('Deerwalk', hour=14, minute=0)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

    # For development, you can also run a test search immediately
    if app.debug:
        with app.app_context():
            scheduled_search('Deerwalk')
