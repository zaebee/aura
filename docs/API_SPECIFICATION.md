# Aura API Gateway - OpenAPI Specification

## 📋 Overview

This document provides the OpenAPI specification for the Aura Platform API Gateway. The gateway provides RESTful endpoints for AI agents to interact with the negotiation and search services.

## 🔐 Security

All endpoints require the following security headers:

### Required Headers

| Header | Type | Description | Example |
|--------|------|-------------|---------|
| `X-Agent-ID` | string | Agent's Decentralized Identifier (DID) | `did:agent:007` |
| `X-Timestamp` | string | ISO 8601 timestamp of request | `2023-12-01T12:00:00Z` |
| `X-Signature` | string | Ed25519 signature of request | `base64_encoded_signature` |

### Signature Verification

The signature is generated using the Ed25519 algorithm:

```
signature = ed25519.sign(
    private_key,
    method + path + timestamp + body_hash
)
```

Where:
- `method`: HTTP method (e.g., "POST")
- `path`: Request path (e.g., "/v1/negotiate")
- `timestamp`: Value from `X-Timestamp` header
- `body_hash`: SHA-256 hash of the request body

## 📡 Endpoints

### Base URL

```
http://localhost:8000
```

### 1. Negotiate Endpoint

**POST** `/v1/negotiate`

#### Description

Initiates a negotiation session for a specific item. The agent submits a bid, and the system responds with acceptance, counteroffer, rejection, or a request for human intervention.

#### Request

**Headers:**
```
Content-Type: application/json
X-Agent-ID: did:agent:007
X-Timestamp: 2023-12-01T12:00:00Z
X-Signature: base64_encoded_signature
```

**Body:**
```json
{
  "item_id": "string",
  "bid_amount": "number",
  "currency": "string",
  "agent_did": "string"
}
```

**Schema:**
```yaml
NegotiationRequest:
  type: object
  required:
    - item_id
    - bid_amount
    - agent_did
  properties:
    item_id:
      type: string
      description: Unique identifier of the item being negotiated
      example: "hotel_alpha"
    bid_amount:
      type: number
      format: float
      description: The proposed bid amount
      example: 850.0
      minimum: 0.01
    currency:
      type: string
      description: Currency code (ISO 4217)
      example: "USD"
      default: "USD"
      enum: ["USD", "EUR", "GBP", "JPY"]
    agent_did:
      type: string
      description: Agent's Decentralized Identifier
      example: "did:agent:007"
```

#### Responses

**200 OK - Successful Negotiation**
```json
{
  "session_token": "string",
  "status": "accepted",
  "valid_until": "integer",
  "data": "object"
}
```

**Response Types:**

1. **Accepted Response** (`status: "accepted"`)
```json
{
  "session_token": "sess_abc123",
  "status": "accepted",
  "valid_until": 1735689600,
  "data": {
    "final_price": 850.0,
    "reservation_code": "MISTRAL-1234567890"
  }
}
```

2. **Countered Response** (`status: "countered"`)
```json
{
  "session_token": "sess_abc123",
  "status": "countered",
  "valid_until": 1735689600,
  "data": {
    "proposed_price": 950.0,
    "message": "We cannot accept less than $950 for this premium item.",
    "reason_code": "BELOW_FLOOR"
  }
}
```

3. **Rejected Response** (`status: "rejected"`)
```json
{
  "session_token": "sess_abc123",
  "status": "rejected",
  "valid_until": 1735689600,
  "data": {
    "reason_code": "OFFER_TOO_LOW"
  }
}
```

4. **UI Required Response** (`status: "ui_required"`)
```json
{
  "session_token": "sess_abc123",
  "status": "ui_required",
  "valid_until": 1735689600,
  "action_required": {
    "template": "high_value_confirm",
    "context": {
      "reason": "Bid of $1200 exceeds security threshold"
    }
  }
}
```

