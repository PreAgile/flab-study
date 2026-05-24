# 08. DB Connection & JDBC — Spring 앱에서 PostgreSQL/MySQL까지 byte는 어떻게 흐르는가

> "JDBC 호출하면 SQL이 DB로 가고 결과가 ResultSet으로 돌아온다" 라고만 답하면 입문자.
> "Spring `@Transactional` 진입 시 HikariCP에서 idle Connection을 dequeue하고 autoCommit=false 전환, PreparedStatement.executeQuery()가 PG extended protocol의 Parse/Bind/Describe/Execute/Sync를 한 TCP write로 묶어 보낸 후, 서버가 RowDescription/DataRow×N/CommandComplete/ReadyForQuery로 응답하면 driver가 fetchSize에 따라 portal cursor로 batch read하고, 종료 시 COMMIT 후 Connection은 pool 반납, HikariCP가 isolation/readOnly/schema reset" 까지 풀어내면 시니어.

---

## 0. 백지 마인드맵

### 루트 한 문장

> **"JDBC는 Java app과 DB 사이의 wire protocol 추상화다. DriverManager → Connection → PreparedStatement → ResultSet 4계층. 현대는 HikariCP가 Connection을 pool로 들고, PostgreSQL extended protocol의 Parse/Bind/Execute 3단계로 SQL injection을 막으면서 빠르다. ResultSet은 기본 eager → fetchSize로 cursor 기반 lazy 전환. Transaction은 한 Connection에 묶여 BEGIN/COMMIT 메시지로 wire에 표현된다."**

### 6개 가지

| 가지 | 키워드 |
|---|---|
| **① 4계층** | DriverManager → Connection → Statement → ResultSet |
| **② Wire** | Simple Query ('Q') vs Extended (Parse/Bind/Execute) |
| **③ Prepared** | parse 1회 + bind N회, parameter 별도 msg → injection 구조적 차단 |
| **④ ResultSet** | 기본 fetchSize 0 (전부 로드, OOM 위험) vs cursor lazy |
| **⑤ Transaction** | 1 Tx = 1 Connection, autoCommit/isolation |
| **⑥ 함정** | idle in transaction, N+1, fetchSize OOM, connection state leak |

---

## 1. JDBC 4계층 — DriverManager → Connection → Statement → ResultSet

### 1.1 4계층 한 표

| 계층 | 무엇 | 역할 | 운영 함정 |
|---|---|---|---|
| **DataSource** (또는 DriverManager legacy) | `javax.sql.DataSource` 인터페이스, 구현체는 HikariCP가 표준 | Connection 발급/풀 관리 | pool size, 연결 누수 |
| **Connection** | 한 DB 세션 | autoCommit/isolation/readOnly 등 state 보유, Statement 생성 | state leak (pool 재사용 시) |
| **Statement / PreparedStatement** | SQL 실행 단위 | wire에 SQL 송신, parameter binding, batch | injection (Statement), prepared cache 누수 |
| **ResultSet** | 결과 row 순회 cursor | next()로 한 줄씩, getXxx로 값 추출 | fetchSize 미설정 OOM |

### 1.2 JDBC URL

```
jdbc:postgresql://db.example.com:5432/mydb?ssl=true&prepareThreshold=5
└─┬─┘ └───┬────┘ └────┬───────┘ └─┬─┘ └────────────┬────────────┘
 scheme  subprotocol  host:port    database         driver-specific params
```

5번 parameter는 driver별로 이름/단위/default가 다름 (PG `connectTimeout` 초 단위 / MySQL `connectTimeout` ms 단위).

### 1.3 `java.sql` vs `javax.sql`

`java.sql` = JDBC 1.0 (1997) core (Driver, Connection, Statement, ResultSet). `javax.sql` = 2.0 확장 (DataSource, XADataSource, RowSet). 호환성 깨지 않으려 분리. 현대는 `javax.sql.DataSource` 가 단일 entry point.

### 1.4 비유

> "JDBC는 **전화기(Connection)** 를 빌려 **메모지에 query를 적어(Statement)** 상대(DB)에게 읽어주고 결과를 표로(ResultSet) 받는다. 전화기는 매번 새로 만들면 비싸니 **풀(DataSource)** 에서 빌린다."

