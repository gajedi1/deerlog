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
        file_exists = os.path.isfile(config.INSTALLS_LOG)
        
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
    """View all logs with search results and application logs"""
    # Process installs log
    daily_logs = {}
    app_logs = []
    
    # Read application logs
    log_file = os.path.join('logs', 'playstore_scraper.log')
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            app_logs = [line.strip() for line in f.readlines() if line.strip()]
    
    # Read and process installs log
    if os.path.exists(config.INSTALLS_LOG):
        with open(config.INSTALLS_LOG, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Parse timestamp and format date
                    timestamp = datetime.fromisoformat(row['timestamp'])
                    date_str = timestamp.strftime('%Y-%m-%d')
                    time_str = timestamp.strftime('%H:%M:%S')
                    
                    # Initialize date entry if not exists
                    if date_str not in daily_logs:
                        daily_logs[date_str] = []
                    
                    # Prepare result data
                    result = {
                        'timestamp': time_str,
                        'result': {
                            'title': row.get('app_name', 'Unknown App'),
                            'developer': 'Unknown',
                            'installs': row.get('installs', 'N/A'),
                            'score': float(row.get('score', 0)) if row.get('score', 'N/A') != 'N/A' else 'N/A',
                            'ratings': int(row.get('ratings', 0)) if row.get('ratings', 'N/A') != 'N/A' else 0,
                            'realInstalls': int(row.get('real_installs', 0)) if row.get('real_installs', 'N/A') != 'N/A' else 0
                        }
                    }
                    
                    # Add to daily logs
                    daily_logs[date_str].append(result)
                except Exception as e:
                    app.logger.error(f"Error processing log entry: {str(e)}")
    
    # Sort daily logs by date (newest first)
    daily_logs = dict(sorted(daily_logs.items(), key=lambda x: x[0], reverse=True))
    
    # Sort each day's searches by time (newest first)
    for date in daily_logs:
        daily_logs[date].sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template('logs.html', 
                         daily_logs=daily_logs, 
                         app_logs=app_logs[-100:])  # Show only last 100 log entries

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

@app.route('/logs/export/real_installs')
@password_required
def export_real_installs():
    """Export all real installs data as CSV"""
    try:
        if not os.path.exists(config.INSTALLS_LOG):
            return "No logs to export", 404
            
        # Read the installs log
        with open(config.INSTALLS_LOG, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
            
        if not data:
            return "No data to export", 404
            
        # Create a CSV in memory
        output = []
        output.append(['Date', 'Time', 'App Name', 'Real Installs', 'Rating', 'Total Ratings'])
        
        for row in data:
            try:
                timestamp = datetime.fromisoformat(row['timestamp'])
                date_str = timestamp.strftime('%Y-%m-%d')
                time_str = timestamp.strftime('%H:%M:%S')
                
                output.append([
                    date_str,
                    time_str,
                    row['app_name'],
                    row.get('real_installs', 'N/A'),
                    row.get('score', 'N/A'),
                    row.get('ratings', 'N/A')
                ])
            except Exception as e:
                app.logger.error(f"Error processing log entry for export: {str(e)}")
        
        # Create a CSV response
        import io
        import csv
        
        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerows(output)
        
        response = app.response_class(
            si.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=real_installs_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error exporting real installs: {str(e)}")
        return f"Error exporting data: {str(e)}", 500

def scheduled_search():
    """Perform a scheduled search for Deerwalk"""
    with app.app_context():
        try:
            app.logger.info("Running scheduled search for 'Deerwalk'")
            result = get_app_info('Deerwalk')
            
            if not result.get('success', False):
                error_msg = result.get('error', 'Unknown error')
                app.logger.error(f"Error in scheduled search: {error_msg}")
                return
                
            # Log successful search
            app.logger.info(f"Successfully fetched data for: {result.get('app', {}).get('title', 'Unknown App')}")
            
            # Log installs information
            if 'app' in result:
                app_data = result['app']
                installs = app_data.get('installs', 'N/A')
                real_installs = app_data.get('realInstalls', 'N/A')
                score = app_data.get('score', 'N/A')
                
                app.logger.info(
                    f"App Stats - Installs: {installs}, "
                    f"Real Installs: {real_installs}, "
                    f"Rating: {score}"
                )
                
        except Exception as e:
            app.logger.error(f"Error in scheduled search: {str(e)}", exc_info=True)
        finally:
            # Log next scheduled run time
            next_run = datetime.now() + timedelta(hours=2)
            app.logger.info(f"Next scheduled search at: {next_run}")

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
