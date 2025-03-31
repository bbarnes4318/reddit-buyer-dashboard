import google.generativeai as genai
import logging
import json
import time
import os
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class IntentDetector:
    def __init__(self):
        """Initialize the Gemini API client with the API key from config."""
        try:
            # Configure the Gemini API
            genai.configure(api_key=config.GEMINI_API_KEY)
            
            # Set up the gemini-pro model
            self.model = genai.GenerativeModel('gemini-pro')
            
            # Load custom prompt if available
            self.custom_prompt_template = self._load_custom_prompt()
            
            logger.info("Gemini API client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini API client: {str(e)}")
            raise
    
    def _load_custom_prompt(self):
        """Load custom prompt template from file if available."""
        try:
            if os.path.exists("prompts/intent_prompt.json"):
                with open("prompts/intent_prompt.json", "r") as f:
                    data = json.load(f)
                    logger.info("Loaded custom intent detection prompt")
                    return data.get("prompt_template")
        except Exception as e:
            logger.error(f"Error loading custom prompt: {str(e)}")
        
        return None
    
    def detect_intent(self, text, context=None):
        """
        Detect buyer intent in the given text using Gemini 2.5 Pro.
        
        Args:
            text (str): The text to analyze for buyer intent
            context (dict, optional): Additional context such as subreddit and title
            
        Returns:
            dict: Intent analysis results containing intent category, confidence, and relevant details
        """
        if not text or text.strip() == "":
            return {
                "intent_category": "NONE",
                "confidence": 1.0,
                "products_services": [],
                "needs": [],
                "timeframe": "unknown",
                "recommended_response": "",
                "raw_analysis": {}
            }
        
        # Create a prompt for the Gemini model
        subreddit_info = f"Subreddit: r/{context['subreddit']}" if context and 'subreddit' in context else ""
        title_info = f"Post title: {context['title']}" if context and 'title' in context else ""
        
        # Use custom prompt if available, otherwise use default
        if self.custom_prompt_template:
            try:
                # Format the custom prompt with the necessary variables
                prompt = self.custom_prompt_template.format(
                    content=text,
                    subreddit_info=subreddit_info,
                    title_info=title_info,
                    context=context
                )
            except Exception as e:
                logger.error(f"Error formatting custom prompt: {str(e)}. Falling back to default prompt.")
                # Fall back to default prompt if there's an error
                prompt = self._get_default_prompt(text, subreddit_info, title_info, context)
        else:
            prompt = self._get_default_prompt(text, subreddit_info, title_info, context)
        
        try:
            # Generate response from Gemini
            response = self.model.generate_content(prompt)
            
            # Extract the JSON data from the response
            response_text = response.text
            
            # Find JSON content within the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                analysis = json.loads(json_str)
            else:
                # If no JSON found, try to parse the whole response
                analysis = json.loads(response_text)
                
            # Log the results
            logger.info(f"Detected intent: {analysis['intent_category']} with confidence {analysis['confidence']}")
            
            return {
                "intent_category": analysis.get("intent_category", "NONE"),
                "confidence": analysis.get("confidence", 0.0),
                "products_services": analysis.get("products_services", []),
                "needs": analysis.get("needs", []),
                "timeframe": analysis.get("timeframe", "unknown"),
                "recommended_response": analysis.get("recommended_response", ""),
                "raw_analysis": analysis
            }
            
        except Exception as e:
            logger.error(f"Error detecting intent: {str(e)}")
            # Return a default response in case of an error
            return {
                "intent_category": "NONE",
                "confidence": 0.0,
                "products_services": [],
                "needs": [],
                "timeframe": "unknown",
                "recommended_response": "",
                "raw_analysis": {}
            }
    
    def _get_default_prompt(self, text, subreddit_info, title_info, context):
        """Get the default prompt for intent detection."""
        return f"""
        Analysis task: Detect buyer intent in the following Reddit {context.get('type', 'content') if context else 'content'}.
        {subreddit_info}
        {title_info}
        
        Content: {text}
        
        Please analyze this content for buyer intent and return a structured JSON object with the following:
        
        1. intent_category: One of ["HIGH", "MEDIUM", "LOW", "NONE"] based on how likely this person is to make a purchase soon
        2. confidence: A number from 0.0 to 1.0 representing your confidence in this classification
        3. products_services: A list of specific products, services, or solutions mentioned or implied
        4. needs: A list of the user's needs, pain points, or requirements
        5. timeframe: The likely purchasing timeframe (immediate, near future, distant future, unknown)
        6. recommended_response: A brief suggestion on how to approach this potential buyer
        
        HIGH intent means actively looking to purchase very soon.
        MEDIUM intent means researching options with a plan to purchase.
        LOW intent means curious but not actively planning to purchase.
        NONE means no detectable buyer intent.
        
        Return ONLY a valid JSON object with these fields, nothing else.
        """
    
    def analyze_reddit_content(self, reddit_data):
        """
        Analyze a list of Reddit posts and comments for buyer intent.
        
        Args:
            reddit_data (list): List of post dictionaries from the Reddit scraper
            
        Returns:
            list: The same list with added intent analysis data
        """
        for post in reddit_data:
            # Add context information for the intent detector
            context = {
                'type': 'post',
                'subreddit': post['subreddit'],
                'title': post['title']
            }
            
            # Analyze the post content
            post_text = f"{post['title']} {post['content']}"
            post['intent_analysis'] = self.detect_intent(post_text, context)
            
            # Sleep to avoid rate limiting
            time.sleep(1)
            
            # Analyze each comment
            for comment in post['comments']:
                # Add context for the comment
                comment_context = {
                    'type': 'comment',
                    'subreddit': post['subreddit'],
                    'title': post['title']
                }
                
                comment['intent_analysis'] = self.detect_intent(comment['content'], comment_context)
                
                # Sleep to avoid rate limiting
                time.sleep(1)
        
        return reddit_data
    
    def filter_high_intent_content(self, reddit_data, min_intent="MEDIUM", min_confidence=0.6):
        """
        Filter Reddit content to only include high-intent posts and comments.
        
        Args:
            reddit_data (list): List of post dictionaries with intent analysis
            min_intent (str): Minimum intent category to include ("HIGH", "MEDIUM", "LOW")
            min_confidence (float): Minimum confidence score to include
            
        Returns:
            list: Filtered list of posts and comments with high buyer intent
        """
        intent_levels = {
            "HIGH": 3,
            "MEDIUM": 2,
            "LOW": 1,
            "NONE": 0
        }
        
        min_intent_level = intent_levels[min_intent]
        high_intent_posts = []
        
        for post in reddit_data:
            post_intent_level = intent_levels[post['intent_analysis']['intent_category']]
            post_confidence = post['intent_analysis']['confidence']
            
            high_intent_comments = []
            
            # Check if any comments have high intent
            for comment in post['comments']:
                comment_intent_level = intent_levels[comment['intent_analysis']['intent_category']]
                comment_confidence = comment['intent_analysis']['confidence']
                
                if (comment_intent_level >= min_intent_level and 
                    comment_confidence >= min_confidence):
                    high_intent_comments.append(comment)
            
            # Include post if it has high intent or contains high intent comments
            if ((post_intent_level >= min_intent_level and post_confidence >= min_confidence) or 
                high_intent_comments):
                # Create a copy of the post with only high intent comments
                filtered_post = post.copy()
                filtered_post['comments'] = high_intent_comments
                high_intent_posts.append(filtered_post)
        
        return high_intent_posts 