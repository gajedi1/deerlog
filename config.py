import os

class Config:
    # Flask settings
    SECRET_KEY = 'dev-key-123'  # Change this to a secure secret key in production
    PASSWORD = 'dss'  # Default password
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    
    # Application settings
    INSTALLS_LOG = os.path.join(LOG_DIR, 'installs_log.csv')
    
    # Ensure logs directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

# Use development config by default
config = DevelopmentConfig()
