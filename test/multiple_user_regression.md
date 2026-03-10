# Multi-User Regression Test Suite

> Last updated: 2026-03-11
> Covers: Auth, User CRUD, Project CRUD, Members, Memory Isolation, API Keys, Navigation

---

## A. Authentication & Login Flow

### A1: Admin Login
- **Steps**: POST `/auth/login` with `arthaszeng / changeme123`
- **Expected**: 200, returns `access_token`, `must_change_password=false`, `user.is_superadmin=true`

### A2: Invalid Login
- **Steps**: POST `/auth/login` with wrong password
- **Expected**: 401 "Invalid credentials"

### A3: Inactive User Login
- **Steps**: Deactivate a user, then try to login
- **Expected**: 401 "Invalid credentials"

### A4: New User Must Change Password
- **Steps**: Create user via admin, login as new user
- **Expected**: `must_change_password=true`, UI redirects to `/change-password`

### A5: Change Password Flow
- **Steps**: POST `/auth/change-password` with old + new password
- **Expected**: 200, `must_change_password` cleared, user can login with new password

### A6: JWT Expiry
- **Steps**: Use an expired JWT token to access API
- **Expected**: 401 from nginx gateway

### A7: API Key Authentication
- **Steps**: Create API key, use `Authorization: Bearer om_xxx` to call API
- **Expected**: Gateway accepts, `X-Auth-*` headers injected correctly

---

## B. User Management (superadmin only)

### B1: Create User
- **Steps**: POST `/auth/users` with username, password, email
- **Expected**: 200, user created with `must_change_password=true`

### B2: Create Duplicate User
- **Steps**: POST `/auth/users` with existing username
- **Expected**: 409 "Username already exists"

### B3: List Users
- **Steps**: GET `/auth/users` as superadmin
- **Expected**: Returns all users with correct fields

### B4: Non-Admin Access Users API
- **Steps**: GET `/auth/users` as non-superadmin
- **Expected**: 403 "Superadmin required"

### B5: Deactivate User
- **Steps**: DELETE `/auth/users/{id}` as superadmin
- **Expected**: User `is_active=false`, cannot login

### B6: Cannot Deactivate Self
- **Steps**: DELETE `/auth/users/{own_id}`
- **Expected**: 400 "Cannot deactivate yourself"

### B7: Reset Password
- **Steps**: POST `/auth/users/{id}/reset-password`
- **Expected**: Password changed, `must_change_password=true`

---

## C. Project Management

### C1: Auto-Default Project on First Access
- **Steps**: Create new user in auth, login, call any API endpoint
- **Expected**: User auto-provisioned in API DB, default project created with username as slug, user is admin member

### C2: Existing User Without Project Gets Default
- **Steps**: User exists in API DB but has no ProjectMember records, makes API call
- **Expected**: Default project auto-created and user added as member

### C3: Create Project
- **Steps**: POST `/api/v1/projects` with name + optional slug
- **Expected**: Project created, caller added as admin member, slug auto-generated if not provided

### C4: List Projects (Normal User)
- **Steps**: GET `/api/v1/projects` as normal user
- **Expected**: Only projects where user is a member

### C5: List Projects (Superadmin)
- **Steps**: GET `/api/v1/projects` as superadmin
- **Expected**: ALL projects visible, with `owner_username` and `member_count` fields

### C6: Get Project Detail
- **Steps**: GET `/api/v1/projects/{slug}`
- **Expected**: Project info with user's role

### C7: Update Project
- **Steps**: PUT `/api/v1/projects/{slug}` with new name
- **Expected**: Updated (admin+ only)

### C8: Update Project (Insufficient Permission)
- **Steps**: PUT as read-only member
- **Expected**: 403

### C9: Delete Project
- **Steps**: DELETE `/api/v1/projects/{slug}` as admin
- **Expected**: Project deleted, members cascade deleted

### C10: Duplicate Slug
- **Steps**: Create project with slug that already exists
- **Expected**: 409

---

## D. Member Management

### D1: List Members
- **Steps**: GET `/api/v1/projects/{slug}/members`
- **Expected**: List of members with username, role, created_at

### D2: Add Member
- **Steps**: POST `/api/v1/projects/{slug}/members` with `{ username, role }`
- **Expected**: Member added (admin+ only)

### D3: Add Member (Non-Admin)
- **Steps**: POST as read-only or normal member
- **Expected**: 403

### D4: Add Duplicate Member
- **Steps**: Add user who is already a member
- **Expected**: 409 "User already a member"

### D5: Add Non-Existent User
- **Steps**: Add username that doesn't exist in API DB
- **Expected**: 404

### D6: Remove Member
- **Steps**: DELETE `/api/v1/projects/{slug}/members/{username}`
- **Expected**: Member removed (admin+ only)

### D7: Remove Non-Member
- **Steps**: Remove username not in project
- **Expected**: 404

---

## E. Memory CRUD & Project Isolation

