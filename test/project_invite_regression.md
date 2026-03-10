# Project Invite & Deletion Regression Test Suite

> Last updated: 2026-03-11
> Covers: Role System, Invites, Project Deletion, Data Isolation Fixes

---

## A. Role System (4-Level)

### A1: Owner Role on Project Creation
- **Steps**: POST `/api/v1/projects` to create project
- **Expected**: Creator gets `owner` role (check `/projects/{slug}/members`)

### A2: Superadmin Sees All Projects as Owner
- **Steps**: Login as `arthaszeng`, GET `/api/v1/projects`
- **Expected**: All projects listed, `my_role` = `owner` for each

### A3: Read-Only Cannot Write Memory
- **Steps**: Add user as `read_only` to project, try POST `/api/v1/memories/`
- **Expected**: 403

### A4: Read-Write Can Write Memory
- **Steps**: Add user as `read_write`, POST `/api/v1/memories/`
- **Expected**: 200, memory created

### A5: Read-Write Cannot Invite
- **Steps**: `read_write` member tries POST `/api/v1/projects/{slug}/invites`
- **Expected**: 403

### A6: Admin Can Invite
- **Steps**: `admin` member creates invite
- **Expected**: 200, invite token returned

### A7: Owner Can Do Everything
- **Steps**: `owner` performs: create invite, delete member, update project, delete project
- **Expected**: All succeed

### A8: Role Hierarchy Enforcement
- **Steps**: Try various operations with escalating min_role requirements
- **Expected**: Each role level is blocked below threshold, allowed at or above

---

## B. Invite Creation

### B1: Create Invite (Happy Path)
- **Steps**: Owner creates invite with `role=read_write`, `expires_in_days=7`
- **Expected**: 200, returns token, role, status=pending, expires_at set

### B2: Create Invite with Admin Role
- **Steps**: Create invite with `role=admin`
- **Expected**: 200, invite with admin role

### B3: Cannot Create Owner Invite
- **Steps**: Try `role=owner` in invite creation
- **Expected**: 400 "Cannot create invite with owner role"

### B4: Invalid Role in Invite
- **Steps**: Try `role=superuser`
- **Expected**: 400 "Invalid role"

### B5: Non-Admin Cannot Create Invite
- **Steps**: `read_write` member tries to create invite
- **Expected**: 403

---

## C. Invite Listing & Revocation

### C1: List Invites
- **Steps**: Create 3 invites, GET `/api/v1/projects/{slug}/invites`
- **Expected**: Returns all 3 in desc order

### C2: Revoke Pending Invite
- **Steps**: POST `/api/v1/projects/{slug}/invites/revoke` with token
- **Expected**: 200, invite status becomes `revoked`

### C3: Cannot Revoke Already Accepted
- **Steps**: Accept invite, then try to revoke
- **Expected**: 400 "Invite already accepted"

### C4: Revoke Non-Existent Token
- **Steps**: Revoke with random token
- **Expected**: 404

---

## D. Invite Info (Public)

### D1: Get Invite Info
- **Steps**: GET `/api/v1/projects/invites/{token}/info` (no auth)
- **Expected**: 200, returns project_name, role, created_by, expires_at

### D2: Expired Invite Info
- **Steps**: Create invite with past expiry, GET info
- **Expected**: 400 "Invite has expired"

### D3: Revoked Invite Info
- **Steps**: Revoke invite, GET info
- **Expected**: 400 "Invite is revoked"

### D4: Non-Existent Token
- **Steps**: GET info with random token
- **Expected**: 404

---

## E. Invite Accept

### E1: Accept Invite (Happy Path)
- **Steps**: Login as different user, POST `/api/v1/projects/invites/{token}/accept`
- **Expected**: 200, user becomes member with invite's role

### E2: Accept Expired Invite
- **Steps**: Accept invite that has expired
- **Expected**: 400 "Invite has expired"

### E3: Accept Revoked Invite
- **Steps**: Accept revoked invite
- **Expected**: 400 "Invite is revoked"

### E4: Accept Already Accepted
- **Steps**: Accept same invite again (same or different user)
- **Expected**: 400 "Invite is accepted"

### E5: Already Member Tries Accept
- **Steps**: Existing project member accepts invite for same project
- **Expected**: 409 "You are already a member"

### E6: Unauthenticated Accept
- **Steps**: Try accept without JWT
- **Expected**: 401

---

## F. Frontend Invite UI

### F1: Invite Button Visibility (Owner)
- **Steps**: Login as project owner, navigate to project
- **Expected**: "Invite" button visible in Navbar

### F2: Invite Button Visibility (Read-Write)
- **Steps**: Login as `read_write` member
- **Expected**: "Invite" button NOT visible

### F3: Invite Dialog Content
- **Steps**: Click "Invite" button
- **Expected**: Dialog shows role selector, expiry input, create button, team members list, invite history

### F4: Create Link & Copy
- **Steps**: Select role, click "Create Link"
- **Expected**: Link shown, copy button works

### F5: Revoke from Dialog
- **Steps**: Click X on pending invite in history
- **Expected**: Invite revoked, list refreshes

### F6: Accept Page (Logged In)
- **Steps**: Open invite link as logged-in user
- **Expected**: Shows project name, role, inviter, "Accept" button

### F7: Accept Page (Not Logged In)
- **Steps**: Open invite link without login
- **Expected**: Redirected to `/login?redirect=/invite/{token}`, then back after login

### F8: Accept Success
- **Steps**: Click "Accept Invitation"
- **Expected**: Success message, redirect to project dashboard

---

## G. Project Deletion

### G1: Delete with Cascade
- **Steps**: Create project with 5 memories and 2 invites, delete project
- **Expected**: Response shows `deleted_memories: 5`, memories removed from Qdrant, all invites/members deleted

### G2: Delete Confirmation (UI)
- **Steps**: Click delete on project in Settings/Projects page
- **Expected**: Dialog shows project name, requires typing slug, button disabled until match

### G3: Delete Non-Member Project
- **Steps**: Non-member tries DELETE `/api/v1/projects/{slug}`
- **Expected**: 403

### G4: Read-Write Cannot Delete
- **Steps**: `read_write` member tries delete
- **Expected**: 403

### G5: Navigate to Deleted Project
- **Steps**: Bookmark a project URL, delete the project, open bookmark
- **Expected**: "Project Not Found" page with link to dashboard

---

## H. Data Isolation Fixes

### H1: Archive Requires Auth
- **Steps**: POST `/api/v1/memories/actions/archive` without auth
- **Expected**: 401

### H2: Archive Requires Ownership
- **Steps**: User A archives User B's memory
- **Expected**: 403

### H3: Archive Respects Project Scope
- **Steps**: Archive memory from Project B while specifying project_slug for Project A
- **Expected**: 403 "Memory does not belong to this project"

### H4: Delete Requires Ownership
- **Steps**: User A deletes User B's memory
- **Expected**: 403

### H5: Global Pause Scoped to User
- **Steps**: User A uses `global_pause`, check User B's memories
- **Expected**: User B's memories unaffected

### H6: Category Pause Scoped to User
- **Steps**: User A pauses by category, check User B's memories in same category
- **Expected**: User B's memories unaffected

---

## Test Data Setup

1. **superadmin**: `arthaszeng`
2. **testowner**: owner of `test-project`
3. **testadmin**: admin of `test-project`
4. **testreader**: read_only of `test-project`
5. **testwriter**: read_write of `test-project`
6. Create memories in `test-project` by different users
7. Create invite links with various roles and expiry settings
