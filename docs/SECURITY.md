# Aura Platform - Security Documentation

## 🔒 Security Overview

The Aura Platform implements **cryptographic signature verification** using Ed25519 to secure all API communications. This modern security approach ensures request authenticity, integrity, and prevents replay attacks.

**Current Implementation**:
- **Algorithm**: Ed25519 (PyNaCl library)
- **Authentication**: DID-based identity (`did:key:public_key_hex`)
- **Signature Format**: `METHOD + PATH + TIMESTAMP + BodyHash`
- **Replay Protection**: Timestamp validation (±60 seconds tolerance)

## 🔐 Authentication and Authorization

### Agent Identity (The Guard's Badge)

**Decentralized Identifiers (DIDs)**:
- Each agent is identified by a unique DID in the format: `did:key:public_key_hex`
- DIDs are self-sovereign identifiers derived from the agent's Ed25519 public key.
- The hive verifies that the signature provided in the headers was created by the owner of the public key mentioned in the DID.

**Agent Setup**:
1. Agents generate an Ed25519 key pair using `AgentWallet()` (or standard OpenSSL tools).
2. The public key is hex-encoded and prefixed with `did:key:`.
3. Agents sign all requests using their private key.
4. The API Gateway (Guard Bee) verifies signatures on-the-fly.

### Signature Verification

**Request Signing Process**:

```
message = method + path + timestamp + body_hash
signature = ed25519.sign(private_key, message)
```

**Components**:
- `method`: HTTP method in uppercase (e.g., "POST").
- `path`: Request path (e.g., "/v1/negotiate").
- `timestamp`: Unix timestamp (seconds) from `X-Timestamp` header.
- `body_hash`: SHA-256 hash of the canonical JSON request body (sorted keys, no whitespace).

**Required Headers**:

| Header | Description | Example |
|--------|-------------|---------|
| `X-Agent-ID` | Agent's DID | `did:key:663055bbbef3f78ecaec5d32a21e201fda6040588835171fb717efbd7bd6fc6c` |
| `X-Timestamp` | Unix timestamp | `1735689600` |
| `X-Signature` | Ed25519 signature (hex) | `cfef8b600ffd80b40eff1960978b91ea58672efae56fbc217f...` |

### Signature Verification Algorithm

```python
from agent_identity import AgentWallet

# Example: Generate a wallet and sign a request
wallet = AgentWallet()
print(f"Agent DID: {wallet.did}")

# Create a request payload
payload = {
    "item_id": "hotel_alpha",
    "bid_amount": 850.0,
    "currency": "USD",
    "agent_did": wallet.did
}

# Sign the request
method = "POST"
path = "/v1/negotiate"
x_agent_id, x_timestamp, x_signature = wallet.sign_request(method, path, payload)

print(f"Security Headers:")
print(f"  X-Agent-ID: {x_agent_id}")
print(f"  X-Timestamp: {x_timestamp}")
print(f"  X-Signature: {x_signature[:50]}...")

# The API Gateway will verify this signature using the public key from the DID
```

## 🛡️ Security Mechanisms

### 1. Request Replay Protection

**Timestamp Validation**:
- Each request includes an `X-Timestamp` header (Unix seconds).
- Server validates that the timestamp is within an acceptable range (**±60 seconds**).
- Prevents replay attacks by rejecting stale requests.

**Implementation (conceptual)**:
```python
import time

def validate_timestamp(timestamp_val):
    try:
        request_time = int(timestamp_val)
        current_time = int(time.time())
        time_diff = abs(current_time - request_time)
        
        # Allow ±60 seconds clock skew
        return time_diff <= 60
    except ValueError:
        return False
```

### 2. Rate Limiting

**Redis-Backed Rate Limiting**:
- Prevents abuse and DoS attacks
- Default: 100 requests per minute per agent
- Uses sliding window algorithm

**Implementation**:
```python
from datetime import UTC, datetime
from redis import Redis

def check_rate_limit(agent_id):
    """
    Check if agent has exceeded rate limits.
    
    Args:
        agent_id: Agent's DID
        
    Returns:
        tuple: (is_allowed: bool, message: str)
    """
    redis = Redis()
    current_minute = datetime.now(UTC).strftime("%Y-%m-%d-%H-%M")
    key = f"rate_limit:{agent_id}:{current_minute}"
    
    # Increment request count
    count = redis.incr(key)
    
    # Set expiration on first request
    if count == 1:
        redis.expire(key, 60)  # 60 second window
    
    # Check if limit exceeded
    if count > 100:
        return False, f"Rate limit exceeded: {count}/100"
    
    return True, f"OK: {count}/100 remaining"
```

