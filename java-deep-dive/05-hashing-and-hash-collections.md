# 05. Hashing & Hash Collections

> "HashMap = put/get 쓰는 거"는 입문자. 시니어는 Object.hashCode 5계약, JDK 8의 `(h ^ h>>>16) & (n-1)` spread, treeify 8 임계의 Poisson 근거, JDK 7→8 ConcurrentHashMap 재설계 이유, 2011 28C3 hash flooding이 왜 모든 언어 표준 라이브러리를 흔들었는지를 본다.
>
> 이 문서는 옵션값/hex 외우기 대신 본질·왜·연결·운영 진단만 다룬다.

---

## 0. 목차

1. Hash 함수 4성질
2. HashTable 자료구조 (chaining vs open addressing, load factor 0.75)
3. Java가 hash를 광범위하게 쓰는 이유
4. Object.hashCode/equals 5계약
5. HashMap (JDK 8) 핵심
6. ConcurrentHashMap (JDK 8) 핵심
7. String hashCode와 31
8. 외부 생태계 (분산/캐시/보안/확률자료구조/DB)
9. Production 사고 패턴
10. 친척 컬렉션
11. 운영 best practice
12. 메모리 관점
13. 진단 도구
14. HashMap 진화 타임라인
15. 꼬리질문
16. 더 깊이

---

## 1. Hash 함수 4성질

```
[Hash Function: 임의 길이 → 고정 길이]

   "hello"                                   3.6 × 10^9
   "안녕"           h(x)                      1.2 × 10^9
   Order{id=7,...}  ─────▶                   8.7 × 10^9
                                             ↑
                                          32-bit int (Java hashCode)
                                          또는 128/256-bit (SHA, MurmurHash)
```

| 성질 | 의미 | 깨지면 |
|---|---|---|
| **deterministic** | 같은 입력 → 항상 같은 출력 | Map.get이 영원히 못 찾음, partition이 흩어짐 |
| **uniform** | 출력이 출력 공간에 균등 분포 | chain 비대칭 → P50 O(1)인데 P99 O(N), "특정 user만 느림" |
| **avalanche** | 입력 1비트 변화 → 출력 절반 변화 | 비슷한 key가 같은 bucket으로 cluster |
| **one-way** | 출력에서 입력 역산 불가 | crypto만 보장. 일반 hashCode는 충돌 생성 쉬움 (→ flooding) |

비둘기집 원리: `|X| = ∞, |Y| = 2^32` → 충돌은 본질적으로 불가피. "충돌을 없앤다"가 아니라 "충돌해도 잘 동작한다"가 목표 — 그래서 chain/probe/tree 자료구조가 붙는다.

| 용도 | 필요한 성질 | 함수 |
|---|---|---|
| HashMap, cache key | det+uniform+avalanche | non-crypto (MurmurHash, xxHash) |
| Password | + one-way + slow + salt | bcrypt, scrypt, argon2 |
| 무결성 | + 충돌 저항 | SHA-256, BLAKE3 |
| Bloom filter | det+uniform 여러 개 | non-crypto 다수 |

Java HashMap이 non-crypto를 쓰는 이유: crypto는 매 op마다 수십~수백 cycle 비용. 대신 hash flooding에 약함.

---

## 2. HashTable 자료구조

### 2.1 충돌 해결 2대 패턴

| | Separate Chaining (Java 표준) | Open Addressing (IdentityHashMap만) |
|---|---|---|
| 충돌 처리 | bucket마다 linked list/tree | 다른 slot probe (linear/quadratic/double) |
| delete | 쉬움 | 어려움 (tombstone) |
| load factor | > 1.0도 가능 | < 0.7~0.8 한계 |
| cache locality | 나쁨 (Node 산재) | 좋음 (배열 한 덩어리) |
| 메모리 | Node 객체 alloc 비용 | 작음 |
| 단점 | GC 압박, cache miss | clustering |

