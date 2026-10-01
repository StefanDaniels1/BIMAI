# Spec Delta

## ADDED Requirements

### Requirement: No secrets in .mcp.json
When the project has a `.mcp.json`, `bimai validate` SHALL report a problem for every `headers` value
and every `env` value that is not entirely an environment-variable reference (`${NAME}` or
`${NAME:-default}`), and for any `oauth.clientSecret`, naming the server and the key but never the
value. Invalid JSON in `.mcp.json` SHALL be reported as a problem.

#### Scenario: Literal token
- **WHEN** a server in `.mcp.json` has `headers: {"Authorization": "Bearer abc123"}`
- **THEN** a problem is reported at `mcpServers.<server>.headers.Authorization`, and the message doesn't contain `abc123`

#### Scenario: Reference is fine
- **WHEN** a header value is `${MY_TOKEN}`
- **THEN** no problem is reported
