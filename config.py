import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-123'
    PASSWORD = os.environ.get('PASSWORD', 'dss')  # Default password is 'dss'
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    
    # Application settings
    INSTALLS_LOG = os.path.join(LOG_DIR, 'installs_log.csv')
    
    # Ensure logs directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    DEBUG = False
    
# Default to development config
config = DevelopmentConfig()

# For production, set RENDER=True in environment variables
if os.environ.get('RENDER') == 'true':
    config = ProductionConfig()
