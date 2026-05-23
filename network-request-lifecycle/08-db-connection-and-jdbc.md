# 08. DB Connection & JDBC — Spring 앱에서 PostgreSQL/MySQL까지 byte는 어떻게 흐르는가

> "Spring이 JDBC 호출하면 SQL이 DB로 가서 결과가 ResultSet으로 돌아온다" 라고만 답하면 입문자.
> "Spring `@Transactional` 진입 시 HikariCP에서 idle Connection을 dequeue하고 autoCommit=false로 전환, `PreparedStatement.executeQuery()`가 PostgreSQL extended protocol의 Parse/Bind/Describe/Execute/Sync 5개 메시지를 한 TCP write로 묶어 보낸 후, 서버가 RowDescription/DataRow×N/CommandComplete/ReadyForQuery를 응답하면 Driver가 fetchSize에 따라 portal cursor로 batch read하고, 트랜잭션 종료 시 COMMIT 메시지 → Connection은 pool로 반납, HikariCP가 isolation/readOnly/schema를 reset" 까지 풀어낼 수 있다면 시니어.
> 이 챕터의 목표는 후자다.

---

## 이 문서의 사용법

1. **0장 백지 마인드맵을 먼저 외운다** — JDBC 4계층 + wire protocol 2모드 + transaction 흐름.
2. **1~10장 본문을 순서대로 학습**.
3. **11장 운영 시나리오** + **12장 꼬리질문 3단**.

---

## 0. 백지 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JDBC는 Java app과 DB 사이의 wire protocol 추상화다. DriverManager → Connection → PreparedStatement → ResultSet 4계층. 현대는 HikariCP가 Connection을 pool로 들고, PostgreSQL extended protocol의 Parse/Bind/Execute 3단계로 SQL injection을 막으면서 빠르다. ResultSet은 기본 eager (전부 로드) 함정 → fetchSize로 cursor 기반 lazy로 전환. Transaction은 한 Connection에 묶여 BEGIN/COMMIT 메시지로 wire에 표현된다."**

### 6개 가지 — 순서를 외운다

```
                [ROOT: JDBC = wire protocol 추상화 + Connection 재사용 모델]
                                       │
   ┌──────┬────────────┬────────────┬───────────┬────────────┬──────────┐
   │      │            │            │           │            │          │
   ① 4계층 ② Wire        ③ Prepared  ④ ResultSet ⑤ Transaction ⑥ 운영 함정
  (Driver  (PG extended (parse+bind  (lazy vs    (autoCommit   (idle in tx,
   /Conn   /Simple,     /injection    eager,      /BEGIN wire   N+1, fetchSize
   /Stmt   MySQL COM_*)  방어)         fetchSize)  /isolation)   미설정 OOM)
   /RS)    │             │            │            │             │
           │             │            │            │             │
   ┌───────┼─────┐   ┌───┼───┐   ┌────┼────┐  ┌────┼────┐   ┌────┼────┐
  TCP handshake  Parse  Bind  Server vs  Cursor  autoCommit  Connection
  Startup msg    /Bind/ /별도 client     vs all  default     state leak
  Auth (SCRAM)   /Exec  msg    prepare   load           (HikariCP reset)
  ReadyForQuery
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 4계층** | DriverManager → Connection | PreparedStatement | ResultSet |
| **② Wire** | Simple Query (Q) | Extended (Parse/Bind/Execute) | Backend msg (RowDesc/DataRow/CC/RFQ) |
| **③ Prepared** | parse 1회 + bind N회 | parameter 별도 msg → injection 차단 | server-side vs client-side |
| **④ ResultSet** | 기본 fetchSize 0 (전부 로드) | cursor (Postgres) | streaming (MySQL Integer.MIN_VALUE) |
| **⑤ Transaction** | 1 Tx = 1 Connection | BEGIN/COMMIT wire | isolation, savepoint, 2PC |
| **⑥ 함정** | idle in transaction (MVCC bloat) | N+1 (ORM) | fetchSize 미설정 OOM |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장.
> 예: "PreparedStatement가 왜 injection을 막나?" → 가지 ③ → "parameter가 별도 메시지로 전송 → 서버가 query template와 절대 mix 안 함" → 가지 ②로 확장 (Bind 메시지 구조).

---

## 1. 가지 ①: JDBC 큰 그림 — 4계층 + DataSource + URL

### 1.1 핵심 질문

> "Spring 코드의 `JdbcTemplate.queryForList()` 한 줄 안에 어떤 객체들이 어떻게 협력하나?"

### 1.2 백지 그리기 — JDBC 4계층

```
[Spring Application]
   │  JdbcTemplate / EntityManager / R2dbc(별개)
   ▼
┌──────────────────────────────────────────────────────────┐
│  JDBC API (javax.sql + java.sql)                          │
│  ─────────────────────────────────────────────────────    │
│                                                            │
│  ┌──────────────┐   ┌──────────────┐                      │
│  │ DataSource    │   │ DriverManager │ (legacy)            │
│  │ (HikariCP 등) │   │              │                      │
│  └──────┬───────┘   └──────┬───────┘                      │
│         │ getConnection()    │                              │
│         ▼                   ▼                              │
│  ┌──────────────────────────────────────┐                  │
│  │ Connection                            │                  │
│  │  - autoCommit, isolation, readOnly    │                  │
│  │  - state 보유 (savepoint, lock, ...)  │                  │
│  └──────┬───────────────────────────────┘                  │
│         │ prepareStatement(sql) / createStatement()         │
│         ▼                                                    │
│  ┌──────────────────────────────────────┐                  │
│  │ Statement / PreparedStatement         │                  │
│  │  - setInt, setString (parameter)      │                  │
│  │  - addBatch, setFetchSize, setQueryTimeout │             │
│  └──────┬───────────────────────────────┘                  │
│         │ executeQuery() / executeUpdate() / execute()      │
│         ▼                                                    │
│  ┌──────────────────────────────────────┐                  │
│  │ ResultSet                              │                  │
│  │  - next(), getString, getInt           │                  │
│  │  - cursor based (lazy) or all-loaded   │                  │
│  └────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────┘
   │                                                          
   ▼ implements
┌──────────────────────────────────────────────────────────┐
│  JDBC Driver (Type 4, pure Java)                          │
│  ─────────────────────────────────────────────────────    │
│  PostgreSQL JDBC (org.postgresql:postgresql)              │
│  MySQL Connector/J (com.mysql:mysql-connector-j)          │
│                                                            │
│  - SQL → wire protocol bytes                              │
│  - Socket I/O + TLS                                       │
│  - 결과 byte → Java object                                │
└──────────────────────────────────────────────────────────┘
   │
   ▼ TCP socket
┌──────────────────────────────────────────────────────────┐
│  PostgreSQL/MySQL Server                                  │
└──────────────────────────────────────────────────────────┘
```

### 1.3 키워드 1 — `java.sql` vs `javax.sql`

| 패키지 | 무엇 |
|---|---|
| `java.sql` | core API (Driver, Connection, Statement, ResultSet, ...). JDK 본체 (Java 1.1, 1997). |
| `javax.sql` | **확장** — DataSource, ConnectionPoolDataSource, RowSet, XADataSource (2PC). JDBC 2.0 Optional Package. |

**왜 둘로 나뉘었나** — 1997년 JDBC 1.0은 DriverManager 직접 사용 모델. 이후 J2EE 서버가 pool 관리 필요 → DataSource를 추가했는데 기존 패키지 호환성 깨면 안 됨 → `javax.sql`로 분리.

**현대 의미** — `javax.sql.DataSource` 가 사실상 단일 entry point. `DriverManager`는 legacy.

### 1.4 키워드 2 — JDBC URL 구조 (3개 부분)

```
jdbc:postgresql://db.example.com:5432/mydb?ssl=true&prepareThreshold=5
└─┬─┘ └───┬────┘ └───────┬───────┘ └─┬─┘ └─────────────┬──────────────┘
 ①scheme   ②subprotocol  ③host:port   ④database        ⑤parameters
 (고정)     (driver 식별)  (or socket)  (db name)        (driver-specific)

MySQL:
jdbc:mysql://db.example.com:3306/mydb?useSSL=true&serverTimezone=UTC
                                       &useUnicode=true&characterEncoding=UTF-8
                                       &rewriteBatchedStatements=true
```

**핵심 인사이트** — 5번 parameter는 driver-specific. PostgreSQL과 MySQL이 같은 옵션을 다른 이름으로 부른다 (예: `connectTimeout` PG / `connectTimeout` MySQL은 둘 다 있지만 단위와 default가 다름).

### 1.5 키워드 3 — DataSource는 추상화일 뿐, 구현체가 본질

```
javax.sql.DataSource (인터페이스)
   │
   ├─ HikariDataSource (HikariCP) ← 현대 표준
   ├─ Tomcat JDBC Pool (Tomcat Connector)
   ├─ DBCP2 (Apache Commons)
   ├─ C3P0 (legacy)
   ├─ Oracle UCP
   ├─ DriverManagerDataSource (Spring, no pool — 테스트용)
   └─ AgroalDataSource (Quarkus)
```

**왜 HikariCP가 standard가 되었나** — 07번 챕터에서 다룬 ConcurrentBag + lock-free 알고리즘. Spring Boot 2.0+가 default로 채택.

### 1.6 직관 — JDBC를 한 줄 비유로

> "JDBC는 **전화기 (Connection)** 를 빌려서, **메모지에 query를 적어 (Statement)** 상대(DB)에게 읽어주고, **상대가 read out한 결과를 표로 받아 (ResultSet) 한 줄씩 본다**. 매번 전화기 새로 만들면 비싸니 **전화기 풀 (DataSource)** 에서 빌린다."

---

## 2. 가지 ①-2: JDBC Driver 종류 (Type 1~4) — 왜 Type 4가 표준이 되었나

### 2.1 4가지 Type — 1997년 정의

```
┌─────────────────────────────────────────────────────────────────┐
│ Type 1: JDBC-ODBC Bridge                                         │
│                                                                   │
│  Java App → JDBC API → JDBC-ODBC Bridge → ODBC → DB              │
│                                       ↑                           │
│                                   native lib                      │
│                                                                   │
│  ❌ Java 8에서 제거. Microsoft가 ODBC를 Windows에 묶음.            │
│  ❌ 플랫폼 종속, 성능 나쁨.                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Type 2: Native API + Java Thin Wrapper                           │
│                                                                   │
│  Java App → JDBC API → Java thin → native DB client lib → DB     │
│                                  ↑                                │
│                              libpq.so / libmysqlclient.so         │
│                                                                   │
│  ⚠️ 네이티브 라이브러리 설치 필요 (배포 복잡).                       │
│  ⚠️ JNI 오버헤드. 단, native lib이 성숙하면 성능 좋음.              │
│  예: OCI driver (Oracle), libpq 기반 PG driver.                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Type 3: Middleware (3-tier)                                      │
│                                                                   │
│  Java App → JDBC API → middleware server → DB (각자 protocol)    │
│                       (proprietary protocol)                      │
│                                                                   │
│  ⚠️ 미들웨어 운영 부담.                                              │
│  ⚠️ 단일 클라이언트로 여러 DB 종류 지원 가능 (장점).                  │
│  거의 사용 안 됨.                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Type 4: Pure Java (현대 표준)                                     │
│                                                                   │
│  Java App → JDBC API → Pure Java Driver → DB                     │
│                       (wire protocol 직접 구현)                    │
│                                                                   │
│  ✅ 100% Java, JAR 하나로 배포.                                    │
│  ✅ 어느 플랫폼에서도 동일 동작.                                     │
│  ✅ JIT 최적화 받음.                                                │
│  예: PostgreSQL JDBC, MySQL Connector/J, MariaDB, H2.             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 왜 Type 4가 이겼나 — 3가지 이유