fastutil/Eclipse Collections primitive map은 open addressing (boxing 없으니 locality 이점 큼).

### 2.2 Load Factor 0.75

`α = size / capacity`, 평균 chain 길이 = α (uniform 가정), get/put 평균 = O(1+α).

Knuth *TAOCP Vol.3* 분석 기반의 시간·공간 sweet spot. 0.5는 메모리 낭비, 1.0은 충돌 폭증. 실전 함의: N entry → table 약 N×1.33 메모리.

**Amortized O(1)**: resize는 size가 2배 될 때마다 1번 발생, 총 비용 = N + 2N = O(N), op당 평균 O(1). 단일 op은 O(N) spike — P99 latency에 영향. 대비책: `new HashMap<>(expected / 0.75 + 1)` 초기 용량 지정.

---

## 3. Java가 hash를 광범위하게 쓰는 이유

### 3.1 사용자 API 차원

- `get/put` O(1) (평균) — TreeMap O(logN)보다 압도적.
- key가 Comparable 필요 없음 — hashCode/equals만 있으면 OK.
- 표준 라이브러리 default: `Map.of`, `Collectors.toMap`, `Set.of`, `groupingBy`, `HashSet` 전부 hash 기반.

### 3.2 JVM 내부 차원

| JDK/JVM 내부 | hash 용도 |
|---|---|
| **StringTable** | String literal/intern dedup. JDK 7부터 Heap. `-XX:StringTableSize` |
| **ClassFile constant pool** | UTF-8/NameAndType lookup 가속 |
| **ClassLoader cache** | `loadClass(name)` 중복 회피 (ClassLoader leak의 근원) |
| **JIT inline cache** | megamorphic call site의 type→target 매핑 |
| **Pattern compile cache** | regex NFA→DFA 변환 결과 reuse |
| **Reflection cache** | `getMethod(name, ...)` lookup |

→ JVM 자체가 거대한 hash 시스템. ClassLoader leak/intern pool overflow 진단은 이걸 알아야 가능.

### 3.3 운영 환경 stack

```
사용자 코드 → HashMap/CHM (in-process)
           → Caffeine (TinyLFU + hash)
           → Redis (CRC16 slot, hash type)
           → Kafka (murmur2(key) % partitions)
           → LB/CDN (consistent hashing)
           → DB (hash partition/join/index)
```

위에도 hash, 아래에도 hash, 옆에도 hash. 시니어는 stack 전체를 본다.

---

## 4. Object.hashCode / equals 5계약

```
[HashMap.get(key)의 흐름]
   key.hashCode()
        │
   spread + & (n-1)
        │
        ▼
   table[i] chain
        │
   for each node: if (hash == && (k == key || key.equals(k))) return value
                                          ↑
                                   equals가 일치 판정
```

→ hashCode = "어느 bucket으로 모일지", equals = "그 안에서 같은지" — 두 역할이 다르다. equals만 override하고 hashCode 미구현하면 `set.contains(new Order("A"))`가 false. IDE의 "Generate hashCode/equals together" 권고가 이래서 있다.


| # | 계약 | 의미 |
|---|---|---|
| 1 | reflexive | `x.equals(x) == true` |
| 2 | symmetric | `x.equals(y) ⇔ y.equals(x)` |
| 3 | transitive | `x.equals(y) ∧ y.equals(z) ⇒ x.equals(z)` |
| 4 | consistent | 변경 없는 한 결과 동일 (immutable key) |
| 5 | **equals → hashCode 동일** | `x.equals(y) ⇒ x.hashCode() == y.hashCode()` (역은 X — 충돌 허용) |

**왜 비대칭?** HashMap이 key 찾는 흐름: `bucket = hashCode & (n-1)` → bucket chain에서 equals 매치. equals true인데 hashCode 다르면 다른 bucket이라 영원히 못 찾음. hashCode 같고 equals false는 같은 bucket의 다른 entry로 분류 OK. **hashCode = 좌표, equals = 일치 판정.**