### 1.5 DataSource 구현체 지형

`javax.sql.DataSource` 구현체: **HikariCP** (현대 표준, Spring Boot 2+ default), Tomcat JDBC Pool, DBCP2 (Apache Commons), C3P0 (legacy), Oracle UCP, Spring `DriverManagerDataSource` (pool 없음, 테스트용). HikariCP가 표준이 된 이유는 ConcurrentBag + lock-free 알고리즘으로 borrow/return latency가 수십 μs (상세는 07번).

---

## 2. JDBC Driver Type 1~4 — 한 표

| Type | 구조 | 장단점 | 현재 |
|---|---|---|---|
| **Type 1** | Java → JDBC-ODBC bridge → ODBC → DB | 플랫폼 종속, Microsoft ODBC 묶임 | Java 8에서 제거 |
| **Type 2** | Java → JDBC API → native client lib (libpq, libmysqlclient) | JNI 오버헤드, 배포 복잡, native 성숙시 빠름 | Oracle OCI 등 일부 잔존 |
| **Type 3** | Java → middleware server → DB | 미들웨어 운영 부담, 다중 DB 지원 | 거의 사용 안 됨 |
| **Type 4** | Java → Pure Java driver → DB (wire protocol 직접 구현) | JAR 하나로 배포, 어느 플랫폼이든 동일, JIT 수혜 | **현대 표준** (PG JDBC, MySQL Connector/J, MariaDB, H2) |

**왜 Type 4가 표준** — (1) JAR 하나 배포 (컨테이너 시대 결정적), (2) JIT 최적화, (3) wire protocol 안정 공개로 Java 구현 가능. 1999년 PG JDBC v3 (libpq 없는 pure Java) 등장이 전환점.

---

## 3. Connection 생성 5단계 — 매번 만들면 왜 비싼가

```
[Application Thread] → DataSource.getConnection()
        │
        ▼
[HikariCP] pool에 idle? → YES → 수십 μs로 반환
                       → NO  → 아래 5단계 (수십~수백 ms)
        │
        ▼
① TCP 3-way handshake          (~1.5 RTT, local 1ms / cross-region 80~200ms)
② TLS handshake (sslmode)       (TLS 1.3 = 1 RTT, 1.2 = 2 RTT)
③ Startup Message (PG)          ("protocol=3.0, user, db, app_name, encoding")
④ Authentication 교환            (SCRAM-SHA-256 = 2.5 RTT 추가, md5 = 1 RTT)
⑤ ParameterStatus + BackendKeyData + ReadyForQuery ('I' = idle)
        │
        ▼
[Connection 사용 가능] — 총 10~50ms (local) / 100~500ms (cross-AZ + TLS + SCRAM)
```

**왜 pool이 필수** — request마다 새 Connection (1000 req/s × 30ms handshake) → DB CPU 폭증, ephemeral port 고갈, TIME_WAIT 누적, max_connections 초과. 해결: HikariCP가 N개 유지 (보통 10~20), borrow/return.

**SCRAM 함정** — PG 10+ default `scram-sha-256`. 2.5 RTT × 30ms (cross-AZ) = 75ms 추가. burst로 새 conn 만들 때 latency spike 원인.

HikariCP 운용 핵심 (상세는 [07-connection-pools-master.md](./07-connection-pools-master.md)):
- `maximumPoolSize` 동시 최대 / `minimumIdle` 상시 유지
- `connectionTimeout` getConnection 대기 한도
- `idleTimeout` idle 폐기 / `maxLifetime` 강제 폐기 (DB max_lifetime보다 짧게)

---

## 4. PostgreSQL Wire Protocol — 한 다이어그램

### 4.1 메시지 framing

모든 PG 메시지: `[type byte 1] [length 4] [payload]`. 첫 Startup만 type 없음. type byte 4 byte length 먼저 읽으면 framing 안전.

대표 type:
- C→S: `Q`(Simple Query), `P`(Parse), `B`(Bind), `D`(Describe), `E`(Execute), `S`(Sync), `X`(Terminate)
- S→C: `R`(Auth), `Z`(ReadyForQuery), `T`(RowDescription), `D`(DataRow), `C`(CommandComplete), `1`(ParseComplete), `2`(BindComplete), `E`(ErrorResponse)

