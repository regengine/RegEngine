#!/bin/bash
set -e

MASTER_KEY="admin-master-key-dev"
BASE_URL="http://localhost:8400/v1"

echo "1. Testing Auth Rejection..."
AUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/admin/keys")
if [ "$AUTH_CODE" != "401" ]; then
  echo "   ❌ Expected 401, got $AUTH_CODE"
  exit 1
fi
echo "   ✅ (401 received)"

echo "2. Creating API Key..."
RESPONSE=$(curl -s -X POST "$BASE_URL/admin/keys" \
  -H "X-Admin-Key: $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Key", "tenant_id": "00000000-0000-0000-0000-000000000001"}')

KEY_ID=$(echo $RESPONSE | jq -r '.key_id')
if [ -z "$KEY_ID" ] || [ "$KEY_ID" = "null" ]; then
  echo "   ❌ Failed to create key: $RESPONSE"
  exit 1
fi
echo "   ✅ Created Key ID: $KEY_ID"

echo "3. Listing Keys..."
LIST_RESPONSE=$(curl -s -X GET "$BASE_URL/admin/keys" -H "X-Admin-Key: $MASTER_KEY")
FOUND=$(echo $LIST_RESPONSE | jq -r --arg KEY_ID "$KEY_ID" '.[] | select(.key_id == $KEY_ID) | .key_id')
if [ -z "$FOUND" ]; then
    echo "   ❌ Key not found in list. Response: $LIST_RESPONSE"
    exit 1
fi
echo "   ✅ Key found in list"

echo "4. Creating Hallucination Record..."
DOC_HASH="verify_hash_$(date +%s)"
REC_RESPONSE=$(curl -s -X POST "$BASE_URL/admin/review/hallucinations" \
  -H "X-Admin-Key: $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"document_id\": \"doc_123\",
    \"doc_hash\": \"$DOC_HASH\",
    \"extractor\": \"ollama-llama3\",
    \"confidence_score\": 0.75,
    \"extraction\": {\"foo\": \"bar\"},
    \"text_raw\": \"Questionable text\"
  }")
REC_REVIEW_ID=$(echo $REC_RESPONSE | jq -r '.review_id // empty')
if [ -z "$REC_REVIEW_ID" ]; then
    echo "   ❌ Failed to create record: $REC_RESPONSE"
    exit 1
fi
echo "   ✅ Record created"

echo "5. Verifying Review List..."
LIST_REVIEW_RESPONSE=$(curl -s -X GET "$BASE_URL/admin/review/hallucinations?status=PENDING" -H "X-Admin-Key: $MASTER_KEY")
REVIEW_ID=$(echo $LIST_REVIEW_RESPONSE | jq -r --arg DOC_HASH "$DOC_HASH" '.items[] | select(.doc_hash == $DOC_HASH) | .review_id')

if [ -z "$REVIEW_ID" ]; then
  echo "   ❌ Failed to find review item. Response len: ${#LIST_REVIEW_RESPONSE}"
  echo "   DEBUG: $LIST_REVIEW_RESPONSE"
  exit 1
fi
echo "   ✅ Found Review ID: $REVIEW_ID"

echo "6. Approving Item..."
APPROVE_RESPONSE=$(curl -s -X POST "$BASE_URL/admin/review/hallucinations/$REVIEW_ID/approve" \
  -H "X-Admin-Key: $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"reviewer_id": "auto-tester"}')
STATUS=$(echo $APPROVE_RESPONSE | jq -r '.status')

if [ "$STATUS" != "APPROVED" ]; then
    echo "   ❌ Approval failed. Status: $STATUS. Response: $APPROVE_RESPONSE"
    exit 1
fi
echo "   ✅ Item approved"
