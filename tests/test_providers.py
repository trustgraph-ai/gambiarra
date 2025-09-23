#!/usr/bin/env python3
"""
Test script to demonstrate Gambiarra server-side provider configuration.
"""

import os

def test_server_provider_configuration():
    """Show how to configure different LLM providers on the server."""

    print("🧪 Gambiarra Server Provider Configuration")
    print("=" * 60)

    print("\n📋 Server-Side Provider Configuration:")
    print("The server chooses which LLM provider to use. Clients just send prompts.")

    print("\n🖥️ Server Configuration Examples:")
    print("=" * 50)

    print("""
1️⃣ TEST PROVIDER (Default - Always Available):
   # No configuration needed - test provider is always available
   gambiarra-server
   # Or: python -m gambiarra.server

2️⃣ OPENAI PROVIDER:
   # Set OpenAI API key and choose OpenAI as default
   export OPENAI_API_KEY="your-openai-api-key"
   export GAMBIARRA_AI_PROVIDER=openai
   export GAMBIARRA_OPENAI_MODEL=gpt-4
   gambiarra-server
   # Or: python -m gambiarra.server

3️⃣ TRUSTGRAPH PROVIDER:
   # Configure TrustGraph URL and flow, set as default
   export GAMBIARRA_TRUSTGRAPH_URL="http://localhost:8088/"
   export GAMBIARRA_TRUSTGRAPH_FLOW="coding-assistant"
   export GAMBIARRA_AI_PROVIDER=trustgraph
   gambiarra-server
   # Or: python -m gambiarra.server

4️⃣ MULTIPLE PROVIDERS (Server chooses based on GAMBIARRA_AI_PROVIDER):
   # Configure multiple providers, server uses the one specified
   export OPENAI_API_KEY="your-openai-key"
   export GAMBIARRA_TRUSTGRAPH_URL="http://localhost:8088/"
   export GAMBIARRA_AI_PROVIDER=trustgraph  # Server will use TrustGraph
   gambiarra-server
   # Or: python -m gambiarra.server
""")

    print("\n👥 Client Usage (Same regardless of server provider):")
    print("=" * 50)
    print("""
# Client doesn't need to know which provider the server is using
gambiarra-client --workspace ./my-project
# Or: python -m gambiarra.client --workspace ./my-project

# Client can specify workspace and server URL
gambiarra-client --workspace /path/to/project --server-url ws://localhost:8000/ws
# Or: python -m gambiarra.client --workspace /path/to/project --server-url ws://localhost:8000/ws
""")

def show_current_configuration():
    """Show current environment configuration."""

    print("\n📊 Current Environment Configuration:")
    print("=" * 60)

    # Server configuration
    env_vars = {
        "GAMBIARRA_AI_PROVIDER": os.getenv("GAMBIARRA_AI_PROVIDER", "test (default)"),
        "OPENAI_API_KEY": "✅ Set" if os.getenv("OPENAI_API_KEY") else "❌ Not set",
        "GAMBIARRA_OPENAI_MODEL": os.getenv("GAMBIARRA_OPENAI_MODEL", "gpt-4 (default)"),
        "GAMBIARRA_TRUSTGRAPH_URL": os.getenv("GAMBIARRA_TRUSTGRAPH_URL", "http://localhost:8088/ (default)"),
        "GAMBIARRA_TRUSTGRAPH_FLOW": os.getenv("GAMBIARRA_TRUSTGRAPH_FLOW", "default"),
    }

    print("\n🖥️ Server Configuration:")
    for var, value in env_vars.items():
        print(f"   {var}: {value}")

    # Determine available providers
    available_providers = ["test", "trustgraph"]  # Both always available
    if os.getenv("OPENAI_API_KEY"):
        available_providers.append("openai")

    current_provider = os.getenv("GAMBIARRA_AI_PROVIDER", "test")

    print(f"\n🔌 Available providers: {', '.join(available_providers)}")
    print(f"🎯 Current default provider: {current_provider}")

    if current_provider not in available_providers:
        print(f"⚠️  Warning: Current provider '{current_provider}' may not be properly configured!")

    # Check if server is running
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code == 200:
            health_data = response.json()
            print(f"\n✅ Server Status: Running")
            ai_providers = health_data.get('services', {}).get('ai_providers', {})
            print(f"   Server-reported providers: {list(ai_providers.keys())}")
            for provider, status in ai_providers.items():
                status_icon = "✅" if status.get('status') == 'healthy' else "❌"
                print(f"     {provider}: {status_icon} {status.get('status', 'unknown')}")
        else:
            print(f"\n❌ Server Status: Error ({response.status_code})")
    except Exception as e:
        print(f"\n⚠️ Server Status: Not running or not accessible")

def show_usage_examples():
    """Show practical usage examples."""

    print("\n🚀 Quick Start Examples:")
    print("=" * 60)

    print("""
🔥 FASTEST WAY TO GET STARTED:
   # Terminal 1: Start server with test provider (no setup needed)
   gambiarra-server

   # Terminal 2: Start client
   gambiarra-client

🔧 USE WITH OPENAI:
   # Terminal 1: Configure and start server
   export OPENAI_API_KEY="your-key-here"
   export GAMBIARRA_AI_PROVIDER=openai
   gambiarra-server

   # Terminal 2: Client (same command as before)
   gambiarra-client

🔗 USE WITH TRUSTGRAPH:
   # Terminal 1: Configure and start server
   export GAMBIARRA_TRUSTGRAPH_URL="http://localhost:8088/"
   export GAMBIARRA_AI_PROVIDER=trustgraph
   gambiarra-server

   # Terminal 2: Client (same command as before)
   gambiarra-client
""")

if __name__ == "__main__":
    test_server_provider_configuration()
    show_current_configuration()
    show_usage_examples()

    print("\n" + "=" * 60)
    print("✨ Key Point: The server decides which LLM to use, not the client!")
    print("🎯 Configure the server environment, then any client can connect.")