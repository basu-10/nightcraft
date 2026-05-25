# portofio site of multiple projects for Asesh Basu

- This folder in local develepment : D:\dev_work\web_dev\personal site\ionos-server
- Each folder here represents a github repo.
- Each folder has their own git repos that they point to. 

- mirrors the structure of the Ionos server where this project will be uploaded.
server ip:  31.70.85.89

## ssh login

ssh dev@31.70.85.89
Project6969ThumsUpClassmateProject6969ThumsUpClassmate

## Routing

### Use subpaths first, not subdomains as we dont yet have a domain purchased:

http://SERVER_IP/auth   → central auth service
http://SERVER_IP/notes  → notes app
http://SERVER_IP/game   → game app
http://SERVER_IP/admin  → admin app

### Behind Nginx

Nginx
├── /auth  → auth service
├── /notes → notes Flask app
├── /game  → game Flask app
└── /admin → admin Flask app


## repo design

Each folder here represents a github repo.

Individual repos for each project:

- notes-app       → standalone capable, SSO capable
- game-app        → standalone capable, SSO capable
- admin-app       → standalone capable, SSO capable
- auth-service    → central login service

Then add a separate deployment repo:
nightcraft-server-stack/
├── nginx/
├── env/
└── README.md

That deployment repo wires everything together.

### Users can choose

#### Option 1

Download only notes-app
Run it standalone

#### Option 2

Download auth-service + notes-app
Run with shared login

#### Option 3

Download nightcraft-server-stack
Run the full ecosystem

#### Central auth app

All projects share the same auth backbone - they have a central authentication/identity service that handles all user management and authentication. This service is responsible for user registration, login, logout, password reset, email verification, session management, and OAuth/OIDC token issuing. Each app becomes an OAuth/OIDC client that relies on the auth service for user authentication and authorization.
D:\dev_work\web_dev\personal site\ionos-server\service-auth

Each product DB stores only product-specific data and user_id, not full user data.  The user_id comes from the auth service. Each app becomes an OAuth/OIDC  client

#### Responsibilities

Signup
Login
Logout
Password reset
Email verification
Session management
OAuth/OIDC token issuing
User profile
App-level access
MFA later, maybe

#### Database:

auth_db
- users
- identities
- sessions
- refresh_tokens
- oauth_clients
- user_app_access
- roles
- permissions

#### expected behaviour 

When the user visits 31.70.85.89.com/notes:

1. Notes app checks: is user logged in locally?
2. If not, redirect to 31.70.85.89.com/auth/login
3. User logs in there
4. Auth service redirects back to notes app with auth code
5. Notes app exchanges code for tokens
6. Notes app creates its own local session cookie
7. User is now logged into notes

Then if they open 31.70.85.89.com/game:

1. Game app redirects to 31.70.85.89.com/auth
2. Auth service sees existing auth session
3. No password asked
4. Redirects back immediately
5. Game app creates local session

### Individual apps

Inside each app
Have an auth adapter layer:

app/auth/
├── local_auth.py
├── sso_auth.py
└── current_user.py

The rest of the app should not care where login came from.

Bad:
notes routes directly query users table

Good:
notes routes call get_current_user()

Then config decides:

AUTH_MODE=local

or:

AUTH_MODE=sso
AUTH_SERVICE_URL=http://127.0.0.1/auth
Product tables stay stable

In both modes, the app uses:

user_id

In standalone mode:
user_id comes from local users table

In SSO mode:
user_id comes from auth service

That means the product logic stays mostly unchanged.
