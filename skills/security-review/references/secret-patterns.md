# Secret & Credential Detection Patterns

Load this file during Step 3 (Secrets & Exposure Scan).

---

## High-Confidence Secret Patterns

These patterns almost always indicate a real secret:

### API Keys & Tokens
```regex
# OpenAI
sk-[a-zA-Z0-9]{48}

# Anthropic
sk-ant-[a-zA-Z0-9\-_]{90,}

# AWS Access Key
AKIA[0-9A-Z]{16}

# AWS Secret Key (look for near AWS_ACCESS_KEY_ID assignment)
[0-9a-zA-Z/+]{40}

# GitHub Token
gh[pousr]_[a-zA-Z0-9]{36,}
github_pat_[a-zA-Z0-9]{82}

# Stripe
sk_live_[a-zA-Z0-9]{24,}
rk_live_[a-zA-Z0-9]{24,}

# Twilio Account SID
AC[a-z0-9]{32}
# Twilio API Key
SK[a-z0-9]{32}

# SendGrid
SG\.[a-zA-Z0-9\-_.]{66}

# Slack
xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+
xoxp-[0-9]+-[0-9]+-[0-9]+-[a-zA-Z0-9]+
xapp-[0-9]+-[A-Z0-9]+-[0-9]+-[a-zA-Z0-9]+

# Google API Key
AIza[0-9A-Za-z\-_]{35}

# Google OAuth
[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com

# Cloudflare (near CF_API_TOKEN)
[a-zA-Z0-9_\-]{37}

# Mailgun
key-[a-zA-Z0-9]{32}

# Heroku
[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}
```

### Private Keys
```regex
-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY( BLOCK)?-----
-----BEGIN CERTIFICATE-----
```

### Database Connection Strings
```regex
# MongoDB
mongodb(\+srv)?:\/\/[^:]+:[^@]+@

# PostgreSQL / MySQL
(postgres|postgresql|mysql):\/\/[^:]+:[^@]+@

# Redis with password
redis:\/\/:[^@]+@

# Generic connection string with password
(connection[_-]?string|connstr|db[_-]?url).*password=
```

### Hardcoded Passwords (variable name signals)
```regex
# Variable names that suggest secrets
(password|passwd|pwd|secret|api_key|apikey|auth_token|access_token|private_key)
  \s*[=:]\s*["'][^"']{8,}["']
```

---

## Entropy-Based Detection

Apply to string literals > 20 characters in assignment context.

**Do not calculate entropy yourself.** Shannon entropy is a numerical computation
over character frequencies, and a language model asked for one will produce a
plausible number rather than a correct one. The failure is silent: the output
looks like a measurement, so nothing signals that no measurement occurred.

Run a tool and use its output as ground truth:

```bash
# Preferred: purpose-built, maintained rulesets
detect-secrets scan --all-files
# or
gitleaks detect --no-git --redact
```

If neither is available, compute it deterministically rather than estimating:

```bash
python3 - "$FILE" <<'PY'
import math, re, sys
from collections import Counter
for lineno, line in enumerate(open(sys.argv[1], errors="replace"), 1):
    for lit in re.findall(r'["\']([^"\']{20,})["\']', line):
        counts = Counter(lit)
        n = len(lit)
        entropy = -sum((c / n) * math.log2(c / n) for c in counts.values())
        if entropy > 4.5:
            print(f"{sys.argv[1]}:{lineno}: entropy={entropy:.2f} {lit[:12]}...")
PY
```

Threshold: > 4.5 bits/char AND > 20 chars AND assigned to a variable.

If no tool ran, say so in the report and mark entropy-based detection as **not
performed**. Claiming a heuristic that never executed is worse than omitting it,
because the reader credits the repo with a check nobody ran.

Where the model does add value here is judgment the tool lacks: deciding whether
a flagged high-entropy string is a real credential or a hash fixture, a UUID, a
minified asset, or test data. Apply that to tool output; do not use it to replace
the measurement.

Common false positives to exclude:
- Lorem ipsum text
- HTML/CSS content
- Base64-encoded non-sensitive config (but flag and note)
- UUID/GUID (entropy is high but format is recognizable)

---

## Files That Should Never Be Committed

Flag if these files exist in the repo root or are tracked by git:
```
.env
.env.local
.env.production
.env.staging
*.pem
*.key
*.p12
*.pfx
id_rsa
id_ed25519
credentials.json
service-account.json
gcp-key.json
secrets.yaml
secrets.json
config/secrets.yml
```

Also check `.gitignore` : if a secret file pattern is NOT in .gitignore, flag it.

---

## CI/CD & IaC Secret Risks

### GitHub Actions : flag these patterns:
```yaml
# Hardcoded values in env: blocks (should use ${{ secrets.NAME }})
env:
  API_KEY: "actual-value-here"   # VULNERABLE

# Printing secrets
- run: echo ${{ secrets.MY_SECRET }}   # leaks to logs
```

### Docker : flag these:
```dockerfile
# Secrets in ENV (persisted in image layers)
ENV AWS_SECRET_KEY=actual-value

# Secrets passed as build args (visible in image history)
ARG API_KEY=actual-value
```

### Terraform : flag these:
```hcl
# Hardcoded sensitive values (should use var or data source)
password = "hardcoded-password"
access_key = "AKIAIOSFODNN7EXAMPLE"
```

---

## Safe Patterns (Do NOT flag)

These are intentional placeholders : recognize and skip:
```
"your-api-key-here"
"<YOUR_API_KEY>"
"${API_KEY}"
"${process.env.API_KEY}"
"os.environ.get('API_KEY')"
"REPLACE_WITH_YOUR_KEY"
"xxx...xxx"
"sk-..." (in documentation/comments)
```
