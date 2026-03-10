# Project Invite & Deletion Feature Spec

> Version: 1.0  
> Date: 2026-03-11

---

## 1. Role System

### 1.1 Project Roles (4 levels)

| Role | Level | Permissions |
|------|-------|-------------|
| `owner` | 3 | Full control: invite, configure, delete project, manage members |
| `admin` | 2 | Same as owner (invite, configure, delete) |
| `read_write` | 1 | Read + write memories; no invite/configure |
| `read_only` | 0 | View memories only; no write/invite/configure |

### 1.2 Superadmin

- User `arthaszeng` has `is_superadmin=true` in the auth system.
- Superadmin has **owner-level** access to all projects, regardless of membership.
- Superadmin can see all projects in the project list.

### 1.3 Role Assignment

- Project creator gets `owner` role automatically.
- Invite links can assign: `read_only`, `read_write`, or `admin` (not `owner`).
- Direct member add (via API) can assign any role except `owner` being restricted by policy.

---

## 2. Project Invitation

### 2.1 Flow

```
Owner/Admin clicks "Invite" in Navbar
  → Selects role + expiry → Creates invite link
  → Copies link → Shares with target user
  → Target user opens link → Sees invite info page
  → Clicks "Accept" → Joins project with assigned role
```

### 2.2 Backend Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/projects/{slug}/invites` | admin+ | Create invite token |
| GET | `/api/v1/projects/{slug}/invites` | admin+ | List all invites for project |
| POST | `/api/v1/projects/{slug}/invites/revoke` | admin+ | Revoke a pending invite |
| GET | `/api/v1/projects/invites/{token}/info` | none | Get invite info (public) |
| POST | `/api/v1/projects/invites/{token}/accept` | logged-in | Accept invite |

### 2.3 Invite States

- `pending` — Active, can be accepted
- `accepted` — Used by a user
- `revoked` — Cancelled by admin
- `expired` — Past expiry date

### 2.4 Data Model: `ProjectInvite`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| project_id | UUID FK | Target project |
| token | String | Unique URL-safe token |
| role | ProjectRole | Role assigned on accept |
| status | InviteStatus | pending/accepted/revoked/expired |
| created_by_id | UUID FK | User who created invite |
| accepted_by_id | UUID FK | User who accepted (nullable) |
| expires_at | DateTime | Expiry timestamp (nullable) |
| created_at | DateTime | Creation timestamp |
| accepted_at | DateTime | Acceptance timestamp (nullable) |

### 2.5 Frontend UI

- **Invite Button**: Visible in Navbar for owner/admin of current project.
- **Invite Dialog**: Role selector, expiry input, create button, copy link.
- **Team Members**: Listed in the dialog with role badges.
- **Invite History**: Listed in the dialog with status, revoke button for pending.
- **Accept Page** (`/invite/[token]`): Shows project name, role, inviter, accept button.

---

## 3. Project Deletion

### 3.1 Cascade Behavior

When a project is deleted (by admin/owner):

1. All project memories are deleted from **Qdrant** vector store
2. All memory-category associations are removed
3. All `ProjectInvite` records are deleted
4. All `ProjectMember` records are deleted
5. All `Memory` rows are hard-deleted
6. The `Project` row is deleted

### 3.2 UI Confirmation

- Delete button opens a confirmation dialog.
- User must type the project slug to confirm.
- "Delete Project" button is disabled until slug matches.

### 3.3 Deleted Project Handling

- If a user navigates to a deleted project's URL, the `ProjectGuard` component shows a "Project Not Found" page with a link back to the dashboard.

---

## 4. Data Isolation Fixes

### 4.1 Archive Endpoint

- Previously: No authentication, accepted raw `user_id` in body.
- Fixed: Uses `get_authenticated_user`, checks ownership, validates project scope.

### 4.2 Delete Endpoint

- Previously: No ownership verification before deleting memories.
- Fixed: Verifies `memory.user_id == auth.db_user.id` (or superadmin).

### 4.3 Pause Endpoint

- Previously: `global_pause` affected ALL users' memories.
- Fixed: Filters by `Memory.user_id == user.id` for non-superadmins.

---

## 5. Migration

### 5.1 Role Migration Script

`scripts/migrate_roles.py` converts existing role values:

| Old | New |
|-----|-----|
| admin | owner |
| normal | read_write |
| read | read_only |

Usage: `python scripts/migrate_roles.py --db /path/to/openmemory.db`

### 5.2 Schema Migration

The `project_invites` table is auto-created by SQLAlchemy `Base.metadata.create_all()` on app startup.
