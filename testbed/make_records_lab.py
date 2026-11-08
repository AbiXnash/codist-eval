"""Builds records-lab: a Spring Boot 4 gateway that reads a database and serves it as JSON, XML, CSV and GraphQL,
with planted bugs, one commit per change, for testing Codist.

The service reads an employee directory (departments, employees, pay and national ids) from a database over JDBC
(JdbcClient, no JPA) and serves it four ways: a JSON REST API, an XML export written with StAX, a CSV export and a
GraphQL API (Spring for GraphQL, with batch loading). Its README holds twelve rules about what may be shown and how.

The bugs come in the same kinds as shop-lab:
  seen-rule   well-known Java mistakes that Codist's code checks look for
  seen-logic  classic mistakes common in public code (XML escaping, locale-dependent lower case)
  novel       mistakes that only show against this service's own rules: personal data leaking, deleted records
              exported, times not in UTC, rounding, CSV formula injection, page size caps, the formats disagreeing
  ai-only     no check matches and the code cannot be run alone (transactions, access checks, swapped arguments)
and controls: a pure refactor, two fixes of earlier bugs and two correct features (anything reported is a false
alarm).

The answer key is written next to this script, never into the repository. Commit messages describe the change the
way a developer would, without naming the bug.

    python3 make_records_lab.py ~/dev/records-lab
"""
import json, os, subprocess, sys

DEST = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/dev/records-lab"))
HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = "4.0.6"
files = {}
truth = []


