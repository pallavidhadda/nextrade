# Locking the NexTrade connector (optional)

**What it does.** By default the connector at `https://nextrade-api-7z41.onrender.com/mcp` is open: anyone who knows the address can start analyses and use up the free server's small CPU. The lock makes the server answer "unauthorized" unless the caller sends a secret you chose. `/api/health` and the REST routes stay open.

**When to use it.** While you are testing privately. Remove it when you want the connector public.

**It is off unless you set it.** If the variable below does not exist on the server, nothing changes.

## Turn it on
1. Make a long random secret (at least 32 characters). On a Mac, in Terminal: `openssl rand -base64 32`. Copy the result. Keep it private: never put it in GitHub, a chat with other people, or a screenshot.
2. In Render: Dashboard > `nextrade-api` > Environment > Add environment variable.
   - Key: `INDIAFACTS_MCP_TOKEN`
   - Value: the secret from step 1.
   Save. Render redeploys (a minute or two).
3. In Claude: Customize > Connectors > nextrade > edit. Under **Request headers** add one header:
   - Name: `Authorization`
   - Value: `Bearer ` followed by the same secret, for example `Bearer abc123...` (the word Bearer, one space, then the secret).
   Leave authentication on "No sign-in". Save, then reconnect the connector.
4. Test: in a new chat ask "Analyse TCS.NS". It should start. If Claude says the connector is unauthorized, the header and the Render value do not match exactly (check for a missing "Bearer ", extra spaces, or a different secret).

## Check it from Terminal (optional)
```
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://nextrade-api-7z41.onrender.com/mcp -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```
Without the header you should see `401`. With `-H 'authorization: Bearer YOUR_SECRET'` added you should see `200`.

## Change the secret
Generate a new one, change it in Render, then update the header in Claude. The old secret stops working as soon as Render finishes redeploying.

## Turn it off (open the connector to everyone)
Delete `INDIAFACTS_MCP_TOKEN` in Render and let it redeploy. You can leave the header in Claude; the server then ignores it.

## Limits
- It is a single shared secret, not user accounts. Anyone who has the secret can use the connector.
- It protects only the `/mcp` address. The API's other routes (`/api/analyze` and others) are not locked; they are rate-limited (6 requests per minute per connection, one analysis at a time on the free setup).
- Not tested against Claude's live connector yet (tested with automated tests only).
