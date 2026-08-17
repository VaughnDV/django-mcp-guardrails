# Adapter support matrix

Status: django-mcp-server adapter implemented. Cumulative budgets and audit
apply in the policy core used by this adapter.

| Extra | Framework | Supported versions | Notes |
| --- | --- | --- | --- |
| `django-mcp-server` | [`django-mcp-server`](https://pypi.org/project/django-mcp-server/) | 0.5.x | Requires MCP Python SDK **1.x** (FastMCP). MCP SDK 2.x is incompatible with django-mcp-server 0.5.x. |
| `mcp-sdk` | Official MCP Python SDK | declared, not wrapped yet | Generic decorator in the core can be used until a dedicated adapter lands. |

## django-mcp-server

Install from this repository until the PyPI release is available:

```bash
pip install "django-mcp-guardrails[django-mcp-server] @ git+https://github.com/VaughnDV/django-mcp-guardrails.git"
```

Register a policy-backed tool. Identity comes from `django_request_ctx`, never from tool arguments:

```python
from django_mcp_guardrails.adapters.django_mcp_server import register_guarded_model_tool

register_guarded_model_tool(
    policy=item_read_policy,
    name="search_items",
    get_organization_id=lambda request: getattr(request, "organization_id", None),
)
```

The adapter:

- Refuses to load when FastMCP is missing or the framework version is outside 0.5.x
- Validates the query through the policy core
- Returns the bounded envelope
- Raises `MCPGuardrailError` with a stable `code` and a safe message

It does not monkey-patch django-mcp-server. Unregistered tools are simply not added to the server.

## Residual adapter risks

- Tool descriptions are developer-supplied and must not advertise hidden fields.
- `django-mcp-server`'s `ModelQueryToolset` is **not** wrapped; using it bypasses this package.
- Protocol transport, OAuth, and session cookies remain the host application's responsibility.