### 4.2 Simple vs Extended — Frontend ↔ Backend 흐름

```
[Simple Query — Statement.execute()]
Client                                  Server
  │  Q "SELECT id FROM users"           │
  │ ───────────────────────────────────►│
  │   T (RowDescription)                │ ← parse + plan + exec 매번
  │   D (DataRow) × N                   │
  │   C (CommandComplete) "SELECT N"    │
  │   Z (ReadyForQuery 'I')             │
  │ ◄───────────────────────────────────│
  
[Extended Query — PreparedStatement]
Client                                  Server
  │  P (Parse: "SELECT ... WHERE id=$1")│ ── 1회 (또는 prepareThreshold 후)
  │  B (Bind: portal, [42])             │
  │  D (Describe: portal)               │ ← (선택) 결과 컬럼 meta
  │  E (Execute: portal, max_rows=N)    │
  │  S (Sync)                           │ ← pipeline boundary
  │ ───────────────────────────────────►│
  │   1 (ParseComplete)                 │
  │   2 (BindComplete)                  │
  │   T (RowDescription)                │
  │   D (DataRow) × N                   │
  │   C (CommandComplete)               │
  │   Z (ReadyForQuery)                 │
  │ ◄───────────────────────────────────│
```

Extended 5단계 의미:
1. **Parse** — SQL template ($1 placeholder) 등록, stmt_name으로 cache (named) 또는 빈 이름 (anonymous).
2. **Bind** — parameter 값 채워 portal 생성. **parameter는 SQL parser를 거치지 않음** (injection 차단의 본질).
3. **Describe** — portal 결과 컬럼 meta (선택).
4. **Execute** — portal 실행. `max_rows`로 cursor batch fetch.
5. **Sync** — pipeline boundary. 서버가 ReadyForQuery 응답.

Simple vs Extended 트레이드오프 (한 표):

| 측면 | Simple | Extended |
|---|---|---|
| 메시지 수 | 1 | 4~5 |
| Parse 재사용 | 불가 | 가능 (plan cache) |
| Parameter | inline (SQL string) | 별도 메시지 |
| Injection 방어 | escape 의존 | **구조적 차단** |
| Cursor 부분 fetch | 불가 | 가능 (max_rows) |
| 여러 SQL | `;` 구분 가능 | 불가 |
| JDBC API | `Statement` | `PreparedStatement` |

> MySQL Protocol은 length(3)+seq(1)+payload framing, COM_QUERY(0x03)/COM_STMT_PREPARE(0x16)/COM_STMT_EXECUTE(0x17). 본질은 PG와 같이 prepare+execute 분리 모델.

---

## 5. PreparedStatement — parse + bind 2단계, SQL injection 구조적 차단

### 5.1 2단계 모델

```
[Phase 1: Parse — 1회]
  SQL template: "SELECT * FROM users WHERE name = $1 AND age > $2"
  → 서버: Lex / Parse(AST) / Resolve / Plan → statement_name 으로 cache

[Phase 2: Bind + Execute — N회]
  Parameter values: ["alice", 18]
  → 서버: statement_name으로 plan 조회, parameter 값을 자리에 채워 실행
```

### 5.2 Injection 차단의 본질

```
[Statement — 위험]
  String name = request.getParameter("name");  // "Alice' OR '1'='1"
  String sql = "SELECT * FROM users WHERE name = '" + name + "'";
  → 서버가 보는 SQL: ... name = 'Alice' OR '1'='1'   ← 새 조건으로 해석
  → injection 성공

[PreparedStatement — 안전]
  ps = conn.prepareStatement("SELECT * FROM users WHERE name = ?");
  ps.setString(1, name);
  → wire:
     [Parse] "SELECT * FROM users WHERE name = $1"   (값 없음)
     [Bind]  param_1 = "Alice' OR '1'='1"            (값만, byte로)
  → 서버 처리:
     - parse 단계에서 $1은 placeholder로만 인식
     - bind의 byte는 SQL parser를 절대 거치지 않음, column literal value일 뿐
  → injection 불가
```

