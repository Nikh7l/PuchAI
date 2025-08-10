import asyncio
import os
import json
from typing import Annotated, Optional
from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp import ErrorData, McpError
from mcp.server.auth.provider import AccessToken
from mcp.types import TextContent, INVALID_PARAMS
from pydantic import Field, BaseModel

# --- Load environment variables ---
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
    try:
        with open(f"data/{filename}", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# --- MCP Server Setup ---
mcp = FastMCP(
    "Digital Nagrik Mitra",
    auth=SimpleBearerAuthProvider(TOKEN),
)

# --- Tool: validate (required by Puch) ---
@mcp.tool
async def validate() -> str:
    return MY_NUMBER

# --- Tool: /seva ---
@mcp.tool
async def seva(service_name: Annotated[str, Field(description='The name of the government service you need information about. e.g., \"Passport\", \"PAN Card\"')]) -> str:
    """Provides step-by-step guides for various Indian government services."""
    services = load_data("services.json")
    service_info = next((s for s in services if s['name'].lower() == service_name.lower()), None)

    if not service_info:
        available_services = ", ".join([s['name'] for s in services])
        return f"Sorry, I don't have information on '{service_name}'. Available services are: {available_services}."

    response = f"📜 Guide for {service_info['name']}\n\n"
    response += "📝 *Procedure:*\n"
    for i, step in enumerate(service_info['procedure'], 1):
        response += f"{i}. {step}\n"
    
    response += "\n📄 *Documents Required:*\n"
    for doc in service_info['documents_required']:
        response += f"- {doc}\n"
    
    response += f"\n🔗 *Official Link:* {service_info['official_link']}"
    
    return response

# --- Tool: /yojana ---
@mcp.tool
async def yojana(category: Annotated[Optional[str], Field(description='The category of scheme you are interested in. e.g., \"Education\", \"Health\"')]) -> str:
    """Helps you find and check eligibility for Indian government schemes."""
    schemes = load_data("schemes.json")
    
    if not category:
        # List all available categories
        all_categories = sorted(list(set(s['category'] for s in schemes)))
        response = "🌟 *Available Scheme Categories:*\n"
        for cat in all_categories:
            response += f"- {cat}\n"
        response += "\nTo see schemes in a category, use `/yojana [category_name]`."
        return response

    # List schemes in the specified category
    category_schemes = [s for s in schemes if s['category'].lower() == category.lower()]
    
    if not category_schemes:
        return f"Sorry, I couldn't find any schemes in the '{category}' category. Please try another one."

    response = f"📚 *Schemes in {category}:*\n"
    for scheme in category_schemes:
        response += f"- *{scheme['name']}*: {scheme['description']}\n"
        
    response += "\n(Eligibility checker coming soon!)"
    return response

# --- Run MCP Server ---
async def main():
    print("🚀 Starting MCP server on http://0.0.0.0:8086")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8086)

# Create FastAPI app for Gunicorn
app = mcp.app

if __name__ == "__main__":
    import uvicorn
    print("Starting Digital Nagrik Mitra MCP Server...")
    uvicorn.run("mcp_server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8087)), reload=True)