**위반 사례**:
- equals만 override → `set.contains(new Order("A"))` false (identity hash 다름)
- mutable field 포함한 hashCode → put 후 mutate → 다른 bucket 봐서 leak
- 권장: `@EqualsAndHashCode(of = {"id"})` 불변 식별자만, key는 immutable

---

## 5. HashMap (JDK 8) 핵심

### 5.1 한 단락 요약

table = `Node[]`, capacity = power of 2, load factor 0.75.
- **bucket index** = `(h ^ (h >>> 16)) & (n-1)` — upper 16 bit를 lower로 XOR mix 후 lower n bit만 사용.
- **collision** → linked list, 길이 ≥ 8 AND table ≥ 64 → Red-Black Tree (TREEIFY). 길이 ≤ 6 → UNTREEIFY (hysteresis로 oscillation 방지).
- **resize**: capacity 2배. 각 entry는 `e.hash & oldCap` 한 비트로 low/high 그룹 분리 (재해시 zero).

### 5.2 다이어그램 — putVal + treeify + resize 한 그림

```
            key.hashCode()
                  │
        spread:  h ^ (h >>> 16)
                  │
        index = h & (n-1)
                  │
                  ▼
   ┌─────────────────────────────┐
   │  table[i]                   │
   └─────────────────────────────┘
         │           │            │
      empty       linked          tree
         │           │            │
       CAS-like    chain          RB-tree
       set         put           putTreeVal
                     │
                  binCount++
                     │
            binCount ≥ 8 AND n ≥ 64?
                     │
                  treeifyBin
                  (list → RB-tree)
                     │
                     ▼
              size > threshold?
                     │
                  resize() — n → 2n
                     │
              for each old bucket:
                  group by (e.hash & oldCap)
                  == 0  → newTab[i]
                  != 0  → newTab[i + oldCap]
              (한 비트 AND로 분리, 재해시 X)
```

### 5.3 왜 그렇게 설계했나

- **spread function**: capacity가 작으면 lower n bit만 사용 → upper bit 무시. XOR mix로 좋은 hashCode를 작은 table에서도 살림.
- **TREEIFY=8**: uniform hash의 chain 길이 ~ Poisson(λ=0.5). JDK 소스 javadoc 수치: 길이 0=60.6%, 1=30.3%, 2=7.6%, 3=1.3%, ..., 8 ≈ 백만분의 3. 8에 도달 = 분포 비정상 (adversarial 또는 poor hashCode). 그때만 tree로 worst case O(log N).
- **MIN_TREEIFY_CAPACITY=64**: 작은 table의 chain 8은 통계 변동일 뿐, resize가 우선.
- **high-bit split**: power of 2 capacity의 핵심 트릭. 새 bit 1개만 검사하면 됨 → 재해시 호출 zero.
- **power of 2 capacity**: `hash % n` 대신 `hash & (n-1)` 비트 AND (수십 배 빠름) + resize 분리 트릭 가능.

---

## 6. ConcurrentHashMap (JDK 8)

```
[JDK 7: segment lock]              [JDK 8: per-bucket]
┌─────────────┐                    table[]
│ Segment 0   │ ← lock 0           ┌────┐
│ (mini-Map)  │                    │ 0  │ ← empty면 CAS set
├─────────────┤                    ├────┤
│ Segment 1   │ ← lock 1           │ 1  │ ← non-empty면 synchronized(first)
├─────────────┤                    ├────┤
│ ...         │                    │ ...│
└─────────────┘                    └────┘
동시성 = 16                         동시성 = N (bucket 수)
별도 lock 객체                      객체 헤더 monitor 활용
resize = segment 단위              resize = helpTransfer 협력
```

### 6.1 한 단락 요약

JDK 7 segment lock (16 segment × mini-HashMap, 동시성 한계 16) → JDK 8에서 단일 `Node[]` table + **per-bucket lock**으로 재설계.