핵심: Statement의 escape는 **임시방편** (corner case 누락 가능). PreparedStatement는 **구조적 차단** (parameter와 SQL이 wire에서 분리).

### 5.3 성능 — parse 1회 + bind N회

100번 호출 시: Statement = 100 × (parse + plan + exec), Prepared = 1 × parse + 100 × exec. parse는 200~500μs라 반복 호출에서 dominant. 자세한 server-side prepared cache 동작, prepareThreshold 의미, MySQL `useServerPrepStmts`, batching의 `rewriteBatchedStatements`는 git 7e4a6c8 참조.

Batching 한 문단: `ps.addBatch()` × N → `executeBatch()` 한 번의 wire 통신으로 RTT × N → 1 RTT. cross-AZ 2ms × 1000 = 2초 → 20ms. MySQL은 `rewriteBatchedStatements=true`로 `INSERT VALUES (1),(2),...` 단일 SQL 변환, PG는 `reWriteBatchedInserts=true`. ETL/bulk insert에서 핵심.

---

## 6. ResultSet — fetchSize 함정 (lazy vs eager OOM)

### 6.1 기본 동작 = Eager (위험)

```
[JDBC default: fetchSize = 0]
  Query 송신 → 서버가 모든 row를 DataRow로 전부 push
  → Driver buffer가 client heap에 누적
  → 1억 row × 1KB = 100GB → OutOfMemoryError
  
  rs.next()는 단순히 in-memory buffer에서 다음 row 반환.
```

왜 default 0 — JDBC spec 호환성, 작은 결과 가정. 큰 결과는 명시 의도.

### 6.2 PostgreSQL cursor lazy 모드 — 3조건

1. `conn.setAutoCommit(false)` — portal은 transaction에 묶임. autoCommit이면 매 SQL이 즉시 COMMIT → portal 사라짐 → 다음 batch 불가.
2. `ps.setFetchSize(N)` — N > 0.
3. `TYPE_FORWARD_ONLY` (default).

wire 측: Execute의 `max_rows=N` → 서버가 N row 보내고 PortalSuspended('s'). rs.next()로 소진 후 추가 Execute. 마지막 batch는 CommandComplete.

### 6.3 MySQL streaming

`stmt.setFetchSize(Integer.MIN_VALUE)` — driver가 받자마자 user에게 전달 (buffer 안 함). 제약: 한 connection의 ResultSet 완전 소진 전 다른 query 불가 ("Streaming result set is still active"). 또는 `useCursorFetch=true`로 server-side cursor.

### 6.4 OOM 실전 시나리오

```
[사고]
  ps = conn.prepareStatement("SELECT * FROM orders WHERE created > '2024-01-01'");
  rs = ps.executeQuery();
  while (rs.next()) { ... }
  → 5000만 row × 2KB = 100GB / heap 4GB → OOM
  → Heap dump: ArrayList<byte[]> of DataRow in PG driver

[해결]
  conn.setAutoCommit(false);   // PG 필수
  ps.setFetchSize(10_000);
  conn.commit();
```

### 6.5 성능 팁

`rs.getString("name")` 매번 hash lookup vs `rs.getString(2)` 인덱스 접근. batch당 10MB DataRow → Young GC 빈발. 가능하면 SQL에서 aggregate.

---

## 7. Transaction — autoCommit / Isolation Level

Transaction wire 표현:

```
Spring TransactionManager.begin()
  → HikariCP.getConnection() → conn C
  → C.setAutoCommit(false) → wire: BEGIN (PG) / START TRANSACTION (MySQL)
  → [app: query 1, query 2 모두 같은 conn C]
  → commit() → wire: COMMIT (또는 ROLLBACK)
  → C.setAutoCommit(true) 복원, HikariCP.return(C)
```

**autoCommit=true (default)**: 매 SQL을 driver가 BEGIN ... COMMIT으로 자동 wrap. **autoCommit=false + @Transactional**: BEGIN, SELECT, SELECT, COMMIT 한 transaction.

**왜 1 tx = 1 conn** — Transaction state (uncommitted, lock, snapshot)는 서버 측에서 connection에 묶임. 다른 connection은 그 변경 못 봄 (MVCC isolation). Spring은 `TransactionSynchronizationManager`의 ThreadLocal에 (DataSource → Connection) map을 들고 같은 메서드 안의 JDBC 호출이 같은 conn 쓰게 함.