1. **배포 단순성** — JAR 하나만 classpath에 넣으면 끝. 컨테이너 시대에 결정적.
2. **JVM 최적화 수혜** — JIT, GC가 wire protocol 코드를 최적화. Native lib보다 메모리 관리 안전.
3. **wire protocol 표준화** — PostgreSQL/MySQL이 protocol을 안정적으로 공개 → Java 구현 가능.

**역사 트리거** — 1999년 PostgreSQL JDBC v3 (libpq 없이 pure Java) 등장. 이후 MySQL Connector/J (2003년 3.0)도 Type 4로 재작성.

**현대 잔재** — Oracle은 여전히 OCI driver (Type 2)를 옵션으로 제공. 일부 기능 (대량 LOB)에서 더 빠름. 하지만 thin driver (Type 4)가 default.

---

## 3. 가지 ②: Connection 생성 과정 — 매번 만들면 왜 비싼가

### 3.1 핵심 질문

> "Connection 하나 만드는 데 정확히 어떤 단계가 있나? 왜 pool이 필수인가?"

### 3.2 백지 그리기 — Connection 5단계 birth

```
[Application Thread]
    │ DataSource.getConnection()
    ▼
[HikariCP]
    │ pool에 idle connection 있나? — YES → 바로 반환 (수십 μs)
    │                              NO  → 아래 5단계 (수십 ms)
    ▼
[Driver: makeConnection()]
    │
    │ ① TCP 3-way handshake
    │    SYN → SYN-ACK → ACK   (~RTT × 1.5)
    │    DB는 보통 같은 region → 1~2 ms
    │    Cross-AZ → 5~10 ms
    │    Cross-region → 80~200 ms
    │
    ▼
    │ ② TLS handshake (sslmode=require일 때)
    │    ClientHello → ServerHello + Cert → Finished
    │    TLS 1.2: 2 RTT
    │    TLS 1.3: 1 RTT (또는 0-RTT)
    │
    ▼
    │ ③ Startup Message (PostgreSQL)
    │    "protocol_version=3.0, user=foo, database=mydb,
    │     application_name=spring-app, client_encoding=UTF8"
    │
    ▼
    │ ④ Authentication 교환
    │    Server: "AuthenticationSCRAM-SHA-256"
    │    Client: SASLInitialResponse (nonce)
    │    Server: SASLContinue (server nonce + salt)
    │    Client: SASLResponse (client proof)
    │    Server: SASLFinal (server signature) + AuthenticationOk
    │    → SCRAM은 5 메시지 = 2.5 RTT 추가
    │    → md5는 1 RTT (덜 안전)
    │
    ▼
    │ ⑤ ParameterStatus messages (서버 설정 알림)
    │    "server_version=15.4, server_encoding=UTF8, ..."
    │    BackendKeyData (cancel용 secret key)
    │    ReadyForQuery ('I' = idle, 'T' = in tx, 'E' = error)
    │
    ▼
[Connection 사용 가능] — 총 10~50 ms (local) / 100~500 ms (cross-AZ + TLS + SCRAM)
```

### 3.3 왜 매번 만들면 안 되나 — 운영 관점

```
[scenario] HTTP request마다 새 Connection 만들 때
   request rate: 1000 req/sec
   각 connection 비용: 30 ms (TLS + SCRAM 포함)
   
   결과:
   - DB CPU: TLS handshake로 폭증
   - request P99: 30 ms 추가 (DB query는 1 ms일 때도)
   - DB의 max_connections 초과 → "too many connections" 에러
   - ephemeral port 고갈 (client side)
   - TIME_WAIT socket 누적 (kernel 메모리)
```

**해결** — Connection pool. 한 번 만든 Connection을 N개 유지 (HikariCP의 maximumPoolSize, 보통 10~20). request마다 borrow/return.

### 3.4 PostgreSQL Auth 메커니즘 비교

| 방식 | RTT 수 | 안전성 | 비고 |
|---|---|---|---|
| `trust` | 0 (no auth) | 매우 위험 | 로컬 dev only |
| `password` | 1 RTT | 평문 전송, 위험 | deprecated |
| `md5` | 1 RTT | salted hash, 약함 (rainbow attack) | legacy default |
| `scram-sha-256` | 2.5 RTT | 강력 (challenge-response) | PG 10+ default |
| `gss/sspi` | Kerberos 의존 | 강력 | 엔터프라이즈 SSO |
| `cert` (TLS client cert) | TLS 안에 포함 | 강력 | mTLS |

**운영 함정** — `scram-sha-256`이 보안은 좋지만 매 Connection 생성 시 2.5 RTT × 30ms (cross-AZ) = 75ms 추가. pool이 가득 차서 burst에 새 connection 생성 시 latency spike의 원인.

### 3.5 HikariCP의 idle pool 운용

```
HikariConfig:
   maximumPoolSize: 20      ← 동시 최대 connection
   minimumIdle: 10          ← 항상 유지할 idle
   connectionTimeout: 30s   ← getConnection() 대기 한계
   idleTimeout: 10min       ← idle connection 폐기 한계
   maxLifetime: 30min       ← connection 강제 폐기 (DB max_lifetime보다 짧게)
   
운용:
   pool 시작 시 minimumIdle 만큼 미리 connection 생성 (preallocation)
   getConnection() → ConcurrentBag에서 dequeue (lock-free)
   close() (실제론 Spring proxy의 release) → ConcurrentBag으로 return
   idleTimeout 초과 idle connection → housekeeper thread가 폐기
   maxLifetime 초과 → 사용 중이어도 다음 return 시 폐기 (재생성)
```

→ 자세한 HikariCP 내부는 [07-connection-pools-master.md](./07-connection-pools-master.md).

---

## 4. 가지 ②-2: PostgreSQL Wire Protocol — byte 수준의 진실 ⭐⭐

### 4.1 핵심 질문

> "`SELECT * FROM users WHERE id = 42` 를 JDBC로 실행하면 socket에 정확히 어떤 byte가 흐르나?"

### 4.2 백지 그리기 — 메시지 포맷 공통 구조

```
[모든 PostgreSQL 메시지]

  ┌─────────┬─────────┬──────────────────────────┐
  │ Type    │ Length  │   Payload                 │
  │ (1 byte)│ (4 byte)│   (length-4 bytes)        │
  └─────────┴─────────┴──────────────────────────┘
   'Q'        00 00 00 1A   ... SQL ...
   (Query)    (26 bytes
                total)

예외: 첫 Startup Message는 type byte 없음 (length + payload만).

Type byte 의미 (대표):
  Frontend → Backend (client → server):
   'Q' = simple Query
   'P' = Parse (extended)
   'B' = Bind (extended)
   'E' = Execute (extended)
   'D' = Describe
   'S' = Sync
   'X' = Terminate

  Backend → Frontend (server → client):
   'R' = Authentication request
   'S' = ParameterStatus
   'K' = BackendKeyData
   'Z' = ReadyForQuery
   'T' = RowDescription (컬럼 메타)
   'D' = DataRow
   'C' = CommandComplete
   'E' = ErrorResponse
   'N' = NoticeResponse
   '1' = ParseComplete
   '2' = BindComplete
   '3' = CloseComplete
```

**왜 type byte + length 형식** — 메시지 경계가 명확. socket read시 4 byte length 먼저 읽고 정확히 그만큼 추가 read → framing 문제 없음.

### 4.3 Simple Query 모드 ('Q' 메시지)

```
Client                                    Server
  │                                         │
  │  Q msg: "SELECT id, name FROM users\0"  │
  │ ──────────────────────────────────────► │
  │                                         │
  │                                         │  ← parse + plan + execute
  │                                         │
  │   T msg: RowDescription                 │
  │   (column_count, [name, type_oid,       │
  │    typmod, format], ...)                │
  │ ◄────────────────────────────────────── │
  │                                         │
  │   D msg: DataRow (1번째 row)            │
  │   (column_count, [length, value], ...)  │
  │ ◄────────────────────────────────────── │
  │                                         │
  │   D msg: DataRow (2번째 row)            │
  │ ◄────────────────────────────────────── │
  │   ...                                   │
  │                                         │
  │   C msg: "SELECT 100" (CommandComplete) │
  │ ◄────────────────────────────────────── │
  │                                         │
  │   Z msg: ReadyForQuery ('I' or 'T')     │
  │ ◄────────────────────────────────────── │
```

**Simple Query의 특징**:
- SQL이 **하나의 string**으로 전송 (parameter 없음).
- 결과는 **text format** (각 컬럼 값을 문자열로 직렬화).
- DB에서 매번 parse + plan → plan cache 못 씀.
- **여러 SQL을 세미콜론으로 묶어** 한 번에 보낼 수 있음 (`SELECT ...; UPDATE ...;`).

**언제 사용** — JDBC `Statement.execute()` (not Prepared). 또는 DDL.

### 4.4 Extended Query 모드 ('P'/'B'/'E' 메시지) ⭐

```
Client                                    Server
  │                                         │
  │  P msg: Parse                           │
  │  ("stmt_name", "SELECT id, name FROM    │
  │   users WHERE age > $1", [oid_of_int])  │
  │ ──────────────────────────────────────► │
  │                                         │
  │  B msg: Bind                            │
  │  ("portal_name", "stmt_name",           │
  │   [param_format], [param_value=18],     │
  │   [result_format])                      │
  │ ──────────────────────────────────────► │
  │                                         │
  │  D msg: Describe (portal)               │
  │  → 결과 컬럼 메타 요청 (선택)              │
  │ ──────────────────────────────────────► │
  │                                         │
  │  E msg: Execute                         │
  │  ("portal_name", max_rows=0 or N)       │
  │ ──────────────────────────────────────► │
  │                                         │
  │  S msg: Sync (트랜잭션 boundary 표시)    │
  │ ──────────────────────────────────────► │
  │                                         │
  │   1 msg: ParseComplete                  │
  │ ◄────────────────────────────────────── │
  │   2 msg: BindComplete                   │
  │ ◄────────────────────────────────────── │
  │   T msg: RowDescription (Describe 응답) │
  │ ◄────────────────────────────────────── │
  │   D msg: DataRow × N                    │
  │ ◄────────────────────────────────────── │
  │   C msg: CommandComplete                │
  │ ◄────────────────────────────────────── │
  │   Z msg: ReadyForQuery                  │
  │ ◄────────────────────────────────────── │
```

**Extended의 핵심 5단계**:
1. **Parse** — SQL template (with `$1`, `$2` placeholder) 를 등록. stmt_name이 빈 문자열이면 unnamed (anonymous).
2. **Bind** — Parsed statement에 parameter 값을 채워 portal 생성.
3. **Describe** — portal의 결과 컬럼 정보 (선택, 첫 호출만).
4. **Execute** — portal 실행. `max_rows`로 부분 결과 fetch 가능 (cursor 기반).
5. **Sync** — pipeline boundary. 서버가 ReadyForQuery 응답.

**왜 5단계로 쪼개나** — Parse 결과를 **재사용**. 같은 stmt_name으로 여러 번 Bind+Execute → parse 비용 1회.

