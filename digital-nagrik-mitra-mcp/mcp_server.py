import asyncio
import json
import os
import logging
import functools
import traceback
from datetime import datetime
from typing import Annotated, Optional, Any, Callable, TypeVar, cast

from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp import ErrorData, McpError
from mcp.server.auth.provider import AccessToken
from mcp.types import TextContent, INVALID_PARAMS, INTERNAL_ERROR
from pydantic import Field, BaseModel

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only log to console
    ]
)
logger = logging.getLogger('nagrik_mitra')

# Type variable for function decorators
F = TypeVar('F', bound=Callable[..., Any])

def log_errors(func: F) -> F:
    """Decorator to log errors and return user-friendly messages."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            logger.info(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
            result = await func(*args, **kwargs)
            logger.info(f"{func.__name__} completed successfully")
            return result
        except McpError as e:
            error_msg = f"McpError in {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"❌ {error_msg}"
        except Exception as e:
            error_msg = f"Unexpected error in {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "❌ An unexpected error occurred. Please try again later."
    return cast(F, wrapper)

# --- Load environment variables ---
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("AUTH_TOKEN")
MY_NUMBER = os.environ.get("MY_NUMBER")

assert TOKEN, "Please set AUTH_TOKEN in your .env file"
assert MY_NUMBER, "Please set MY_NUMBER in your .env file"

# --- Auth Provider ---
class SimpleBearerAuthProvider(BearerAuthProvider):
    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(public_key=k.public_key, jwks_uri=None, issuer=None, audience=None)
        self.token = token

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(
                token=token,
                client_id="puch-client",
                scopes=["*"],
                expires_at=None,
            )
        return None

# --- Data Loading Utilities ---
def load_data(filename: str):
    """Load JSON data from the data directory with error handling."""
    try:
        # Get the directory where the current script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Build the path to the data file
        filepath = os.path.join(script_dir, "data", filename)
        logger.debug(f"Loading data from {filepath}")
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
        logger.debug(f"Successfully loaded data from {filepath}")
        return data
    except FileNotFoundError:
        error_msg = f"Data file not found: {filename}"
        logger.error(error_msg)
        raise McpError(ErrorData(code=INVALID_PARAMS, message=error_msg))
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in {filename}: {str(e)}"
        logger.error(error_msg)
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=error_msg))
    except Exception as e:
        error_msg = f"Error loading {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=error_msg))

# --- MCP Server Setup ---
mcp = FastMCP(
    "Digital Nagrik Mitra",
    auth=SimpleBearerAuthProvider(TOKEN),
)

# --- Tool: validate (required by Puch) ---
@mcp.tool
@log_errors
async def validate() -> str:
    """Validate the MCP server connection."""
    logger.info("Validation request received")
    return MY_NUMBER

# --- Tool: /seva ---
@mcp.tool
@log_errors
async def seva(service_name: Annotated[str, Field(description='The name of the government service you need information about. e.g., "Passport", "PAN Card"')]) -> str:
    """
    Provides step-by-step guides for various Indian government services.
    
    Args:
        service_name: Name of the service to get information about (e.g., "Passport", "PAN Card")
        
    Returns:
        str: Formatted guide for the requested service
    """
    logger.info(f"Processing request for service: {service_name}")
    
    try:
        # First try to load from services1.json, fallback to services.json if not found
        try:
            services = load_data("services.json")
            logger.debug(f"Loaded {len(services)} services from services1.json")
        except FileNotFoundError:
            services = load_data("services.json")
            logger.debug(f"Loaded {len(services)} services from services.json")
        
        service_info = next((s for s in services if s['name'].lower() == service_name.lower()), None)

        if not service_info:
            available_services = ", ".join([s['name'] for s in services])
            error_msg = f"Service not found: {service_name}"
            logger.warning(f"{error_msg}. Available services: {available_services}")
            return f"❌ {error_msg}. Available services are: {available_services}."

        logger.info(f"Found service: {service_info['name']}")
        
        response = f"📜 *Guide for {service_info['name']}*\n\n"
        
        # Add fees information if available (new schema)
        if 'fees' in service_info and isinstance(service_info['fees'], dict):
            response += "💰 *Fees:*\n"
            for fee_type, amount in service_info['fees'].items():
                response += f"- *{fee_type}:* {amount}\n"
            response += "\n"
        
        response += "📝 *Procedure:*\n"
        for i, step in enumerate(service_info.get('procedure', []), 1):
            response += f"{i}. {step}\n"
        
        if 'documents_required' in service_info and service_info['documents_required']:
            response += "\n📄 *Documents Required:*\n"
            for doc in service_info['documents_required']:
                response += f"- {doc}\n"
        
        if 'official_link' in service_info and service_info['official_link']:
            response += f"\n🔗 *Official Link:* {service_info['official_link']}"
        
        response += "\n\n🔄 *Need more help?* Ask me about any step!"
        
        logger.debug(f"Successfully generated response for {service_name}")
        return response
        
    except Exception as e:
        logger.error(f"Error in seva tool: {str(e)}", exc_info=True)
        return f"❌ An error occurred while processing your request: {str(e)}"

# --- Tool: /yojana ---
@mcp.tool
@log_errors
async def yojana(category: Annotated[Optional[str], Field(description='The category of scheme you are interested in. e.g., \"Education\", \"Health\"')]) -> str:
    """
    Helps you find and check eligibility for Indian government schemes.
    
    Args:
        category: Category of schemes to list (optional)
        
    Returns:
        str: List of schemes in the specified category or all categories if none specified
    """
    logger.info(f"Processing yojana request for category: {category or 'all'}")
    
    try:
        schemes = load_data("schemes.json")
        logger.debug(f"Loaded {len(schemes)} schemes from data")
        
        if not schemes:
            logger.warning("No schemes found in the database")
            return "❌ No schemes available at the moment. Please check back later."
        
        if not category:
            all_categories = sorted(list(set(s.get('category', 'Uncategorized') for s in schemes)))
            response = "🌟 *Available Scheme Categories:*\n"
            for cat in all_categories:
                response += f"- {cat}\n"
            response += "\nTo see schemes in a category, use `/yojana [category_name]`."
            return response

        # List schemes in the specified category (flexible matching for special chars and whitespace)
        def normalize_category(cat):
            if not cat:
                return ''
            # Replace common variations and normalize whitespace
            return ' '.join(str(cat).lower()
                          .replace('&', 'and')
                          .replace('  ', ' ')
                          .strip()
                          .split())
        
        normalized_target = normalize_category(category)
        category_schemes = [s for s in schemes 
                          if normalize_category(s.get('category')) == normalized_target]
        if not category_schemes:
            logger.warning(f"No schemes found in category: {category}")
            response = "❌ No schemes found in the '{category}' category.\n\n"
            response += "Available categories are:\n"
            all_categories = sorted(list(set(s.get('category', 'Uncategorized') for s in schemes)))
            for cat in all_categories:
                response += f"- {cat}\n"
            return response

        response = f"📚 *Schemes in {category}:*\n\n"
        for scheme in category_schemes:
            response += f"🔹 *{scheme.get('name', 'Unnamed Scheme')}*\n\n"
            if 'description' in scheme:
                response += f"📝 *Description:* {scheme['description']}\n\n"
            if 'eligibility_criteria' in scheme:
                response += f"✅ *Eligibility Criteria:* {scheme['eligibility_criteria']}\n\n"
            if 'benefits' in scheme and isinstance(scheme['benefits'], list):
                response += "💡 *Key Benefits:*\n"
                for benefit in scheme['benefits']:
                    response += f"  • {benefit}\n"
                response += "\n"
                
            if 'official_link' in scheme:
                response += f"🔗 *Official Link:* {scheme['official_link']}\n"
            response += "\n" + "-"*30 + "\n\n"
            
        response = response.rstrip("\n" + "-"*30 + "\n\n") + "\n\n*Need more details?* Ask me about any scheme!"
        logger.info(f"Successfully generated response for category: {category}")
        return response
        
    except Exception as e:
        logger.error(f"Error in yojana tool: {str(e)}", exc_info=True)
        return f"❌ An error occurred while processing your request: {str(e)}"

# --- Middleware for Request/Response Logging ---
# @mcp.app.middleware("http")
async def log_requests(request, call_next):
    request_id = str(id(request))
    logger.info(f"Request {request_id}: {request.method} {request.url}")
    
    try:
        # Log request body if present
        if request.method in ["POST", "PUT"]:
            body = await request.body()
            if body:
                logger.debug(f"Request {request_id} body: {body.decode()}")
        
        # Process the request
        response = await call_next(request)
        
        # Log successful response
        logger.info(f"Response {request_id}: {response.status_code}")
        return response
        
    except Exception as e:
        logger.error(f"Error processing request {request_id}: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )

# --- Run MCP Server ---
async def main():
    logger.info("🚀 Starting Digital Nagrik Mitra MCP Server...")
    logger.info(f"Server will run on http://0.0.0.0:8086")
    
    try:
        await mcp.run_async("streamable-http", host="0.0.0.0", port=8086)
    except Exception as e:
        logger.critical(f"Failed to start server: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("Server shutdown complete")

if __name__ == "__main__":
    try:
        print("Starting Digital Nagrik Mitra MCP Server...")
        print("Logs are being written to 'nagrik_mitra.log'")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
        raise