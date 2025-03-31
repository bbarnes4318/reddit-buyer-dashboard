import praw
import time
import logging
from datetime import datetime, timedelta
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RedditScraper:
    def __init__(self, client_id=None, client_secret=None, username=None, password=None, user_agent=None):
        """
        Initialize the Reddit scraper with API credentials.
        
        Args:
            client_id (str, optional): Reddit API client ID. Defaults to config value.
            client_secret (str, optional): Reddit API client secret. Defaults to config value.
            username (str, optional): Reddit username. Defaults to config value.
            password (str, optional): Reddit password. Defaults to config value.
            user_agent (str, optional): User agent string. Defaults to config value.
        """
        try:
            self.reddit = praw.Reddit(
                client_id=client_id or config.REDDIT_CLIENT_ID,
                client_secret=client_secret or config.REDDIT_CLIENT_SECRET,
                username=username or config.REDDIT_USERNAME,
                password=password or config.REDDIT_PASSWORD,
                user_agent=user_agent or config.REDDIT_USER_AGENT
            )
            logger.info("Reddit API client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Reddit API client: {str(e)}")
            raise

        # Track when users were last messaged to avoid spam
        self.last_messaged = {}
    
    def test_connection(self):
        """
        Test the Reddit API connection by attempting to fetch the authenticated user.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Try to get the authenticated user's identity
            username = self.reddit.user.me().name
            logger.info(f"Successfully connected to Reddit as u/{username}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Reddit: {str(e)}")
            return False
        
    def scrape_subreddit(self, subreddit_name, keywords=None, limit=None):
        """
        Scrape posts from a subreddit that contain any of the given keywords.
        
        Args:
            subreddit_name (str): Name of the subreddit to scrape
            keywords (list): List of keywords to filter posts by
            limit (int): Maximum number of posts to retrieve
            
        Returns:
            list: List of dictionaries containing post data
        """
        if keywords is None:
            keywords = config.BUYER_INTENT_KEYWORDS
            
        if limit is None:
            limit = config.MAX_POSTS_PER_SUBREDDIT
            
        logger.info(f"Scraping r/{subreddit_name} for buyer intent keywords")
        scraped_data = []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get new posts from the subreddit
            for post in subreddit.new(limit=limit):
                # Apply rate limiting to comply with Reddit API policies
                time.sleep(config.API_RATE_LIMIT_SECONDS)
                
                # Check if the post contains any of the keywords
                post_text = f"{post.title} {post.selftext}".lower()
                
                # Extract post data if it contains any of the keywords
                if any(keyword.lower() in post_text for keyword in keywords):
                    post_data = {
                        'id': post.id,
                        'title': post.title,
                        'content': post.selftext,
                        'author': str(post.author),
                        'url': post.url,
                        'created_utc': post.created_utc,
                        'subreddit': subreddit_name,
                        'type': 'post',
                        'comments': []
                    }
                    
                    # Get top-level comments
                    post.comments.replace_more(limit=0)  # Skip "load more comments" links
                    for comment in post.comments:
                        time.sleep(config.API_RATE_LIMIT_SECONDS)
                        if comment.author:  # Check if the comment has an author (not deleted)
                            comment_data = {
                                'id': comment.id,
                                'content': comment.body,
                                'author': str(comment.author),
                                'created_utc': comment.created_utc
                            }
                            post_data['comments'].append(comment_data)
                    
                    scraped_data.append(post_data)
                    
            logger.info(f"Scraped {len(scraped_data)} posts from r/{subreddit_name}")
            
        except Exception as e:
            logger.error(f"Error scraping r/{subreddit_name}: {str(e)}")
            
        return scraped_data
    
    def scrape_multiple_subreddits(self, subreddit_list=None, keywords=None, limit=None):
        """
        Scrape posts from multiple subreddits.
        
        Args:
            subreddit_list (list): List of subreddit names to scrape
            keywords (list): List of keywords to filter posts by
            limit (int): Maximum number of posts to retrieve per subreddit
            
        Returns:
            list: Combined list of post data from all subreddits
        """
        if subreddit_list is None:
            subreddit_list = config.MONITORED_SUBREDDITS
            
        all_data = []
        
        for subreddit in subreddit_list:
            subreddit_data = self.scrape_subreddit(subreddit, keywords, limit)
            all_data.extend(subreddit_data)
            
        return all_data
    
    def can_message_user(self, username):
        """
        Check if a user can be messaged based on cooldown period.
        
        Args:
            username (str): Reddit username
            
        Returns:
            bool: True if the user can be messaged, False otherwise
        """
        now = datetime.now()
        if username in self.last_messaged:
            last_time = self.last_messaged[username]
            cooldown = timedelta(hours=config.DM_COOLDOWN_HOURS)
            
            if now - last_time < cooldown:
                logger.info(f"User {username} was recently messaged. Skipping.")
                return False
                
        return True
    
    def send_direct_message(self, username, subject, message):
        """
        Send a direct message to a Reddit user.
        
        Args:
            username (str): Reddit username to message
            subject (str): Subject of the message
            message (str): Content of the message
            
        Returns:
            bool: True if the message was sent, False otherwise
        """
        if not self.can_message_user(username):
            return False
            
        try:
            # Send the message
            self.reddit.redditor(username).message(subject, message)
            
            # Update the last messaged time
            self.last_messaged[username] = datetime.now()
            
            logger.info(f"Sent message to u/{username}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to u/{username}: {str(e)}")
            return False 