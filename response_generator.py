import logging
import google.generativeai as genai
import json
import os
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ResponseGenerator:
    def __init__(self):
        """Initialize the Gemini API client for response generation."""
        try:
            # Configure the Gemini API
            genai.configure(api_key=config.GEMINI_API_KEY)
            
            # Set up the gemini-pro model
            self.model = genai.GenerativeModel('gemini-pro')
            
            # Load custom prompt if available
            self.custom_prompt_template = self._load_custom_prompt()
            
            logger.info("Gemini API client initialized for response generation")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini API client for response generation: {str(e)}")
            raise
    
    def _load_custom_prompt(self):
        """Load custom prompt template from file if available."""
        try:
            if os.path.exists("prompts/response_prompt.json"):
                with open("prompts/response_prompt.json", "r") as f:
                    data = json.load(f)
                    logger.info("Loaded custom response generation prompt")
                    return data.get("prompt_template")
        except Exception as e:
            logger.error(f"Error loading custom prompt: {str(e)}")
        
        return None
    
    def generate_response(self, content_data, include_resources=True):
        """
        Generate a personalized response for a Reddit user based on their post or comment.
        
        Args:
            content_data (dict): Dictionary containing the post/comment data with intent analysis
            include_resources (bool): Whether to include resources/links in the response
            
        Returns:
            dict: Response data containing subject, message, and metadata
        """
        try:
            # Determine if this is a post or comment
            content_type = content_data.get('type', 'post')
            author = content_data.get('author', 'Redditor')
            content = content_data.get('content', '')
            
            if content_type == 'post':
                title = content_data.get('title', '')
                content_text = f"Title: {title}\n\nContent: {content}"
            else:
                content_text = f"Comment: {content}"
            
            # Get intent analysis data
            intent_analysis = content_data.get('intent_analysis', {})
            intent_category = intent_analysis.get('intent_category', 'NONE')
            products_services = intent_analysis.get('products_services', [])
            needs = intent_analysis.get('needs', [])
            timeframe = intent_analysis.get('timeframe', 'unknown')
            
            # Use custom prompt if available, otherwise use default
            if self.custom_prompt_template:
                try:
                    # Format the custom prompt with the necessary variables
                    prompt = self.custom_prompt_template.format(
                        content=content_text,
                        intent_category=intent_category,
                        products_services=', '.join(products_services) if products_services else 'Unknown',
                        needs=', '.join(needs) if needs else 'Unknown',
                        timeframe=timeframe,
                        author=author,
                        include_resources=include_resources
                    )
                except Exception as e:
                    logger.error(f"Error formatting custom prompt: {str(e)}. Falling back to default prompt.")
                    # Fall back to default prompt if there's an error
                    prompt = self._get_default_prompt(content_text, intent_category, products_services, needs, timeframe, include_resources)
            else:
                prompt = self._get_default_prompt(content_text, intent_category, products_services, needs, timeframe, include_resources)
            
            # Generate response from Gemini
            response = self.model.generate_content(prompt)
            
            # Extract the JSON data from the response
            response_text = response.text
            
            # Find JSON content within the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                response_data = json.loads(json_str)
            else:
                # If no JSON found, try to parse the whole response
                response_data = json.loads(response_text)
            
            # Create response data with metadata
            result = {
                "subject": response_data.get("subject", "Regarding your Reddit post"),
                "message": response_data.get("message", ""),
                "author": author,
                "intent_category": intent_category,
                "products_services": products_services,
                "content_type": content_type,
                "include_resources": include_resources
            }
            
            logger.info(f"Generated response for {author} with {intent_category} buyer intent")
            return result
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            # Return a default response in case of error
            return {
                "subject": "Regarding your Reddit post",
                "message": "I noticed your post and thought I might be able to help. Would you be interested in discussing this further?",
                "author": content_data.get('author', 'Redditor'),
                "intent_category": intent_analysis.get('intent_category', 'NONE'),
                "products_services": [],
                "content_type": content_data.get('type', 'post'),
                "include_resources": include_resources
            }
    
    def _get_default_prompt(self, content_text, intent_category, products_services, needs, timeframe, include_resources):
        """Get the default prompt for response generation."""
        return f"""
        Task: Generate a professional, personalized direct message (DM) to send to a Reddit user who has shown interest in making a purchase.
        
        Reddit User's Content:
        {content_text}
        
        Buyer Intent Analysis:
        - Intent Level: {intent_category}
        - Products/Services of Interest: {', '.join(products_services) if products_services else 'Unknown'}
        - Needs/Requirements: {', '.join(needs) if needs else 'Unknown'}
        - Purchasing Timeframe: {timeframe}
        
        Requirements for the DM:
        1. Use a friendly, helpful tone without being pushy or salesy
        2. Briefly mention you noticed their post/comment about {', '.join(products_services) if products_services else 'their interest'}
        3. Offer genuine value or insights related to their specific needs
        4. {"Include 1-2 relevant resources or links that might help them" if include_resources else "Keep the message concise without external links"}
        5. End with a clear call-to-action to schedule an appointment or consultation
        6. The message should be brief (150-200 words maximum)
        7. Include a professional subject line
        
        Return a JSON object with:
        1. "subject": The subject line for the DM
        2. "message": The complete message content ready to send
        
        Return ONLY valid JSON with these fields, nothing else.
        """
    
    def batch_generate_responses(self, filtered_content, min_intent="MEDIUM"):
        """
        Generate responses for a batch of high-intent Reddit content.
        
        Args:
            filtered_content (list): List of posts with intent analysis
            min_intent (str): Minimum intent category to generate responses for
            
        Returns:
            list: List of response data for high-intent content
        """
        responses = []
        
        intent_levels = {
            "HIGH": 3,
            "MEDIUM": 2,
            "LOW": 1,
            "NONE": 0
        }
        
        min_intent_level = intent_levels[min_intent]
        
        for post in filtered_content:
            post_intent_level = intent_levels[post['intent_analysis']['intent_category']]
            
            # Generate response for the post if it has sufficient intent
            if post_intent_level >= min_intent_level:
                post_response = self.generate_response(post)
                responses.append(post_response)
            
            # Generate responses for high-intent comments
            for comment in post['comments']:
                comment_intent_level = intent_levels[comment['intent_analysis']['intent_category']]
                
                if comment_intent_level >= min_intent_level:
                    # Add post context to the comment data
                    comment['post_title'] = post.get('title', '')
                    comment['post_url'] = post.get('url', '')
                    comment['subreddit'] = post.get('subreddit', '')
                    
                    comment_response = self.generate_response(comment)
                    responses.append(comment_response)
        
        return responses 