import logging
import schedule
import time
import argparse
import json
from datetime import datetime
import os

from reddit_scraper import RedditScraper
from intent_detector import IntentDetector
from response_generator import ResponseGenerator
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("reddit_buyer_intent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RedditBuyerIntentApp:
    def __init__(self):
        """Initialize the application components."""
        try:
            self.scraper = RedditScraper()
            self.intent_detector = IntentDetector()
            self.response_generator = ResponseGenerator()
            
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            
            logger.info("Application initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize application: {str(e)}")
            raise
    
    def run_monitoring_cycle(self, subreddits=None, keywords=None, limit=None, min_intent="MEDIUM", 
                            min_confidence=0.6, send_messages=False):
        """
        Run a full monitoring cycle: scrape, analyze, generate responses, and optionally send DMs.
        
        Args:
            subreddits (list): List of subreddits to monitor
            keywords (list): List of keywords to filter posts by
            limit (int): Maximum number of posts to retrieve per subreddit
            min_intent (str): Minimum intent category to consider ("HIGH", "MEDIUM", "LOW")
            min_confidence (float): Minimum confidence score for intent detection
            send_messages (bool): Whether to send DMs to users
            
        Returns:
            dict: Results of the monitoring cycle
        """
        start_time = datetime.now()
        logger.info(f"Starting monitoring cycle at {start_time}")
        
        try:
            # 1. Scrape Reddit for potentially relevant posts
            scraped_data = self.scraper.scrape_multiple_subreddits(subreddit_list=subreddits, 
                                                                keywords=keywords, 
                                                                limit=limit)
            logger.info(f"Scraped {len(scraped_data)} posts from {len(subreddits) if subreddits else len(config.MONITORED_SUBREDDITS)} subreddits")
            
            if not scraped_data:
                logger.info("No relevant posts found. Ending cycle.")
                return {
                    "start_time": start_time.isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "posts_scraped": 0,
                    "high_intent_content": 0,
                    "responses_generated": 0,
                    "messages_sent": 0
                }
            
            # 2. Analyze posts and comments for buyer intent
            analyzed_data = self.intent_detector.analyze_reddit_content(scraped_data)
            
            # 3. Filter for high-intent content
            high_intent_content = self.intent_detector.filter_high_intent_content(
                analyzed_data, min_intent=min_intent, min_confidence=min_confidence
            )
            
            logger.info(f"Found {len(high_intent_content)} posts/comments with {min_intent}+ buyer intent")
            
            # 4. Generate responses for high-intent content
            responses = self.response_generator.batch_generate_responses(high_intent_content, min_intent=min_intent)
            
            logger.info(f"Generated {len(responses)} personalized responses")
            
            # 5. Save the data
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save analyzed data
            with open(f"data/analyzed_data_{timestamp}.json", "w") as f:
                json.dump(analyzed_data, f, indent=2)
            
            # Save responses
            with open(f"data/responses_{timestamp}.json", "w") as f:
                json.dump(responses, f, indent=2)
            
            # 6. Optionally send DMs to users
            messages_sent = 0
            if send_messages and responses:
                for response in responses:
                    author = response.get("author")
                    subject = response.get("subject")
                    message = response.get("message")
                    
                    if self.scraper.send_direct_message(author, subject, message):
                        messages_sent += 1
                
                logger.info(f"Sent {messages_sent} direct messages to Reddit users")
            
            # 7. Return results
            end_time = datetime.now()
            results = {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
                "posts_scraped": len(scraped_data),
                "high_intent_content": len(high_intent_content),
                "responses_generated": len(responses),
                "messages_sent": messages_sent
            }
            
            logger.info(f"Monitoring cycle completed in {results['duration_seconds']:.2f} seconds")
            return results
            
        except Exception as e:
            logger.error(f"Error during monitoring cycle: {str(e)}")
            return {
                "start_time": start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "error": str(e)
            }
    
    def schedule_monitoring(self, interval_minutes=None):
        """
        Schedule regular monitoring based on the configured interval.
        
        Args:
            interval_minutes (int): Minutes between monitoring cycles
        """
        if interval_minutes is None:
            interval_minutes = config.MONITORING_INTERVAL_MINUTES
            
        logger.info(f"Scheduling monitoring every {interval_minutes} minutes")
        
        # Create job function that uses default parameters
        def job():
            self.run_monitoring_cycle()
        
        # Schedule the job
        schedule.every(interval_minutes).minutes.do(job)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Error in monitoring scheduler: {str(e)}")

def main():
    """Main function to parse arguments and run the application."""
    parser = argparse.ArgumentParser(description="Reddit Buyer Intent Detection")
    
    # Define command-line arguments
    parser.add_argument("--monitor", action="store_true", help="Run continuous monitoring")
    parser.add_argument("--interval", type=int, help="Monitoring interval in minutes")
    parser.add_argument("--run-once", action="store_true", help="Run a single monitoring cycle")
    parser.add_argument("--send-messages", action="store_true", help="Send messages to users")
    parser.add_argument("--min-intent", choices=["HIGH", "MEDIUM", "LOW"], default="MEDIUM", 
                        help="Minimum intent level to consider")
    parser.add_argument("--min-confidence", type=float, default=0.6, 
                        help="Minimum confidence score (0.0-1.0)")
    parser.add_argument("--subreddits", nargs="+", help="Specific subreddits to monitor")
    parser.add_argument("--limit", type=int, help="Limit posts per subreddit")
    
    args = parser.parse_args()
    
    try:
        app = RedditBuyerIntentApp()
        
        if args.run_once:
            app.run_monitoring_cycle(
                subreddits=args.subreddits,
                limit=args.limit,
                min_intent=args.min_intent,
                min_confidence=args.min_confidence,
                send_messages=args.send_messages
            )
        elif args.monitor:
            app.schedule_monitoring(interval_minutes=args.interval)
        else:
            parser.print_help()
    except Exception as e:
        logger.error(f"Application error: {str(e)}")

if __name__ == "__main__":
    main() 