**put 흐름**:
1. spread hash 계산
2. bucket empty → **CAS로 set** (성공 시 lock zero, lock-free)
3. non-empty → **synchronized(firstNode)** — 객체 헤더 monitor 활용 (별도 lock 객체 없음)
4. resize 중이면 **helpTransfer** — 다른 thread가 도와줌 (multi-thread cooperative)
5. size 증가는 **counterCells** (LongAdder 패턴 striped counter)

lock 단위 = bucket 1개. 동시성 한계 = bucket 수 (수천~수만). segment보다 작고 빠르고 scalable.

### 6.2 null 금지 — Doug Lea의 답

`get(k)`가 null을 돌려줄 때 의미 2개: (1) key 없음, (2) value가 null. 단일 thread면 `containsKey + get` 2-step으로 구분 가능. concurrent에선 두 호출 사이에 다른 thread가 put할 수 있어 구분 자체가 race. 그래서 **key/value 모두 null 금지**로 명확화. HashMap은 단일 thread 가정이라 null 허용.

### 6.3 weak consistency

- `size()` = `sumCount()` — counterCells 합, 다른 thread가 add 중이면 stale. 통계용만.
- iterator = weakly consistent — `ConcurrentModificationException` 안 던짐, 도중 추가/삭제는 보일 수도 안 보일 수도. 정확한 snapshot은 `new HashMap<>(chm)`.
- `computeIfAbsent` 안에서 같은 map 재귀 update → JDK 8 deadlock-like, JDK 9+ `IllegalStateException`.

---

## 7. String hashCode와 31

```java
h = 31 * h + c   // for each char
// 수식: h(s) = s[0]·31^(n-1) + s[1]·31^(n-2) + ... + s[n-1]
```

**왜 31?** odd prime (lower bit 0 패턴 방지 + 인수분해 어려움) + `31*h == (h<<5) - h` shift 최적화 (1990s CPU 곱셈 비용 시대 의미 있었음) + Joshua Bloch 실험에서 분포 좋음. 37/41도 후보, 31이 관습.

**lazy caching**: `String` 내부 `int hash` 필드, default 0, 첫 호출에 계산 후 저장. JDK 12부터 `boolean hashIsZero`로 empty string 매번 재계산 함정 해결 (이전엔 `""`이 cache 안 작동).

**충돌은 수학적으로 쉽다**: `"Aa".hashCode() == "BB".hashCode()` (`65*31+97 == 66*31+66 == 2112`), `"AaAa" == "AaBB" == "BBAa" == "BBBB"`. → hash flooding 공격의 기반. Compact String (JDK 9+, byte[]+coder)도 hash 결과는 동일 (호환성).

---

## 8. 외부 생태계 hash 활용

```
[Consistent Hashing — 분산 시스템 핵심]
            hash space (ring, 0 ~ 2^32)
                  ┌─────────┐
            Node-A│         │Node-B
             (10) │         │(80)
                  │         │
              ●k1 │         │● k2
              (15)│         │(85)
              "다음 시계방향 노드에 저장"
                  │         │
            Node-D│         │Node-C
             (180)│         │(120)
                  └─────────┘
            노드 추가/제거 시 영향 = 1/N
            virtual node로 균형 개선
```