### 3. Request Integrity

**Body Hash Verification**:
- Request body is hashed using SHA-256
- Hash is included in signature calculation
- Prevents tampering with request content

**Implementation**:
```python
import hashlib
import json

def calculate_body_hash(body):
    """
    Calculate SHA-256 hash of request body for signature verification.
    
    Args:
        body: Request body (dict or string)
        
    Returns:
        str: Hexadecimal SHA-256 hash
    """
    if isinstance(body, dict):
        body_str = json.dumps(body, sort_keys=True, separators=(',', ':'))
    else:
        body_str = str(body)
    
    return hashlib.sha256(body_str.encode('utf-8')).hexdigest()
```

### 4. Hidden Knowledge Pattern

**Floor Price Protection**:
- Agents never see actual floor prices
- Core service enforces floor price logic internally
- Prevents agents from gaming the system

**Implementation**:
```python
# In pricing strategy
if bid < item.floor_price:
    # Counter with floor price, but don't reveal it's the floor
    response.countered.proposed_price = calculate_counter_price(item.floor_price)
    response.countered.reason_code = "NEGOTIATION_ONGOING"  # Generic reason
```

## 🔍 Threat Model and Mitigations

### Potential Attack Vectors

| Threat | Description | Mitigation |
|--------|-------------|------------|
| **Replay Attacks** | Reusing valid signed requests | Timestamp validation, short-lived sessions |
| **Tampering** | Modifying request content | Signature verification, body hash |
| **Impersonation** | Pretending to be another agent | DID verification, public key infrastructure |
| **DoS Attacks** | Flooding with requests | Rate limiting, request validation |
| **Information Leakage** | Exposing sensitive data | Hidden knowledge pattern, minimal error details |
| **Man-in-the-Middle** | Intercepting communications | TLS encryption (planned) |
| **Brute Force** | Trying many bids quickly | Rate limiting, negotiation cooldowns |

### Specific Attack Scenarios

#### 1. Replay Attack

**Scenario**: Attacker captures a valid signed request and replays it.

**Mitigation**:
- Timestamp validation rejects stale requests
- Session tokens are short-lived (10 minute TTL)
- Each request must have unique timestamp

#### 2. Bid Tampering

**Scenario**: Agent modifies bid amount after signing.

**Mitigation**:
- Body hash included in signature
- Any modification invalidates the signature
- Server verifies signature before processing

#### 3. Agent Impersonation

**Scenario**: Attacker pretends to be a legitimate agent.

**Mitigation**:
- DID must be registered with valid public key
- Signature must match registered public key
- Unregistered agents are rejected immediately

#### 4. Rate Limit Bypass

**Scenario**: Agent tries to bypass rate limits.

**Mitigation**:
- Redis-backed distributed rate limiting
- Rate limits per agent DID
- IP-based rate limiting as secondary measure

## 🔐 Key Management

### Agent Key Management

**Key Generation**:
```bash
# Using OpenSSL
openssl genpkey -algorithm ed25519 -out private_key.pem
openssl pkey -in private_key.pem -pubout -out public_key.pem
```

**Key Storage**:
- **Private Key**: Stored securely by agent, never transmitted
- **Public Key**: Registered with platform, stored in database
- **Key Rotation**: Agents should rotate keys periodically

### Platform Key Management

**Database Storage**:
- Public keys stored in `agents` table
- Associated with agent DID
- Indexed for fast lookup

**Key Rotation Support**:
- Agents can update their public key
- Old keys are invalidated immediately
- Transition period for active sessions

## 🛑 Security Headers

### Required Security Headers

```
X-Agent-ID: did:key:public_key_hex
X-Timestamp: 1735689600
X-Signature: a1b2c3d4...
```

### Optional Security Headers

```
X-Agent-Token: JWT_token_for_additional_auth
X-Request-ID: unique_request_identifier
X-Client-Version: agent_software_version
```

## 🔒 Implementation Details

**AgentWallet Class**:
- Located in `agent_identity.py`
- Handles key generation, signing, and verification
- Supports both full wallets (with private keys) and view-only wallets (public key only)

**Security Module**:
- Located in `api-gateway/src/security.py`
- FastAPI dependency for signature verification
- Validates headers, timestamps, and signatures
- Stores parsed body in `request.state` for endpoint reuse

**API Gateway Integration**:
- Both `/v1/negotiate` and `/v1/search` endpoints use the `verify_signature` dependency
- Endpoints retrieve the parsed body from `request.state.parsed_body`
- Verified agent DID is passed to the endpoint for use in business logic

## 📊 Security Monitoring

### Logging Security Events