**Response Schema:**
```yaml
NegotiationResponse:
  type: object
  properties:
    session_token:
      type: string
      description: Unique token for this negotiation session
      example: "sess_abc123"
    status:
      type: string
      description: Result of the negotiation
      enum: ["accepted", "countered", "rejected", "ui_required"]
      example: "accepted"
    valid_until:
      type: integer
      description: Unix timestamp when this session expires
      example: 1735689600
    data:
      type: object
      description: Response-specific data (structure varies by status)
      oneOf:
        - $ref: '#/components/schemas/AcceptedData'
        - $ref: '#/components/schemas/CounteredData'
        - $ref: '#/components/schemas/RejectedData'
    action_required:
      type: object
      description: UI action required (only for ui_required status)
      properties:
        template:
          type: string
          description: UI template identifier
          example: "high_value_confirm"
        context:
          type: object
          description: Context data for UI rendering
          additionalProperties:
            type: string

AcceptedData:
  type: object
  properties:
    final_price:
      type: number
      format: float
      description: Final agreed price
      example: 850.0
    reservation_code:
      type: string
      description: Unique reservation code
      example: "MISTRAL-1234567890"

CounteredData:
  type: object
  properties:
    proposed_price:
      type: number
      format: float
      description: Counteroffer price
      example: 950.0
    message:
      type: string
      description: Human-readable message
      example: "We cannot accept less than $950 for this premium item."
    reason_code:
      type: string
      description: Machine-readable reason code
      example: "BELOW_FLOOR"
      enum: ["BELOW_FLOOR", "NEGOTIATION_ONGOING", "MARKET_CONDITIONS"]

RejectedData:
  type: object
  properties:
    reason_code:
      type: string
      description: Reason for rejection
      example: "OFFER_TOO_LOW"
      enum: ["OFFER_TOO_LOW", "ITEM_NOT_FOUND", "AI_ERROR"]
```

**Error Responses:**

**400 Bad Request**
```json
{
  "detail": "Invalid request parameters"
}
```

**401 Unauthorized**
```json
{
  "detail": "Invalid or missing authentication"
}
```

**429 Too Many Requests**
```json
{
  "detail": "Rate limit exceeded"
}
```

**500 Internal Server Error**
```json
{
  "detail": "Core service error"
}
```

### 2. Search Endpoint

**POST** `/v1/search`

#### Description

Performs semantic search across the inventory using vector embeddings. Returns items ranked by similarity to the query.

#### Request

**Headers:**
```
Content-Type: application/json
X-Agent-ID: did:agent:007
X-Timestamp: 2023-12-01T12:00:00Z
X-Signature: base64_encoded_signature
```

**Body:**
```json
{
  "query": "string",
  "limit": "integer",
  "min_similarity": "number"
}
```

**Schema:**
```yaml
SearchRequest:
  type: object
  required:
    - query
  properties:
    query:
      type: string
      description: Search query text
      example: "Luxury stay with spa and ocean view"
    limit:
      type: integer
      description: Maximum number of results to return
      example: 3
      default: 5
      minimum: 1
      maximum: 50
    min_similarity:
      type: number
      format: float
      description: Minimum similarity score (0.0 to 1.0)
      example: 0.7
      minimum: 0.0
      maximum: 1.0
```

#### Responses

**200 OK - Successful Search**
```json
{
  "results": [
    {
      "id": "string",
      "name": "string",
      "price": "number",
      "score": "number",
      "details": "string"
    }
  ]
}
```

**Response Schema:**
```yaml
SearchResponse:
  type: object
  properties:
    results:
      type: array
      items:
        $ref: '#/components/schemas/SearchResultItem'

SearchResultItem:
  type: object
  properties:
    id:
      type: string
      description: Unique item identifier
      example: "hotel_alpha"
    name:
      type: string
      description: Item name
      example: "Luxury Beach Resort"
    price:
      type: number
      format: float
      description: Base price of the item
      example: 1000.0
    score:
      type: number
      format: float
      description: Similarity score (0.0 to 1.0, higher is better)
      example: 0.95
      minimum: 0.0
      maximum: 1.0
    details:
      type: string
      description: Brief description or snippet
      example: "5-star resort with private beach"
```

**Error Responses:**

**400 Bad Request**
```json
{
  "detail": "Invalid search parameters"
}
```

**500 Internal Server Error**
```json
{
  "detail": "Core service search error"
}
```

## 📊 Response Status Types

### Accepted (`status: "accepted"`)

**Description**: The bid has been accepted. The agent can proceed with the transaction using the provided reservation code.

**Use Case**: Bid meets or exceeds the floor price and business rules.

**Example Scenario**: Agent bids $850 for an item with $800 floor price.

### Countered (`status: "countered"`)

**Description**: The bid is too low, but the system is willing to negotiate. A counteroffer is proposed.

**Use Case**: Bid is below floor price but within a negotiable range.