**Isolation Level**: `conn.setTransactionIsolation(REPEATABLE_READ)` → wire `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`. 4표준: READ UNCOMMITTED / READ COMMITTED (PG default) / REPEATABLE READ (MySQL InnoDB default) / SERIALIZABLE. HikariCP의 `resetIsolationOnReturn=true`로 반납 시 default 복원. 각 레벨별 wire 비용/동작 상세는 git 7e4a6c8 참조.

**Savepoint**: `conn.setSavepoint("sp1")` → wire `SAVEPOINT sp1`. 부분 rollback. **2PC**는 무거움 (lock 오래, in-doubt tx), 마이크로서비스는 Saga + 보상 tx 선호.

---

## 8. Connection State Leak — pool 재사용의 위험

Connection은 서버 측에 state를 들고 있다 (autoCommit, isolation, readOnly, schema, session variables, prepared cache, advisory lock, temp tables, savepoint, open tx, client_encoding). pool 반납 시 reset 안 되면 다음 사용자에게 leak.

대표 leak:
1. **미rollback transaction** — A가 BEGIN + UPDATE 후 예외 발생, rollback 없이 conn.close(). B가 같은 conn 받아 SELECT → A의 uncommitted 변경 보임.
2. **isolation leak** — A가 SERIALIZABLE 설정 → B가 의도치 않게 strict isolation → 성능 저하 + deadlock 증가.
3. **session variable leak** — A `SET statement_timeout='60s'` → B가 60초 timeout으로 동작.
4. **advisory lock leak** — A `pg_advisory_lock(42)` 후 unlock 안 함 → 다음 borrower 전체 hang.

HikariCP의 자동 reset: autoCommit, isolation, readOnly, catalog, warnings. **세션 변수/prepared cache/advisory lock은 자동 reset 안 됨**. 방어: SET 자제, `maxLifetime`으로 conn 주기적 폐기 (30min), `pg_advisory_xact_lock` (tx 종료시 자동 해제) 선호.

> Character encoding 4계층 (HTTP → Java String → JDBC wire → DB column)은 [01-url-input-and-serialization.md](./01-url-input-and-serialization.md) 참조. MySQL utf8 vs utf8mb4 함정만 기억: "utf8" = utf8mb3 (3 byte), 이모지 저장 불가, MySQL 8 default가 utf8mb4.
>
> Timeout 4계층 (OS socket / JDBC Statement / DB statement_timeout / PG idle_in_transaction_session_timeout)은 [java-deep-dive/04-timeouts-connection-vs-read.md](../java-deep-dive/04-timeouts-connection-vs-read.md) 참조. 핵심: 짧은 것이 먼저 발동. idle_in_transaction은 MVCC bloat 방어.

---

## 9. DB 내부 처리 + ORM — 한 문단씩

**DB 내부**: Backend Process가 메시지 받으면 **Parser**(SQL→AST, syntax check) → **Rewriter**(view 전개, RULE) → **Planner/Optimizer**(통계 pg_statistic 참조, join 순서/access method/join 알고리즘 결정) → **Executor**(plan tree 순회, volcano model로 row 전달) → **Storage**(Shared Buffer 25% RAM, 8KB page) → **WAL Writer**(변경 먼저 기록, commit 시 sync). app 개발자 관점에서 중요한 건: index 없는 WHERE → seq scan으로 100만 row 읽음, EXPLAIN으로 확인. buffer hit ratio 낮으면 디스크 I/O dominant.

**ORM/JPA**: Hibernate가 entity.persist() 시 즉시 INSERT 보내지 않고 **Persistence Context** (1st level cache, Map<Id, Entity>) 등록 후 **flush 시점** (explicit flush / query 직전 auto-flush / commit 직전)에 dirty entity들의 SQL을 PreparedStatement로 wire에 묶어 보냄. 가장 흔한 함정은 **N+1**: `FROM Order` 1 query → 각 order의 lazy `getCustomer()` 100 query = 101 query, DB CPU는 낮은데 RTT × 101로 latency 폭증. 해결은 `JOIN FETCH`, `EntityGraph`, `@BatchSize(20)`. Spring `@Transactional`은 메서드 진입 시 EntityManager+Connection을 ThreadLocal에 묶고 메서드 내 모든 EntityManager 호출이 같은 conn 쓰게 함.

