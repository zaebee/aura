package aura.gateway.vision

import future.keywords.if

# Default to deny
default allow = false

# Maximum allowed image size (5MB in bytes)
max_content_length := 5242880

# Main allow rule
allow if {
    valid_auth_token
    valid_content_length
}

# Check for presence of auth token (X-Agent-Signature or similar)
# In Aura Gateway, authentication is typically handled by DID signatures.
# Here we check if the required security headers are present.
valid_auth_token if {
    input.headers["x-agent-id"]
    input.headers["x-signature"]
    input.headers["x-timestamp"]
}

# Validate Content-Length to prevent DoS by large images
valid_content_length if {
    content_length := to_number(input.headers["content-length"])
    content_length <= max_content_length
}

# Error messages for debugging/feedback
errors["Missing authentication headers"] if {
    not valid_auth_token
}

errors["Image size exceeds maximum limit (5MB)"] if {
    content_length := to_number(input.headers["content-length"])
    content_length > max_content_length
}