**Example Scenario**: Agent bids $700 for an item with $800 floor price, system counters with $800.

**Reason Codes**:
- `BELOW_FLOOR`: Bid is below the minimum acceptable price
- `NEGOTIATION_ONGOING`: Part of an ongoing negotiation sequence
- `MARKET_CONDITIONS`: Current market conditions warrant a higher price

### Rejected (`status: "rejected"`)

**Description**: The bid is unacceptable and no counteroffer is made.

**Use Case**: Bid is unreasonably low or item doesn't exist.

**Example Scenario**: Agent bids $1 for a premium item.

**Reason Codes**:
- `OFFER_TOO_LOW`: Bid is unreasonably low
- `ITEM_NOT_FOUND`: Requested item doesn't exist
- `AI_ERROR`: LLM decision making failed

### UI Required (`status: "ui_required"`)

**Description**: Human intervention is required before proceeding. The agent must present this to a human for approval.

**Use Case**: High-value transactions, suspicious activity, or policy requirements.

**Example Scenario**: Agent bids $1200 for an item, triggering security review.

**Template Types**:
- `high_value_confirm`: Confirmation required for high-value transaction
- `suspicious_activity`: Potential fraud detection
- `policy_violation`: Violation of business policies

## 🎯 Usage Examples

### Example 1: Successful Negotiation

**Request:**
```bash
curl -X POST http://localhost:8000/v1/negotiate \
  -H "Content-Type: application/json" \
  -H "X-Agent-ID: did:agent:007" \
  -H "X-Timestamp: 2023-12-01T12:00:00Z" \
  -H "X-Signature: base64_signature" \
  -d '{
    "item_id": "hotel_alpha",
    "bid_amount": 850.0,
    "currency": "USD",
    "agent_did": "did:agent:007"
  }'
```

**Response:**
```json
{
  "session_token": "sess_abc123",
  "status": "accepted",
  "valid_until": 1735689600,
  "data": {
    "final_price": 850.0,
    "reservation_code": "MISTRAL-1234567890"
  }
}
```

### Example 2: Counteroffer

**Request:**
```bash
curl -X POST http://localhost:8000/v1/negotiate \
  -H "Content-Type: application/json" \
  -H "X-Agent-ID: did:agent:007" \
  -H "X-Timestamp: 2023-12-01T12:00:00Z" \
  -H "X-Signature: base64_signature" \
  -d '{
    "item_id": "hotel_alpha",
    "bid_amount": 700.0,
    "currency": "USD",
    "agent_did": "did:agent:007"
  }'
```

**Response:**
```json
{
  "session_token": "sess_abc123",
  "status": "countered",
  "valid_until": 1735689600,
  "data": {
    "proposed_price": 800.0,
    "message": "We cannot accept less than $800 for this premium item.",
    "reason_code": "BELOW_FLOOR"
  }
}
```

### Example 3: Semantic Search

**Request:**
```bash
curl -X POST http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -H "X-Agent-ID: did:agent:007" \
  -H "X-Timestamp: 2023-12-01T12:00:00Z" \
  -H "X-Signature: base64_signature" \
  -d '{
    "query": "Luxury stay with spa and ocean view",
    "limit": 3
  }'
```

**Response:**
```json
{
  "results": [
    {
      "id": "hotel_alpha",
      "name": "Luxury Beach Resort",
      "price": 1000.0,
      "score": 0.95,
      "details": "5-star resort with private beach and spa facilities"
    },
    {
      "id": "hotel_beta",
      "name": "Ocean View Suite",
      "price": 800.0,
      "score": 0.87,
      "details": "Luxury suite with panoramic ocean views"
    }
  ]
}
```

## 🔧 API Versioning

The API uses URL-based versioning:

```
/v1/negotiate
/v1/search
```

Future versions will be added as:

```
/v2/negotiate
/v2/search
```

## 📊 Rate Limiting

- **Default Limit**: 100 requests per minute per agent
- **Response Headers**:
  - `X-RateLimit-Limit`: Maximum allowed requests
  - `X-RateLimit-Remaining`: Remaining requests in current window
  - `X-RateLimit-Reset`: Time when limit resets (Unix timestamp)

## 📚 OpenAPI Specification

A machine-readable OpenAPI specification is available. This document serves as the human-readable version with additional context and examples.

## 🤝 Support

For API-related issues or questions, please refer to the main README or open an issue in the GitHub repository.