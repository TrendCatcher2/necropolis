# Lantern Lane: the Necropolis demo site

A **fictional** shop that Zombie API Necropolis probes in its demo. All people, data and orders are invented, and
every JSON body carries `"_fake": true`. Deploy it only on a host you control.

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

`DEMO_FRONTEND=v1` serves a front end whose JS (`/static/app.v1.js`) calls the v1 API. It also names
`/api/v1/debug/trace` as a development leftover. `DEMO_FRONTEND=v2` serves one that calls only v2. The v1 API keeps
answering either way. That is the zombie.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
DEMO_FRONTEND=v1 .venv/bin/uvicorn app:app --port 8080     # then open http://127.0.0.1:8080/
```

## Deploy free on Render (no domain needed)

Render's free web services ([docs](https://render.com/docs/free)):
- spin down after 15 minutes without traffic and take about a minute to wake;
- give you `https://<name>.onrender.com`;
- deploy from this GitHub repo.

1. Sign up at https://render.com with **GitHub**, and allow access to the `necropolis` repo.
2. Go to **New → Web Service** and pick the `TrendCatcher2/necropolis` repo.
3. Settings:

   | Field | Value |
   |---|---|
   | Name | `lantern-lane` (if taken, Render's URL gets a suffix; note the real URL) |
   | Root Directory | `demo-site` |
   | Language | **Docker** (Render finds `demo-site/Dockerfile`) |
   | Instance type | **Free** |
   | Environment variable | `DEMO_FRONTEND` = `v1` |

   - The app listens on `$PORT`, which Render sets, so there is no port to configure.
   - If Docker isn't offered on Free, choose **Python 3** instead, with build command
     `pip install -r requirements.txt` and start command `uvicorn app:app --host 0.0.0.0 --port $PORT`.
4. Click **Deploy**. When it says *Live*, open `https://<name>.onrender.com/`. You should see "Lantern Lane · front
   end v1" with Casper Example signed in.

Ownership proof for Necropolis: there is no DNS to edit on `onrender.com`, so use the **file proof**. When
Necropolis gives you a challenge token, add the environment variable `NECROPOLIS_VERIFICATION_TOKEN` = `<token>` on
Render. The site then serves the token at `/.well-known/necropolis-verification.txt`.

**Wake it first.** While a free service is asleep, browsers get Render's loading page and `/robots.txt` answers
"disallow all". Before archiving it, or probing it with Necropolis, open the site in your browser and wait for the
real page. It then stays awake while it gets traffic, and for 15 minutes after.

## Archive the history (by hand, in a browser)

1. With `DEMO_FRONTEND=v1` live and awake, open https://web.archive.org/save/ and save each URL separately:
   - `https://<name>.onrender.com/`
   - `https://<name>.onrender.com/static/app.v1.js`
   - `https://<name>.onrender.com/api/v1/users/1`
   - `https://<name>.onrender.com/api/v1/users/2`
   - `https://<name>.onrender.com/api/v1/status`

   The JS file already names the orders, legacy-export and debug endpoints, so their 401, 410 and 500 pages don't
   need saving. The concrete `/users/1` and `/users/2` captures give Necropolis a real path to probe.
2. Check that the captures exist (this can take a while):
   `curl -s 'https://web.archive.org/cdx/search/cdx?url=<name>.onrender.com/*&output=json&fl=timestamp,original,statuscode&collapse=urlkey'`
3. A few days later, set `DEMO_FRONTEND` = `v2` on Render (it redeploys). Wake the site, then save
   `https://<name>.onrender.com/` and `https://<name>.onrender.com/static/app.v2.js`. **Keep the v1 API running.**

## Other hosts

Any host that runs the `Dockerfile` with HTTPS works: `docker build -t lantern-lane . && docker run -p 8080:8080 -e
DEMO_FRONTEND=v1 lantern-lane`. On a domain whose DNS you control, Necropolis can use the DNS TXT proof instead.
