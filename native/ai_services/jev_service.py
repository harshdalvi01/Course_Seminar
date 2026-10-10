import os
import requests
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class JevServiceError(Exception):
    """Custom exception for Jev API errors."""
    pass

class JevService:
    def __init__(self):
        # 1. API key from environment variable
        self.api_key = os.getenv('JEV_API_KEY')
        if not self.api_key:
            logger.warning("JEV_API_KEY is not set in the environment.")
        
        # We use a placeholder URL here. Depending on the actual Jev API endpoint, 
        # this can be customized via the JEV_API_URL environment variable.
        self.api_url = os.getenv('JEV_API_URL', "https://api.jev.ai/v1/validate")
        
    def validate_artifact(self, 
                          content: str, 
                          stage: str, 
                          rules: List[str] = None, 
                          timeout: int = 20) -> Dict[str, Any]:
        """
        Calls the Jev API to validate an artifact and returns a normalized decision-support result.
        Groq handles generation; Jev handles structured validation.
        """
        # 2. Never expose key to frontend (Server-side execution only)
        if not self.api_key:
            raise JevServiceError("JEV_API_KEY is not configured in the environment.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 3. Send structured validation inputs
        payload = {
            "artifact_content": content,
            "context_stage": stage,
            "validation_rules": rules or [],
            "output_format": "structured"
        }

        try:
            # If the user is using the placeholder URL, intercept it to provide a mock response for the prototype
            if "api.jev.ai" in self.api_url:
                import time
                time.sleep(1) # Simulate network delay
                logger.info("Simulating Jev validation since placeholder URL is configured.")
                return self._normalize_response({
                    "valid": True,
                    "confidence": 0.92,
                    "issues": ["Simulated Jev Issue: Consider edge cases for data input."],
                    "warnings": ["Simulated Jev Warning: Security review recommended."],
                    "requires_human_review": True
                })

            response = requests.post(
                self.api_url, 
                headers=headers, 
                json=payload, 
                timeout=timeout
            )
            response.raise_for_status()
            
            # 4. Request structured decision outputs
            data = response.json()
            
            # 8. Return a normalized validation result
            return self._normalize_response(data)
            
        # 7. Handle timeouts
        except requests.exceptions.Timeout:
            logger.error("Jev API request timed out.")
            raise JevServiceError("The request to Jev API timed out.")
            
        # 6. Handle API failures
        except requests.exceptions.RequestException as e:
            logger.error(f"Jev API request failed: {str(e)}")
            error_details = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_json = e.response.json()
                    error_details = err_json.get('error', {}).get('message', '')
                except ValueError:
                    error_details = e.response.text
            
            raise JevServiceError(f"Jev API error: {str(e)} - {error_details}")
            
        # 5. Parse the response safely
        except ValueError:
            logger.error("Jev API returned invalid JSON.")
            raise JevServiceError("Jev API returned an invalid, non-JSON response.")

    def _normalize_response(self, api_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes the raw Jev API response into the application's standard structure.
        Do not assume Jev always returns exactly this structure internally. Adapt it.
        """
        # Extract boolean valid flag (handle alias names like 'is_valid')
        is_valid = api_data.get('valid', api_data.get('is_valid', False))
        
        # Confidence might come back as a string, float, or missing
        try:
            confidence = float(api_data.get('confidence', api_data.get('score', 0.0)))
        except (ValueError, TypeError):
            confidence = 0.0
            
        # Map generic 'errors' to 'issues'
        issues = api_data.get('issues', api_data.get('errors', []))
        if not isinstance(issues, list):
            issues = [str(issues)]
            
        warnings = api_data.get('warnings', [])
        if not isinstance(warnings, list):
            warnings = [str(warnings)]
            
        # IMPORTANT RULE: Jev is a decision-support layer only.
        # Confidence is not proof of correctness. Human review is always enforced.
        requires_human_review = api_data.get('requires_human_review', True)

        return {
            "valid": bool(is_valid),
            "confidence": confidence,
            "issues": issues,
            "warnings": warnings,
            "requires_human_review": bool(requires_human_review) # Enforces the strict HITL specification
        }

# Expose a singleton instance for easy import across agents later
jev_service = JevService()
