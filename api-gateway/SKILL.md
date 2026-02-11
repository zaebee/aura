# Vision Cortex (Perception Gateway)

## Biological Metaphor: The Occipital Lobe
The Vision Cortex represents the Hive's ability to process visual signals from the environment (Terrestrial Bytes) and translate them into structured understanding (Celestial Thought). It acts as the primary sensory gateway for multimodal data, ensuring that raw pixels are distilled into actionable Hive assets before they reach the higher reasoning centers.

## External Contract: `/v1/vision/analyze`

This endpoint allows external agents or sensors to submit visual data for structural analysis and asset mapping.

### Endpoint Specification
- **URL:** `/v1/vision/analyze`
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`
- **Authentication:** Verified DID Signature (X-Agent-ID, X-Timestamp, X-Signature)

### Request Parameters
| Field | Type | Description |
|---|---|---|
| `file` | Binary | The image file to be analyzed (max 5MB). |
| `focus` | String | (Optional) A hint for the perception engine (e.g., "automotive", "real-estate"). |

### Response Schema (JSON)
```json
{
  "identifier": "perceived-sha256-hash",
  "name": "Identified Object Name",
  "price": 0.0,
  "reputation": 1.0,
  "metadata": {
    "type": "category",
    "confidence": "high",
    "attributes": { ... }
  },
  "source": "vision-cortex"
}
```

## Safety Protocol (C2C9)
The Vision Cortex implements strict immune responses to prevent metabolic exhaustion:
1. **Size Membrane:** Requests exceeding 5MB are incinerated before processing to prevent Denial of Service.
2. **Identity Verification:** Only signed requests from verified DIDs are permitted to consume perception cycles.
3. **Format Validation:** Only standard image formats (JPEG, PNG, WEBP) are accepted. *(Note: Not yet enforced by OPA policy)*