**Pipelining 가능성** — Parse/Bind/Execute/Sync를 한 TCP write로 묶어 보낼 수 있음 (request batching). 응답을 기다리지 않고 다음 명령 전송 → latency 감소.

### 4.5 구체 예시 — `SELECT * FROM users WHERE id = 42`

**Simple Query 모드 (raw byte)**:

```
Direction: C → S
Total: 36 bytes

51                                   'Q' (Query)
00 00 00 23                          length = 35
53 45 4C 45 43 54 20 2A 20           "SELECT * "
46 52 4F 4D 20 75 73 65 72 73 20     "FROM users "
57 48 45 52 45 20 69 64 20 3D 20     "WHERE id = "
34 32 00                             "42\0"
```

**Extended Query 모드 (raw byte 흐름)**:

```
Direction: C → S
[Parse]
50                                   'P'
00 00 00 33                          length = 51
00                                   stmt_name = "" (unnamed)
53 45 4C 45 43 54 20 2A 20 46 52     "SELECT * FR
4F 4D 20 75 73 65 72 73 20 57 48     OM users WH
45 52 45 20 69 64 20 3D 20 24 31     ERE id = $1"
00                                   \0
00 01                                num_param_types = 1
00 00 00 17                          oid 23 = int4

[Bind]
42                                   'B'
00 00 00 1E                          length = 30
00                                   portal_name = ""
00                                   stmt_name = ""
00 01                                num_param_formats = 1
00 01                                format = binary (1)
00 01                                num_param_values = 1
00 00 00 04                          value length = 4
00 00 00 2A                          int32 value = 42
00 01                                num_result_formats = 1
00 01                                format = binary

[Execute]
45                                   'E'
00 00 00 09                          length = 9
00                                   portal_name = ""
00 00 00 00                          max_rows = 0 (no limit)

[Sync]
53                                   'S'
00 00 00 04                          length = 4
```

**핵심 인사이트** — Parse 메시지에는 SQL template만, Bind 메시지에는 parameter 값만. **둘은 절대 같은 message에 섞이지 않음**. 이게 SQL injection 방어의 본질 (가지 ③ 참조).

### 4.6 Simple vs Extended 트레이드오프

| 측면 | Simple Query | Extended Query |
|---|---|---|
| 메시지 수 | 1 | 4~5 |
| Parse 재사용 | 불가 | 가능 |
| Parameter 전달 | inline (SQL string) | 별도 메시지 |
| SQL Injection | 직접 방어 필요 | 구조적 차단 |
| 결과 format | text only | text or binary |
| Cursor 부분 fetch | 불가 (전체 반환) | 가능 (max_rows) |
| 여러 SQL 한 번에 | 가능 (`;` 구분) | 불가 |
| JDBC API | `Statement` | `PreparedStatement` |

**현대 권장** — 거의 모든 경우 Extended (PreparedStatement). Simple은 DDL이나 `Statement` 명시 사용시만.

---

## 5. 가지 ②-3: MySQL Protocol 짧게

### 5.1 MySQL의 packet 포맷

```
┌─────────────┬──────────┬─────────────────┐
│ Length      │ Seq #    │ Payload          │
│ (3 byte LE) │ (1 byte) │                  │
└─────────────┴──────────┴─────────────────┘
   max 16MB    한 conn      command + args
              내에서 순환

Command byte (payload 1번째):
  0x03 = COM_QUERY (text 기반 query)
  0x16 = COM_STMT_PREPARE
  0x17 = COM_STMT_EXECUTE
  0x18 = COM_STMT_SEND_LONG_DATA
  0x19 = COM_STMT_CLOSE
  0x1A = COM_STMT_RESET
  0x0E = COM_PING
  0x01 = COM_QUIT
```

### 5.2 Handshake + Auth

```
Client                                    Server
  │  (TCP connect)                          │
  │                                         │
  │   Handshake Packet                      │
  │   (server_version, capability flags,    │
  │    auth_plugin_name, salt)              │
  │ ◄────────────────────────────────────── │
  │                                         │
  │  HandshakeResponse                      │
  │  (capabilities, max_packet,             │
  │   username, auth_response=SHA256(...))  │
  │ ──────────────────────────────────────► │
  │                                         │
  │   OK packet (0x00) or                   │
  │   AuthSwitchRequest (0xFE) or           │
  │   Err packet (0xFF)                     │
  │ ◄────────────────────────────────────── │
```

**MySQL의 auth plugin** (`mysql_native_password`, `caching_sha2_password` MySQL 8 default). PostgreSQL의 SCRAM과 비슷한 challenge-response.

### 5.3 Query 실행 (COM_QUERY)

```
Client                                    Server
  │  [0x03 + "SELECT id FROM users"]        │
  │ ──────────────────────────────────────► │
  │                                         │
  │   Column count packet (1 byte LE)       │
  │ ◄────────────────────────────────────── │
  │   Column Definition × N                 │
  │   (catalog, schema, table, name,        │
  │    type, length, charset, ...)          │
  │ ◄────────────────────────────────────── │
  │   EOF packet (or end-of-columns marker) │
  │ ◄────────────────────────────────────── │
  │   Row packet × M (length-prefix string) │
  │ ◄────────────────────────────────────── │
  │   EOF packet (end of result)            │
  │ ◄────────────────────────────────────── │
```

### 5.4 Prepared Statement (COM_STMT_PREPARE + EXECUTE)

```
Client                                    Server
  │  [0x16 + "SELECT id FROM users WHERE   │
  │           name = ?"]                    │
  │ ──────────────────────────────────────► │
  │                                         │
  │   COM_STMT_PREPARE_OK                   │
  │   (statement_id, num_columns, num_params)│
  │ ◄────────────────────────────────────── │
  │                                         │
  │  [0x17 + statement_id +                 │
  │   null bitmap + param types + values]   │
  │ ──────────────────────────────────────► │
  │                                         │
  │   Column Definition × N                 │
  │   Row × M (binary protocol format)      │
  │ ◄────────────────────────────────────── │
```

**MySQL의 binary protocol** — Row가 binary로 인코딩 (PostgreSQL extended의 format=1과 유사). int를 4 byte LE로, varchar는 length-prefix string으로.

### 5.5 PostgreSQL vs MySQL 비교

| 측면 | PostgreSQL | MySQL |
|---|---|---|
| 메시지 framing | type(1) + length(4) | length(3) + seq(1) |
| Max packet | 무제한 (length 4 byte) | 16MB (length 3 byte) |
| Auth (current) | SCRAM-SHA-256 | caching_sha2_password |
| Prepared 방식 | Parse + Bind 분리 | PREPARE + EXECUTE |
| Result format | text or binary 선택 | text or binary (prepared만) |
| Cursor | portal max_rows | server-side cursor (별도) |
| Encryption | TLS via STARTTLS | TLS via SSL Request packet |

---

## 6. 가지 ③: PreparedStatement — 왜 빠르고 왜 안전한가 ⭐

### 6.1 핵심 질문

> "PreparedStatement는 정확히 어떻게 SQL injection을 막고 왜 빠른가? Statement에서 단순 escape하는 것과 무엇이 다른가?"

### 6.2 백지 그리기 — 2단계 모델

```
[Phase 1: Parse — 1회]
   SQL template: "SELECT * FROM users WHERE name = $1 AND age > $2"
                                                ▲          ▲
                                                │          │
                                            placeholder    placeholder
   │
   │ Parse 메시지로 전송
   ▼
[Server]
   - Lex (tokenize)
   - Parse (AST 생성)
   - Resolve (table/column 존재 확인)
   - Plan 생성 (optional, generic plan)
   - statement_name으로 cache

[Phase 2: Bind + Execute — N회]
   Parameter values: ["alice", 18]
                       ▲       ▲
                       │       │
                  parameter   parameter
                  values      values
   │
   │ Bind + Execute 메시지로 전송
   ▼
[Server]
   - statement_name 으로 plan 조회
   - parameter 값을 그 자리에 채움 (절대 SQL 텍스트와 mix 안 함)
   - 실행
```

### 6.3 키워드 1 — Parse 1회 + Bind N회

```
[비유]
  Parse = 빈칸 있는 양식 작성 (한 번)
  Bind = 그 양식의 빈칸에 값을 채워 제출 (여러 번)

[성능]
  Statement (매번 parse):
    100번 호출 = 100 × (parse + plan + execute)
    parse + plan = 보통 200~500 μs (간단한 쿼리)
    
  PreparedStatement (parse 1회):
    100번 호출 = 1 × parse + 100 × execute
    parse 분 amortize → 무시 가능

[plan cache hit ratio]
  pg_stat_statements 의 query 별 calls 카운트
  prepared 사용 시 같은 query가 한 row로 합쳐짐
```

### 6.4 키워드 2 — Parameter는 별도 메시지 (SQL injection 차단의 본질)

```
[Statement (위험)]
  String name = request.getParameter("name");   // "Alice' OR '1'='1"
  String sql = "SELECT * FROM users WHERE name = '" + name + "'";
  stmt.executeQuery(sql);
  
  → 서버가 보는 SQL:
     SELECT * FROM users WHERE name = 'Alice' OR '1'='1'
                                                ↑
                                          파서가 새 조건으로 해석
  → injection 성공

[PreparedStatement (안전)]
  String name = request.getParameter("name");   // "Alice' OR '1'='1"
  PreparedStatement ps = conn.prepareStatement(
      "SELECT * FROM users WHERE name = ?");
  ps.setString(1, name);
  ps.executeQuery();
  
  → wire:
     [Parse] SQL = "SELECT * FROM users WHERE name = $1"   (값 없음!)
     [Bind]  param_1 = "Alice' OR '1'='1"                   (값만)
     
  → 서버 처리:
     - parse 단계에서 $1은 placeholder로만 인식
     - bind 단계의 string은 SQL parser를 절대 거치지 않음
     - 그 string은 column "name"과 비교할 literal value일 뿐
  → injection 불가
```

**핵심 인사이트** — Statement의 escape는 **임시방편** (escape 함수가 모든 corner case를 커버해야 하는데 어려움). PreparedStatement는 **구조적 차단** (parameter와 SQL이 wire에서 분리됨).

### 6.5 키워드 3 — Server-side vs Client-side Prepare

| 방식 | 동작 | DB 측 |
|---|---|---|
| **Server-side prepare** | wire에 실제 Parse 메시지 전송, 서버가 plan cache | DB 메모리에 prepared stmt 보관 |
| **Client-side prepare** | driver가 client에서 escape + substitute → 일반 Query 전송 | DB는 prepared 인지 못 함 |

**MySQL Connector/J 기본** — client-side! `useServerPrepStmts=true`로 server-side 활성화.

**PostgreSQL JDBC 기본** — server-side, 단 **5번째 호출부터** (prepareThreshold=5). 그 전에는 server-side parse + bind를 매번 함 (anonymous prepare). 5번 넘으면 named prepare로 전환 → plan cache 본격 활용.

**왜 prepareThreshold가 있나** — server에 plan을 cache하면 메모리 사용. 한 번만 호출되는 query를 매번 cache하면 누수. 5번 이상 호출되는 query만 cache → balance.

```
[PostgreSQL JDBC 동작]
  call 1~4: 매번 anonymous prepare (parse + bind + execute + close)
  call 5~: named prepare로 전환, 이후 bind + execute만
  
[옵션]
  prepareThreshold=0 → 항상 anonymous (server cache 안 함)
  prepareThreshold=1 → 첫 호출부터 named
  prepareThreshold=N → N+1번째부터 named
```

