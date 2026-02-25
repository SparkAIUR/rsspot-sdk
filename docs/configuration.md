# Configuration

`rsspot` reads credentials and defaults from a local config file and environment variables.

## Config File Formats

Supported: YAML, JSON, TOML.

Default file is `~/.spot_config` (extensionless files are auto-detected and written as YAML).

### Legacy flat shape

```yaml
org: sparkai
region: us-central-dfw-1
refreshToken: <token>
accessToken: <optional-id-token>
```

### Profile-aware shape

```yaml
active_profile: prod
profiles:
  prod:
    org: sparkai
    region: us-central-dfw-1
    refreshToken: <token>
  staging:
    org: another-org
    region: us-east-iad-1
    refreshToken: <token>
```

## Environment Overrides

`rsspot` supports both `RSSPOT_*` and Rackspace-compatible env names:

- `RSSPOT_CONFIG_FILE` / `SPOT_CONFIG_FILE`
- `RSSPOT_PROFILE` / `SPOT_PROFILE`
- `RSSPOT_ORG`, `RSSPOT_ORG_ID`, `RSSPOT_REGION`
- `RSSPOT_REFRESH_TOKEN` / `SPOT_REFRESH_TOKEN`
- `RSSPOT_ACCESS_TOKEN` / `SPOT_ACCESS_TOKEN`
- `RSSPOT_CLIENT_ID` / `RXTSPOT_CLIENT_ID`
- `RSSPOT_BASE_URL` / `SPOT_BASE_URL`
- `RSSPOT_OAUTH_URL` / `SPOT_AUTH_URL`

Order of precedence: explicit constructor args, env vars, selected profile, defaults.