| 영역 | 함수/기법 | 용도 |
|---|---|---|
| **Consistent Hashing** | ring + virtual node | Cassandra (Murmur3), DynamoDB, Memcached libketama, Redis Cluster (변형). 노드 추가/제거 영향 = 1/N |
| **Rendezvous (HRW)** | argmax over `hash(k, n)` | CDN, distributed cache. ring 없이 동등 효과 |
| **Maglev** | precomputed lookup table | Google L4 LB. 균형 더 좋음 |
| **Kafka** | `murmur2(key) % partitions` | partition 추가 시 순서 보장 깨짐 — 초기 설계 신중 |
| **Redis Cluster** | `CRC16(key) & 16383` (16384 slot) | hash tag `{user}:profile`로 같은 slot 묶기 |
| **HTTP ETag / CDN** | content hash (MD5/SHA prefix) | `If-None-Match` 304 처리 |
| **bcrypt/scrypt/argon2** | slow + salt + work factor | password 저장. SHA로 저장 X (GPU rainbow table) |
| **HMAC** | `HMAC-SHA256(payload, secret)` | JWT signature (HS256). secret 모르면 위조 불가 |
| **Merkle Tree** | leaf→root hash 체인 | Git commit, blockchain, Docker layer digest |
| **Bloom filter** | k개 hash, bit array | "있다" 추측, "없다" 보장. Cassandra row filter, CDN |
| **HyperLogLog** | bucket별 leading-zero | unique count 근사 (±2%). BigQuery `APPROX_COUNT_DISTINCT`, Redis `PFCOUNT` |
| **Count-Min Sketch** | 다수 hash + min | frequency 근사. Caffeine TinyLFU |
| **DB hash join** | small side build, large side probe | equi-join O(|A|+|B|) vs nested loop O(|A|×|B|) |
| **DB hash partition** | `hash(user_id) % N` | 균등 분배. archival엔 불리 |

**보안 3구분 (혼동 단골)**:
- hash = 무결성, key 없음, 누구나 같은 결과 (SHA-256)
- MAC = 인증+무결성, key 필요 (HMAC)
- KDF = password 저장, slow + salt + work (bcrypt)

---

## 9. Production 사고 패턴

### 9.1 Hash Flooding / Collision DoS

```
[정상 분포]                          [공격받은 분포]
table                                table
┌────┐ A                             ┌────┐ A → B → C → D → E → ...
│ 0  │                               │ 0  │      (모두 hashCode 충돌)
├────┤ B                             ├────┤
│ 1  │                               │ 1  │ (empty)
└────┘ ...                           └────┘ ...
평균 chain = 1                       평균 chain = N
put N개 = O(N)                       put N개 = O(N²)
```

**공격**: String multiplicative hash 충돌은 수학적으로 쉬움 (`"Aa"=="BB"`). 1 HTTP request에 collision form param 10K → `HashMap<String,String[]>`에 같은 bucket으로 10K chain → put N개 비용 O(N²) = 10^8 → CPU 100%.

**역사**: 2003 Crosby/Wallach 논문 → 2011 28C3 (Klink/Wälde)에서 PHP/Python/Ruby/Java/ASP.NET 모두 영향 공개. 대응:
- PHP `max_input_vars`, Python 3.3 per-process random seed
- Java 7u40 alternative hashing (호환성 문제로 부분 해제)
- Java 8 tree 변환 (worst case O(log N)) — 사실상의 정답
- Java 9 `Map.of` salted hashing — process마다 다른 salt로 완전 방어 (immutable만)

**완전 방어 아님**: 사용자 정의 key가 poor hashCode + Comparable 미구현이면 tree에서도 비교 불가 → list 처리 → O(N) 잔존.

**실제 사고**:
- **Tomcat form param** — `Map<String, String[]>`에 form param 저장. Java 8 이전엔 `maxParameterCount` 제한 도입으로 대응.
- **JSON parser** — Jackson/Gson이 JSON object를 `LinkedHashMap`에 저장. nested JSON collision으로 동일 패턴.
- **HTTP header 파싱** — case-insensitive map에 lowercase collision.

**운영 시그널**: 특정 endpoint CPU 100%, thread dump에서 다수 thread가 `HashMap.putVal/getNode` 머무름, input size 대비 비선형 처리 시간. 진단: async-profiler `HashMap.putVal` top → Tomcat `maxParameterCount` 설정, WAF에서 큰 form 차단.

### 9.2 Mutable Key 함정

```java
class K { String name; hashCode() { return name.hashCode(); } }
K k = new K("A"); set.add(k);
k.name = "B";        // hash 변경
set.contains(k);     // false! 새 hash로 다른 bucket
set.remove(k);       // false! → 영원히 leak
```