### 6.6 server-side prepared의 함정 — 메모리 누수

```
[패턴]
  app이 동적으로 SQL을 생성 (예: WHERE 조건이 매번 달라짐)
   → 수천 종류의 prepared statement
   → 각각 server-side cache
   → DB 메모리 폭증 (pg_prepared_statements 테이블 비대화)
   → 결국 connection 재시작 필요

[해결]
  - prepareThreshold=0 또는 낮게
  - 또는 prepared cache 크기 제한
  - HikariCP의 maxLifetime으로 connection 주기적 재생성
```

**현실 사례** — Spring Data JPA에서 `findByDynamic` 류 메서드가 조건마다 다른 SQL 생성. 운영 6개월 후 DB OOM. 진단: `pg_prepared_statements` 에 connection 당 수천 row.

### 6.7 Batching — round-trip 줄이기

```
[일반 호출]
  for (i = 0; i < 1000; i++) {
      ps.setInt(1, i);
      ps.executeUpdate();   ← 매번 wire round-trip
  }
  → 1000 × RTT
  → RTT 2ms (cross-AZ) → 2초

[Batching]
  for (i = 0; i < 1000; i++) {
      ps.setInt(1, i);
      ps.addBatch();   ← driver 내부 buffer에 쌓음
  }
  ps.executeBatch();   ← 한 번의 wire 통신 (또는 chunk)
  → 거의 1 RTT
  → 20ms

[MySQL rewriteBatchedStatements=true]
  INSERT INTO t (a) VALUES (1);
  INSERT INTO t (a) VALUES (2);
  ...
  → 다음으로 rewrite:
  INSERT INTO t (a) VALUES (1), (2), (3), ...
  → 단일 SQL로 변환 → 더 빠름

[PostgreSQL]
  reWriteBatchedInserts=true (PG JDBC 9.4.1209+)
  비슷한 INSERT VALUES rewrite
```

**왜 batching이 효과적** — DB query 자체는 빠른데 wire round-trip (RTT × N)이 dominant 비용일 때. ETL, bulk insert에서 핵심.

---

## 7. 가지 ④: ResultSet — Lazy인가 Eager인가, 그리고 OOM 함정 ⭐

### 7.1 핵심 질문

> "`SELECT * FROM huge_table` 의 결과 1억 row를 JDBC로 받으면 어떻게 되나?"

### 7.2 백지 그리기 — 기본 동작 (Eager의 함정)

```
[JDBC 기본: fetchSize = 0]

Client (Driver buffer)                  Server
  │                                         │
  │  Query                                  │
  │ ──────────────────────────────────────► │
  │                                         │
  │   RowDescription                        │
  │ ◄────────────────────────────────────── │
  │   DataRow × ALL ROWS                    │
  │ ◄────────────────────────────────────── │
  │   ...                                   │
  │   ...                                   │
  │   CommandComplete                       │
  │ ◄────────────────────────────────────── │
  │                                         │
  ▼                                         
Client Heap에 모든 row가 쌓임
   → 1억 row × 1KB = 100GB → OOM
   → 또는 GC 폭증

ResultSet.next()는 단순히 in-memory buffer에서 다음 row 반환.
```

**왜 default가 0** — JDBC spec 호환성. 대부분 small result라 가정. 큰 result는 명시적으로 fetchSize 지정 의도.

### 7.3 PostgreSQL의 cursor 기반 lazy 모드

```
[fetchSize = N (예: 1000)]
[전제 조건: autoCommit = false]

Client                                    Server
  │  Parse + Bind + Execute (max_rows=N)    │
  │ ──────────────────────────────────────► │
  │                                         │
  │   RowDescription                        │
  │   DataRow × N                           │
  │   PortalSuspended ('s')                 │
  │ ◄────────────────────────────────────── │
  │                                         │
  │  rs.next() → ... → N번째 row 소진       │
  │  Execute (portal, max_rows=N)           │  ← 다음 batch 요청
  │ ──────────────────────────────────────► │
  │                                         │
  │   DataRow × N                           │
  │   PortalSuspended                       │
  │ ◄────────────────────────────────────── │
  │  ...                                    │
  │                                         │
  │  마지막 batch (row < N):                │
  │   DataRow × M                           │
  │   CommandComplete                       │
  │ ◄────────────────────────────────────── │
```

**핵심 조건**:
1. `autoCommit = false` (transaction 안에 있어야 portal 유지됨).
2. `setFetchSize(N)` (N > 0).
3. `TYPE_FORWARD_ONLY` (default, 뒤로 못 감).

**autoCommit이 왜 필요** — portal은 transaction에 묶임. autoCommit이면 매 SQL이 즉시 commit → portal 사라짐 → 다음 batch 불가능.

### 7.4 MySQL의 streaming 모드

```
[MySQL Connector/J에서 streaming]
stmt.setFetchSize(Integer.MIN_VALUE);   // (-2147483648)

→ wire는 변하지 않음 (server는 그냥 모든 row 전송)
→ 단, driver는 받자마자 user에게 전달 (buffering 안 함)
→ 사실상 streaming

[제약]
  - 한 connection에서 ResultSet 완전히 소진 전까지 다른 query 불가
    (서버가 한 stream에 모든 row를 putting 중)
  - ResultSet 닫기 전에 다음 query 시도 → "Streaming result set is still active"
  
[옵션]
  useCursorFetch=true → server-side cursor 모드 (PostgreSQL과 유사)
  단, 서버 메모리 부담 증가 (cursor가 결과를 보유)
```

### 7.5 키워드 1 — fetchSize 미설정 OOM 시나리오

```
[운영 사고 시나리오]
  분석 팀이 "최근 1년 주문 데이터를 전부 가져와 통계"
  코드:
     PreparedStatement ps = conn.prepareStatement("SELECT * FROM orders WHERE created > '2024-01-01'");
     ResultSet rs = ps.executeQuery();
     while (rs.next()) { ... }
  
  결과: 5000만 row × 평균 2KB = 100GB
  Heap 4GB → OutOfMemoryError: Java heap space
  Heap dump 분석: ArrayList<byte[]> of DataRow in PG driver

[해결]
  ps.setFetchSize(10_000);
  conn.setAutoCommit(false);   // PG는 필수
  // ... 처리 ...
  conn.commit();
```

### 7.6 키워드 2 — ResultSet 메타 + getXxx의 동작

```
[ResultSet 사용]
while (rs.next()) {
    int id = rs.getInt("id");
    String name = rs.getString("name");
}

[내부]
  rs.next():
    - 현재 row 포인터를 다음 row로 이동
    - buffer 끝이면 다음 batch fetch (cursor 모드)
    - 끝이면 false
  
  rs.getString("name"):
    - 현재 row의 "name" 컬럼 위치 찾기 (RowDescription metadata)
    - byte → String 변환 (charset 적용)
    - text format이면 그대로
    - binary format이면 type별 decode (int4 → 4 byte BE → int)

[성능 팁]
  컬럼 이름 vs 인덱스:
    rs.getString("name") → 매번 hash lookup
    rs.getString(2) → 인덱스 접근 (빠름, 단 컬럼 순서 의존)
```

### 7.7 키워드 3 — ResultSet과 GC

```
[scenario] fetchSize 적절 설정해도 큰 ResultSet의 GC 압박

  fetchSize = 10000
  각 batch마다 10000 × 1KB = 10MB 객체 (DataRow + parsed String)
  
  while (rs.next()) {
      processBatch(...);   // 빠르게 처리 후 GC 대상
  }
  
  → batch마다 10MB 할당 + 10MB 해제
  → Young GC 빈발
  → 처리 속도가 GC 속도에 묶임

[튜닝]
  - 큰 String을 byte[]로 받아 stream 처리
  - Direct ByteBuffer 사용 (off-heap)
  - 가능하면 SQL에서 aggregate해서 줄이기
```

---

## 8. 가지 ⑤: Transaction — Connection과의 1:1 결혼

### 8.1 핵심 질문

> "Spring `@Transactional` 메서드 안에서 DB query 두 번을 호출하면, 두 query는 어떻게 같은 transaction인 줄 알 수 있나?"

### 8.2 백지 그리기 — Transaction의 wire 표현

```
[Transaction lifecycle]

  ┌─────────────────────────────────────────────────────────────┐
  │ Spring: TransactionManager.begin()                          │
  │  ↓                                                            │
  │ HikariCP.getConnection() → Connection C                      │
  │  ↓                                                            │
  │ C.setAutoCommit(false)                                       │
  │  → driver가 wire에 보냄: "BEGIN" (PostgreSQL) /              │
  │                          "START TRANSACTION" (MySQL)         │
  │  ↓                                                            │
  │ [Application code]                                            │
  │   1번째 query → wire: PreparedStatement msg (same conn C)    │
  │   2번째 query → wire: PreparedStatement msg (same conn C)    │
  │  ↓                                                            │
  │ Spring: commit() / rollback()                                │
  │  → driver가 wire에 보냄: "COMMIT" / "ROLLBACK"               │
  │  ↓                                                            │
  │ C.setAutoCommit(true)  (default 복원)                        │
  │  ↓                                                            │
  │ HikariCP.return(C)                                           │
  └─────────────────────────────────────────────────────────────┘
```

### 8.3 키워드 1 — autoCommit의 진실

```
[JDBC default]
  Connection.getAutoCommit() = true
  → 매 SQL 후 즉시 COMMIT
  → 사실은 driver가 BEGIN ... COMMIT을 한 SQL 단위로 자동 wrap

[Spring @Transactional]
  실제 동작:
    1. DataSourceTransactionManager가 getConnection()
    2. conn.setAutoCommit(false)
    3. ThreadLocal에 conn binding
    4. 메서드 안의 모든 JDBC 호출이 같은 conn 사용
    5. 메서드 정상 종료 → conn.commit()
       메서드 예외 → conn.rollback()
    6. conn.setAutoCommit(true) 복원 (HikariCP의 resetOnReturn)
    7. HikariCP.return(conn)

[wire 흐름 비교]
  autoCommit=true (default):
    SELECT ...  ← driver가 BEGIN; SELECT ...; COMMIT 으로 wrap
    SELECT ...  ← 다시 BEGIN ... COMMIT
  
  autoCommit=false + @Transactional:
    BEGIN
    SELECT ...
    SELECT ...
    COMMIT
```

**왜 1 transaction = 1 connection** — Transaction state (uncommitted changes, locks, snapshot) 는 서버 측에서 connection에 묶임. 다른 connection에서는 보이지 않음 (MVCC isolation). 따라서 같은 transaction의 모든 query는 같은 connection이어야 함.

**Spring의 마법** — `TransactionSynchronizationManager` 가 ThreadLocal에 (DataSource → Connection) map을 들고 있음. `DataSource.getConnection()` 호출 시 Spring proxy가 가로채어 ThreadLocal 먼저 확인.

### 8.4 키워드 2 — Isolation Level — wire에서 어떻게 설정

```
[JDBC API]
  conn.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);

[wire]
  driver가 send:
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED
  (또는 BEGIN ISOLATION LEVEL READ COMMITTED)

[4 표준 레벨]
  READ UNCOMMITTED   ← dirty read 가능 (PG는 사실상 READ COMMITTED와 동일)
  READ COMMITTED     ← PG default
  REPEATABLE READ    ← MySQL InnoDB default
  SERIALIZABLE       ← 가장 strict

[운영 함정]
  Spring @Transactional(isolation=REPEATABLE_READ):
    conn 차용 시 setTransactionIsolation 호출
    transaction 종료 후 default로 복원해야 함
    → HikariCP의 resetIsolationOnReturn=true (default)
```

