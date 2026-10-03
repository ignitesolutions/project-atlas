# Auth Plan

## Identity

- How do users sign up and sign in? (local credentials, SSO, invitation-only)

## Sessions

- Session storage and lifetime; session ID rotation on login.

## Roles and permissions

| Role | Can do | Cannot do |
| --- | --- | --- |
|  |  |  |

## Password storage

- Adaptive hashing algorithm (BCrypt/Argon2). Never MD5/SHA-1/unsalted.

## Protected surface

- Which pages/routes/APIs are gated, and how is the gate enforced?
