import os
import logging
import csv
import json
import atexit
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request, jsonify, session, flash, redirect, url_for, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from google_play_scraper import search, app as get_app_details
# Using plain text password instead of hashing
from functools import wraps

# Import configuration
from config import config

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY

# Configure logging
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/playstore_scraper.log',
                                     maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Play Store Scraper startup')

# Default password if not set in config
if not hasattr(config, 'PASSWORD') or not config.PASSWORD:
    config.PASSWORD = 'dss'  # Default password is 'dss'

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Ensure scheduler shuts down properly
atexit.register(lambda: scheduler.shutdown())

def log_installs(app_name, installs_data):
    """Log installs data to CSV"""
    try:
        file_exists = os.path.isfile(INSTALLS_LOG)
        
        with open(config.INSTALLS_LOG, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['timestamp', 'app_name', 'installs', 'real_installs', 'score', 'ratings']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
                
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'app_name': app_name,
                'installs': installs_data.get('installs', 'N/A'),
                'real_installs': installs_data.get('realInstalls', 'N/A'),
                'score': installs_data.get('score', 'N/A'),
                'ratings': installs_data.get('ratings', 'N/A')
            })
            
    except Exception as e:
        app.logger.error(f"Error logging installs: {str(e)}")

def get_app_info(app_name):
    """Fetch app information from Google Play Store"""
    try:
        app.logger.info(f"Searching for app: {app_name}")
        
        # Search for the app
        results = search(app_name, n_hits=1, lang='en', country='us')
        
        if not results:
            app.logger.warning(f"No results found for: {app_name}")
            return {"success": False, "error": "App not found on Google Play Store"}
        
        # Get app ID from search results
        app_id = results[0]['appId']
        app.logger.info(f"Found app ID: {app_id}")
        
        # Get detailed app information
        app_details = get_app_details(
            app_id,
            lang='en',
            country='us'
        )
        
        if not app_details:
            app.logger.error(f"No details found for app ID: {app_id}")
            return {"success": False, "error": "Could not fetch app details"}
        
        # Log the installs data
        log_installs(app_name, app_details)
        
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
                'realInstalls': app_details.get('realInstalls', 0),
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
        app.logger.error(error_msg, exc_info=True)
        return {
            'success': False,
            'error': 'Failed to fetch app data',
            'details': str(e) if app.debug else None
        }

def password_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session or not session['authenticated']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Unexpected error in search: {str(e)}"
        app.logger.error(error_msg, exc_info=True)
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred',
            'details': str(e) if app.debug else None
        }), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == config.PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('view_logs'))
        else:
            flash('Invalid password')
    return '''
        <form method="post">
            <h2>Log in to view logs</h2>
            <p>Password: <input type="password" name="password" required>
            <input type="submit" value="Login">
        </form>
    '''

@app.route('/logs')
@password_required
def view_logs():
    """View all logs"""
    if not os.path.exists(config.INSTALLS_LOG):
        return "No logs found"
        
    # Read the installs log
    with open(config.INSTALLS_LOG, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        logs = list(reader)
    
    return render_template('logs.html', logs=logs)

@app.route('/logs/export')
@password_required
def export_logs():
    """Export real installs data as CSV"""
    if not os.path.exists(config.INSTALLS_LOG):
        return "No logs to export"
        
    # Create a CSV with only real installs and dates
    output = []
    with open(config.INSTALLS_LOG, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            output.append({
                'Date': datetime.fromisoformat(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                'App Name': row['app_name'],
                'Real Installs': row['real_installs']
            })
    
    # Create a temporary CSV file
    import tempfile
    import csv
    
    fd, path = tempfile.mkstemp(suffix='.csv')
    try:
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Date', 'App Name', 'Real Installs'])
            writer.writeheader()
            writer.writerows(output)
            
        return send_from_directory(
            os.path.dirname(path),
            os.path.basename(path),
            as_attachment=True,
            download_name=f'real_installs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    finally:
        # Clean up the temporary file
        try:
            os.unlink(path)
        except:
            pass

@app.route('/logs/delete', methods=['POST'])
@password_required
def delete_logs():
    """Delete all logs"""
    try:
        if os.path.exists(config.INSTALLS_LOG):
            os.remove(config.INSTALLS_LOG)
            flash('Logs deleted successfully')
        else:
            flash('No logs to delete')
    except Exception as e:
        app.logger.error(f"Error deleting logs: {str(e)}")
        flash('Error deleting logs')
    
    return redirect(url_for('view_logs'))

def scheduled_search():
    """Perform a scheduled search for Deerwalk"""
    with app.app_context():
        try:
            app.logger.info("Running scheduled search for 'Deerwalk'")
            result = get_app_info('Deerwalk')
            if 'error' in result:
                app.logger.error(f"Error in scheduled search: {result['error']}")
            else:
                app.logger.info("Scheduled search completed successfully")
        except Exception as e:
            app.logger.error(f"Error in scheduled search: {str(e)}")

# Schedule the job to run every 2 hours
scheduler.add_job(
    scheduled_search,
    IntervalTrigger(hours=2),
    id='deerwalk_search',
    name='Scheduled search for Deerwalk',
    replace_existing=True
)

if __name__ == '__main__':
    # Create initial logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Run the scheduled search immediately on startup
    with app.app_context():
        scheduled_search()
    
    # Start the Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=app.debug)
