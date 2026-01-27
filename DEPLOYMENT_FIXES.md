# Kubernetes Deployment Fixes - Implementation Summary

## What Was Fixed

### 1. Mistral API Key Configuration (CRITICAL BUG)
**Problem:** Secret configuration had architectural mismatch between creation and reference.
- `values.yaml` defined `mistralApiKey` as object `{name: "mistral-api-key"}`
- `secrets.yaml` tried to render this object as string value
- `core-deployment.yaml` expected secret named "mistral-api-key" but actual secret was "aura-secrets"

**Solution:** Unified secret approach
- Changed `mistralApiKey` to simple string value in `values.yaml:92`
- Fixed `core-deployment.yaml:42-46` to reference `aura-secrets` with key `mistral-key`
- Now matches the actual secret created by `secrets.yaml`

### 2. CI/CD Secret Injection
**Problem:** Secrets were not being injected during deployment, causing:
- Empty Mistral API key → `CreateContainerConfigError` in aura-core pod
- Empty FRP token → `CrashLoopBackOff` in aura-frpc-tunnel pod

**Solution:** Added secret injection to CI/CD workflow
- Added `env` block with `MISTRAL_API_KEY` and `FRP_CLIENT_TOKEN`
- Added `--set` flags to helm upgrade command
- Secrets pulled from GitHub Secrets (must be configured separately)

## Next Steps Required

### Step 1: Add GitHub Secrets (REQUIRED)
Go to your GitHub repository → Settings → Secrets and variables → Actions → New repository secret

Add these two secrets:

1. **Name:** `MISTRAL_API_KEY`
   - **Value:** Your actual Mistral AI API key

2. **Name:** `FRP_CLIENT_TOKEN`
   - **Value:** Your FRP server authentication token

### Step 2: Delete Orphaned frpc-tunnel Deployment
On your self-hosted runner (where kubectl is configured):

```bash
kubectl delete deployment frpc-tunnel
```

This removes the duplicate/orphaned deployment that's running without the "aura-" prefix.

### Step 3: Commit and Deploy
```bash
git add .
git commit -m "fix: configure secrets in CI/CD and fix Mistral API key reference"
git push origin feat/mcp
```

Then create a PR and merge to `main` branch. The CI/CD pipeline will:
1. Run quality checks
2. Build and push Docker images
3. Deploy to Minikube with secrets properly injected

### Step 4: Verification
After deployment completes, verify:

```bash
# Check all pods are running
kubectl get pods

# Expected output - all should be "Running":
# aura-core-xxx          1/1   Running
# aura-gateway-xxx       1/1   Running
# aura-frontend-xxx      1/1   Running
# aura-frpc-tunnel-xxx   1/1   Running  ← No longer CrashLoopBackOff
# aura-postgres-xxx      1/1   Running
# aura-redis-xxx         1/1   Running
# aura-jaeger-xxx        1/1   Running

# Verify secrets exist with actual values (not empty)
kubectl get secret aura-secrets -o jsonpath='{.data.mistral-key}' | base64 -d
kubectl get secret aura-frp-client-token -o jsonpath='{.data.token}' | base64 -d

# Check logs for success
kubectl logs -f deployment/aura-core | grep -i "mistral"
kubectl logs -f deployment/aura-frpc-tunnel
```

## Files Modified

1. **deploy/aura/values.yaml:89-93**
   - Changed `mistralApiKey` from object to string value
   - Added comment explaining CI/CD injection

2. **deploy/aura/templates/core-deployment.yaml:42-46**
   - Fixed secret reference to use `aura-secrets` instead of `mistral-api-key`
   - Fixed key name to `mistral-key` instead of `mistral-api-key`

3. **.github/workflows/ci-cd.yaml:82-94**
   - Added `env` block to deployment step with secrets
   - Added `--set` flags for both Mistral and FRP secrets

## Architecture After Fix

### Secret Flow
```
GitHub Secrets (MISTRAL_API_KEY, FRP_CLIENT_TOKEN)
  ↓
CI/CD env variables
  ↓
helm --set flags
  ↓
values.yaml (mistralApiKey, frpClientToken.value)
  ↓
secrets.yaml template → Kubernetes Secret "aura-secrets"
  ↓
core-deployment.yaml env → MISTRAL_API_KEY in container
```

### Key Points
- All secrets flow through CI/CD, never committed to git
- Unified `aura-secrets` Secret contains all shared secrets
- Individual secrets (like `aura-frp-client-token`) use dedicated Secret resources
- Secret names and keys now match between creation and reference

## Troubleshooting

### If aura-core still has CreateContainerConfigError:
```bash
kubectl describe pod aura-core-xxx
# Look for "MountVolume.SetUp failed" or secret not found errors

# Check if secret exists and has value
kubectl get secret aura-secrets -o yaml
```

### If aura-frpc-tunnel still has CrashLoopBackOff:
```bash
kubectl logs aura-frpc-tunnel-xxx
# Look for authentication or token errors

# Check FRP token secret
kubectl get secret aura-frp-client-token -o yaml
```

### If GitHub Secrets are not being injected:
- Verify secrets are added to repository (Settings → Secrets → Actions)
- Check CI/CD logs for env variable values (should be "***" for secrets)
- Ensure branch is `main` (deployment only runs on main branch)

## Security Notes

- ✅ Secrets never committed to git
- ✅ GitHub Secrets are encrypted at rest
- ✅ CI/CD masks secret values in logs
- ⚠️ Kubernetes Secrets are base64-encoded but NOT encrypted by default
- 💡 Future improvement: Consider External Secrets Operator or Sealed Secrets

## Contact

If you encounter issues:
1. Check the verification commands above
2. Review pod logs: `kubectl logs -f deployment/aura-<service>`
3. Check pod events: `kubectl describe pod aura-<service>-xxx`