JPA에서 ID null인 entity를 set에 넣고 ID 할당 — 동일 함정. **권장**: key는 immutable, `@EqualsAndHashCode(of = {"id"})` 불변 식별자만.

### 9.3 JDK 7 HashMap 동시 resize cycle

```
JDK 7 transfer (head insertion):
   old: A → B → C → null
   thread1이 A를 새 bucket head로 옮기는 도중
   thread2도 같은 작업 진행 → B.next = A 와 A.next = B 동시 발생
   결과: A ⇄ B 영구 cycle
   다음 get → 영원히 순회 → CPU 100%
```

JDK 7 `transfer`가 head insertion → 두 thread 동시 resize → list cyclic → 다음 get 영원 순회 → CPU 100% 무한 루프. 2014 LinkedIn engineering blog 등 다수 실제 사고. JDK 8에서 tail insertion + high-bit split으로 cycle 사라짐. 다만 size 정합성은 여전히 깨짐 (size++ atomic 아님) — **HashMap은 단 한 줄도 concurrent write 안 됨**. 동시성 필요하면 무조건 ConcurrentHashMap.

### 9.4 보조 함정

- **autobox `HashMap<Long, V>`**: `long → Long.valueOf` boxing 비용 + small Long 분포 (자기 자신과 같은 hash, lower bit 패턴 노출) + Young gen GC 압박. JFR allocation에서 `java.lang.Long` top. 대안: fastutil `Long2ObjectOpenHashMap`, Eclipse Collections `LongObjectHashMap`, Koloboke.
- **비싼 hashCode**: `BigInteger.hashCode`는 O(digits) 매번 계산, 캐시 없음. List 100개 item 포함한 hashCode도 동일 패턴 (`Objects.hash(items)`로 매번 100개 element hash). 대안: id만 사용, Lombok `cacheStrategy = LAZY`.
- **`computeIfAbsent` 안에서 같은 key 재귀**: JDK 8 deadlock-like, JDK 9+ `IllegalStateException`. compute 함수는 짧고 self-contained 하게.

### 9.5 운영 시나리오 매핑

| 증상 | 의심 | 진단 | 해결 |
|---|---|---|---|
| 특정 user만 응답 느림 | hash cluster | 그 key set hashCode 분포 측정 | key 생성 방식 변경 |
| Redis Cluster 한 node만 CPU 100% | hash tag로 hot slot | `CLUSTER COUNTKEYSINSLOT`, `--hotkeys` | hash tag 세분화 |
| Heap dump CHM 1위 | unbounded cache | MAT incoming reference | Caffeine 교체 (size+expire) |
| form param CPU 폭주 | hash flooding | async-profiler `HashMap.putVal` top | `maxParameterCount`, WAF |
| Kafka 특정 partition lag 누적 | producer key 비대칭 | partition별 message 분포 | producer key 재설계 |

---

## 10. 친척 컬렉션

| 컬렉션 | 자료구조 | 특징 | 사용처 |
|---|---|---|---|
| **LinkedHashMap** | HashMap + doubly-linked list | insertion/access order. `accessOrder=true` + `removeEldestEntry` → LRU |
| **WeakHashMap** | WeakReference key | key strong ref 사라지면 GC가 수거, lazy cleanup. `ClassValue` 내부. cycle ref면 누수 |
| **IdentityHashMap** | open addressing | `==` 비교, `System.identityHashCode()`. 객체 그래프 visited set, cycle 감지 |
| **EnumMap** | `Object[]` index by ordinal | hash 호출 zero, 가장 빠른 Map. enum key면 무조건 이거 |
| **ConcurrentSkipListMap** | probabilistic skip list (CAS) | sorted + concurrent, hash 아님. ordered concurrent 필요 시 |
| **HashSet/LinkedHashSet** | HashMap with dummy value | set 표준 |

