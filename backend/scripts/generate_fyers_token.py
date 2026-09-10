import os
import sys
from fyers_apiv3 import fyersModel

def main():
    print("=== Fyers Access Token Generator ===")
    
    client_id = input("1. Enter your FYERS_CLIENT_ID (e.g. ABCDEFGH-100): ").strip()
    secret_key = input("2. Enter your FYERS_SECRET_KEY: ").strip()
    
    # We use a dummy redirect URI specifically for this local script generation
    # Make sure this exact URI is added to your Fyers App Dashboard under Redirect URIs!
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
    print("1. Please click the link below to open the Fyers Login page.")
    print("2. Login with your Mobile/Client ID, PIN, and OTP.")
    print("3. After a successful login, you will be redirected to a dummy page.")
    print("4. Look at the URL of that page. It will look like this:")
    print("   https://trade.fyers.in/api-login/redirect-uri/index.html?s=ok&auth_code=YOUR_AUTH_CODE_HERE")
    print("--------------------------------------------------\n")
    print(f"🔗 CLICK HERE -> {auth_link}\n")

    auth_code = input("Paste the YOUR_AUTH_CODE_HERE from the URL: ").strip()

    if not auth_code:
        print("Error: Auth code cannot be empty.")
        sys.exit(1)

    print("\nGenerating Access Token...")
    session.set_token(auth_code)
    try:
        response = session.generate_token()
        if response.get("s") == "ok":
            print("\n✅ SUCCESS! Here is your FYERS_ACCESS_TOKEN:")
            print("\n==================================================")
            print(response["access_token"])
            print("==================================================\n")
            print("Copy the token above and paste it into your .env file!")
        else:
            print("❌ Failed to generate token. API Response:")
            print(response)
    except Exception as e:
        print(f"❌ Error occurred: {e}")

if __name__ == "__main__":
    main()