### 8.5 키워드 3 — Savepoint + 2PC

```
[Savepoint — nested transaction 흉내]
  BEGIN
  INSERT INTO orders ...
  SAVEPOINT sp1
  UPDATE inventory ...   ← 실패 가능
  
  실패 시:
    ROLLBACK TO SAVEPOINT sp1   ← inventory 변경만 취소
    -- orders는 살아있음
  
  COMMIT

[JDBC API]
  Savepoint sp = conn.setSavepoint("sp1");
  ...
  conn.rollback(sp);   // sp1 이후만 rollback

[2PC — distributed transaction]
  여러 DB (또는 DB + JMS)에 걸친 transaction.
  
  ┌─────────────┐
  │ Coordinator │
  │ (JTA, Atomikos, Narayana)
  └──┬───────┬──┘
     │       │
     ▼       ▼
  ┌────┐  ┌────┐
  │ DB1│  │ DB2│
  └────┘  └────┘
  
  Phase 1 (prepare):
    coord → DB1: PREPARE TRANSACTION 'tx1'   ← 변경 저장 + lock 유지
    coord → DB2: PREPARE TRANSACTION 'tx1'
    
    DB1, DB2 모두 "ready" 응답하면 Phase 2.
  
  Phase 2 (commit/rollback):
    coord → DB1: COMMIT PREPARED 'tx1'
    coord → DB2: COMMIT PREPARED 'tx1'
    
    한쪽이 prepare에서 실패하면 모두 ROLLBACK.

[현대 권장]
  2PC는 무거움 (lock 오래 잡힘, coordinator 장애 시 in-doubt transaction).
  마이크로서비스에서는 Saga 패턴 + 보상 transaction 선호.
```

---

## 9. 가지 ⑥: Connection State — pool 재사용의 위험 ⭐

### 9.1 핵심 질문

> "Connection을 pool에서 재사용할 때 어떤 state가 다음 사용자에게 leak되는가?"

### 9.2 백지 그리기 — Connection이 들고 있는 state

```
┌─────────────────────────────────────────────────────────┐
│  Connection State (server side, per-connection)          │
│                                                           │
│  ① autoCommit (true/false)                                │
│  ② isolation level                                        │
│  ③ readOnly flag                                          │
│  ④ schema / current_database                              │
│  ⑤ session variables                                      │
│     PG: SET statement_timeout = '10s'                    │
│     MySQL: SET @user_var = ...                            │
│  ⑥ prepared statement cache                               │
│     pg_prepared_statements                                │
│     mysql server-side prepared                            │
│  ⑦ Advisory lock                                          │
│     PG: pg_advisory_lock()                                │
│     MySQL: GET_LOCK()                                     │
│  ⑧ Temporary tables                                       │
│     CREATE TEMP TABLE ...                                 │
│  ⑨ Savepoints                                             │
│  ⑩ Open transaction (uncommitted)                         │
│  ⑪ Client encoding                                        │
└─────────────────────────────────────────────────────────┘
```

### 9.3 leak 시나리오들

```
[시나리오 1: 미rollback transaction]
  Request A: BEGIN; UPDATE ...; (예외 후 conn.close() but no rollback)
  HikariCP.return(conn)
  Request B: getConnection() → 같은 conn
  Request B: SELECT ...   ← 여전히 A의 uncommitted 변경이 visible
  
  → 데이터 무결성 깨짐!

[시나리오 2: isolation leak]
  Request A: setTransactionIsolation(SERIALIZABLE)
  Request A: ... commit ...
  HikariCP.return(conn)
  Request B: getConnection() → 같은 conn, isolation 여전히 SERIALIZABLE
  Request B: 의도치 않게 strict isolation → 성능 저하 + deadlock 증가

[시나리오 3: session variable leak]
  Request A: SET statement_timeout = '60s'
  return
  Request B: 60초 timeout으로 동작 (자기는 10초 의도)
```

### 9.4 HikariCP의 reset 옵션

```
HikariConfig:
  autoCommit: true            (return 시 복원)
  isolateInternalQueries: true
  
  → 내부적으로 connection 반납 시:
     conn.setAutoCommit(true);          // ① 복원
     conn.setTransactionIsolation(default);  // ②
     conn.setReadOnly(false);           // ③
     conn.setCatalog(default);          // ④
     conn.clearWarnings();
  
  → 하지만 ⑤ session variables, ⑥ prepared cache, ⑦ advisory lock 등은
     자동 reset 안 됨!

[방어]
  - 운영 코드에서 SET session var 자제
  - 필요하면 명시적 RESET 호출
  - HikariCP의 connectionInitSql: "RESET ALL" (PostgreSQL)
    → 매 connection 차용 시 실행 (성능 비용 있음)
```

### 9.5 advisory lock의 위험

```
[현실 사례]
  Request A: pg_advisory_lock(42)
  Request A: 작업 중 예외 → conn close (but pg_advisory_unlock 안 함)
  HikariCP.return(conn)   ← lock은 server에 여전히 남아있음
  
  Request B: pg_advisory_lock(42) → blocked
  ...
  Request N: 마찬가지로 blocked → 모든 worker hang
  
[해결]
  - HikariCP의 maxLifetime으로 connection 주기적 폐기 (30분)
  - 또는 try-finally로 명시적 unlock
  - 또는 pg_advisory_xact_lock (transaction 종료 시 자동 해제) 선호
```

---

## 10. 가지 ⑥-2: Character Encoding — 모지바케의 근원

### 10.1 핵심 질문

> "한글 'ㄱ'이 DB에 '?'로 저장되는 모지바케, 어디서 발생하나?"

### 10.2 4단계 charset chain

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ HTTP request │ →  │ Java String  │ →  │ JDBC wire    │ →  │ DB column    │
│ charset      │    │ (UTF-16 in   │    │ encoding     │    │ encoding     │
│ (Content-Type│    │  Heap)        │    │ (client_enc) │    │ (DB level)   │
│  charset)    │    │              │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘

각 화살표마다 charset 변환 발생. 한 곳이라도 불일치 → 모지바케.
```

### 10.3 PostgreSQL 측

```
[Server 측]
  - DB 전체 encoding: CREATE DATABASE ... ENCODING 'UTF8' (default).
  - 한번 정하면 변경 불가.

[Connection 측]
  - client_encoding parameter.
  - JDBC URL에 별도 옵션 없음. driver가 자동으로 UTF-8 설정.
  - 또는: SET client_encoding TO 'UTF8';

[운영 함정]
  - DB encoding이 SQL_ASCII (구식 시스템) → byte를 그대로 저장.
  - app은 UTF-8로 write, BI 도구는 EUC-KR로 read → 깨짐.
  - 해결: DB encoding 통일 (pg_dump + ENCODING 'UTF8'로 재생성).
```

### 10.4 MySQL 측 — utf8 vs utf8mb4 함정

```
[MySQL의 utf8은 가짜 UTF-8]
  MySQL의 "utf8" = utf8mb3 (3 byte까지). 
  이모지 (4 byte UTF-8 sequence) 저장 불가.

[증상]
  INSERT INTO t (msg) VALUES ('Hello 😀');
  → Error: Incorrect string value: '\xF0\x9F...'
  또는 silent truncation: 'Hello '

[해결]
  CREATE DATABASE x CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  
[JDBC URL]
  jdbc:mysql://host/db?useUnicode=true&characterEncoding=UTF-8
  → driver 측 String <-> byte 변환을 UTF-8로
  → server 측 client charset도 자동 설정 (handshake에서)

[server config]
  my.cnf:
    [client]
    default-character-set = utf8mb4
    [mysql]
    default-character-set = utf8mb4
    [mysqld]
    character-set-server = utf8mb4
    collation-server = utf8mb4_unicode_ci
```

### 10.5 디버깅 — 어디서 깨졌는지 추적

```
[step-by-step 확인]

1. HTTP request의 charset:
   curl -v ... → Content-Type 헤더 확인
   percent-encoding이면 어떤 charset으로 디코딩되나
   → [01-url-input-and-serialization.md](./01-url-input-and-serialization.md)

2. Java String:
   log.info("name: {} bytes: {}", name, name.getBytes("UTF-8"))
   "가" → C2 80 (잘못) vs EA B0 80 (정상)

3. JDBC wire (tcpdump):
   sudo tcpdump -i any -A port 5432
   Bind 메시지의 parameter value byte 확인

4. DB column:
   SELECT name, octet_length(name), length(name) FROM users WHERE id = X;
   PG: octet_length=byte 수, length=문자 수
   "가" → octet_length 3, length 1 (정상)
       → octet_length 6, length 2 (UTF-8을 다시 UTF-8로 인코딩한 더블 인코딩 사고)
```

---

## 11. 가지 ⑦: Timeout 계층 — 둘 중 누가 먼저 죽나

### 11.1 timeout 4계층

```
┌─────────────────────────────────────────────────────────┐
│ ① OS socket read timeout                                 │
│    SO_RCVTIMEO                                            │
│    JDBC URL: socketTimeout=Ns                             │
│    PG default: 0 (무한 대기)                              │
│                                                           │
│    어떤 경우: DB 자체가 응답 안 함 (네트워크 drop, DB crash) │
└─────────────────────────────────────────────────────────┘
   ▼
┌─────────────────────────────────────────────────────────┐
│ ② JDBC Statement timeout                                 │
│    Statement.setQueryTimeout(N) — 초 단위                │
│    내부: 별도 thread가 N초 후 Statement.cancel() 호출   │
│    cancel() → CancelRequest msg (별도 connection)        │
│                                                           │
│    어떤 경우: long-running query 차단                    │
└─────────────────────────────────────────────────────────┘
   ▼
┌─────────────────────────────────────────────────────────┐
│ ③ DB-side statement_timeout                              │
│    PG: SET statement_timeout = '30s'                     │
│    MySQL: SET SESSION MAX_EXECUTION_TIME = 30000        │
│                                                           │
│    DB가 자체적으로 N초 후 query abort                    │
│    Application 모르게 DB가 끊음                          │
└─────────────────────────────────────────────────────────┘
   ▼
┌─────────────────────────────────────────────────────────┐
│ ④ idle_in_transaction_session_timeout (PG)               │
│    Transaction이 N초 idle (no query) → connection drop   │
│    → uncommitted transaction abort                       │
│    → MVCC bloat 방어                                      │
└─────────────────────────────────────────────────────────┘
```

### 11.2 어느 timeout이 먼저 발동하나

```
[일반 동작]
  ②, ③ 중 짧은 것이 먼저 발동.
  
  예: setQueryTimeout(60) + statement_timeout=30s
    → 30초에 DB가 ERROR 응답 → Driver는 SQLException throw.
    → JDBC timer가 60초에 cancel() 보내는데 이미 끝남.

[② 메커니즘 세부]
  Statement.setQueryTimeout(N):
    Driver가 ScheduledExecutorService에 task 등록:
      "N초 후 Statement.cancel() 호출"
    cancel():
      별도 connection으로 PG: "SELECT pg_cancel_backend(pid)"
      (또는 wire protocol의 CancelRequest)
    