---

## 10. 운영 시나리오 — 3대 실전

### 10.1 idle in transaction (MVCC bloat)

```
[증상]
  pg_stat_activity: state = 'idle in transaction', state_change > 10min ago
  → 어떤 connection이 BEGIN 후 query 안 함

[원인]
  - @Transactional 메서드 안에서 외부 API 호출 (몇 분 대기)
  - 예외 발생 후 rollback 누락
  - 너무 큰 @Transactional 범위

[영향]
  ⚠️ MVCC bloat — 그 tx 시점 row version 살려둠 → vacuum 못 함 → 테이블 비대화
  ⚠️ Lock 점유 → 다른 tx 대기
  ⚠️ Connection 점유 → pool 고갈

[진단]
  SELECT pid, state, state_change, query FROM pg_stat_activity
   WHERE state = 'idle in transaction' ORDER BY state_change ASC;

[해결]
  - @Transactional 범위 최소화, 외부 API 호출은 tx 밖으로
  - idle_in_transaction_session_timeout = '30s'
  - SELECT pg_terminate_backend(pid)로 강제 종료
```

### 10.2 N+1 problem (ORM)

```
[증상]
  P99 latency 500ms+, DB CPU 30% (여유), slow query log에 100ms+ 없음

[원인]
  ORM lazy loading으로 1 + N query 발생

[진단]
  app log + sleuth/zipkin: 한 request에 query 수
  HikariCP: hikaricp_connections_pending (대기 thread)
  pg_stat_statements: calls 큰데 mean 작은 query → N+1 의심

[해결]
  fetch join (JOIN FETCH), EntityGraph, @BatchSize(size=20)
  read replica 활용
```

### 10.3 connection reset by peer

```
[증상]
  java.net.SocketException: Connection reset (query 도중)

[원인]
  - DB의 idle_in_transaction_session_timeout
  - 방화벽/NAT idle timeout (default 5min~1h)
  - DB crash + restart
  - Load balancer가 backend 교체

[진단]
  tcpdump -i any port 5432 → RST 누가 보냄
  DB log: "could not receive data from client"

[해결]
  HikariCP.keepaliveTime = 5min (idle ping)
  HikariCP.maxLifetime = 30min < NAT idle timeout
  JDBC URL: tcpKeepAlive=true
```

---

### 10.4 보너스 — Prepared statement cache 누수 (간단)

동적 SQL 패턴 (WHERE 조건이 매번 다른 `findByDynamic`, Spring Data JPA의 일부 동적 query) → server-side prepared stmt 무한 누적 → `pg_prepared_statements`에 connection당 1000+ row → DB OOM (`out of memory for query result`). 운영 6개월 후 갑자기 표면화되는 종류. 해결:

- `prepareThreshold=0` (cache 비활성) 또는 낮춤
- `maxLifetime` 짧게 (30min) → connection 주기적 재생성
- parameterize 강화 (동적 컬럼 명 대신 정해진 set)
- connectionInitSql에 `RESET ALL` (PG) — 단, borrow마다 1 RTT 비용

---

## 11. 진단 도구 — 한 표

| 도구 | 무엇을 본다 | 핵심 사용법 |
|---|---|---|
| **pg_stat_activity** | 살아있는 query/connection state | `WHERE state != 'idle'`, query_start ASC로 long-running 추적, wait_event_type으로 Lock/IO 구분 |
| **pg_stat_statements** | top slow query (누적 시간) | `ORDER BY total_exec_time DESC`, calls 큰데 mean 작으면 N+1 의심 |
| **MySQL slow log + performance_schema** | slow query, digest 통계 | `events_statements_summary_by_digest` |
| **EXPLAIN ANALYZE** | query plan + 실제 행동 | Seq Scan(인덱스 부재), rows 예측 vs actual(통계 outdated), Buffers hit/read |
| **jstack** | Java thread 어디서 stuck | `SocketInputStream.socketRead0` 다수 → DB 측 slow, `Park` → pool 대기 |
| **tcpdump** | wire byte 직접 | `tcpdump -i any -A port 5432` → Q/P/B/E msg, RST 출처 |
| **HikariCP metrics** | pool 상태 | `pending > 0` pool 부족, `acquire P99 spike` DB 문제, `usage P99 큼` tx 길음 |

