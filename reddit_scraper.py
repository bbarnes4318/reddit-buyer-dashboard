import praw
import time
import logging
from datetime import datetime, timedelta
import requests
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RedditScraper:
    def __init__(self, access_token=None, refresh_token=None, token_expires_at=None):
        """
        Initialize the Reddit scraper with OAuth tokens.
        
        Args:
            access_token (str, optional): OAuth access token for Reddit API.
            refresh_token (str, optional): OAuth refresh token for Reddit API.
            token_expires_at (datetime, optional): When the access token expires.
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires_at = token_expires_at
        self.user_agent = "RedditBuyerIntentBot/1.0"
        
        # Use app credentials for OAuth
        self.client_id = config.REDDIT_CLIENT_ID
        self.client_secret = config.REDDIT_CLIENT_SECRET
        
        # Initialize PRAW with the access token if available
        if access_token:
            self._init_with_token(access_token)
        else:
            # Fallback to app-only auth for non-authenticated operations
            self._init_read_only()
            
        # Track when users were last messaged to avoid spam
        self.last_messaged = {}
    
    def _init_with_token(self, access_token):
        """Initialize PRAW with an OAuth access token."""
        try:
            self.reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
                token_manager=self._get_token_manager(access_token)
            )
            logger.info("Reddit API client initialized with OAuth token")
        except Exception as e:
            logger.error(f"Failed to initialize Reddit API client with OAuth: {str(e)}")
            raise
    
    def _init_read_only(self):
        """Initialize PRAW in read-only mode."""
        try:
            self.reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent
            )
            self.reddit.read_only = True
            logger.info("Reddit API client initialized in read-only mode")
        except Exception as e:
            logger.error(f"Failed to initialize Reddit API client: {str(e)}")
            raise
    
    def _get_token_manager(self, access_token):
        """Create a token manager for PRAW to use the access token."""
        from praw.auth import ImplicitAuth
        class CustomTokenManager:
            def __init__(self, access_token):
                self.access_token = access_token
            
            def post_refresh_callback(self, authorizer):
                pass
                
            def pre_refresh_callback(self, authorizer):
                pass
                
            def is_valid(self):
                return True
                
            def refresh(self):
                pass
        
        return CustomTokenManager(access_token)
    
    def refresh_token_if_needed(self):
        """Check if the access token is expired and refresh if needed."""
        if not self.refresh_token:
            return False
            
        now = datetime.utcnow()
        if self.token_expires_at and now >= self.token_expires_at:
            # Token has expired, refresh it
            try:
                token_data = self._refresh_access_token()
                if token_data and 'access_token' in token_data:
                    self.access_token = token_data['access_token']
                    expires_in = token_data.get('expires_in', 3600)
                    self.token_expires_at = now + timedelta(seconds=expires_in)
                    self._init_with_token(self.access_token)
                    return True
            except Exception as e:
                logger.error(f"Failed to refresh access token: {str(e)}")
                return False
        return True
        
    def _refresh_access_token(self):
        """Refresh the OAuth access token using the refresh token."""
        try:
            auth = (self.client_id, self.client_secret)
            headers = {"User-Agent": self.user_agent}
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
            
            response = requests.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                headers=headers,
                data=data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to refresh token. Status: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Exception while refreshing token: {str(e)}")
            return None
    
    def test_connection(self):
        """
        Test the Reddit API connection by attempting to fetch the authenticated user.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if self.access_token:
                # If we have a token, check if it's valid and refresh if needed
                if not self.refresh_token_if_needed():
                    return False
                    
                # Try to get the authenticated user's identity
                username = self.reddit.user.me().name
                logger.info(f"Successfully connected to Reddit as u/{username}")
            else:
                # Just test basic connectivity
                subreddit = self.reddit.subreddit("all")
                for _ in subreddit.new(limit=1):
                    pass
                logger.info("Successfully connected to Reddit API")
                
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
        # Ensure token is valid if we have one
        if self.access_token and not self.refresh_token_if_needed():
            logger.error("Failed to refresh token, cannot scrape subreddit")
            return []
            
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
        # Check if we have valid OAuth credentials with required scopes
        if not self.access_token:
            logger.error("Cannot send message: No OAuth access token")
            return False
            
        # Make sure token is valid
        if not self.refresh_token_if_needed():
            logger.error("Cannot send message: Failed to refresh token")
            return False
            
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