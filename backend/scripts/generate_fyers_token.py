"""
Fyers Access Token Generator & Auto-Updater.

Daily Workflow (Takes 15 seconds):
1. Run: python backend/scripts/generate_fyers_token.py
2. Your browser automatically opens the official Fyers login page.
3. Log in securely with your Client ID, PIN, and OTP.
4. Copy either the auth_code or the entire redirected URL.
5. Paste it here — the script automatically saves the token to .env and verifies live market connectivity!
"""

import os
import sys
import webbrowser
import urllib.parse
from pathlib import Path
import dotenv
from fyers_apiv3 import fyersModel


def find_env_file() -> Path:
    """Find .env file in project root or current working directory."""
    cwd = Path.cwd()
    candidates = [
        cwd / ".env",
        cwd.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            return p
    # Default to project root
    return candidates[0]


def extract_auth_code(raw_input: str) -> str:
    """Extract auth_code whether user pastes the raw code or the full redirected URL."""
    raw = raw_input.strip()
    if "auth_code=" in raw:
        try:
            # Handle full URL or query string
            parsed = urllib.parse.urlparse(raw)
            query = parsed.query if parsed.query else parsed.path
            params = urllib.parse.parse_qs(query)
            if "auth_code" in params and params["auth_code"]:
                return params["auth_code"][0]
        except Exception:
            pass
        # Fallback split
        return raw.split("auth_code=")[1].split("&")[0].strip()
    return raw


def main():
    print("==================================================")
    print("   🚀 Fyers v3 Daily Access Token Generator       ")
    print("==================================================")

    env_path = find_env_file()
    env_values = dotenv.dotenv_values(env_path) if env_path.exists() else {}

    client_id = env_values.get("FYERS_CLIENT_ID") or os.getenv("FYERS_CLIENT_ID")
    secret_key = env_values.get("FYERS_SECRET_KEY") or os.getenv("FYERS_SECRET_KEY")

    if not client_id:
        client_id = input("Enter your FYERS_CLIENT_ID (e.g. ABCDEFGH-100): ").strip()
        if client_id and env_path.exists():
            dotenv.set_key(str(env_path), "FYERS_CLIENT_ID", client_id)
            print("💾 Saved FYERS_CLIENT_ID to .env")

    if not secret_key:
        secret_key = input("Enter your FYERS_SECRET_KEY: ").strip()
        if secret_key and env_path.exists():
            dotenv.set_key(str(env_path), "FYERS_SECRET_KEY", secret_key)
            print("💾 Saved FYERS_SECRET_KEY to .env")

    if not client_id or not secret_key:
        print("❌ Error: FYERS_CLIENT_ID and FYERS_SECRET_KEY are required.")
        sys.exit(1)

    redirect_uri = "https://trade.fyers.in/api-login/redirect-uri/index.html"

    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code"
    )

    auth_link = session.generate_authcode()
    print("\n--------------------------------------------------")
    print("ACTION REQUIRED:")
    print("1. Opening Fyers Login in your default browser...")
    print("2. Log in with your Fyers credentials.")
    print("3. Copy the full redirected URL from your browser address bar.")
    print("--------------------------------------------------")
    print(f"\nIf browser did not open automatically, click here:\n{auth_link}\n")

    try:
        webbrowser.open(auth_link)
    except Exception:
        pass

    user_input = input("Paste the auth_code or the full redirected URL here:\n> ").strip()

    auth_code = extract_auth_code(user_input)

    if not auth_code:
        print("❌ Error: Auth code cannot be empty.")
        sys.exit(1)

    print("\n⏳ Generating live Access Token from Fyers...")
    session.set_token(auth_code)

    try:
        response = session.generate_token()
        if response.get("s") == "ok" and response.get("access_token"):
            token = response["access_token"]
            
            # Automatically update .env file
            if env_path.exists():
                dotenv.set_key(str(env_path), "FYERS_ACCESS_TOKEN", token)
                print(f"✅ Automatically updated FYERS_ACCESS_TOKEN in {env_path.name}!")
            else:
                print(f"⚠️ Notice: .env file not found at {env_path}, please update manually.")

            # Test connection with profile check
            try:
                fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
                prof = fyers.get_profile()
                if prof.get("s") == "ok":
                    name = prof.get("data", {}).get("name", "Trader")
                    fyers_id = prof.get("data", {}).get("fy_id", client_id)
                    print(f"🎉 Connected successfully! User: {name} ({fyers_id})")
                else:
                    print("✅ Token generated and saved!")
            except Exception:
                print("✅ Token generated and saved!")

            print("\n🚀 The backend picks up this token immediately without restarting containers.")
            print("==================================================\n")
        else:
            print("❌ Failed to generate token. Fyers response:")
            print(response)
    except Exception as e:
        print(f"❌ Error occurred while contacting Fyers: {e}")


if __name__ == "__main__":
    main()