def git(*args):
    subprocess.run(["git", "-C", DEST, "-c", "user.name=Lab Dev", "-c", "user.email=dev@records-lab.test",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def put(path, text):
    files[path] = text
    full = os.path.join(DEST, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def edit(path, old, new):
    text = files[path]
    assert text.count(old) == 1, (path, old)
    put(path, text.replace(old, new))


def line_of(path, needle):
    for i, l in enumerate(files[path].split("\n"), 1):
        if needle in l:
            return i
    raise SystemExit(f"{needle!r} not in {path}")


def commit(message, kind=None, bug=None, path=None, needle=None, rule=None, behaviour=False):
    git("add", "-A")
    git("commit", "-q", "-m", message)
    sha = subprocess.run(["git", "-C", DEST, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if kind:
        truth.append({"sha": sha, "message": message, "kind": kind, "bug": bug, "path": path,
                      "line": line_of(path, needle) if needle else None, "rule": rule, "behaviourCanSee": behaviour})


# ---------------------------------------------------------------- base: a correct gateway

if os.path.exists(DEST):
    raise SystemExit(f"{DEST} exists; remove it first")
os.makedirs(DEST)
git("init", "-q", "-b", "main")

put(".gitignore", "target/\n")
put("pom.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{BOOT}</version>
    <relativePath/>
  </parent>
  <groupId>com.recordslab</groupId>
  <artifactId>records-lab</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
""")

RULES = """1. **Personal data stays in the HR view.** Pay and national ids are shown only by `/api/hr/**`, and only to a
   request with the header `X-Role: hr`. Every other view (the JSON API, the XML and CSV exports, GraphQL) leaves
   them out.
2. **Money is exact.** Amounts are `BigDecimal`, never `double`, with two decimals, rounded half-even (banker's
   rounding).
3. **Times are UTC.** Every format shows a time as ISO-8601 in UTC to the second, such as `2024-05-01T09:30:00Z`.
4. **Pages are numbered from 1, and hold at most 100.** A missing or smaller page is page 1; a missing size is 20;
   a larger size is cut to 100. This holds in every API, GraphQL included.
5. **Deleted records are gone.** A row with `deleted_at` set is never shown, counted or exported.
6. **The formats agree.** JSON, XML, CSV and GraphQL give the same records with the same values.
7. **Filters are parameters.** Text from a request reaches SQL only as a bound parameter.
8. **CSV cannot run.** A CSV cell that starts with `=`, `+`, `-` or `@` gets a leading `'`, so a spreadsheet shows
   it as text rather than running it as a formula.
9. **One order everywhere.** Records are sorted by family name, then given name, ignoring case, then id, so pages
   never overlap or skip anyone.
10. **Emails are lower case.** In every format, whatever case was stored.
11. **An export is one snapshot.** A full export reads the employees and departments in one read-only transaction,
    so it never mixes data from before and after a change.
12. **Head counts are of active people.** A department's head count leaves out deleted employees.
"""

put("README.md", f"""# Records Lab

A read-only gateway to a company's employee directory, on Spring Boot 4. It reads the directory from a database over
JDBC and serves it four ways:

| Way | Where | For |
|---|---|---|
| JSON | `GET /api/employees`, `/api/employees/{{id}}`, `/api/departments`, `/api/hr/employees/{{id}}` | apps |
| XML | `GET /export/employees.xml` | the payroll provider's import |
| CSV | `GET /export/employees.csv` | spreadsheets |
| GraphQL | `POST /graphql` (GraphiQL at `/graphiql`) | the intranet |

The database is H2 in memory, filled from `schema.sql` and `data.sql` at start. Run it with `mvn spring-boot:run`;
it listens on port 8090.

## Rules

{RULES}""")
put(".codist/rules.md", "# Records Lab rules\n\n" + RULES)

put("src/main/resources/application.yml", """spring:
  application:
    name: records-lab
  datasource:
    url: jdbc:h2:mem:records;DB_CLOSE_DELAY=-1
  sql:
    init:
      mode: always
  graphql:
    graphiql:
      enabled: true
server:
  port: 8090
""")
put("src/main/resources/schema.sql", """CREATE TABLE department (
    id   BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(10)  NOT NULL UNIQUE
);

CREATE TABLE employee (
    id            BIGINT PRIMARY KEY,
    given_name    VARCHAR(100) NOT NULL,
    family_name   VARCHAR(100) NOT NULL,
    email         VARCHAR(200) NOT NULL,
    department_id BIGINT NOT NULL REFERENCES department (id),
    hired_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    salary        DECIMAL(14, 4) NOT NULL,
    national_id   VARCHAR(20) NOT NULL,
    deleted_at    TIMESTAMP WITH TIME ZONE
);
""")
put("src/main/resources/data.sql", """INSERT INTO department (id, name, code) VALUES
    (1, 'Engineering', 'ENG'),
    (2, 'Finance', 'FIN'),
    (3, 'People', 'HR');

INSERT INTO employee (id, given_name, family_name, email, department_id, hired_at, salary, national_id, deleted_at) VALUES
    (1, 'Asha', 'Rao', 'Asha.Rao@Example.com', 1, TIMESTAMP WITH TIME ZONE '2021-03-01 09:00:00+05:30', 1850000.00, 'IN-1234-5678', NULL),
    (2, 'ben', 'de Vries', 'ben.devries@example.com', 1, TIMESTAMP WITH TIME ZONE '2022-07-15 08:30:00+02:00', 1625000.50, 'NL-8765-4321', NULL),
    (3, 'Chen', 'Li', 'chen.li@example.com', 2, TIMESTAMP WITH TIME ZONE '2019-11-04 10:00:00+08:00', 2100000.00, 'CN-1111-2222', NULL),
    (4, 'Dara', 'O''Neill', 'dara.oneill@example.com', 3, TIMESTAMP WITH TIME ZONE '2020-01-20 09:00:00+00:00', 1400000.25, 'IE-3333-4444', NULL),
    (5, 'Emre', 'Yilmaz', 'EMRE.YILMAZ@EXAMPLE.COM', 2, TIMESTAMP WITH TIME ZONE '2023-05-02 09:00:00+03:00', 1550000.00, 'TR-5555-6666', NULL),
    (6, 'Farah', 'Khan', 'farah.khan@example.com', 1, TIMESTAMP WITH TIME ZONE '2018-02-12 09:00:00+05:00', 1990000.00, 'PK-7777-8888',
        TIMESTAMP WITH TIME ZONE '2024-06-30 17:00:00+00:00'),
    (7, '=HYPERLINK("http://x.test")', 'Test', 'test@example.com', 3, TIMESTAMP WITH TIME ZONE '2024-01-01 00:00:00+00:00', 1.00, 'XX-0000-0000', NULL),
    (8, 'Ana', 'rao', 'ana.rao@example.com', 2, TIMESTAMP WITH TIME ZONE '2024-08-19 09:15:30+00:00', 1200000.005, 'BR-9999-0000', NULL);
""")

J = "src/main/java/com/recordslab"
put(f"{J}/RecordsApplication.java", """package com.recordslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RecordsApplication {
    public static void main(String[] args) {
        SpringApplication.run(RecordsApplication.class, args);
    }
}
""")

# ---- the data, as stored
put(f"{J}/model/Employee.java", """package com.recordslab.model;

import java.math.BigDecimal;
import java.time.Instant;

/** One row of the employee table. Salary and nationalId are personal data: only HrEmployee shows them (rule 1). */
public record Employee(long id, String givenName, String familyName, String email, long departmentId,
                       Instant hiredAt, BigDecimal salary, String nationalId, Instant deletedAt) {

    public boolean active() {
        return deletedAt == null;
    }
}
""")
put(f"{J}/model/Department.java", """package com.recordslab.model;

public record Department(long id, String name, String code) {
}
""")

# ---- formatting rules shared by every format
put(f"{J}/format/Dates.java", """package com.recordslab.format;

import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

/** Rule 3: every format shows a time as ISO-8601 in UTC to the second, such as 2024-05-01T09:30:00Z. */
public final class Dates {
    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_INSTANT;

    private Dates() {
    }

    public static String iso(Instant time) {
        if (time == null) {
            return null;
        }
        return ISO.format(time.truncatedTo(ChronoUnit.SECONDS));
    }
}
""")
put(f"{J}/format/Money.java", """package com.recordslab.format;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** Rule 2: money is BigDecimal with two decimals, rounded half-even. */
public final class Money {
    private Money() {
    }

    public static BigDecimal round(BigDecimal amount) {
        return amount.setScale(2, RoundingMode.HALF_EVEN);
    }

    public static String format(BigDecimal amount) {
        return round(amount).toPlainString();
    }

    /** A twelfth of a yearly amount. */
    public static BigDecimal monthly(BigDecimal yearly) {
        return yearly.divide(BigDecimal.valueOf(12), 2, RoundingMode.HALF_EVEN);
    }
}
""")
put(f"{J}/format/Emails.java", """package com.recordslab.format;

import java.util.Locale;

/** Rule 10: emails are shown in lower case in every format. */
public final class Emails {
    private Emails() {
    }

    public static String normal(String email) {
        if (email == null) {
            return null;
        }
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
""")
put(f"{J}/format/CsvCell.java", """package com.recordslab.format;

/** One CSV cell. Rule 8: a cell a spreadsheet would run as a formula gets a leading quote. */
public final class CsvCell {
    private static final String FORMULA_STARTS = "=+-@";

    private CsvCell() {
    }

    public static String of(String value) {
        if (value == null || value.isEmpty()) {
            return "";
        }
        String text = value;
        if (FORMULA_STARTS.indexOf(text.charAt(0)) >= 0) {
            text = "'" + text;
        }
        if (text.contains(",") || text.contains("\\"") || text.contains("\\n")) {
            text = "\\"" + text.replace("\\"", "\\"\\"") + "\\"";
        }
        return text;
    }

    public static String row(String... values) {
        StringBuilder line = new StringBuilder();
        for (int i = 0; i < values.length; i++) {
            if (i > 0) {
                line.append(',');
            }
            line.append(of(values[i]));
        }
        return line.append("\\r\\n").toString();
    }
}
""")

# ---- paging
put(f"{J}/query/Paging.java", """package com.recordslab.query;

/** Rule 4: pages are numbered from 1; a missing size is 20 and a larger one is cut to 100. */
public record Paging(int page, int size) {
    public static final int DEFAULT_SIZE = 20;
    public static final int MAX_SIZE = 100;

    public static Paging of(Integer page, Integer size) {
        int p = page == null || page < 1 ? 1 : page;
        int s = size == null || size < 1 ? DEFAULT_SIZE : Math.min(size, MAX_SIZE);
        return new Paging(p, s);
    }

    public int offset() {
        return (page - 1) * size;
    }
}
""")

# ---- the database
put(f"{J}/db/EmployeeRepository.java", """package com.recordslab.db;

import com.recordslab.model.Employee;
import com.recordslab.query.Paging;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class EmployeeRepository {
    private static final String SELECT = "SELECT id, given_name, family_name, email, department_id, hired_at, salary, "
            + "national_id, deleted_at FROM employee";
    /** Rule 9: one order everywhere, ignoring case, with the id last so pages never overlap. */
    private static final String ORDER = " ORDER BY LOWER(family_name), LOWER(given_name), id";

    private final JdbcClient jdbc;

    public EmployeeRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public List<Employee> page(Paging paging) {
        return jdbc.sql(SELECT + " WHERE deleted_at IS NULL" + ORDER + " LIMIT :size OFFSET :offset")
                .param("size", paging.size())
                .param("offset", paging.offset())
                .query(this::row)
                .list();
    }

    public Optional<Employee> find(long id) {
        return jdbc.sql(SELECT + " WHERE id = :id AND deleted_at IS NULL")
                .param("id", id)
                .query(this::row)
                .optional();
    }

    /** Every active employee, for the exports. */
    public List<Employee> all() {
        return jdbc.sql(SELECT + " WHERE deleted_at IS NULL" + ORDER).query(this::row).list();
    }

    /** Active employees per department id (rule 12). */
    public Map<Long, Integer> headCounts() {
        Map<Long, Integer> counts = new HashMap<>();
        jdbc.sql("SELECT department_id, COUNT(*) AS n FROM employee WHERE deleted_at IS NULL GROUP BY department_id")
                .query(rs -> {
                    counts.put(rs.getLong("department_id"), rs.getInt("n"));
                });
        return counts;
    }

    private Employee row(ResultSet rs, int n) throws SQLException {
        OffsetDateTime deleted = rs.getObject("deleted_at", OffsetDateTime.class);
        return new Employee(rs.getLong("id"), rs.getString("given_name"), rs.getString("family_name"),
                rs.getString("email"), rs.getLong("department_id"),
                rs.getObject("hired_at", OffsetDateTime.class).toInstant(), rs.getBigDecimal("salary"),
                rs.getString("national_id"), deleted == null ? null : deleted.toInstant());
    }
}
""")
put(f"{J}/db/DepartmentRepository.java", """package com.recordslab.db;

import com.recordslab.model.Department;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class DepartmentRepository {
    private final JdbcClient jdbc;

    public DepartmentRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public List<Department> all() {
        return jdbc.sql("SELECT id, name, code FROM department ORDER BY name").query(Department.class).list();
    }

    public Optional<Department> find(long id) {
        return jdbc.sql("SELECT id, name, code FROM department WHERE id = :id")
                .param("id", id)
                .query(Department.class)
                .optional();
    }

    /** Every department by id, read once so a list of employees never queries per row. */
    public Map<Long, Department> byId() {
        Map<Long, Department> out = new LinkedHashMap<>();
        for (Department d : all()) {
            out.put(d.id(), d);
        }
        return out;
    }
}
""")

# ---- what each audience sees
put(f"{J}/view/PublicEmployee.java", """package com.recordslab.view;

import com.recordslab.format.Dates;
import com.recordslab.format.Emails;
import com.recordslab.model.Department;
import com.recordslab.model.Employee;

/** What anyone may see about an employee (rule 1): no pay, no national id. */
public record PublicEmployee(long id, String givenName, String familyName, String email, String department,
                             String hiredAt) {

    public static PublicEmployee of(Employee e, Department d) {
        return new PublicEmployee(e.id(), e.givenName(), e.familyName(), Emails.normal(e.email()), d.name(),
                Dates.iso(e.hiredAt()));
    }
}
""")
put(f"{J}/view/HrEmployee.java", """package com.recordslab.view;

import com.recordslab.format.Dates;
import com.recordslab.format.Emails;
import com.recordslab.format.Money;
import com.recordslab.model.Department;
import com.recordslab.model.Employee;

/** The HR view: everything, pay and national id included (rule 1). Only for X-Role: hr. */
public record HrEmployee(long id, String givenName, String familyName, String email, String department,
                         String hiredAt, String salary, String monthly, String nationalId) {

    public static HrEmployee of(Employee e, Department d) {
        return new HrEmployee(e.id(), e.givenName(), e.familyName(), Emails.normal(e.email()), d.name(),
                Dates.iso(e.hiredAt()), Money.format(e.salary()), Money.monthly(e.salary()).toPlainString(),
                e.nationalId());
    }
}
""")
put(f"{J}/view/DepartmentView.java", """package com.recordslab.view;

import com.recordslab.model.Department;

public record DepartmentView(long id, String name, String code, int headCount) {

    public static DepartmentView of(Department d, int headCount) {
        return new DepartmentView(d.id(), d.name(), d.code(), headCount);
    }
}
""")

# ---- access
put(f"{J}/security/Access.java", """package com.recordslab.security;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Rule 1: only a request with X-Role: hr sees pay and national ids. */
public final class Access {
    public static final String HEADER = "X-Role";
    public static final String HR = "hr";

    private Access() {
    }

    public static void requireHr(String role) {
        if (!HR.equals(role)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "This view is for HR only.");
        }
    }
}
""")

# ---- the service the four formats share
put(f"{J}/service/Directory.java", """package com.recordslab.service;

import com.recordslab.db.DepartmentRepository;
import com.recordslab.db.EmployeeRepository;
import com.recordslab.model.Department;
import com.recordslab.query.Paging;
import com.recordslab.view.DepartmentView;
import com.recordslab.view.HrEmployee;
import com.recordslab.view.PublicEmployee;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class Directory {
    private final EmployeeRepository employees;
    private final DepartmentRepository departments;

    public Directory(EmployeeRepository employees, DepartmentRepository departments) {
        this.employees = employees;
        this.departments = departments;
    }

    public List<PublicEmployee> page(Paging paging) {
        Map<Long, Department> byId = departments.byId();
        return employees.page(paging).stream().map(e -> PublicEmployee.of(e, byId.get(e.departmentId()))).toList();
    }

    public Optional<PublicEmployee> one(long id) {
        Map<Long, Department> byId = departments.byId();
        return employees.find(id).map(e -> PublicEmployee.of(e, byId.get(e.departmentId())));
    }

    public Optional<HrEmployee> hr(long id) {
        Map<Long, Department> byId = departments.byId();
        return employees.find(id).map(e -> HrEmployee.of(e, byId.get(e.departmentId())));
    }

    /** Everyone, for a full export: one snapshot (rule 11). */
    @Transactional(readOnly = true)
    public List<PublicEmployee> everyone() {
        Map<Long, Department> byId = departments.byId();
        return employees.all().stream().map(e -> PublicEmployee.of(e, byId.get(e.departmentId()))).toList();
    }

    public List<DepartmentView> departments() {
        Map<Long, Integer> counts = employees.headCounts();
        return departments.all().stream().map(d -> DepartmentView.of(d, counts.getOrDefault(d.id(), 0))).toList();
    }
}
""")

# ---- JSON
put(f"{J}/api/EmployeeController.java", """package com.recordslab.api;

import com.recordslab.query.Paging;
import com.recordslab.security.Access;
import com.recordslab.service.Directory;
import com.recordslab.view.DepartmentView;
import com.recordslab.view.HrEmployee;
import com.recordslab.view.PublicEmployee;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class EmployeeController {
    private final Directory directory;

    public EmployeeController(Directory directory) {
        this.directory = directory;
    }

    @GetMapping("/employees")
    public List<PublicEmployee> list(@RequestParam(required = false) Integer page,
                                     @RequestParam(required = false) Integer size) {
        return directory.page(Paging.of(page, size));
    }

    @GetMapping("/employees/{id}")
    public PublicEmployee one(@PathVariable long id) {
        return directory.one(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @GetMapping("/hr/employees/{id}")
    public HrEmployee hr(@PathVariable long id, @RequestHeader(value = Access.HEADER, required = false) String role) {
        Access.requireHr(role);
        return directory.hr(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @GetMapping("/departments")
    public List<DepartmentView> departments() {
        return directory.departments();
    }
}
""")

# ---- XML, written with StAX so nothing extra is needed
put(f"{J}/export/XmlExportController.java", """package com.recordslab.export;

import com.recordslab.service.Directory;
import com.recordslab.view.PublicEmployee;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamWriter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** The payroll provider's import: every active employee as XML, UTF-8. */
@RestController
public class XmlExportController {
    private final Directory directory;

    public XmlExportController(Directory directory) {
        this.directory = directory;
    }

    @GetMapping("/export/employees.xml")
    public void export(HttpServletResponse response) throws IOException, XMLStreamException {
        response.setContentType("application/xml;charset=UTF-8");
        XMLStreamWriter xml = XMLOutputFactory.newFactory().createXMLStreamWriter(response.getOutputStream(), "UTF-8");
        xml.writeStartDocument("UTF-8", "1.0");
        xml.writeStartElement("employees");
        for (PublicEmployee e : directory.everyone()) {
            xml.writeStartElement("employee");
            xml.writeAttribute("id", Long.toString(e.id()));
            text(xml, "givenName", e.givenName());
            text(xml, "familyName", e.familyName());
            text(xml, "email", e.email());
            text(xml, "department", e.department());
            text(xml, "hiredAt", e.hiredAt());
            xml.writeEndElement();
        }
        xml.writeEndElement();
        xml.writeEndDocument();
        xml.flush();
    }

    private static void text(XMLStreamWriter xml, String name, String value) throws XMLStreamException {
        xml.writeStartElement(name);
        xml.writeCharacters(value == null ? "" : value);
        xml.writeEndElement();
    }
}
""")

# ---- CSV
put(f"{J}/export/CsvExportController.java", """package com.recordslab.export;

import com.recordslab.format.CsvCell;
import com.recordslab.service.Directory;
import com.recordslab.view.PublicEmployee;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Every active employee as CSV, for spreadsheets. */
@RestController
public class CsvExportController {
    private final Directory directory;

    public CsvExportController(Directory directory) {
        this.directory = directory;
    }

    @GetMapping(value = "/export/employees.csv", produces = "text/csv")
    public String export() {
        StringBuilder csv = new StringBuilder(CsvCell.row("id", "givenName", "familyName", "email", "department", "hiredAt"));
        for (PublicEmployee e : directory.everyone()) {
            csv.append(CsvCell.row(Long.toString(e.id()), e.givenName(), e.familyName(), e.email(), e.department(),
                    e.hiredAt()));
        }
        return csv.toString();
    }
}
""")

# ---- GraphQL
put("src/main/resources/graphql/schema.graphqls", """type Query {
    employees(page: Int, size: Int): [Employee!]!
    employee(id: ID!): Employee
    departments: [Department!]!
}

type Employee {
    id: ID!
    givenName: String!
    familyName: String!
    email: String!
    hiredAt: String!
    department: Department!
}

type Department {
    id: ID!
    name: String!
    code: String!
    headCount: Int!
}
""")
put(f"{J}/graphql/DirectoryGraph.java", """package com.recordslab.graphql;

import com.recordslab.db.DepartmentRepository;
import com.recordslab.db.EmployeeRepository;
import com.recordslab.format.Dates;
import com.recordslab.format.Emails;
import com.recordslab.model.Department;
import com.recordslab.model.Employee;
import com.recordslab.query.Paging;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

/** The intranet's GraphQL API. The schema has no pay or national id fields (rule 1). */
@Controller
public class DirectoryGraph {
    private final EmployeeRepository employees;
    private final DepartmentRepository departments;

    public DirectoryGraph(EmployeeRepository employees, DepartmentRepository departments) {
        this.employees = employees;
        this.departments = departments;
    }

    @QueryMapping
    public List<Employee> employees(@Argument Integer page, @Argument Integer size) {
        return employees.page(Paging.of(page, size));
    }

    @QueryMapping
    public Employee employee(@Argument long id) {
        return employees.find(id).orElse(null);
    }

    @QueryMapping
    public List<Department> departments() {
        return departments.all();
    }

    @SchemaMapping(typeName = "Employee")
    public String email(Employee e) {
        return Emails.normal(e.email());
    }

    @SchemaMapping(typeName = "Employee")
    public String hiredAt(Employee e) {
        return Dates.iso(e.hiredAt());
    }

    /** All the departments of one page of employees in one read, not one per employee. */
    @BatchMapping(typeName = "Employee")
    public Map<Employee, Department> department(List<Employee> list) {
        Map<Long, Department> byId = departments.byId();
        Map<Employee, Department> out = new LinkedHashMap<>();
        for (Employee e : list) {
            out.put(e, byId.get(e.departmentId()));
        }
        return out;
    }

    @BatchMapping(typeName = "Department")
    public Map<Department, Integer> headCount(List<Department> list) {
        Map<Long, Integer> counts = employees.headCounts();
        Map<Department, Integer> out = new LinkedHashMap<>();
        for (Department d : list) {
            out.put(d, counts.getOrDefault(d.id(), 0));
        }
        return out;
    }
}
""")
commit("Set up the records gateway: JSON, XML, CSV and GraphQL over the employee directory")

D, R, X, C, G = (f"{J}/service/Directory.java", f"{J}/db/EmployeeRepository.java",
                 f"{J}/export/XmlExportController.java", f"{J}/export/CsvExportController.java",
                 f"{J}/graphql/DirectoryGraph.java")
API, ACC, PUB = f"{J}/api/EmployeeController.java", f"{J}/security/Access.java", f"{J}/view/PublicEmployee.java"

# ---------------------------------------------------------------- seen, found by code checks

edit(R, """    /** Active employees per department id (rule 12). */""", """    /** Active employees whose given or family name contains the text, ignoring case. */
    public List<Employee> search(String text, Paging paging) {
        return jdbc.sql(SELECT + " WHERE deleted_at IS NULL AND (LOWER(family_name) LIKE '%" + text.toLowerCase()
                        + "%' OR LOWER(given_name) LIKE '%" + text.toLowerCase() + "%')" + ORDER
                        + " LIMIT :size OFFSET :offset")
                .param("size", paging.size())
                .param("offset", paging.offset())
                .query(this::row)
                .list();
    }

    /** Active employees per department id (rule 12). */""")
edit(D, """    public Optional<PublicEmployee> one(long id) {""", """    public List<PublicEmployee> search(String text, Paging paging) {
        Map<Long, Department> byId = departments.byId();
        return employees.search(text, paging).stream().map(e -> PublicEmployee.of(e, byId.get(e.departmentId()))).toList();
    }

    public Optional<PublicEmployee> one(long id) {""")
edit(API, """    @GetMapping("/employees/{id}")""", """    @GetMapping("/employees/search")
    public List<PublicEmployee> search(@RequestParam String q, @RequestParam(required = false) Integer page,
                                       @RequestParam(required = false) Integer size) {
        return directory.search(q, Paging.of(page, size));
    }

    @GetMapping("/employees/{id}")""")
commit("Search employees by name", "seen-rule", "The search text is joined into the SQL, so a request can change the query (SQL injection; rule 7)",
       R, "LIKE '%\" + text.toLowerCase()", "sql-concatenation")

edit(D, """    public Optional<HrEmployee> hr(long id) {
        Map<Long, Department> byId = departments.byId();
        return employees.find(id).map(e -> HrEmployee.of(e, byId.get(e.departmentId())));
    }""", """    public Optional<HrEmployee> hr(long id) {
        return employees.find(id).map(e -> HrEmployee.of(e, departments.find(e.departmentId()).get()));
    }""")
commit("Read only the employee's own department for the HR view", "seen-rule",
       "Optional.get() on the department lookup without a check", D, "departments.find(e.departmentId()).get()", "optional-get")

edit(D, """    /** Everyone, for a full export: one snapshot (rule 11). */
    @Transactional(readOnly = true)
    public List<PublicEmployee> everyone() {
        Map<Long, Department> byId = departments.byId();
        return employees.all().stream().map(e -> PublicEmployee.of(e, byId.get(e.departmentId()))).toList();
    }""", """    /** Everyone, for a full export: one snapshot (rule 11). */
    @Transactional(readOnly = true)
    public List<PublicEmployee> everyone() {
        List<PublicEmployee> out = new ArrayList<>();
        for (Employee e : employees.all()) {
            Department d = departments.find(e.departmentId()).orElseThrow();
            out.add(PublicEmployee.of(e, d));
        }
        return out;
    }""")
edit(D, "import com.recordslab.model.Department;\n", "import com.recordslab.model.Department;\nimport com.recordslab.model.Employee;\n")
edit(D, "import java.util.List;\n", "import java.util.ArrayList;\nimport java.util.List;\n")
commit("Load each employee's department as the export goes", "seen-rule",
       "A database query per employee in a loop (N+1) where the departments were read once before", D,
       "Department d = departments.find(e.departmentId()).orElseThrow();", "cost-loop")

edit(ACC, """        if (!HR.equals(role)) {""", """        if (role == null || role != HR) {""")
commit("Make the HR check explicit about a missing header", "seen-rule",
       "The role header is compared with == against \"hr\", so a real request's header never matches and HR is always refused",
       ACC, "role != HR", "string-identity")

M = f"{J}/format/Money.java"
edit(M, """    /** A twelfth of a yearly amount. */""", """    /** A yearly amount after a raise of the given percent, such as 3.5. */
    public static BigDecimal raised(BigDecimal yearly, double percent) {
        return round(yearly.multiply(new BigDecimal(1 + percent / 100)));
    }

    /** A twelfth of a yearly amount. */""")
commit("Work out pay after a raise for the HR view", "seen-rule",
       "BigDecimal built from a double, so 1.035 becomes 1.03499999... and some raises round a cent low (rule 2)",
       M, "new BigDecimal(1 + percent / 100)", "bigdecimal-double", behaviour=True)

# ---------------------------------------------------------------- seen, logic

edit(X, """        xml.writeStartElement("employees");""", """        xml.writeStartElement("employees");
        xml.writeAttribute("exportedAt", STAMP.format(new Date()));""")
edit(X, """    private final Directory directory;

    public XmlExportController""", """    private static final SimpleDateFormat STAMP = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'");

    private final Directory directory;

    public XmlExportController""")
edit(X, "import java.io.IOException;\n", "import java.io.IOException;\nimport java.text.SimpleDateFormat;\nimport java.util.Date;\n")
commit("Stamp each XML export with the time it was made", "seen-logic",
       "One SimpleDateFormat shared by every request is not thread-safe, so parallel exports can get garbled stamps; it also formats in the server's zone while printing Z (rule 3)",
       X, "new SimpleDateFormat(", None)

E = f"{J}/format/Emails.java"
edit(E, """        return email.trim().toLowerCase(Locale.ROOT);""", """        return email.trim().toLowerCase();""")
edit(E, "import java.util.Locale;\n\n", "")
commit("Tidy the email helper", "seen-logic",
       "toLowerCase() without a locale: on a Turkish server EMRE.YILMAZ becomes emre.yılmaz with a dotless i, so the formats disagree with the stored email (rules 6 and 10)",
       E, "return email.trim().toLowerCase();", None)

# ---------------------------------------------------------------- novel: only wrong against this service's rules

edit(PUB, """public record PublicEmployee(long id, String givenName, String familyName, String email, String department,
                             String hiredAt) {

    public static PublicEmployee of(Employee e, Department d) {
        return new PublicEmployee(e.id(), e.givenName(), e.familyName(), Emails.normal(e.email()), d.name(),
                Dates.iso(e.hiredAt()));
    }""", """public record PublicEmployee(long id, String givenName, String familyName, String email, String department,
                             String hiredAt, String salary) {

    public static PublicEmployee of(Employee e, Department d) {
        return new PublicEmployee(e.id(), e.givenName(), e.familyName(), Emails.normal(e.email()), d.name(),
                Dates.iso(e.hiredAt()), Money.format(e.salary()));
    }""")
edit(PUB, "import com.recordslab.format.Emails;\n", "import com.recordslab.format.Emails;\nimport com.recordslab.format.Money;\n")
commit("Show pay in the employee list so managers can plan budgets", "novel",
       "Pay is added to the public view, so the JSON API and anything built on PublicEmployee now shows every salary to anyone (rule 1)",
       PUB, "Dates.iso(e.hiredAt()), Money.format(e.salary()));")

edit(R, """    /** Every active employee, for the exports. */
    public List<Employee> all() {
        return jdbc.sql(SELECT + " WHERE deleted_at IS NULL" + ORDER).query(this::row).list();
    }""", """    /** Every employee, for the exports. */
    public List<Employee> all() {
        return jdbc.sql(SELECT + ORDER).query(this::row).list();
    }""")
commit("Simplify the export query", "novel",
       "The deleted_at filter is gone, so the XML and CSV exports include people who were deleted (rule 5)",
       R, "return jdbc.sql(SELECT + ORDER)")

DT = f"{J}/format/Dates.java"
edit(DT, """    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_INSTANT;""",
     """    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_OFFSET_DATE_TIME.withZone(ZoneId.systemDefault());""")
edit(DT, "import java.time.Instant;\n", "import java.time.Instant;\nimport java.time.ZoneId;\n")
commit("Show times with their offset so people can read them", "novel",
       "Times are now in the server's own zone with an offset, not UTC with Z, in every format (rule 3)",
       DT, "withZone(ZoneId.systemDefault())", None, behaviour=True)

edit(M, """        return amount.setScale(2, RoundingMode.HALF_EVEN);""", """        return amount.setScale(2, RoundingMode.HALF_UP);""")
commit("Round money the way people expect", "novel",
       "Half-up rounding instead of half-even: 1200000.005 shows as 1200000.01, not 1200000.00 (rule 2)",
       M, "RoundingMode.HALF_UP", None, behaviour=True)

CC = f"{J}/format/CsvCell.java"
edit(CC, """    private static final String FORMULA_STARTS = "=+-@";""", """    private static final String FORMULA_STARTS = "=+@";""")
commit("Keep negative numbers readable in CSV", "novel",
       "'-' no longer counts as a formula start, so a cell like -2+3+cmd|'/C calc'!A0 runs in a spreadsheet (rule 8)",
       CC, "FORMULA_STARTS = \"=+@\"", None, behaviour=True)

edit(G, """        return employees.page(Paging.of(page, size));""", """        return employees.page(new Paging(page == null ? 1 : page, size == null ? Paging.DEFAULT_SIZE : size));""")
commit("Pass GraphQL paging straight through", "novel",
       "GraphQL skips Paging.of: a size of 100000 is not cut to 100 and page 0 gives a negative offset (rule 4)",
       G, "new Paging(page == null ? 1 : page")

edit(R, """        jdbc.sql("SELECT department_id, COUNT(*) AS n FROM employee WHERE deleted_at IS NULL GROUP BY department_id")""",
     """        jdbc.sql("SELECT department_id, COUNT(*) AS n FROM employee GROUP BY department_id")""")
commit("Count everyone in each department", "novel",
       "Head counts now include deleted employees (rule 12)", R, "COUNT(*) AS n FROM employee GROUP BY")

edit(R, """    private static final String ORDER = " ORDER BY LOWER(family_name), LOWER(given_name), id";""",
     """    private static final String ORDER = " ORDER BY family_name, given_name";""")
commit("Let the database index do the sorting", "novel",
       "Sorting is now case-sensitive with no id tie-break: 'rao' sorts after 'Yilmaz', and equal names can move between pages (rule 9)",
       R, "ORDER BY family_name, given_name\"")

edit(C, """        for (PublicEmployee e : directory.everyone()) {
            csv.append(CsvCell.row(Long.toString(e.id()), e.givenName(), e.familyName(), e.email(), e.department(),
                    e.hiredAt()));
        }""", """        Map<Long, Department> byId = departments.byId();
        for (Employee e : employees.all()) {
            csv.append(CsvCell.row(Long.toString(e.id()), e.givenName(), e.familyName(), e.email(),
                    byId.get(e.departmentId()).name(), e.hiredAt().toString()));
        }""")
edit(C, """    private final Directory directory;

    public CsvExportController(Directory directory) {
        this.directory = directory;
    }""", """    private final EmployeeRepository employees;
    private final DepartmentRepository departments;

    public CsvExportController(EmployeeRepository employees, DepartmentRepository departments) {
        this.employees = employees;
        this.departments = departments;
    }""")
edit(C, """import com.recordslab.format.CsvCell;
import com.recordslab.service.Directory;
import com.recordslab.view.PublicEmployee;
""", """import com.recordslab.db.DepartmentRepository;
import com.recordslab.db.EmployeeRepository;
import com.recordslab.format.CsvCell;
import com.recordslab.model.Department;
import com.recordslab.model.Employee;
import java.util.Map;
""")
commit("Export CSV straight from the tables", "novel",
       "The CSV skips the shared view: emails keep their stored case and times keep fractions, so CSV disagrees with JSON and XML; it also reads outside the export snapshot (rules 6, 10, 11)",
       C, "e.email(),")

# ---------------------------------------------------------------- AI only: no check matches, the code cannot be run alone

edit(D, """    /** Everyone, for a full export: one snapshot (rule 11). */
    @Transactional(readOnly = true)
    public""", """    /** Everyone, for a full export. */
    public""")
edit(D, "import org.springframework.transaction.annotation.Transactional;\n", "")
commit("Drop the transaction around exports, they only read", "ai-only",
       "Without the read-only transaction the employees and departments are read separately, so an export can mix data from before and after a change (rule 11)",
       D, "    /** Everyone, for a full export. */")

edit(ACC, """        if (role == null || role != HR) {""", """        if (role != null && role != HR) {""")
commit("Let the admin tool open the HR view without a role", "ai-only",
       "A request with no X-Role header now passes the HR check, so anyone sees pay and national ids (rule 1)",
       ACC, "role != null && role != HR")

edit(API, """        return directory.page(Paging.of(page, size));""", """        return directory.page(Paging.of(size, page));""")
commit("Tidy the employee list endpoint", "ai-only",
       "page and size are swapped: ?page=2&size=50 returns page 50 of 2 rows",
       API, "Paging.of(size, page)")

# ---------------------------------------------------------------- controls

edit(X, """        for (PublicEmployee e : directory.everyone()) {
            xml.writeStartElement("employee");
            xml.writeAttribute("id", Long.toString(e.id()));
            text(xml, "givenName", e.givenName());
            text(xml, "familyName", e.familyName());
            text(xml, "email", e.email());
            text(xml, "department", e.department());
            text(xml, "hiredAt", e.hiredAt());
            xml.writeEndElement();
        }""", """        for (PublicEmployee e : directory.everyone()) {
            employee(xml, e);
        }""")
edit(X, """    private static void text(""", """    private static void employee(XMLStreamWriter xml, PublicEmployee e) throws XMLStreamException {
        xml.writeStartElement("employee");
        xml.writeAttribute("id", Long.toString(e.id()));
        text(xml, "givenName", e.givenName());
        text(xml, "familyName", e.familyName());
        text(xml, "email", e.email());
        text(xml, "department", e.department());
        text(xml, "hiredAt", e.hiredAt());
        xml.writeEndElement();
    }

    private static void text(""")
commit("Move writing one employee into its own method", "control-refactor",
       "No behaviour change; anything reported is a false alarm", X, "employee(xml, e);")

edit(R, """        return jdbc.sql(SELECT + " WHERE deleted_at IS NULL AND (LOWER(family_name) LIKE '%" + text.toLowerCase()
                        + "%' OR LOWER(given_name) LIKE '%" + text.toLowerCase() + "%')" + ORDER
                        + " LIMIT :size OFFSET :offset")
                .param("size", paging.size())""", """        return jdbc.sql(SELECT + " WHERE deleted_at IS NULL AND (LOWER(family_name) LIKE :q OR LOWER(given_name) LIKE :q)"
                        + ORDER + " LIMIT :size OFFSET :offset")
                .param("q", "%" + text.toLowerCase(Locale.ROOT) + "%")
                .param("size", paging.size())""")
edit(R, "import java.util.List;\n", "import java.util.List;\nimport java.util.Locale;\n")
commit("Bind the search text as a parameter", "control-fix",
       "Fixes the SQL joined from the search text; the checks should report nothing new and the issue should close",
       R, "LIKE :q OR LOWER(given_name) LIKE :q")

edit(ACC, """        if (role != null && role != HR) {""", """        if (!HR.equals(role)) {""")
commit("Compare the role by value", "control-fix",
       "Fixes both the identity comparison and the missing-header hole in the HR check",
       ACC, "if (!HR.equals(role)) {")

edit(D, """    public List<DepartmentView> departments() {""", """    public Optional<DepartmentView> department(String code) {
        Map<Long, Integer> counts = employees.headCounts();
        return departments.all().stream()
                .filter(d -> d.code().equalsIgnoreCase(code))
                .findFirst()
                .map(d -> DepartmentView.of(d, counts.getOrDefault(d.id(), 0)));
    }

    public List<DepartmentView> departments() {""")
edit(API, """    @GetMapping("/departments")
    public List<DepartmentView> departments() {
        return directory.departments();
    }""", """    @GetMapping("/departments")
    public List<DepartmentView> departments() {
        return directory.departments();
    }

    @GetMapping("/departments/{code}")
    public DepartmentView department(@PathVariable String code) {
        return directory.department(code).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }""")
commit("Look up a department by its code", "control-feature",
       "New feature, correct; anything reported is a false alarm", API, "public DepartmentView department(@PathVariable String code)")

edit(G, """    @QueryMapping
    public List<Department> departments() {""", """    @QueryMapping
    public List<Employee> search(@Argument String text, @Argument Integer page, @Argument Integer size) {
        return employees.search(text, Paging.of(page, size));
    }

    @QueryMapping
    public List<Department> departments() {""")
put("src/main/resources/graphql/schema.graphqls", files["src/main/resources/graphql/schema.graphqls"].replace(
    "    employee(id: ID!): Employee\n", "    employee(id: ID!): Employee\n    search(text: String!, page: Int, size: Int): [Employee!]!\n"))
commit("Search from GraphQL too", "control-feature",
       "New feature, correct; anything reported is a false alarm", G, "return employees.search(text, Paging.of(page, size));")

out = os.path.join(HERE, "records-lab-truth.json")
with open(out, "w") as f:
    json.dump(truth, f, indent=1)
print(f"{DEST}: {len(truth) + 1} commits; answer key in {out}")
for t in truth:
    print(f"  {t['sha'][:7]} {t['kind']:16} {t['message']}")
