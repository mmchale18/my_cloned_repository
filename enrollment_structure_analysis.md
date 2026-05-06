## Structural diagnosis

The backend is implemented as a single procedural module with no explicit database/service separation. That makes the issues systemic rather than isolated.

| Issue identified | Where it appears in the system | Why it is a problem | Impact on scalability or maintainability |
|---|---|---|---|
| Single-module mixed responsibilities | `enrollment_starter.py` entire file | Database setup, SQL access, business validation, application flow, and export logic all live in one module. This means there is no clear boundary between persistence and domain logic. | Hard to evolve. Changes to data schema or business rules can require edits across many functions in one file, increasing risk and slowing refactors. |
| Database operations mixed with business rules | `enroll_with_key()` | This function validates input, resolves a course from an enrollment key, then inserts or updates enrollment rows with UPSERT semantics. It also embeds the “reactivate enrollment” business rule inside SQL. | Makes testing hard because service behavior cannot be isolated from DB side effects, and maintenance is harder because the function is doing too much. |
| Implicit session/state via globals | `CURRENT_STUDENT`, `STATUS_ENROLLED`, `STATUS_UNENROLLED`, `AVAILABLE_COURSE_KEYS`, `SAMPLE_ENROLLMENTS` | Shared global constants are used as runtime state rather than passing explicit student/context information into service methods. `main()` depends on `CURRENT_STUDENT`. | Limits reuse for multiple students/sessions or different environments, and increases coupling to module-level state. |
| Repeated SQL/query logic without shared abstraction | `get_student_enrollments()`, `get_student_enrollment_history()`, `get_student_course_record()`, `get_all_enrollment_records()`, `get_course_by_key()` | Multiple functions duplicate similar SELECT/JOIN patterns and row conversion logic. There is no reusable data access abstraction or repository layer. | Increases the chance of inconsistencies, makes schema changes expensive, and hides opportunities to centralize query semantics. |
| Application flow coupled directly with persistence | `main()` | `main()` performs DB setup, seeding, calling business operations, printing results, and exporting snapshots all in one flow. | Hard to test or reuse business flow separately from database initialization and CLI behavior. |
| Validation mixed with persistence logic | `enroll_with_key()`, `get_course_by_key()` | `enroll_with_key()` validates email and key, and `get_course_by_key()` normalizes the enrollment key input before querying. These are business/validation concerns embedded in data access routines. | Makes it harder to change validation rules independently of persistence logic, and obscures the responsibilities of each function. |
| Export and snapshot logic coupled with data access | `export_database_snapshot()` | This function composes current student info, course keys, and enrollment records, then writes JSON. It combines application-level export concerns with database queries. | Limits testability and makes the persistence layer depend on a specific export format and global state. |
| Schema definition and seed data in operational module | `create_tables()`, `seed_sample_data()` | The same module defines tables and seeds sample data while also containing runtime enrollment operations. | Blurs the line between database initialization/migration and application runtime behavior, making the module less modular and harder to maintain. |

### Key architectural observations

- There is no explicit “database layer” abstraction: every data operation opens a raw SQLite connection and executes SQL directly.
- There is no explicit “service/business layer”: functions like `enroll_with_key()` and `get_student_summary()` act as domain services, but they are mixed with SQL access and global state.
- The module is effectively a mixed layer: some functions are clearly persistence-focused, others are clearly business-focused, but there is no architectural boundary.
- Repeated logic and global state suggest the code is not organized for extensibility or unit-level testing.

This diagnosis should help orient a refactor by identifying where the current implementation violates separation of concerns and where responsibilities are currently mixed.

## Refactor plan

### 1. Define a clear separation between database logic and service logic

- **Database layer** should be responsible only for:
  - opening SQLite connections
  - creating tables
  - seeding sample data
  - executing SQL queries and updates
  - converting raw database rows into simple dictionaries or domain records
- **Service layer** should be responsible only for:
  - business rules and validation
  - enrollment workflows
  - status transitions
  - summary calculation
  - orchestrating calls to the database layer
  - composing higher-level application state such as export payloads

This means the service layer should never execute raw SQL, and the database layer should never decide whether an enrollment key is valid or whether a student should be reactivated.

---

### 2. Move business rules into a service layer

Identify these business responsibilities and relocate them from procedural functions into service methods:

- `enroll_with_key()`
  - validation of `user_id`, `email`, and `enrollment_key`
  - normalization of the enrollment key
  - decision that an existing record should be reactivated rather than treated as a fresh insert
- `soft_unenroll_student()`
  - verification that the provided `user_id` and `course_id` are valid before persistence
  - handling of the unenrollment workflow
- `get_student_summary()`
  - counting `enrolled` vs `unenrolled` records
  - deriving summary values from enrollment history
- `export_database_snapshot()`
  - assembling the snapshot object from application state and repository data
  - writing JSON output should remain separate from raw query logic

---

### 3. Restrict the database layer to only SQLite queries and updates

The database layer should expose only well-defined repository methods such as:

- `get_course_by_key(enrollment_key)`
- `get_available_course_keys()`
- `get_student_enrollments(user_id)`
- `get_student_enrollment_history(user_id)`
- `get_student_course_record(user_id, course_id)`
- `insert_or_update_enrollment(user_id, email, course_id, status)`
- `soft_unenroll(user_id, course_id)`
- `get_all_enrollment_records()`

