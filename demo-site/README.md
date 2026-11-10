# Lantern Lane: the Necropolis demo site

A **fictional** shop that Zombie API Necropolis probes in its demo. All people, data and orders are invented, and
every JSON body carries `"_fake": true`. Deploy it only on a domain you own.

## The zombie story

| Endpoint | Answer | What Necropolis should conclude |
|---|---|---|
| `/api/v1/users/{id}` | 200, fake user with email/phone, **no auth** | Rampaging: auth asymmetry, data exposed, version behind |
| `/api/v2/users/{id}` | 401 without the demo token | The guarded sibling |
| `/api/v1/orders` | 401 | Stirring |
| `/api/v1/status` | 200 `{"status":"ok"}` | Risen, no risk signal |
| `/api/v1/debug/trace` | 500, fake Python traceback | Rampaging: verbose error, sensitive path |
| `/api/v1/legacy-export` | 410 Gone | Buried |
| `/api/v2/orders`, `POST /api/v2/session` | v2 API used by the current front end | Not zombies |

`DEMO_FRONTEND=v1` serves a front end whose JS (`/static/app.v1.js`) calls the v1 API. `DEMO_FRONTEND=v2` serves one
that calls only v2. The v1 API keeps answering either way. That is the zombie.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
DEMO_FRONTEND=v1 .venv/bin/uvicorn app:app --port 8080     # then open http://127.0.0.1:8080/
```

## Deploy (any host that runs a Docker image and gives you HTTPS)

```bash
docker build -t lantern-lane .
docker run -p 8080:8080 -e DEMO_FRONTEND=v1 lantern-lane
```

- Domain: a domain or subdomain **you own**.
  - For the DNS proof, you need to be able to add a TXT record at `_necropolis.<domain>`.
  - With a platform subdomain you can't control DNS for, use the file proof instead: set
    `NECROPOLIS_VERIFICATION_TOKEN` and the site serves it at `/.well-known/necropolis-verification.txt`.

## Archive the history (by hand, in a browser)

1. With `DEMO_FRONTEND=v1` live, open https://web.archive.org/save/ and save each URL separately:
   - `https://<demo>/`
   - `https://<demo>/static/app.v1.js`
   - `https://<demo>/api/v1/users/1`
   - `https://<demo>/api/v1/users/2`
   - `https://<demo>/api/v1/status`
   - `https://<demo>/api/v1/debug/trace`
2. Check that the captures exist (this can take a while):
   `curl -s 'https://web.archive.org/cdx/search/cdx?url=<demo>/*&output=json&fl=timestamp,original,statuscode&collapse=urlkey'`
3. A few days later, redeploy with `DEMO_FRONTEND=v2`, then save `https://<demo>/` and
   `https://<demo>/static/app.v2.js`. **Keep the v1 API running.**