[④ 발동 패턴]
  app 코드:
    BEGIN
    UPDATE ...   (1초)
    [그 후 외부 API 호출 (60초 hang)]
    COMMIT
  
  → idle_in_transaction_session_timeout=30s 면:
    DB가 30초 후 transaction abort + connection drop
    → app은 socket read 시 connection reset
```

→ 더 자세한 timeout 분류는 [java-deep-dive/04-timeouts-connection-vs-read.md](../java-deep-dive/04-timeouts-connection-vs-read.md).

---

## 12. 가지 ⑦-2: Connection Validation — dead connection 감지

### 12.1 dead connection이 생기는 시나리오

```
1. DB 재시작 — connection 측은 모름 (TCP RST 못 받을 수 있음)
2. 방화벽 NAT timeout — idle 5분 후 firewall이 state 폐기
3. Load balancer가 backend 교체 — 옛 connection은 RST 없이 끊김
4. Network split — 패킷이 그냥 안 옴
5. DB crash — kernel이 OS-level TCP RST 보내긴 함 (보통)

→ 다음 getConnection() 시 dead connection 받으면 query 시 실패
→ HikariCP는 idle connection을 주기적/사용 직전 validate
```

### 12.2 두 검증 방식

```
[① connectionTestQuery (legacy)]
  매 getConnection() 직전 driver에 "SELECT 1" 같은 쿼리 실행.
  성공 → 살아있음.
  실패 → connection 폐기 + 새로 생성.
  
  단점: 매 borrow마다 round-trip (latency ~ms)

[② Connection.isValid(timeout) — JDBC 4.0+]
  driver가 effecient하게 검증. 보통 wire 측 ping 메시지.
  PG: 빈 Query 또는 dummy.
  MySQL: COM_PING (0x0E).
  
  HikariCP는 driver가 JDBC4 isValid 지원하면 ② 자동 사용 (default).
```

### 12.3 HikariCP의 validation 옵션

```
HikariConfig:
  validationTimeout: 5s     ← isValid 호출의 timeout
  
  housekeeperThread:
    idle connection → idleTimeout/keepaliveTime 따라 ping
    
  borrowFromPool():
    if (connection.idle_time > aliveBypassWindow) {
        connection.isValid(validationTimeout);
    }
    // 너무 자주는 안 함 (성능)
```

### 12.4 failFast vs validation overhead

```
[failFast=true (Spring Boot default since 2.x)]
  app startup 시 pool 초기 connection들이 valid한지 즉시 검증.
  실패 → app 시작 실패 (DB 없으면 stop).
  
  장점: prod 배포 시 DB 미연결 즉시 발견.
  단점: dev 환경에서 DB 없으면 시작 못 함.
```

---

## 13. 가지 ⑧: DB 측 — Query 받은 후 무엇이 일어나나

### 13.1 PostgreSQL 내부 처리

```
[DB가 Bind+Execute 메시지 받은 시점]

   ▼
[Backend Process — postmaster가 fork한 per-connection process]
   ▼
[Parser] (이미 Parse 단계에서 끝났으면 skip)
   - SQL → AST
   - syntax check
   ▼
[Rewriter]
   - View 전개 (view를 underlying table query로)
   - RULE 적용
   ▼
[Planner / Optimizer]
   - 통계 (pg_statistic) 참조
   - join 순서, access method (seq vs index), join 알고리즘 (nested loop vs hash) 결정
   - Plan tree 생성
   ▼
[Executor]
   - Plan tree 순회
   - 각 노드가 row를 위 노드에 전달 (volcano model)
   ▼
[Storage Layer]
   - Shared Buffer (shared_buffers, 보통 25% RAM)
   - Page (8KB) 단위 read/write
   - Buffer hit → 메모리에서 즉시
   - Buffer miss → OS page cache → disk
   ▼
[WAL Writer]
   - 변경 발생 시 WAL log에 먼저 기록 (durability)
   - 디스크 sync 시점은 commit
```

### 13.2 MySQL InnoDB 내부

```
[Server]
  Parser → Optimizer (Cost-Based) → Executor
   ▼
[Storage Engine: InnoDB]
   ▼
[Buffer Pool]
   - innodb_buffer_pool_size (보통 70% RAM)
   - LRU list로 page 관리
   ▼
[Redo Log (WAL의 MySQL 명)]
   - innodb_log_file_size
   - circular log
   ▼
[ibd file]
   - clustered index (B+tree) + secondary index
```

### 13.3 Replication

```
[Physical Replication (PG streaming, MySQL row-based binlog)]
  Primary의 WAL/binlog를 Replica에 wire로 전송.
  Replica가 적용.
  
  Sync mode:
    asynchronous — primary는 replica 응답 안 기다림 (latency 최소, data loss 위험)
    synchronous — primary는 replica의 receipt 기다림 (안전, latency 증가)

[Read replica routing]
  read query → replica로 routing.
  복제 지연 (replication lag): primary 변경 직후 replica read는 옛 데이터.
  
[Spring 측 routing]
  AbstractRoutingDataSource로 read/write 분리.
  @Transactional(readOnly=true) → replica로.
```

### 13.4 왜 알아야 하나 (앱 개발자도)

```
- Index 없는 WHERE 절: seq scan → 100만 row 전부 읽음 → 느림.
  → EXPLAIN으로 확인.

- Buffer hit ratio 낮음: 디스크 I/O dominant.
  → pg_stat_database 에서 blks_hit / (blks_hit + blks_read).
  → shared_buffers 부족 또는 working set이 너무 큼.

- WAL 폭증: bulk update 시 WAL 양이 데이터의 2배 이상.
  → 디스크 부족 + replica 전송 지연.
  → 큰 데이터는 batch 분할.
```

---

## 14. 가지 ⑨: ORM (JPA/Hibernate)이 JDBC 위에서 하는 일

### 14.1 핵심 질문

> "Hibernate가 entity 한 줄 save하면 JDBC 수준에서 어떤 일이 일어나나?"

### 14.2 JPA → JDBC 변환

```
[JPA 코드]
  User u = new User();
  u.setName("Alice");
  em.persist(u);
  // ... 메서드 끝에 transaction commit

[Hibernate 내부]
  1. Persistent context (1st level cache)에 entity 등록 (Map<Id, Entity>)
  2. INSERT SQL 즉시 안 보냄. flush 시점까지 미룸.
  
[flush 시점 — 다음 중 하나]
  - explicit em.flush() 호출
  - query 실행 직전 (auto-flush)
  - transaction commit 직전

[flush]
  Persistent context의 dirty entity들 → SQL 생성 → PreparedStatement → wire.
  순서 보장: INSERT → UPDATE → DELETE (parent → child)

[transaction commit]
  Hibernate가 flush + JDBC commit.
  wire: COMMIT 메시지.
```

### 14.3 N+1 problem — 가장 흔한 함정 ⭐

```
[코드]
  List<Order> orders = em.createQuery("FROM Order").getResultList();
  for (Order o : orders) {
      System.out.println(o.getCustomer().getName());   // lazy load
  }

[wire]
  1. SELECT * FROM orders;   ← 1 query, 100 row 반환
  2. for each order:
     SELECT * FROM customers WHERE id = ?;   ← 100 query
  
  → 총 101 query
  → DB CPU 사용은 적은데 (각 query 빠름), latency는 RTT × 101 = 폭증

[해결]
  fetch join:
    FROM Order o JOIN FETCH o.customer
    → 1 query로 join
  
  EntityGraph
  @BatchSize(size=20) → 20개 단위로 묶어 IN 절로 fetch (총 6 query)
```

### 14.4 1st level cache vs 2nd level cache

```
[1st level — Persistence Context (Hibernate Session)]
  - transaction 단위 (보통 web request)
  - 같은 entity를 id로 두 번 조회 → 두 번째는 cache hit (DB 안 감)
  - flush 전 dirty checking
  
[2nd level — SessionFactory (전체 app)]
  - 모든 transaction에서 공유
  - 별도 활성화 + provider 필요 (Ehcache, Hazelcast, Caffeine)
  - cluster에서는 cache 일관성 문제 (다른 노드의 update)
```

### 14.5 @Transactional → Connection 차용 패턴

```
@Transactional
public void method() {
    repo1.save(...);   // ← 같은 Connection
    repo2.save(...);   // ← 같은 Connection
}

[내부 (Spring TransactionInterceptor + Hibernate)]
  1. 메서드 진입 → JpaTransactionManager.begin()
  2. EntityManager 생성 + Connection 차용 (HikariCP)
  3. ThreadLocal에 (EntityManager, Connection) 저장
  4. 메서드 안의 모든 EntityManager 호출 → ThreadLocal 조회
  5. 메서드 종료 → flush + commit
  6. Connection.close() (실제론 HikariCP에 반납)
  7. ThreadLocal 청소
```

---

## 15. 운영 장애 패턴 ⭐ — 7대 실전 시나리오

### 15.1 시나리오 1: "DB CPU 정상인데 API가 slow"

```
[증상]
  P99 latency 500ms 이상.
  DB CPU 30% (여유).
  Slow query log에 100ms+ 없음.

[가설]
  - N+1 problem (수많은 짧은 query)
  - Connection pool 부족 (대기)
  - Network latency 증가 (cross-AZ)

[진단]
  app log + sleuth/zipkin: 한 request에 몇 개 query?
    → 100+ 면 N+1.
  
  HikariCP metrics:
    hikaricp_connections_pending → 대기 중인 thread.
    hikaricp_connections_acquire_time → getConnection 평균.

[해결]
  - fetch join, EntityGraph
  - pool size 증가 (단, DB max_connections 한도 내)
  - read replica 활용
```

### 15.2 시나리오 2: "connection refused"

```
[증상]
  org.postgresql.util.PSQLException: 
    Connection to db:5432 refused. ...
  
  또는 HikariCP:
    "Failed to obtain JDBC Connection"

[원인]
  ① DB max_connections 초과
     PG: pg_stat_activity row count == max_connections
  ② DB 재시작 중
  ③ 방화벽 차단 (security group 변경)
  ④ DNS 변경 (DB 주소 옮김)

[진단]
  - PG: SHOW max_connections; SELECT count(*) FROM pg_stat_activity;
  - app에서 telnet db_host 5432
  - dig db_host
  - SG/network ACL 확인

[해결]
  - app당 pool size × app instance 수가 max_connections 넘지 않게
  - PgBouncer/ProxySQL로 connection multiplexing
  - DB max_connections 증가 (단, RAM 비례 비용)
```

### 15.3 시나리오 3: "connection reset by peer"

```
[증상]
  java.net.SocketException: Connection reset
  
  중간에 query 도중 발생.

[원인]
  ① DB가 connection drop (idle_in_transaction_session_timeout)
  ② 방화벽/NAT의 idle timeout (default 5분~1시간)
  ③ DB crash + restart
  ④ Load balancer가 backend 교체

[진단]
  - tcpdump -i any port 5432 → RST 패킷 누가 보냄
  - DB log: "could not receive data from client"
  - HikariCP의 keepaliveTime 설정 (idle ping)

[해결]
  - HikariCP.keepaliveTime = 5min (idle conn 주기 ping)
  - HikariCP.maxLifetime = 30min < NAT idle timeout
  - TCP keepalive: tcpKeepAlive=true (JDBC URL)
```

### 15.4 시나리오 4: "deadlock detected"

```
[증상]
  PG: ERROR: deadlock detected
  MySQL: Deadlock found when trying to get lock