### E1: Create Memory in Project
- **Steps**: POST `/api/v1/memories/` with `project_slug`
- **Expected**: Memory created with `project_id` set, visible in that project only

### E2: List Memories (Project Scoped)
- **Steps**: POST `/api/v1/memories/filter` with `project_slug`
- **Expected**: Only memories belonging to that project returned

### E3: Cross-Project Isolation
- **Steps**: User is member of Project A and B; create memory in A; list memories in B
- **Expected**: Memory from A does NOT appear in B's list

### E4: Memory Without Project
- **Steps**: Create memory without `project_slug`
- **Expected**: Memory created with `project_id=null`, not visible in any project-scoped query

### E5: Get Single Memory
- **Steps**: GET `/api/v1/memories/{id}`
- **Expected**: Only accessible if user owns the memory or is superadmin

### E6: Delete Memory
- **Steps**: DELETE `/api/v1/memories/` with memory_ids
- **Expected**: Memories marked as deleted in DB and removed from Qdrant

### E7: Superadmin Sees All Project Memories
- **Steps**: Superadmin views project that has memories from other users
- **Expected**: All memories in the project visible to superadmin

### E8: Non-Member Cannot Access Project Memories
- **Steps**: User not in project tries to list memories with that project_slug
- **Expected**: 403 "Not a member of this project"

### E9: Read-Only Cannot Create Memory
- **Steps**: Read-only member tries POST `/api/v1/memories/` with project_slug
- **Expected**: 403

---

## F. API Keys Management

### F1: Create API Key
- **Steps**: POST `/auth/api-keys` with name
- **Expected**: Returns raw key (only shown once), key_prefix, name

### F2: List Own Keys
- **Steps**: GET `/auth/api-keys`
- **Expected**: User's own keys only

### F3: Admin List All Keys
- **Steps**: GET `/auth/api-keys/admin/all` as superadmin
- **Expected**: All keys grouped by username

### F4: Revoke Own Key
- **Steps**: DELETE `/auth/api-keys/{id}`
- **Expected**: Key `is_active=false`

### F5: Admin Revoke Any Key
- **Steps**: DELETE `/auth/api-keys/admin/{id}` as superadmin
- **Expected**: Key revoked

### F6: Non-Admin Cannot Admin Endpoints
- **Steps**: Non-superadmin calls admin key endpoints
- **Expected**: 403

---

## G. UI Navigation & Routing

### G1: Login → Dashboard Redirect
- **Steps**: Login as user with projects
- **Expected**: Redirected to `/{firstProjectSlug}`

### G2: Login → No Projects
- **Steps**: Login as user with no projects (should not happen after auto-project fix)
- **Expected**: Auto-project created, redirected to it

### G3: Project Switcher
- **Steps**: Click project dropdown, select different project
- **Expected**: URL changes to `/{newSlug}`, data reloads for new project

### G4: Admin Settings Visibility
- **Steps**: Login as superadmin
- **Expected**: "Admin Settings" nav link visible

### G5: Admin Settings Hidden for Non-Admin
- **Steps**: Login as normal user
- **Expected**: "Admin Settings" nav link NOT visible

### G6: Admin Settings Guard
- **Steps**: Non-admin navigates directly to `/settings`
- **Expected**: "Access Denied" message

### G7: User Switch Updates Nav
- **Steps**: Logout, login as different user
- **Expected**: Nav correctly shows/hides Admin Settings based on new user's role

### G8: Dashboard Stats Per Project
- **Steps**: Switch between projects
- **Expected**: Stats (memory count, app count) update per project

### G9: Memories Page Pagination
- **Steps**: Navigate to `/memories` in a project with >10 memories
- **Expected**: Pagination works, page switcher functional

### G10: Apps Page
- **Steps**: Navigate to `/{slug}/apps`
- **Expected**: App list loads correctly with memory counts

---

## H. Data Isolation Security

### H1: Cross-User Memory Read
- **Steps**: User A creates memory; User B (in same project) tries GET `/api/v1/memories/{id}`
- **Expected**: 403 (unless B is superadmin)

### H2: Cross-Project Memory in Qdrant
- **Steps**: Verify Qdrant payload includes `project_id` for project-scoped memories
- **Expected**: `project_id` field present in Qdrant payload

### H3: Archive Without Auth
- **Steps**: Call POST `/api/v1/memories/actions/archive` without auth
- **Expected**: 401 (currently a known bug -- no auth check)

### H4: Delete Memories Cross-Project
- **Steps**: User in Project A tries to delete memory_ids that belong to Project B
- **Expected**: Should be rejected or filtered

### H5: Pause Memories Cross-Project
- **Steps**: User tries to pause memories from another project
- **Expected**: Only own memories affected

---

## Test Data Setup

For running these tests, prepare:
1. **superadmin**: `arthaszeng` (already exists)
2. **testuser1**: normal user, member of `project-alpha`
3. **testuser2**: normal user, member of `project-alpha` (read-only) and `project-beta` (admin)
4. Create projects: `project-alpha`, `project-beta`
5. Create memories in each project by different users