**결정 트리**: enum→EnumMap / sorted→TreeMap or CSLM / insertion order→LinkedHashMap / weak→WeakHashMap / identity→IdentityHashMap / concurrent→CHM / 그 외→HashMap.

---

## 11. 운영 best practice

1. **Map key는 immutable** — String/Long/UUID/java.time 또는 final field만 (`@EqualsAndHashCode(of={"id"})`). mutable key는 leak의 1번 원인.
2. **큰 Map은 initial capacity 지정** — `new HashMap<>((int)(expected/0.75)+1)`로 resize spike 회피 (P99 latency 보호).
3. **동시성에는 ConcurrentHashMap** — `Collections.synchronizedMap`은 throughput 한계, HashMap은 단 한 줄도 concurrent write 안 됨.
4. **외부 input을 직접 key로 쓰지 말 것** — hash flooding 방어. sanitize/canonicalize 후 사용. JDK 9+ `Map.of`는 salted hashing.
5. **Cache는 반드시 size limit + expire** — unbounded는 시한폭탄. Caffeine 기본 (Guava Cache는 deprecated 권고). hit rate < 50% 재검토.
6. **partition key는 분포 먼저 측정** — Kafka/Redis slot/DB partition. consistent hashing 사용 시 virtual node로 균형.
7. **password는 무조건 bcrypt/scrypt/argon2** — SHA 저장 X (GPU rainbow table 즉시 깨짐). JWT secret은 강력하고 회전.

---

## 12. 메모리 관점 — HashMap retained size

```
HashMap with N entries:
  table[]    = (N/0.75) reference slots
  Node × N   = 32 bytes each (hash + key ref + value ref + next ref + header)
  + key, value 자체

대략:
  HashMap<Long, String> 100만 entry
  = 1M × (32 + ~24 Long + ~50 String)  ≈  100 MB
```

운영 시 heap dump에서 HashMap이 retained 1위인 경우 = 보통 cache 누수, cleanup 없는 unbounded map. Caffeine(`maximumSize` + `expireAfter*`) 또는 WeakReference로 교체.

---

## 13. 진단 도구

| 도구 | 명령/용도 |
|---|---|
| **jcmd GC.class_histogram** | `HashMap$Node` 비정상 많으면 map 누수 |
| **Eclipse MAT** | heap dump → Dominator Tree → CHM retained 1위 → incoming reference 추적 |
| **async-profiler** | CPU(`HashMap.hash/putVal`), alloc(`HashMap$Node`/`Long` boxing), wall |
| **Caffeine recordStats** | hitRate < 50% 재검토, evictionCount 폭주 = working set 초과 |
| **Redis** | `CLUSTER COUNTKEYSINSLOT` slot 분포, `--hotkeys` hot key |
| **분포 직접 측정** | `keys.stream().collect(groupingBy(k -> (k.hashCode() ^ k.hashCode()>>>16) & 15, counting()))` |

---

## 14. HashMap 진화 한 줄 타임라인

| JDK | 변화 | 트리거 |
|---|---|---|
| 1.0 (1996) | Hashtable + Vector (synchronized) | 일찍 도입된 동기화 컬렉션 |
| 1.2 (1998) | HashMap, HashSet, TreeMap | Collections Framework |
| 1.4 (2002) | LinkedHashMap, IdentityHashMap | order, identity 요구 |
| 5 (2004) | ConcurrentHashMap (segment lock) | 멀티코어 시대, Hashtable global lock 병목 |
| 7 (2011) | String hashCode 캐싱, alternative hashing | 28C3 hash flooding 직격 |
| 8 (2014) | **chain → tree (TREEIFY 8)**, **CHM 재설계 (per-bucket)**, atomic compute API | hash flooding 완화 + segment 한계 + 동시성 API |
| 9 (2017) | `Map.of/Set.of` immutable + salted hashing | hash flooding 완전 방어 (immutable만) |
| 12 (2019) | String `hashIsZero` 추가 | empty string cache 함정 |
| 21 (2023) | Sequenced Collections interface | minor |