[원인]
  Tx A: lock row 1 → wait row 2
  Tx B: lock row 2 → wait row 1
  → cycle
  
  DB가 자동 감지 → 한쪽 abort.

[진단]
  PG log: deadlock detected. Process X waits for ... Process Y waits for ...
  pg_locks JOIN pg_stat_activity
  MySQL: SHOW ENGINE INNODB STATUS

[해결]
  - 같은 순서로 row lock (예: id 오름차순)
  - SELECT FOR UPDATE 줄이기
  - retry 로직 (deadlock SQLSTATE 40P01 시 재시도)
  - 가능하면 short transaction
```

### 15.5 시나리오 5: "idle in transaction"

```
[증상]
  pg_stat_activity:
    state = 'idle in transaction'
    state_change > 10min ago
  
  → 어떤 connection이 BEGIN 후 query 안 하고 멍하니 있음.
  
[원인]
  - app이 BEGIN 후 외부 API 호출 (몇 분 대기)
  - app 코드 버그 (예외 발생했는데 rollback 안 함)
  - Spring @Transactional이 너무 큰 메서드 wrap

[영향]
  ⚠️ MVCC bloat — 그 transaction 시작 시점의 row version 살려둠.
     → vacuum이 청소 못 함 → 테이블 비대화.
  ⚠️ Lock 점유 — 다른 transaction의 lock 대기.
  ⚠️ Connection 점유 — pool 고갈.

[진단]
  SELECT pid, state, state_change, query FROM pg_stat_activity
   WHERE state = 'idle in transaction'
   ORDER BY state_change ASC;

[해결]
  - @Transactional 메서드 범위 최소화 (외부 API 호출은 밖으로)
  - PG: idle_in_transaction_session_timeout = '30s' 설정
  - 강제 종료: SELECT pg_terminate_backend(pid)
```

### 15.6 시나리오 6: "ResultSet 처리 중 OOM"

```
[증상]
  분석/배치 job 실행 중 OOM.
  Heap dump: byte[] in PgResultSet.tuples 가 80% 차지.

[원인]
  fetchSize 미설정.
  대용량 SELECT.

[해결]
  ps.setFetchSize(10_000);
  conn.setAutoCommit(false);   // PG 필수
```

### 15.7 시나리오 7: "Prepared statement cache 누수"

```
[증상]
  DB 메모리 사용 증가, 결국 connection 죽음.
  PG: ERROR: out of memory for query result

[원인]
  동적 SQL 너무 많음 → server-side prepared stmt 무한 누적.
  pg_prepared_statements 에 connection 당 1000+ row.

[해결]
  - SQL 다양성 줄이기 (parameterize 잘)
  - HikariCP.maxLifetime 짧게 (30min)
  - PG JDBC: prepareThreshold=0 (cache 안 함)
  - 또는 connection-level RESET ALL 주기적
```

---

## 16. 측정·진단 도구 — 7단

### 16.1 pg_stat_activity — PostgreSQL 살아있는 query 보기

```sql
SELECT pid, usename, application_name, client_addr,
       state, wait_event_type, wait_event,
       query_start, state_change,
       query
  FROM pg_stat_activity
 WHERE state != 'idle'
 ORDER BY query_start ASC;

[state 값]
  active                  — 실행 중
  idle                    — connection 살아있고 query 안 함
  idle in transaction     — BEGIN 후 query 안 함 (위험)
  idle in transaction (aborted)  — 예외 후 rollback 안 함

[wait_event_type / wait_event]
  Lock / relation         — 다른 lock 대기
  IO / DataFileRead       — 디스크 I/O
  Client / ClientRead     — 네트워크 read 대기
```

### 16.2 pg_stat_statements — top slow query

```sql
CREATE EXTENSION pg_stat_statements;  -- 한 번
shared_preload_libraries = 'pg_stat_statements'  -- postgresql.conf

SELECT query, calls, total_exec_time, mean_exec_time,
       rows, shared_blks_hit, shared_blks_read
  FROM pg_stat_statements
 ORDER BY total_exec_time DESC
 LIMIT 20;

[활용]
  - 총 CPU 누적 시간 기준 정렬 → 최적화 우선순위
  - calls가 매우 큰데 mean이 작아도 누적이 클 수 있음 (N+1 의심)
  - shared_blks_hit vs read → buffer hit ratio
```

### 16.3 MySQL slow query log + performance_schema

```ini
# my.cnf
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 0.5    # 0.5초 이상

# performance_schema (more granular)
SELECT digest_text, count_star, sum_timer_wait/1e9 as total_ms,
       avg_timer_wait/1e9 as avg_ms
  FROM performance_schema.events_statements_summary_by_digest
 ORDER BY sum_timer_wait DESC LIMIT 20;
```

### 16.4 EXPLAIN — query plan 분석

```sql
EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = 42;

Index Scan using orders_customer_id_idx on orders  
  (cost=0.43..8.45 rows=1 width=80) (actual time=0.012..0.013 rows=1 loops=1)
  Index Cond: (customer_id = 42)
Planning Time: 0.085 ms
Execution Time: 0.025 ms

[확인 포인트]
  - Seq Scan → index 부재 (큰 테이블이면 위험)
  - rows 예측치 vs actual 차이 큼 → 통계 outdated (ANALYZE)
  - Buffers: hit / read → I/O 비중
  - Nested Loop on big tables → 대신 Hash Join 유도
```

### 16.5 jstack — Java thread 어디서 stuck

```bash
jstack <pid>

[찾을 패턴]
  "http-nio-8080-exec-12" #57 prio=5 ...
     java.net.SocketInputStream.socketRead0(Native Method)
     ...
     org.postgresql.core.PGStream.receive(PGStream.java:...)
     ...
     org.springframework.jdbc.core.JdbcTemplate.execute(...)
     
  → 여러 thread가 SocketInputStream.socketRead0 에서 BLOCKED/RUNNABLE
  → DB read 대기 중
  → DB 측 slow query 또는 lock 대기
```

### 16.6 tcpdump — wire 직접 보기

```bash
sudo tcpdump -i any -A -n port 5432 -w pg.pcap
# 잠시 후 Ctrl+C

# Wireshark에서 pg.pcap 열기
# 또는:
sudo tcpdump -i any -X port 5432

[확인]
  - 'Q' (0x51), 'P' (0x50), 'B' (0x42), 'E' (0x45) 메시지
  - 'T' (0x54 — RowDescription), 'D' (0x44 — DataRow)
  - SQL byte 직접 확인 (TLS 안 쓸 때)
  - TCP RST 누가 보냄
```

### 16.7 HikariCP metrics + Micrometer

```
hikaricp_connections                 — total
hikaricp_connections_active          — 사용 중
hikaricp_connections_idle            — pool 안 idle
hikaricp_connections_pending         — 대기 중인 thread
hikaricp_connections_max             — 한도
hikaricp_connections_acquire_seconds — getConnection 시간 분포
hikaricp_connections_usage_seconds   — 차용 → 반납 시간 분포
hikaricp_connections_creation_seconds — 새 conn 생성 시간

[Grafana dashboard 패턴]
  - pending이 0보다 크면 pool 부족
  - acquire P99 spike → pool 또는 DB 문제
  - usage P99 큰 값 → 트랜잭션이 너무 큼 (외부 API 의심)
  - active == max 지속 → pool 한도 도달
