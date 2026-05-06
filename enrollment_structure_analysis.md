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