JDK 7→8 CHM 재설계의 핵심: lock의 granularity를 segment(16개)에서 bucket(N개)으로 더 잘게. segment의 메모리 오버헤드(16 lock 객체) 제거 + 동시성 한계 N으로 확대 + multi-thread cooperative resize.

---

## 15. 꼬리질문

**Q1. `equals → hashCode 동일`이 왜 비대칭(역은 X)인가?**
> HashMap이 hashCode로 bucket 찾고 equals로 매치. equals true인데 hashCode 다르면 다른 bucket이라 못 찾음. hashCode 같고 equals false는 같은 bucket의 다른 entry로 OK. hashCode = 좌표, equals = 일치 판정 — 역할 분담.

**Q2. JDK 8 spread function `(h ^ h>>>16) & (n-1)`가 작은 capacity에서 왜 중요한가?**
> capacity = 2^4 = 16이면 mask가 lower 4 bit만 사용. 좋은 hashCode라도 upper bit가 lower로 안 흘러가면 충돌. XOR mix로 upper 16 bit를 lower 16 bit에 섞어 작은 table에서도 영향력 확보. 큰 capacity면 자연히 더 많은 bit를 보므로 spread의 효과는 작은 table 보호용.

**Q3. ConcurrentHashMap이 null을 금지하는 이유?**
> Doug Lea의 답: `get(k)` 결과 null의 의미가 (key 없음) vs (value null) 2가지. 단일 thread는 `containsKey + get`으로 구분 가능하지만 concurrent는 두 호출 사이에 race. 그래서 null 금지로 모호성 제거. HashMap은 단일 thread 가정이라 null 허용.

**Q4. Heap dump에서 ConcurrentHashMap retained 1위 (2GB). 어떻게 진단?**
> MAT Dominator Tree로 incoming reference 추적 (어떤 static/bean이 들고 있는지) → 그 chm의 key/value 타입 확인 (Class/ClassLoader면 ClassLoader leak) → 보통은 unbounded cache (size limit/expire/eviction 없음). 해결: Caffeine으로 교체 (`maximumSize`, `expireAfterWrite`), 또는 cleanup 도입, WeakReference 활용.

**Q5. Tomcat hash flooding 어떻게 방어?**
> (1) `maxParameterCount` (default 10000) request 단위 param 제한. (2) `maxPostSize` body 제한. (3) WAF/nginx에서 비정상 form 차단. (4) JDK 8 tree로 worst case 완화 (단 Comparable 미구현 custom key는 list 잔존). (5) input validation — 사용자가 임의 key 만드는 endpoint는 위험.

**Q6. `Map.of(...)` salted hashing의 동작과 한계?**
> JVM 시작 시 process-wide random salt 생성, `Map.of`로 만든 immutable map의 hash 계산에 salt mix → 같은 key set이라도 process마다 다른 bucket 분포. 공격자가 미리 collision key 계산해도 server마다 다른 salt라 무력화. 단점: 그 map의 entry hashCode가 process마다 다름 → 외부 저장/직렬화엔 부적합. HashMap은 salt 없음 (mutable + 호환성). 따라서 hash flooding 완전 방어는 immutable map만.

---

## 16. 더 깊이

HashMap putVal/resize 풀 코드, ConcurrentHashMap counterCells 구현, Poisson 8 임계 수학 유도, JDK 7 ConcurrentHashMap cycle 사고 풀버전, Consistent Hashing 구현, Maglev hashing은 git 7e4a6c8 참조.

---

> hash라는 단어를 들었을 때 머릿속에 자동으로 떠올라야 한다: bucket array + chain (또는 tree) + load factor 0.75 + hashCode 5계약 + production 사고 패턴 + 분산/캐시/보안 생태계 전체. 이게 시니어가 hash를 "안다"는 의미다.
