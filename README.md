# Reddit Buyer Intent Detector

A Python application that monitors Reddit for buyer intent across various industries. The application uses Gemini Pro to analyze Reddit posts and comments, detect purchase intent, and generate personalized responses for potential buyers.

## Features

- **Reddit Scraping**: Monitor multiple subreddits for posts and comments containing buyer intent keywords
- **Intent Analysis**: Use Gemini 2.5 Pro to detect and classify buyer intent (High, Medium, Low)
- **Personalized Responses**: Generate tailored direct messages to engage with potential buyers
- **DM Automation**: Automatically send messages to Reddit users with high buyer intent
- **Dashboard**: Web-based interface to monitor results and manage the application

## Prerequisites

- Python 3.8+
- Reddit API credentials (client ID, client secret, username, password)
- Gemini API key

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd reddit-buyer-intent
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file by copying the example:
   ```
   copy .env.example .env
   ```

4. Edit the `.env` file with your Reddit API credentials and other configuration options:
   ```
   # Reddit API Credentials
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   REDDIT_USERNAME=your_username
   REDDIT_PASSWORD=your_password
   REDDIT_USER_AGENT=RedditBuyerIntentBot/1.0

   # Gemini API Key - already provided
   GEMINI_API_KEY=AIzaSyBX_4_GoOitrlS30Fa-wVscPkuovZ6bdN4

   # Application Settings
   MONITORING_INTERVAL_MINUTES=30
   MAX_POSTS_PER_SUBREDDIT=25
   DM_COOLDOWN_HOURS=24
   ```

## Usage

### Command Line Interface

Run a single monitoring cycle:
```
python app.py --run-once
```

Run with specific parameters:
```
python app.py --run-once --subreddits buildapc technology gadgets --min-intent MEDIUM --min-confidence 0.7
```

Start continuous monitoring:
```
python app.py --monitor --interval 60
```

Send messages to users (use with caution):
```
python app.py --run-once --send-messages
```

### Web Dashboard

Start the web dashboard:
```
python dashboard.py
```

Then open your browser and navigate to:
```
http://localhost:8000
```

## Configuration

You can customize the application by editing the `config.py` file:

- Modify the list of monitored subreddits
- Add or remove buyer intent keywords
- Adjust confidence thresholds and monitoring intervals

## How It Works

1. **Scraping**: The application monitors specified subreddits for posts and comments containing buyer intent keywords.
2. **Analysis**: Gemini 2.5 Pro analyzes the content to detect buyer intent, classifying it as High, Medium, or Low.
3. **Response Generation**: For high-intent users, the application generates personalized direct messages.
4. **DM Automation**: Optionally, the application can automatically send direct messages to users.

## Project Structure

- `app.py`: Main application entry point
- `reddit_scraper.py`: Reddit API interaction and content scraping
- `intent_detector.py`: Buyer intent detection using Gemini
- `response_generator.py`: Personalized response generation
- `config.py`: Application configuration
- `dashboard.py`: Web dashboard for monitoring and control

## Security Considerations

- Store your API credentials securely and never commit them to version control
- Respect Reddit's API usage policies and rate limits
- Use the DM automation feature responsibly to avoid spam

## License

[MIT License](LICENSE)

## Disclaimer

This application is for educational purposes. Always use Reddit's API responsibly and in accordance with their terms of service. 