These methods should not:
- validate email addresses
- enforce business-specific enrollment rules
- alter the meaning of status values
- write JSON exports

---

### 4. Identify what should become classes vs remaining functions

#### Classes
- `SqliteCourseRepository` (or `CourseRepository`)
  - responsibility: course-specific queries and seed data
  - methods: `get_by_enrollment_key`, `get_all_available_keys`, `seed_courses`
- `SqliteEnrollmentRepository` (or `EnrollmentRepository`)
  - responsibility: enrollment persistence operations
  - methods: `get_enrollments_for_student`, `get_enrollment_history`, `get_course_record`, `upsert_enrollment`, `soft_unenroll`, `get_all_records`, `seed_enrollments`
- `EnrollmentService`
  - responsibility: business logic for enrollment and unenrollment workflows
  - methods: `enroll_with_key`, `unenroll_student`, `get_student_summary`, `get_student_enrollments`, `get_student_enrollment_history`
  - should depend on repository instances instead of global state
- `SnapshotExporter` or `ExportService`
  - responsibility: create the JSON snapshot using service/repository data
  - methods: `export_snapshot(path, student_context)`

#### Functions
- `connect()` can remain as a small helper function or be encapsulated in a repository connection provider
- `create_tables()` and `seed_sample_data()` can remain as procedural setup functions, but they should be clearly separated from service behavior and likely called during application startup
- `main()` should remain as the application runner, orchestrating setup and calling service methods. It should not contain business rules.

---

### 5. Explain how state should flow through the system

- Remove reliance on module-level globals like `CURRENT_STUDENT`
- Pass student context explicitly into service methods:
  - `user_id`
  - `email`
  - `enrollment_key`
  - `course_id`
- Keep constants such as `STATUS_ENROLLED` and `STATUS_UNENROLLED` as simple module-level values or an internal enum-like configuration, but not as dynamic application state
- Ensure every state transition is explicit:
  - repository returns data
  - service validates and transforms it
  - application layer invokes service methods with explicit inputs
- Avoid using `CURRENT_STUDENT` inside service logic; instead, the caller provides current student details

---

### 6. Prioritize maintainability, scalability, and clarity

- Use dependency injection:
  - `EnrollmentService` should accept repository instances in its constructor
  - this makes the service testable without touching SQLite
- Consolidate repeated database/row-conversion logic inside repositories
- Keep SQL isolated and centralized, so schema changes only affect repository code
- Keep business rules explicit and easy to locate inside the service layer
- Keep application flow simple and readable in `main()` or an equivalent runner

---

## Separate implementation prompt

Create a refactored backend for the student enrollment system with the following structure:

- `SqliteCourseRepository`
  - responsible for course persistence and query operations
  - should handle only SQL queries against the `courses` table
  - methods should include:
    - `get_by_enrollment_key(enrollment_key)`
    - `get_all_available_keys()`
    - `seed_courses(course_list)`
- `SqliteEnrollmentRepository`
  - responsible for enrollment persistence and query operations
  - should handle only SQL queries against the `enrollments` table
  - methods should include:
    - `get_enrollments_for_student(user_id, status=STATUS_ENROLLED)`
    - `get_enrollment_history(user_id)`
    - `get_course_record(user_id, course_id)`
    - `upsert_enrollment(user_id, email, course_id, status)`
    - `soft_unenroll(user_id, course_id)`
    - `get_all_records()`
    - `seed_enrollments(enrollment_list)`
- `EnrollmentService`
  - responsible for business rules and service workflows
  - should enforce validation and decision-making logic before calling repository methods
  - methods should include:
    - `enroll_with_key(user_id, email, enrollment_key)`
    - `unenroll_student(user_id, course_id)`
    - `get_student_summary(user_id)`
    - `get_student_enrollments(user_id)`
    - `get_student_enrollment_history(user_id)`
  - should never execute raw SQL
  - should not depend on module-level student state
- `SnapshotExporter`
  - responsible for assembling the export snapshot and writing JSON to disk
  - should pull data from repositories/service and write it to the configured path
  - should accept explicit student context rather than using `CURRENT_STUDENT`
- `main()` or application runner
  - responsible for startup orchestration only
  - should create tables, seed sample data, instantiate repositories and services, and call service methods
  - should not contain business validation logic

Rules to enforce during refactoring:

- preserve existing behavior exactly
- keep SQL isolated in repository classes
- move validation and business rules into the service layer
- eliminate implicit global application state in service logic
- reduce repeated database-query patterns by centralizing them in repositories
- keep the procedural shell only for startup and demonstration flow, not for business operations
- do not introduce UI or frontend concerns
- do not merge planning and implementation; the refactor should only clarify layering

Context from analysis:

- The existing system mixes database logic and service logic in the same functions, especially in enrollment and unenrollment workflows.
- The current procedural structure leaves no consistent layering, causing business rules and persistence to be tangled.
- Global state like `CURRENT_STUDENT` is used instead of explicit state passing.
- This refactor should be minimal enough to keep behavior unchanged while making the codebase maintainable, testable, and clearly layered.