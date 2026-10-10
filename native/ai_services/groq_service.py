import os
import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class GroqServiceError(Exception):
    """Custom exception for Groq API errors."""
    pass

class GroqService:
    def __init__(self):
        # 1. API key from environment variable
        self.api_key = os.getenv('GROQ_API_KEY')
        if not self.api_key:
            logger.warning("GROQ_API_KEY is not set in the environment.")
        
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b') # Default model if none specified
        
    def generate(self, 
                 user_prompt: str, 
                 system_prompt: Optional[str] = None, 
                 context: Optional[str] = None,
                 timeout: int = 30) -> str:
        """
        Calls the Groq API securely from the backend.
        """
        # 3. Never expose to JS (executed purely on server)
        # 2. Never hardcode secrets
        if not self.api_key:
            raise GroqServiceError("GROQ_API_KEY is not configured in the environment.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        
        # 4. Support a system prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        # 6. Support project context
        if context:
            context_msg = (
                "Project Context:\n"
                f"{context}\n\n"
                "Please use the above context for the following request."
            )
            messages.append({"role": "user", "content": context_msg})
            
        # 5. Support a user prompt
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2, # Low temperature for more deterministic coding outputs
        }

        try:
            response = requests.post(
                self.api_url, 
                headers=headers, 
                json=payload, 
                timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            
            # 9. Return a clean response
            if 'choices' in data and len(data['choices']) > 0:
                return data['choices'][0]['message']['content']
            else:
                raise GroqServiceError("Invalid response format from Groq API.")
                
        # 8. Handle timeouts
        except requests.exceptions.Timeout:
            logger.error("Groq API request timed out.")
            raise GroqServiceError("The request to Groq API timed out.")
            
        # 7. Handle API errors
        except requests.exceptions.RequestException as e:
            logger.error(f"Groq API request failed: {str(e)}")
            error_details = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_json = e.response.json()
                    error_details = err_json.get('error', {}).get('message', '')
                except ValueError:
                    error_details = e.response.text
            
            raise GroqServiceError(f"Groq API error: {str(e)} - {error_details}")

# Expose a singleton instance for easy import across agents later
groq_service = GroqService()