**Security-Related Logs**:
```json
{
  "level": "warn",
  "event": "security.invalid_signature",
  "agent_id": "did:agent:unknown",
  "timestamp": "2023-12-01T12:00:00Z",
  "ip_address": "192.168.1.100",
  "user_agent": "AuraAgent/1.0",
  "error": "Signature verification failed"
}
```

### Security Metrics

**Key Metrics to Monitor**:
- Failed authentication attempts
- Rate limit violations
- Invalid signature attempts
- Unregistered agent requests
- High-value transaction attempts

### Alerting

**Alert Conditions**:
- More than 10 failed authentications per minute
- Rate limit violations from single IP
- Unusual bid patterns (e.g., rapid sequential bids)
- Attempts to access non-existent items

## 🛡️ Defense in Depth

### Layered Security Approach

```
Client → [TLS] → API Gateway → [Signature Verification] → [Rate Limiting] →
[Request Validation] → Core Service → [Business Logic] → [Database Access] → Response
```

### Security Layers

1. **Transport Layer**: TLS encryption (planned)
2. **Authentication Layer**: Signature verification
3. **Authorization Layer**: DID validation
4. **Rate Limiting Layer**: Abuse prevention
5. **Input Validation Layer**: Request sanitization
6. **Business Logic Layer**: Floor price enforcement
7. **Data Access Layer**: Database security

## 🔧 Security Best Practices

### For Platform Operators

1. **Regular Key Rotation**: Rotate platform secrets periodically
2. **Monitor Security Logs**: Watch for unusual patterns
3. **Update Dependencies**: Keep all libraries up to date
4. **Database Security**: Encrypt sensitive data at rest
5. **Network Security**: Use firewalls and network segmentation
6. **Backup Strategy**: Regular backups of critical data

### For Agent Developers

1. **Secure Key Storage**: Protect private keys
2. **Proper Signing**: Sign all requests correctly
3. **Error Handling**: Handle security errors gracefully
4. **Rate Limit Awareness**: Respect rate limits
5. **Session Management**: Handle session tokens properly
6. **Input Validation**: Validate server responses

## 🔮 Future Security Enhancements

### Planned Security Features

1. **TLS Encryption**: End-to-end encryption for all communications
2. **OAuth 2.0 Support**: Alternative authentication method
3. **Hardware Security Modules**: For key management
4. **Anomaly Detection**: ML-based attack detection
5. **Audit Logging**: Comprehensive security audit trails
6. **Multi-Factor Authentication**: For high-value transactions

### Security Roadmap

| Feature | Priority | Target Version |
|---------|----------|----------------|
| TLS Encryption | High | v1.1 |
| OAuth 2.0 Support | Medium | v1.2 |
| Audit Logging | High | v1.1 |
| Anomaly Detection | Medium | v1.3 |
| HSM Integration | Low | v2.0 |

## 📚 Security References

### Cryptographic Standards
- **Ed25519**: [RFC 8032](https://tools.ietf.org/html/rfc8032)
- **SHA-256**: [FIPS 180-4](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.180-4.pdf)

### Security Best Practices
- **OWASP Top 10**: [https://owasp.org/www-project-top-ten/](https://owasp.org/www-project-top-ten/)
- **CIS Controls**: [https://www.cisecurity.org/controls/](https://www.cisecurity.org/controls/)
- **NIST Cybersecurity Framework**: [https://www.nist.gov/cyberframework](https://www.nist.gov/cyberframework)

## 🤝 Security Contact

For security vulnerabilities or concerns, please contact:

- **Email**: security@aura-platform.io
- **GitHub Security**: Report via GitHub Security Advisories
- **PGP Key**: Available upon request for encrypted communication

## 📝 Security Policy

### Responsible Disclosure

1. **Report**: Submit vulnerability reports to security@aura-platform.io
2. **Acknowledge**: We'll acknowledge receipt within 48 hours
3. **Investigate**: Our team will investigate and verify the issue
4. **Fix**: We'll develop and test a fix
5. **Disclose**: We'll coordinate public disclosure
6. **Credit**: Researchers will be credited in release notes

### Supported Versions

| Version | Supported | Security Updates |
|---------|-----------|------------------|
| v1.0.x | ✅ Yes | ✅ Yes |
| v0.x.x | ❌ No | ❌ No |

## 🙏 Acknowledgments

The Aura Platform security model is inspired by best practices from:
- **Decentralized Identity Foundation** (DIF)
- **W3C Decentralized Identifier** (DID) standards
- **IETF Security Standards**
- **OWASP Application Security**

We appreciate the security research community's contributions to making the platform more secure.