```

---

## 17. 트레이드오프 정리 — 6단

### 17.1 Statement vs PreparedStatement

| 측면 | Statement | PreparedStatement |
|---|---|---|
| Parse 비용 | 매번 | 1회 |
| SQL Injection | 위험 | 안전 |
| 동적 SQL | 유연 | 제한 |
| 운영 사용 | DDL, 매우 단순 query | 99% case |

### 17.2 fetchSize 선택

| 값 | 동작 | 권장 case |
|---|---|---|
| 0 (default) | 전부 로드 | 결과 작을 때 (~1000 row) |
| 100~1000 | cursor batch | 중간 크기 |
| 10000+ | cursor batch | 큰 결과 + 메모리 여유 |
| Integer.MIN_VALUE (MySQL) | streaming | 무제한 결과 |

### 17.3 Isolation Level 선택

| 레벨 | wire 비용 | 사용 case |
|---|---|---|
| READ COMMITTED | 낮음 | 대부분 OLTP (PG default) |
| REPEATABLE READ | 중 | 같은 transaction 안 일관 snapshot (MySQL default) |
| SERIALIZABLE | 높음 (lock or retry) | 정확한 회계 |

### 17.4 server-side vs client-side Prepared

| 측면 | Server-side | Client-side |
|---|---|---|
| plan cache | DB 측 | 없음 |
| 반복 호출 성능 | 우수 | 같음 |
| 첫 호출 성능 | 약간 느림 (Parse 메시지) | 빠름 |
| DB 메모리 | prepared stmt 누적 | 0 |
| Injection 방어 | 구조적 | escape 의존 |

---

## 18. 꼬리질문 트리 (3단)

### Q1 [가지 ①]. JDBC의 4 레이어 (DriverManager → Connection → Statement → ResultSet)를 한 줄씩 설명해주세요.

> DriverManager(legacy) 또는 DataSource(modern, 풀 관리)가 Connection을 얻고, Connection은 Statement/PreparedStatement를 만들고, Statement.execute*() 가 SQL을 wire에 보낸 후 결과를 ResultSet으로 받는다. ResultSet은 cursor (또는 in-memory)로 row를 한 줄씩 next()로 순회.

**🪝 Q1-1: DataSource는 인터페이스인데 실제 구현체가 뭐?**

> 현대 표준은 HikariCP의 HikariDataSource. Spring Boot 2+의 default. Tomcat JDBC Pool, DBCP2, C3P0가 legacy. Spring의 DriverManagerDataSource는 pool 없는 thin wrapper (테스트용).

**🪝 Q1-2: 왜 javax.sql과 java.sql 두 패키지로 나뉘었나?**

> 1997년 JDBC 1.0의 java.sql은 core API (DriverManager 직접 사용). 이후 J2EE 환경에서 pool/distributed transaction 같은 확장이 필요 → 호환성 깨지 않게 javax.sql로 추가. DataSource, XADataSource(2PC), RowSet 등이 여기.

### Q2 [가지 ②]. PostgreSQL Wire protocol의 Simple Query와 Extended Query 차이는?

> Simple Query는 'Q' 메시지 하나에 SQL string 전체. parameter 없음, 매번 parse + plan. Extended Query는 Parse + Bind + Execute + Sync 4~5개 메시지로 분리. SQL template과 parameter가 wire에서 분리되어 injection 안전. Parse 결과는 재사용 (plan cache) → 반복 호출에 빠름. PreparedStatement는 Extended 사용.

**🪝 Q2-1: Bind 메시지에는 어떤 정보가 들어있나?**

> portal_name, statement_name, parameter format codes (text 0 / binary 1), parameter values (각각 length + bytes), result format codes. parameter value는 raw byte로 들어가고 SQL parser를 절대 거치지 않음. 이게 injection 구조적 차단.

**🪝 Q2-2: Sync 메시지의 역할은?**

> Pipeline boundary. 서버가 여러 Parse/Bind/Execute를 받아도 응답을 Sync 만나야 ReadyForQuery 보냄. Sync 전에 error 나면 그 batch 전체 abort. 따라서 transaction 경계로도 사용. pipelined driver는 여러 명령을 묶어 한 번에 보낸 후 마지막에 Sync.

### Q3 [가지 ③]. PreparedStatement가 어떻게 SQL injection을 막나? 단순 escape와 무엇이 다른가?

> 단순 escape는 client에서 위험 문자 (', \, 등)를 변환하여 SQL string에 inline. corner case (multi-byte charset, \\' 등) 누락 가능. PreparedStatement (server-side)는 parameter를 SQL과 별도 wire 메시지로 보냄. 서버는 Parse 단계에서 SQL template만 보고 AST 만듦, Bind의 parameter byte는 절대 parse하지 않음. 구조적으로 injection 불가.

**🪝 Q3-1: client-side prepared는 위험한가?**

> MySQL Connector/J 기본이 client-side. driver가 escape + substitute하여 일반 Query 전송. 잘 만든 driver는 안전하지만 escape 함수에 버그가 있을 가능성. useServerPrepStmts=true로 server-side 권장.

**🪝 Q3-2: PostgreSQL JDBC의 prepareThreshold=5의 의미는?**

> 같은 PreparedStatement를 4번까지는 anonymous (매번 Parse), 5번째부터 named (server-side cache). 한 번만 호출되는 query를 cache하면 DB 메모리 누적 → 5번 이상 호출되어야 cache 가치. 0이면 항상 anonymous, 1이면 즉시 named.

### Q4 [가지 ④]. ResultSet은 lazy인가 eager인가? fetchSize 미설정하면 어떻게 되나?

> JDBC default fetchSize=0 = 전부 로드 (eager). 1억 row면 client heap에 전부 → OOM. PostgreSQL에서 lazy하게 cursor로 받으려면 (1) autoCommit=false, (2) setFetchSize(N), (3) TYPE_FORWARD_ONLY 3조건. MySQL은 setFetchSize(Integer.MIN_VALUE)로 streaming 또는 useCursorFetch=true.

**🪝 Q4-1: autoCommit=false가 왜 cursor에 필수인가?**

> PostgreSQL의 portal (cursor)은 transaction에 묶임. autoCommit=true면 매 SQL이 즉시 COMMIT → portal 사라짐 → 다음 batch 불가. transaction 안에 있어야 portal 유지.

**🪝 Q4-2: MySQL Integer.MIN_VALUE streaming의 제약은?**

> Server는 그냥 모든 row를 socket에 push. Driver는 받는 즉시 user에게 전달 (buffer 안 함). 단점: ResultSet 완전 소진 전에 같은 connection에서 다른 query 불가 ("Streaming result set is still active"). 해결: 처리 빨리 끝내거나 별도 connection 사용.

### Q5 [가지 ⑤]. Spring @Transactional의 두 query가 어떻게 같은 transaction인 줄 아나?

> Spring TransactionInterceptor가 메서드 진입 시 DataSource.getConnection() 호출, conn.setAutoCommit(false), 그 conn을 TransactionSynchronizationManager의 ThreadLocal에 등록. 메서드 안의 JdbcTemplate/EntityManager가 DataSource.getConnection() 호출하면 Spring proxy가 가로채어 ThreadLocal의 conn 반환. → 같은 conn = 같은 wire transaction.

**🪝 Q5-1: 한 transaction이 두 connection을 쓸 수 있나?**

> 일반적으로 불가. transaction state (uncommitted, lock, snapshot)는 server 측에서 connection에 묶임. 다른 connection은 그 변경 못 봄 (isolation). 예외: 2PC (Distributed Transaction)에서 여러 DB connection을 한 logical tx로 묶지만, 각 DB 측에선 별개 tx.

**🪝 Q5-2: isolation level을 wire 측에 어떻게 전달하나?**

> conn.setTransactionIsolation(REPEATABLE_READ) → driver가 wire에 "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" 보냄. 또는 BEGIN ISOLATION LEVEL ... 한 줄로. HikariCP는 connection 반납 시 default로 reset (resetIsolationOnReturn).

### Q6 [가지 ⑥, Killer]. 운영 중 "DB connection이 hang 걸린다" 라는 신고가 들어왔습니다. 어떻게 진단하시겠어요?

> 1. **HikariCP 메트릭 확인**: hikaricp_connections_pending (대기 thread 수), active vs max. active==max + pending>0 면 pool 고갈.
> 2. **DB 측 확인**:
>    - `SELECT count(*) FROM pg_stat_activity` vs max_connections.
>    - `SELECT pid, state, query, query_start FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start ASC` → long-running query 또는 idle in transaction 발견.
>    - `pg_locks` JOIN `pg_stat_activity` → lock 대기 chain.
> 3. **jstack으로 app thread 확인**:
>    - 다수 thread가 `Socket.read` (DB 응답 대기)? → DB 측 slow.
>    - HikariCP 내부에서 `Park` (pool 대기)? → pool 부족.
> 4. **wire dump**: tcpdump port 5432로 패킷 흐름 확인. RST 자주 발생하면 firewall/NAT timeout 의심.
> 5. **장애 격리**: app instance 분리 운영, 한 instance만 영향이면 instance 측. 모두 영향이면 DB 측.
> 6. **해결**:
>    - pool 고갈 → 일시 pool size 증가, 근본은 N+1/long tx 제거.
>    - DB slow → 문제 query EXPLAIN, index 추가.
>    - idle in transaction → idle_in_transaction_session_timeout 설정.
>    - firewall idle → HikariCP keepaliveTime + maxLifetime 조정.

### Q7 [가지 ⑦]. Spring 앱에서 한글이 DB에 '?'로 저장됩니다. 어디부터 봐야 하나?

> charset chain 4단계 각각 확인:
> 1. **HTTP request**: Content-Type charset, percent-encoding의 디코딩 charset. → 01-url-input-and-serialization.md.
> 2. **Java String**: log로 byte sequence 출력. "가"가 EAB080 (UTF-8) 인지 확인.
> 3. **JDBC wire**: tcpdump 또는 PG client_encoding 설정. MySQL은 jdbc URL의 useUnicode + characterEncoding.
> 4. **DB column**: PG의 server_encoding, MySQL의 utf8 vs utf8mb4 (이모지면 mb4 필수). `SELECT octet_length(name), length(name)` 로 byte 수 vs 문자 수 비교.

**🪝 Q7-1: MySQL의 utf8과 utf8mb4 차이는?**

> MySQL의 "utf8" = utf8mb3 (3 byte). 4 byte UTF-8 sequence (이모지, 일부 한자 확장)는 저장 불가. utf8mb4가 진짜 UTF-8. MySQL 8 default가 utf8mb4. 옛 DB는 utf8mb3 → 이모지 INSERT 실패하거나 truncation.

### Q8 [Killer]. Spring 앱에서 동시 1000 req/sec, 각 request가 transaction 안에서 DB 5번 호출, DB 한 query 평균 1ms. 적정 HikariCP pool size는?

> Little's Law: concurrency = throughput × latency.
> 한 request의 connection 사용 시간 = 5 query × 1ms = 5ms.
> 1000 req/sec × 5ms = 5 동시 connection 필요 (이론).
> 실제는 jitter, GC, network 변동 대비 2~3배 안전 마진 → 10~15.
> HikariCP 공식 권장은 (core_count × 2) + spindle_count 가 출발점이지만, 워크로드 측정이 진리.

**🪝 Q8-1: pool size를 무한정 늘리면 좋나?**

> 아니. DB max_connections 한도. 그리고 DB 측 context switch 비용 증가 (PG는 process per connection). 너무 많으면 처리량 오히려 감소. PgBouncer 같은 connection multiplexer로 app 측 pool은 작게, DB 측 client 수는 더 작게.

**🪝 Q8-2: connection이 idle 상태로 너무 많으면?**

> DB 측 메모리 점유 (PG는 connection 당 약 10MB). idle connection이 100개면 1GB. HikariCP의 idleTimeout으로 줄임 (default 10분). 단, minimumIdle은 burst 대비 유지.

---

## 19. 학습 체크리스트

- [ ] 0장 백지 마인드맵을 1분 이내로 그릴 수 있다 (6가지 + 키워드 3개)
- [ ] 가지 ①: JDBC 4계층을 화이트보드에 그릴 수 있다
- [ ] 가지 ①: JDBC Driver Type 1~4 차이와 왜 Type 4가 표준이 되었는지 설명한다
- [ ] 가지 ②: Connection 생성 5단계 (TCP/TLS/Startup/Auth/Ready) 를 인용한다
- [ ] 가지 ②: PostgreSQL wire의 메시지 framing (type + length + payload) 을 그린다
- [ ] 가지 ②: Simple vs Extended 차이 + Parse/Bind/Execute/Sync 메시지 흐름
- [ ] 가지 ③: PreparedStatement가 SQL injection을 어떻게 구조적으로 차단하는지 설명
- [ ] 가지 ③: server-side vs client-side prepared, prepareThreshold의 의미
- [ ] 가지 ③: Batching이 왜 효과적이고 rewriteBatchedStatements가 무엇 하는지
- [ ] 가지 ④: fetchSize 미설정의 OOM 함정 + PG의 cursor + autoCommit=false 3조건
- [ ] 가지 ④: MySQL Integer.MIN_VALUE streaming의 제약
- [ ] 가지 ⑤: Spring @Transactional이 ThreadLocal로 Connection 공유하는 메커니즘
- [ ] 가지 ⑤: BEGIN/COMMIT/SET TRANSACTION ISOLATION의 wire 메시지
- [ ] 가지 ⑤: Savepoint + 2PC 개념
- [ ] 가지 ⑥: Connection state leak 시나리오 (uncommitted tx, isolation, session var, advisory lock)
- [ ] 가지 ⑥: HikariCP의 resetOnReturn으로 무엇이 reset되고 무엇은 안 되나
- [ ] 가지 ⑦: timeout 4계층 + 어느 것이 먼저 발동하는지
- [ ] 가지 ⑦: Connection.isValid vs connectionTestQuery 차이
- [ ] 가지 ⑧: DB가 query 받은 후 Parser → Optimizer → Executor → Storage 흐름
- [ ] 가지 ⑨: Hibernate의 1st level cache, flush 시점, N+1 problem 해결
- [ ] 운영 7대 시나리오 진단 + 해결 전략 (DB CPU 정상인데 slow / connection refused / connection reset / deadlock / idle in transaction / ResultSet OOM / prepared cache leak)
- [ ] 측정 도구 7개를 능숙히 사용 (pg_stat_activity / pg_stat_statements / slow query log / EXPLAIN ANALYZE / jstack / tcpdump / HikariCP metrics)

---

## 20. 다음 학습

이 챕터를 마쳤으면 다음으로:

| 다음 | 왜 |
|---|---|
| `network-request-lifecycle/07-connection-pools-master.md` | HikariCP 내부 (ConcurrentBag, housekeeper) 더 깊이 |
| `network-request-lifecycle/01-url-input-and-serialization.md` | character encoding chain 의 시작점 |
| `jvm/05-threading/` | HikariCP의 lock-free 알고리즘 = JMM happens-before + CAS 기반 |
| `jvm/04-gc/` | ResultSet의 큰 byte[] 가 GC에 미치는 영향 |
| `java-deep-dive/04-timeouts-connection-vs-read.md` | timeout 4계층의 Java API 측 정리 |

---

> 이 가이드는 학습 진행에 따라 보완된다. 운영 사고 사례, 새 driver 옵션, 새 wire protocol 확장 (PG 17 등) 발견 시 업데이트.
