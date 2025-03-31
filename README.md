# Reddit Buyer Intent Dashboard

A web application for monitoring Reddit for buyer intent and generating personalized responses.

## Features

- 🔍 **Intelligent Monitoring**: Automatically scans Reddit posts to detect purchase intent
- 🤖 **AI-Powered Response Generation**: Creates personalized, contextual responses to potential buyers
- 📊 **Analytics Dashboard**: Tracks engagement and conversion metrics
- 🔑 **Multi-Provider Authentication**: Secure login via email/password, Google, or Reddit
- 🔄 **OAuth Integration**: Easy connection of Reddit accounts without API credentials
- ☁️ **Cloud Deployment**: Ready for Google Cloud Platform with CI/CD pipeline

## Setup (Windows Quick Start)

### Quick Setup

The easiest way to get started on Windows is to:

1. Download this repository
2. Run `setup.bat` by double-clicking it
3. Edit the `.env` file with your credentials (this is created from `.env.example`)
4. Run `start.bat` to launch the application

### Manual Setup

### Prerequisites

- Python 3.8 or higher
- SQLite (default) or other database supported by SQLAlchemy
- PRAW (Python Reddit API Wrapper) for Reddit integration

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/reddit-buyer-intent.git
   cd reddit-buyer-intent
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   ```

3. Activate the virtual environment:
   ```
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
   
   If you encounter issues with PRAW installation, install it directly:
   ```
   pip install praw
   ```

5. Copy the example environment file:
   ```
   # Windows
   copy .env.example .env
   
   # macOS/Linux
   cp .env.example .env
   ```

6. **IMPORTANT**: Edit the `.env` file with your actual credentials:
   - `.env.example` is just a template with placeholder values
   - Your actual credentials need to be added to the `.env` file
   - Never commit your real `.env` file to version control

### Obtaining Reddit OAuth Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create app" or "Create another app" at the bottom
3. Fill in the details:
   - Name: Reddit Buyer Intent Dashboard
   - App type: Web app
   - Redirect URI: http://localhost:8000/auth/reddit/callback
   - Description: Optional
4. Click "Create app"
5. Copy the client ID (under your app name) and client secret to your `.env` file

### Initializing the Database

Run the database initialization script:
```
python init_db.py
```

## Running the Application

Start the dashboard:
```
python run.py
```

The application will be available at http://localhost:8000

## Connecting Your Reddit Account

1. Create an account or sign in to the dashboard
2. Navigate to the Account Management page
3. Click the "Connect Reddit Account" button
4. Authorize the application on Reddit
5. Your Reddit account will now be connected and available for monitoring

## Deployment

### Google Cloud Platform

1. Install Google Cloud SDK
2. Authenticate with GCP:
   ```
   gcloud auth login
   ```
3. Set your project:
   ```
   gcloud config set project your-project-id
   ```
4. Deploy to App Engine:
   ```
   gcloud app deploy
   ```

## Troubleshooting

### Common Issues

- **ModuleNotFoundError: No module named 'praw'**: PRAW is not installed. Run `pip install praw` to fix.
- **Missing modules**: Make sure you've activated your virtual environment before running the app.
- **OAuth errors**: Verify your Reddit credentials in the `.env` file are correct and the redirect URIs match.

## Development

### Project Structure

- `app.py`: Core application logic for Reddit monitoring
- `dashboard.py`: FastAPI web dashboard
- `reddit_scraper.py`: Reddit API integration
- `intent_detector.py`: AI-based buyer intent detection
- `response_generator.py`: Personalized response generation
- `models.py`: Database models
- `auth.py` & `auth_routes.py`: Authentication system
- `account_routes.py`: Account management
- `templates/`: HTML templates
- `static/`: CSS, JavaScript, and other assets

## License

[MIT License](LICENSE) 