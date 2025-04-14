#!/bin/bash
SHEET_ID="1LNkLSMD6Cqkle_GlT7hkzLKeJC3DyDkDyUqmuSH3c50"
SHEET_NAME="Collective Data"
PRIVATE_KEY_FILE="private_key.pem"
CLIENT_EMAIL=$(cat credentials.json | jq -r ".client_email")
HEADER="{\"alg\":\"RS256\",\"typ\":\"JWT\"}"
HEADER_BASE64=$(echo -n "$HEADER" | base64 | tr -d "=" | tr "/+" "_-")
NOW=$(($(date +%s)))
EXPIRE=$((NOW + 3600))
CLAIMS="{\"iss\":\"$CLIENT_EMAIL\",\"scope\":\"https://www.googleapis.com/auth/spreadsheets.readonly\",\"aud\":\"https://oauth2.googleapis.com/token\",\"exp\":$EXPIRE,\"iat\":$NOW}"
CLAIMS_BASE64=$(echo -n "$CLAIMS" | base64 | tr -d "=" | tr "/+" "_-")
UNSIGNED_JWT="${HEADER_BASE64}.${CLAIMS_BASE64}"
SIGNATURE=$(echo -n "$UNSIGNED_JWT" | openssl dgst -binary -sha256 -sign "$PRIVATE_KEY_FILE" | base64 | tr -d "=" | tr "/+" "_-")
SIGNED_JWT="${UNSIGNED_JWT}.${SIGNATURE}"
TOKEN_RESPONSE=$(curl -s -d "grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=$SIGNED_JWT" https://oauth2.googleapis.com/token)
ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r ".access_token")
if [ "$ACCESS_TOKEN" == "null" ]; then
  echo "Error getting access token: $TOKEN_RESPONSE"
  exit 1
fi
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" "https://sheets.googleapis.com/v4/spreadsheets/$SHEET_ID/values/${SHEET_NAME// /%20}!A1:Z1"
