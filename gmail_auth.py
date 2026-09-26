from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json",
    SCOPES
)

credentials = flow.run_local_server(
    port=8080,
    access_type="offline",
    prompt="consent"
)

with open("token.json", "w") as token:
    token.write(credentials.to_json())

print("Gmail authorization successful!")
print("token.json created.")