---

## 12. 트레이드오프 — 핵심 3표

**Statement vs PreparedStatement**

| 측면 | Statement | PreparedStatement |
|---|---|---|
| Parse 비용 | 매번 | 1회 |
| SQL Injection | 위험 | 구조적 안전 |
| 운영 사용 | DDL, 단순 일회성 | 99% case |

**fetchSize 선택**

| 값 | 동작 | 권장 case |
|---|---|---|
| 0 (default) | 전부 로드 | 결과 작을 때 (~1000 row) |
| 100~1000 | cursor batch | 중간 크기 |
| 10000+ | cursor batch | 큰 결과 + 메모리 여유 |
| Integer.MIN_VALUE (MySQL) | streaming | 무제한 |

**Isolation Level**

| 레벨 | 비용 | case |
|---|---|---|
| READ COMMITTED | 낮음 | OLTP (PG default) |
| REPEATABLE READ | 중 | 일관 snapshot 필요 (MySQL default) |
| SERIALIZABLE | 높음 (lock/retry) | 정확한 회계 |

---

## 13. 꼬리질문

### Q1. PreparedStatement는 어떻게 SQL injection을 구조적으로 막나? Statement escape와 무엇이 다른가?

> Statement escape는 client에서 위험 문자(', \\, multi-byte)를 변환해 SQL string에 inline → corner case 누락 가능. PreparedStatement는 parameter를 SQL과 별도 wire 메시지(Bind)로 보냄. 서버는 Parse 단계에서 SQL template만 AST로 만들고, Bind의 parameter byte는 절대 SQL parser를 거치지 않음 — column literal value일 뿐. 구조적으로 injection 불가.

### Q2. ResultSet은 lazy인가 eager인가? fetchSize 미설정 시 1억 row면 어떻게 되나?

> JDBC default fetchSize=0 = eager (전부 로드). 1억 row × 1KB = 100GB → client heap OOM. PG에서 lazy cursor로 받으려면 (1) autoCommit=false, (2) setFetchSize(N), (3) TYPE_FORWARD_ONLY 3조건. autoCommit이 필수인 이유는 portal이 transaction에 묶여 매 SQL이 COMMIT되면 portal이 사라지기 때문. MySQL은 setFetchSize(Integer.MIN_VALUE) streaming 또는 useCursorFetch=true.

### Q3. Spring @Transactional의 두 query가 어떻게 같은 transaction인 줄 아나?

> Spring TransactionInterceptor가 메서드 진입 시 DataSource.getConnection() + setAutoCommit(false) 호출하고 그 conn을 TransactionSynchronizationManager의 ThreadLocal에 등록. 메서드 안의 JdbcTemplate/EntityManager가 DataSource.getConnection() 호출하면 Spring proxy가 ThreadLocal 먼저 확인해 같은 conn 반환. → 같은 conn = 같은 wire transaction (BEGIN ... COMMIT 한 묶음).

### Q4. "DB connection이 hang 걸린다" 신고. 어떻게 진단?

> (1) **HikariCP 메트릭**: pending>0 + active==max → pool 고갈. (2) **DB**: `pg_stat_activity` long-running query 또는 idle in transaction 추적, `pg_locks` JOIN으로 lock chain. (3) **jstack**: `SocketInputStream.socketRead0` 다수 → DB 응답 대기, `Park` → pool 대기. (4) **tcpdump**: RST 발생이면 firewall/NAT timeout. (5) **격리**: 한 instance만이면 instance 측, 전체면 DB 측. (6) **해결**: pool 고갈 → 일시 확장 + 근본 N+1/long tx 제거, idle in tx → idle_in_transaction_session_timeout, firewall idle → HikariCP keepaliveTime + maxLifetime.

### Q5. 동시 1000 req/sec, 각 request가 tx 안에서 DB 5번 호출 (1ms씩). 적정 pool size?

> Little's Law: concurrency = throughput × latency. conn 사용 시간 = 5 × 1ms = 5ms. 1000 × 5ms = 5 동시 conn (이론). 실제는 jitter/GC/network 변동 2~3배 마진 → 10~15. HikariCP 공식 권장 `(core × 2) + spindle`은 출발점, 워크로드 측정이 진리. 무한정 늘리면 DB max_connections + context switch 비용 (PG는 process per conn) → 처리량 오히려 감소. PgBouncer로 multiplex 권장.

### Q6. Connection 한 번 만드는 데 정확히 어떤 단계가 있고 왜 pool이 필수인가?

> 5단계: (1) TCP 3-way handshake (cross-AZ면 5~10ms), (2) TLS handshake (TLS 1.3 = 1 RTT), (3) Startup Message (protocol/user/db/encoding), (4) Auth 교환 (SCRAM-SHA-256 = 2.5 RTT 추가), (5) ParameterStatus + BackendKeyData + ReadyForQuery. 총 10~50ms (local) ~ 500ms (cross-AZ+TLS+SCRAM). request마다 새로 만들면 DB CPU 폭증, ephemeral port 고갈, TIME_WAIT 누적, max_connections 초과. HikariCP가 N개 유지하며 borrow/return으로 수십 μs로 빌려준다.

### Q7. PostgreSQL JDBC의 prepareThreshold=5는 뭘 의미하나?

> 같은 PreparedStatement를 호출 1~4번까지는 anonymous prepare (매번 Parse+Bind+Execute, server cache 안 함), 5번째부터 named prepare로 전환되어 server-side plan cache 본격 활용. 왜 threshold가 필요한가 — 한 번만 호출되는 query를 cache하면 DB 메모리 누적 (pg_prepared_statements 비대). 5번 이상이면 cache 가치. 0 = 항상 anonymous, 1 = 즉시 named. 동적 SQL이 많은 앱은 0으로 두거나 maxLifetime 짧게 (30min) 잡아 누적 방지.

---

## 14. 학습 체크리스트

- [ ] JDBC 4계층 (DataSource → Connection → Statement → ResultSet) 화이트보드 그리기
- [ ] Driver Type 1~4 한 표로 차이 + 왜 Type 4가 표준
- [ ] Connection 생성 5단계 (TCP/TLS/Startup/Auth/Ready) 인용
- [ ] PG wire 메시지 framing (type + length + payload) + 대표 type byte
- [ ] Simple vs Extended 차이 + Parse/Bind/Execute/Sync 의미
- [ ] PreparedStatement가 injection을 구조적으로 차단하는 wire-level 이유
- [ ] fetchSize 미설정 OOM + PG cursor 3조건 (autoCommit=false, setFetchSize, FORWARD_ONLY)
- [ ] MySQL Integer.MIN_VALUE streaming의 제약
- [ ] Spring @Transactional이 ThreadLocal로 Connection 공유하는 메커니즘
- [ ] BEGIN/COMMIT/SET TRANSACTION ISOLATION의 wire 표현
- [ ] Connection state leak 4가지 (uncommitted tx / isolation / session var / advisory lock)
- [ ] 운영 시나리오 3대 (idle in tx / N+1 / connection reset) 진단 + 해결
- [ ] 진단 도구 7개 활용 (pg_stat_activity / pg_stat_statements / EXPLAIN / jstack / tcpdump / HikariCP metrics / slow log)

---

## 15. 다음 학습

| 다음 | 왜 |
|---|---|
| `07-connection-pools-master.md` | HikariCP 내부 (ConcurrentBag, housekeeper) |
| `01-url-input-and-serialization.md` | character encoding chain 시작점 |
| `jvm/05-threading/` | HikariCP lock-free 알고리즘 = JMM + CAS |
| `jvm/04-gc/` | ResultSet 큰 byte[] 가 GC에 미치는 영향 |
| `java-deep-dive/04-timeouts-connection-vs-read.md` | timeout 4계층의 Java API 측 정리 |

---

> PostgreSQL Wire Protocol 메시지 byte map, Extended Query 풀 시퀀스, server-side prepared cache, isolation level별 동작은 git 7e4a6c8 참조.
