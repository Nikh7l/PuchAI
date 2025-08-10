import asyncio
import os
import json
from typing import Annotated, Optional
from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp.server.auth.provider import AccessToken
from pydantic import Field

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
        super().__init__(
            public_key=k.public_key,
            jwks_uri=None,
            issuer=None,
            audience=None
        )
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


# --- Data Loading Utility ---
def load_data(filename: str):
    """
    Loads JSON data from the 'data' directory.
    Returns an empty list if file not found or invalid JSON.
    """
    path = os.path.join("data", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
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
    """Validation endpoint for Puch integration."""
    return MY_NUMBER


# --- Tool: /seva ---
@mcp.tool
async def seva(
    service_name: Annotated[str, Field(description='The government service name. e.g., "Passport", "PAN Card"')]
) -> str:
    """
    Provides step-by-step guides for Indian government services.
    """
    services = load_data("services.json")
    service_info = next(
        (s for s in services if s['name'].lower() == service_name.lower()),
        None
    )

    if not service_info:
        available_services = ", ".join(s['name'] for s in services)
        return (
            f"❌ Sorry, I don't have information on '{service_name}'.\n"
            f"📋 Available services are: {available_services}."
        )

    response = f"📜 **Guide for {service_info['name']}**\n\n"

    if service_info.get('procedure'):
        response += "📝 **Procedure:**\n"
        for i, step in enumerate(service_info['procedure'], 1):
            response += f"{i}. {step}\n"

    if service_info.get('documents_required'):
        response += "\n📄 **Documents Required:**\n"
        for doc in service_info['documents_required']:
            response += f"- {doc}\n"

    if service_info.get('official_link'):
        response += f"\n🔗 **Official Link:** {service_info['official_link']}"

    return response


# --- Tool: /yojana ---
@mcp.tool
async def yojana(
    query: Annotated[
        Optional[str],
        Field(description='Category or keyword for the scheme. e.g., "Education", "farmer", "pension"')
    ]
) -> str:
    """
    Search for Indian government schemes by category or keyword.
    - If no query, returns available categories.
    - Supports multi-word partial matches in category, name, or description.
    """
    schemes = load_data("schemes.json")

    if not schemes:
        return "⚠️ No scheme data found. Please check `schemes.json`."

    if not query:
        all_categories = sorted({s['category'] for s in schemes})
        response = "🌟 **Available Scheme Categories:**\n"
        response += "\n".join(f"- {cat}" for cat in all_categories)
        response += "\n\n💡 Example: `/yojana farmer` or `/yojana Health`"
        return response

    # Fuzzy search by keywords
    query_words = query.lower().split()

    def matches(scheme):
        text = f"{scheme['category']} {scheme['name']} {scheme['description']}".lower()
        return all(word in text for word in query_words)

    matched_schemes = [s for s in schemes if matches(s)]

    if not matched_schemes:
        return f"❌ No schemes found matching '{query}'. Try another keyword or category."

    response = f"📚 **Schemes matching '{query}':**\n"
    for scheme in matched_schemes:
        response += f"\n**{scheme['name']}** — {scheme['description']}"
        response += f"\n_Category:_ {scheme['category']}"
        if scheme.get('official_link'):
            response += f"\n🔗 {scheme['official_link']}\n"

    return response


# --- Run MCP Server ---
async def main():
    print("🚀 Starting MCP server on http://0.0.0.0:8086")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8086)


# Create FastAPI app for Gunicorn
app = mcp.app

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Digital Nagrik Mitra MCP Server...")
    uvicorn.run(
        "mcp_server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8087)),
        reload=True
    )
