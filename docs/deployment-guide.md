# Deploying alexpetrakes.com

This guide walks you through deploying this Django project to **alexpetrakes.com** for the first time. The project is already set up for production (WhiteNoise for static files, `ALLOWED_HOSTS` includes your domain).

---

## Overview

1. **Put your code on GitHub** (if it isn’t already).
2. **Pick a host** that runs Python/Django and supports custom domains (e.g. **Render** or **PythonAnywhere**).
3. **Deploy the app** and set environment variables.
4. **Point your domain** (alexpetrakes.com) to the host using DNS.

---

## Option A: Render (recommended, free tier)

[Render](https://render.com) has a free tier and supports custom domains and Django.

### 1. Push your project to GitHub

```bash
cd /Users/alexpetrakes/PycharmProjects/alexpetrakes.com
git init
git add .
git commit -m "Initial commit"
# Create a repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/alexpetrakes.com.git
git branch -M main
git push -u origin main
```

(If you use a different branch name, use that instead of `main`.)

### 2. Create a Render account and new Web Service

1. Go to [render.com](https://render.com) and sign up (GitHub login is easiest).
2. **Dashboard** → **New** → **Web Service**.
3. Connect your GitHub account and select the **alexpetrakes.com** repository.
4. Use these settings:

| Field | Value |
|-------|--------|
| **Name** | `alexpetrakes-com` (or any name) |
| **Region** | Choose closest to you |
| **Branch** | `main` (or your default branch) |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| **Start Command** | `gunicorn alexpetrakes_site.wsgi:application` |

5. Under **Advanced** → **Add Environment Variable**:

| Key | Value |
|-----|--------|
| `SECRET_KEY` | A long random string (e.g. generate one: `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DEBUG` | `False` |

6. Click **Create Web Service**. Render will build and deploy. You’ll get a URL like `https://alexpetrakes-com.onrender.com`.

### 3. Add your custom domain on Render

1. In your service → **Settings** → **Custom Domains**.
2. Click **Add Custom Domain**.
3. Enter **alexpetrakes.com** and add it.
4. Optionally add **www.alexpetrakes.com** (Render will show the DNS records).

### 4. Point your domain to Render (DNS)

Where you registered **alexpetrakes.com** (e.g. Namecheap, Google Domains, Cloudflare, GoDaddy):

**For apex domain (alexpetrakes.com):**

- Add an **A record**:
  - **Host:** `@` (or leave blank for “root”)
  - **Value / Points to:** Render’s IP (Render shows this in Custom Domains; often `216.24.57.1` or similar—**use the value Render gives you**).

**For www (www.alexpetrakes.com):**

- Add a **CNAME**:
  - **Host:** `www`
  - **Value / Points to:** `alexpetrakes-com.onrender.com` (your Render service hostname).

Save the DNS changes. Propagation can take from a few minutes up to 24–48 hours.

### 5. SSL (HTTPS)

Render provides free HTTPS. After DNS is correct, Render will issue a certificate for alexpetrakes.com and www. No extra steps needed.

---

## Option B: PythonAnywhere

[PythonAnywhere](https://www.pythonanywhere.com) is another beginner-friendly option with a free tier.

1. Sign up, create a new **Web** app, choose **Manual configuration** and Python 3.10+.
2. Open a **Bash** console, clone your repo (or upload code), then:
   ```bash
   pip install -r requirements.txt
   python manage.py collectstatic --noinput
   python manage.py migrate
   ```
3. In the **Web** tab, set the **WSGI configuration file** to load `alexpetrakes_site.wsgi`.
4. Add your domain under the **Web** app’s **Static files** and **Domain** settings; PythonAnywhere will show you what to put in DNS (CNAME to their hostname).
5. Set `SECRET_KEY` and `DEBUG=False` in the **Consoles** or in a `.env` file and load it in your WSGI/settings if you use one.

Their [Django tutorial](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/) has step-by-step details.

---

## Before you go live – checklist

- [ ] **SECRET_KEY** is set in the host’s environment and is a long random value (not the default in `settings.py`).
- [ ] **DEBUG** is `False` in production.
- [ ] Code is in a Git repo and the host deploys from it.
- [ ] **Build command** runs `pip install -r requirements.txt` and `python manage.py collectstatic --noinput`.
- [ ] **Start command** is `gunicorn alexpetrakes_site.wsgi:application`.
- [ ] DNS for **alexpetrakes.com** (and **www** if you use it) points to your host as above.

---

## After deployment

- Visit **https://alexpetrakes.com** (and **https://www.alexpetrakes.com** if configured).
- If you use Django admin, create a superuser on the server (e.g. via Render Shell or PythonAnywhere console):
  ```bash
  python manage.py createsuperuser
  ```
- Your app uses SQLite by default. For the free tier this is fine; if you later need multi-instance or backups, consider switching to a hosted database (e.g. Render PostgreSQL) and updating `DATABASES` in `settings.py`.

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| 500 error | Host logs (Render **Logs** tab; PythonAnywhere **Error log**). Ensure `SECRET_KEY` and `DEBUG` are set and `collectstatic` ran. |
| Static files (CSS/JS) missing | Build command must include `python manage.py collectstatic --noinput`. WhiteNoise is already in the project. |
| Domain not loading | DNS propagation (wait up to 48h), and that A/CNAME records match exactly what the host shows. |
| “Invalid HTTP_HOST” | Your domain is already in `ALLOWED_HOSTS` in `settings.py`; if you use another hostname, add it there. |

---

## Summary

1. Push code to **GitHub**.
2. Create a **Web Service** on **Render** (or set up the app on **PythonAnywhere**).
3. Set **SECRET_KEY** and **DEBUG=False**.
4. Add **alexpetrakes.com** (and **www**) as custom domains.
5. Point your domain’s **DNS** to the host (A record for apex, CNAME for www as instructed by the host).

After DNS propagates, **https://alexpetrakes.com** will serve your Django site.
