# 05. Hashing & Hash Collections — 표준 라이브러리·생태계 전체를 지탱하는 자료구조

> "HashMap? `put/get` 쓰는 거" 라고 답하면 입문자.
> 시니어가 hashing을 안다는 건 **Object.hashCode 계약의 5조항**을 인용하면서 `equals == true → hashCode 같아야 함`의 비대칭이 왜 그런지 설명할 수 있고, JDK 8 HashMap이 `(h ^ (h >>> 16)) & (n-1)`로 bucket index를 계산하는 이유(low bit만으로 modulo를 취하면 좋은 hashCode도 무의미해진다), tree 변환 임계값 8이 Poisson 분포로부터 도출됐다는 사실, JDK 7 ConcurrentHashMap의 segment lock이 JDK 8에서 per-bucket CAS로 재설계된 이유, 그리고 2011년 28C3에서 발표된 hash flooding이 왜 모든 언어 표준 라이브러리를 흔들었는지를 알아본다는 뜻이다.
> 이 문서는 옵션값과 hex 상수를 외우지 않는다. 표준 라이브러리, JVM 내부, 분산 시스템, 캐시, 보안, 데이터 무결성, DB까지 — Java 생태계 전체가 hash 위에 서 있다는 사실을 어떻게 보고 어떻게 진단하는지만 다룬다.

---

## 이 문서의 사용법

면접용 마인드맵을 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 8가지 가지 + 각 가지 키워드 3개.
2. **1~12장을 순서대로 학습** — 각 장이 마인드맵의 한 가지 또는 운영 시나리오에 대응.
3. **13~14장 진단·운영 best practice로 검증**.
4. **15장 꼬리질문 트리로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Hash는 임의 입력 → 고정 길이 출력의 deterministic 함수다. Bucket array + 충돌 해결 = HashTable이고, Java는 separate chaining + power-of-2 table + load factor 0.75 + JDK 8 tree 변환을 택했다. Object.hashCode/equals 5계약이 그 기반이고, ConcurrentHashMap은 JDK 8에서 per-bucket CAS + synchronized로 재설계됐다. 표준 라이브러리부터 분산 시스템·캐시·보안까지 거의 모든 곳이 hash 위에 서 있고, hash flooding · mutable key · 동시성 사고는 시니어가 진단해야 할 production 패턴이다."**

이 한 문장에서 모든 답변이 출발한다.

### 8개 가지 — 순서를 외운다

```
              [ROOT: Hash = bucket+chain, contract 5조, 어디나 쓰임]
                                  │
   ┌────────┬────────┬────────────┼────────────┬────────┬────────┬────────┐
   │        │        │            │            │        │        │        │
  ① 원리   ② 자료    ③ 계약       ④ HashMap   ⑤ CHM   ⑥ 친척    ⑦ 외부    ⑧ 사고
 (수학)   구조      (Object)      JDK 8       (Doug    (Linked/  생태계   (flooding,
   │     bucket+     5조항        treeify     Lea CAS) Weak/    분산/캐시 mutable
  uniform  chain    equals/hash   resize      bucket-  Identity 보안/DB   key,
  avalanc  load 0.75 사용/금지    (h^>>>16)   level             확률자료  GC,
  one-way  amort O(1) immutable   power of 2  scalable          hash join autobox)
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 원리 (수학)** | deterministic + uniform | avalanche | crypto vs non-crypto |
| **② 자료구조** | bucket array + chaining | open addressing 대안 | load factor 0.75 + amortized O(1) |
| **③ contract** | reflexive/symm/transitive | equals → hashCode 동일 | mutable key 금지 |
| **④ HashMap (JDK 8)** | (h ^ (h>>>16)) & (n-1) | TREEIFY ≥ 8 (Poisson) | resize: high-bit split |
| **⑤ CHM (JDK 8)** | per-bucket CAS + synchronized | weak iterator + 부정확 size | null 금지 (Doug Lea) |
| **⑥ 친척** | LinkedHashMap (order) | WeakHashMap (GC) | EnumMap (ordinal) |
| **⑦ 외부 생태계** | consistent hashing | Redis CRC16 / Kafka murmur2 | bcrypt/HMAC/Merkle |
| **⑧ 사고 패턴** | hash flooding (28C3) | mutable key / JDK7 CHM cycle | autobox Long 함정 |

### 면접 답변 흐름

> 질문 → 루트 문장 → 가지 1개 선택 → 키워드 3개 → 운영 시나리오로 확장

---

## 1. 백지 그리기 — 손그림 가이드

### 1.1 Hash function의 본질

```
[Hash Function: 임의 길이 → 고정 길이]

   input (어떤 길이든)         h(x)         output (고정 길이)
   ─────────────────────  ─────────▶   ────────────────────
   "hello"                                  3.6 × 10^9
   "안녕"                                    1.2 × 10^9
   42                                       42
   Order{id=7, total=...}                   8.7 × 10^9
                                            ↑
                                         32-bit int  (Java hashCode)
                                            또는
                                            128/256-bit bytes (SHA, MurmurHash)

   성질 4가지:
     ① deterministic — 같은 입력 → 항상 같은 출력
     ② uniform       — 출력이 골고루 분포 (bucket 충돌 최소)
     ③ avalanche     — 입력 1비트 변화 → 출력 절반쯤 변화
     ④ one-way       — 출력에서 입력 복원 불가 (crypto만 보장)

   비둘기집 원리:
     입력 공간 |X| = 무한
     출력 공간 |Y| = 2^32 또는 2^256 (유한)
     → ∃ x1 ≠ x2: h(x1) = h(x2)   (충돌은 본질적으로 불가피)
```

### 1.2 HashTable 자료구조

```
[Separate Chaining = Java가 택한 방식]

   bucket index = h(key) % n      (Java는 & (n-1), n은 2의 거듭제곱)

   table (capacity = 16)
   ┌────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┐
   │ 0  │ 1  │ 2  │ 3  │ 4  │ 5  │ 6  │ 7  │ 8  │ 9  │ 10 │ 11 │ 12 │ 13 │ 14 │ 15 │
   └────┴─┬──┴─┬──┴────┴─┬──┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┘
          │    │         │
          ▼    ▼         ▼
        [K=A]  [K=B]    [K=C]
                ↓        ↓
              [K=D]    [K=E]    ← linked list (충돌 시 같은 bucket에 chain)
                        ↓
                      [K=F]

   JDK 8+ : list 길이가 ≥ 8 이고 table size ≥ 64이면 Red-Black Tree로 변환
                                                     (TREEIFY)
            tree에서 size가 ≤ 6으로 줄면 list로 역변환 (UNTREEIFY)
            → hysteresis: oscillation 방지를 위해 임계값 다름
```

### 1.3 Open Addressing (Java가 안 쓰는 방식 — IdentityHashMap만 예외)

```
[Open Addressing = chain 없음, table 안에서 다른 slot 탐색]

   table (capacity = 8)
   ┌────┬────┬────┬────┬────┬────┬────┬────┐
   │  - │ A  │ B  │ B' │ -  │ C  │ -  │ -  │
   └────┴────┴────┴────┴────┴────┴────┴────┘
                 ▲     ▲
                 │     │
          h(B)=2 자리 차있음 → 다음 slot probe → 3
          (linear probing: 한 칸씩 / quadratic / double hash)

   장점: cache locality 좋음 (배열 한 덩어리)
   단점: clustering — 한 곳에 몰리면 검색 비용 ↑
        delete가 어려움 (probe 경로 끊김)

   Java에서 IdentityHashMap만 이 방식. 그 외 모든 표준 컬렉션은 chaining.
```

### 1.4 HashMap의 bucket index 계산 (JDK 8)

```
[hashCode() 만으로는 부족하다]

   key.hashCode() = 32 bit int
                   ┌────────────────┬────────────────┐
                   │ upper 16 bit   │ lower 16 bit   │
                   └────────────────┴────────────────┘
                            │
                            │  table capacity = 16 = 2^4
                            │  bucket index = hash & (16-1) = hash & 0x0F
                            │                                  ↑↑↑↑
                            │                          lower 4 bit만 사용!
                            ▼
                   upper 16 bit가 모두 무시됨 → 좋은 hashCode가 망함

   JDK 8의 해법: hash spread function
     hash = (h = key.hashCode()) ^ (h >>> 16)
                                  ↑
                       upper 16 bit를 lower로 XOR redistribution
                       → 작은 table에서도 upper bit가 영향력을 가진다
```

### 1.5 HashMap resize (JDK 8 — high-bit split)

```
[resize: 16 → 32. 모든 entry 재해시? NO!]

   old capacity = 16        new capacity = 32
   index = hash & 0x0F     index = hash & 0x1F
                                    ↑↑↑↑↑
                                새로 보는 bit 1개 (bit 4)

   각 old bucket의 chain을 두 그룹으로 분리:
     hash & 16 == 0  → 새 table의 같은 index (low group)
     hash & 16 != 0  → 새 table의 (index + 16) (high group)

   재해시 비용 zero — XOR 한 번으로 분기

   ┌────┐                          ┌────┐
   │ 5  │ → A → B → C → D    ───▶  │ 5  │ → A → C    (hash & 16 == 0)
   └────┘                          ├────┤
                                   │ 21 │ → B → D    (hash & 16 != 0)
                                   └────┘
```

### 1.6 ConcurrentHashMap (JDK 8 — per-bucket CAS + synchronized)

```
[JDK 7: segment lock]                   [JDK 8: per-bucket]

   ┌───────────────┐                     table[]
   │ Segment 0     │                     ┌────┐
   │ (mini-HashMap)│ ← lock 0            │ 0  │  ← CAS로 empty면 set
   ├───────────────┤                     ├────┤
   │ Segment 1     │ ← lock 1            │ 1  │  ← non-empty이면 synchronized(first)
   ├───────────────┤                     ├────┤
   │ ...           │                     │ ... │
   ├───────────────┤                     ├────┤
   │ Segment 15    │ ← lock 15           │ N-1│
   └───────────────┘                     └────┘
   default 16 lock                       lock 단위 = bucket 1개
   동시성 한계 = 16                       동시성 한계 = N (bucket 수)

   put 흐름 (JDK 8):
     1. spread hash 계산
     2. bucket이 비어 있으면 CAS로 set (성공 → 끝)
     3. 비어 있지 않으면 first node를 monitor lock으로 동기화
     4. list/tree 탐색 후 put
     5. resize는 다른 thread가 도와줌 (helpTransfer — multi-thread cooperative)

   size():
     - counterCells (LongAdder 패턴) — striped counter
     - 정확한 sum은 high contention 시 비싸므로 weakly consistent
```

### 1.7 Consistent Hashing (분산 시스템의 핵심)

```
[Naive: hash(key) % N]
   N개 노드 → N+1로 늘리면 거의 모든 key의 위치가 바뀜 (rehash 폭탄)

[Consistent Hashing: ring]

                  hash space (0 ~ 2^32)
                       ┌─────────┐
                Node-A │         │ Node-B
                 (h=10)│   ●     │ (h=80)
                       │  / \    │
                       │ /   \   │
              key1 ●──┘     \  │
              (h=15) ↑       \ │
              "다음 시계방향   key2 ●  (h=85)
              노드에 저장"        ↓ "B 노드에 저장"
                       │         │
                Node-D │         │ Node-C
                (h=180)│         │ (h=120)
                       └─────────┘

   장점: 노드 추가/삭제 시 영향 받는 key = 1/N (전체의 일부분만 이동)
   사용처: Cassandra, DynamoDB, Memcached client(libketama), Redis Cluster (변형)

   virtual node: 노드 1개를 ring에 여러 점으로 매핑 → 균형 개선
```

### 1.8 Hash Flooding (DoS 공격)

```
[정상 분포]                           [공격받은 분포]

   table                              table
   ┌────┐ A                           ┌────┐ A → B → C → D → E → ...
   │ 0  │                             │ 0  │      ← 같은 bucket에 N개 chain
   ├────┤ B                           ├────┤        (모두 hashCode 충돌)
   │ 1  │                             │ 1  │ (empty)
   ├────┤ C                           ├────┤
   │ 2  │                             │ ...│
   ├────┤ ...                         ├────┤
   │ ...│                             │ N-1│ (empty)
   └────┘                             └────┘
   평균 chain 길이 = 1                평균 chain 길이 = N (1개 bucket만)
   get: O(1)                          get: O(N)
   put N개: O(N)                      put N개: O(N²)  ← 공격자가 1 request에 10K 파라미터

   1 request에 form param 10000개 → 10K × 10K = 1억 연산 → CPU 100%
   2011년 28C3에서 공개. PHP/Python/Ruby/Java/ASP.NET 모두 영향.
```

이 그림들이 머리에 그려지면 본문으로 들어간다.

---

## 2. 가지 ①: WHY — Hash의 수학적 본질

### 2.1 핵심 질문

> "Hash는 그냥 큰 숫자 만드는 거 아닌가? 왜 함수에 4가지 성질을 요구하나?"

### 2.2 4가지 성질 — 모든 hash 사용처가 이걸 가정한다

#### 2.2.1 Deterministic (결정성)

> 같은 입력은 항상 같은 출력을 낸다.

당연해 보이지만 깨지면 모든 게 무너진다. 예:
- `Map.get(key)`가 어떤 bucket을 보는지는 `h(key)`에 의존. 매번 다른 값이 나오면 영원히 못 찾는다.
- DB partitioning에서 `partition = h(user_id) % N`이 매번 달라지면 같은 user의 데이터가 흩어진다.

**Java에서 깨지는 사례**:
```java
class Order {
    String id;
    // hashCode 미구현 → Object.hashCode() = 객체별 identity hash
}
Order o1 = new Order("A");
Order o2 = new Order("A");
o1.hashCode() != o2.hashCode();   // ★ 내용은 같지만 identity가 다르다
```

#### 2.2.2 Uniform distribution (균등 분포)

> 출력이 출력 공간 전체에 균등하게 분포한다.

bucket 충돌이 적어야 평균 O(1)을 유지한다. 분포가 한쪽으로 쏠리면:
- chain 길이가 비대칭 → P50은 O(1)이지만 P99는 O(N)
- production에서 "특정 user만 느림" 패턴 (그 user의 key가 hot bucket)

**Java의 31 곱셈이 우연이 아닌 이유** (→ 9장).

#### 2.2.3 Avalanche effect (눈사태 효과)

> 입력의 1비트가 바뀌면 출력의 약 절반이 바뀐다.

```
"order_id=1234" → hash = 0x8A3F1C99
"order_id=1235" → hash = 0x2B7E04A2   (전혀 다름)
                          ↑↑↑↑↑↑↑↑
                       절반쯤 비트가 다름
```

avalanche가 약한 hash는:
- 비슷한 key들이 비슷한 bucket으로 → clustering → 충돌 폭발
- 대표 사례: Java의 `Long.hashCode()` — 작은 양수 값들이 자기 자신과 같은 hash → autobox `HashMap<Long, ...>` 성능 저하 (→ 12.6).

#### 2.2.4 One-way (단방향)

> 출력에서 입력을 역산할 수 없다.

이 성질은 **crypto hash만** 보장한다 (SHA-256, BLAKE3, ...). non-crypto (MurmurHash, xxHash)는 안 보장.

| 용도 | 필요한 성질 | 함수 |
|---|---|---|
| HashMap, Cache key | 1, 2, 3 (one-way 불필요) | non-crypto가 표준 (MurmurHash, xxHash) |
| Password 저장 | 1, 2, 3, 4 + slow + salt | bcrypt, scrypt, argon2 |
| 무결성 확인 | 1, 2, 3, 4 (충돌 저항) | SHA-256, BLAKE3 |
| Bloom filter | 1, 2 (다른 hash function 여러 개) | non-crypto multiple |

**Java HashMap은 non-crypto를 쓴다**. 왜? crypto hash는 ns 단위로 수십~수백 사이클 — `put/get`이 매 op당 그 비용을 감당하면 너무 느리다. 대신 `hash flooding` 공격에 약함 (→ 12.1).

### 2.3 비둘기집 원리 — 충돌은 본질적으로 불가피

```
입력 공간 |X| = ∞ (혹은 매우 큼)
출력 공간 |Y| = 2^32 (Java hashCode) 또는 2^256 (SHA-256)

|X| > |Y|  →  ∃ x1 ≠ x2 : h(x1) = h(x2)
```

→ "충돌을 없앤다"가 아니라 "충돌해도 잘 동작한다"가 목표. 그래서 자료구조 (chain / probe / tree)가 필요.

### 2.4 정확한 정의

| 비유 | 정확한 정의 |
|---|---|
| "큰 숫자로 압축" | 임의 길이 입력을 받아 고정 길이 출력을 내는 결정론적 함수 `h: X → Y`. `|Y|`는 유한 (보통 2^32 또는 2^n bits) |
| "지문 같은 것" | 우연히 같은 출력을 낼 확률이 매우 낮아야 함 (uniform + avalanche). crypto hash는 + 역산·충돌 생성이 계산적으로 어렵다는 보장 추가 |

---

## 3. 가지 ②: WHAT — HashTable 자료구조의 본질

### 3.1 핵심 질문

> "Hash 함수만 있으면 안 되고 왜 자료구조가 필요한가? 충돌 해결을 어떻게?"

### 3.2 충돌 해결 2대 패턴

#### 3.2.1 Separate Chaining (Java가 택한 방식)

```
table[i] → 충돌 entry들의 linked list (또는 tree)
```

장점:
- delete가 쉽다 (list에서 노드 빼기)
- load factor > 1.0도 가능 (단, 성능 저하)
- 충돌 entry 수가 늘어나도 다른 bucket 영향 없음

단점:
- 매 entry마다 Node 객체 할당 (메모리 + GC 압박)
- linked list는 cache miss — Node가 Heap 여기저기 흩어짐

#### 3.2.2 Open Addressing (linear / quadratic / double hashing)

```
충돌 시 같은 table 배열에서 다른 slot을 probe
linear:    next slot           h(k), h(k)+1, h(k)+2, ...
quadratic: 거리 제곱            h(k), h(k)+1, h(k)+4, h(k)+9, ...
double:    두 번째 hash 함수    h(k), h(k)+h2(k), h(k)+2*h2(k), ...
```

장점:
- Node 객체 없음 — cache locality 우수
- 메모리 footprint 작음

단점:
- clustering (특히 linear) — 한 곳이 막히면 그 주변이 다 막힘
- delete가 어려움 (tombstone 처리 필요)
- load factor < 0.7~0.8 이상 가면 성능 급락

Java에서 open addressing은 `IdentityHashMap`만 사용 (`==` 비교라 hash가 단순하고, 메모리 효율 우선).

대부분의 fastutil/Eclipse Collections primitive map은 open addressing — primitive를 box하지 않으니 cache locality 이점이 크다.

### 3.3 Load Factor — 왜 0.75인가

```
load factor (α) = size / capacity

separate chaining의 평균 chain 길이 = α (uniform 가정)
get/put 평균 비용 = O(1 + α)

α 너무 작 → capacity 낭비 (메모리)
α 너무 큼 → chain 길어짐 (시간)
```

JDK의 0.75는 Donald Knuth의 *The Art of Computer Programming Vol.3*의 분석에서 영감을 얻은 값:
- 시간/공간 균형점
- resize 빈도 ↔ 충돌 빈도의 sweet spot
- 0.5는 메모리 낭비, 1.0은 성능 급락

**실전 의미**: HashMap에 N개 entry를 넣으면 실제 table 크기는 약 N/0.75 ≈ N × 1.33 → **메모리는 size의 1.33배**.

### 3.4 Amortized O(1) — 평균 O(1)의 진짜 의미

```
N개 put:
  - 대부분은 O(1)
  - 가끔 resize 발생 (capacity 2배) → O(현재 size) 비용
  - resize는 size가 2배 되어야 다시 발생
  
총 비용:
  1 + 1 + 2 + 1 + 1 + 1 + 1 + 4 + 1 + ... + 1 + 1 + 8 + ...
  = N + (resize 비용 1 + 2 + 4 + 8 + ... + N/2 + N) = N + 2N - 1 = O(N)
  
평균 = O(N) / N = O(1)   ← amortized
```

→ "평균 O(1)"의 의미는 단일 op이 O(1)이 아니라, N개 op의 총합이 O(N). 가끔 한 번의 op은 O(N) (resize 순간). production에서는 이 spike가 latency P99에 영향.

→ **대비책**: 초기 용량을 적절히 지정. `new HashMap<>(expectedSize / 0.75 + 1)` → resize 회피.

### 3.5 비유 + 정확한 정의

| 비유 | 정확한 정의 |
|---|---|
| "사물함과 라벨 시스템" | 고정 크기 배열 `table[N]`에 (key, value) entry를 저장. 위치 = hash(key) mod N. 충돌은 chain 또는 probe로 해결 |
| "여러 칸에 짐 분산" | 평균 O(1) 조회를 달성하기 위해 hash로 entry를 bucket에 분산하는 자료구조. worst case는 O(N) — Java 8 tree로 O(log N) 완화 |

---

## 4. 왜 Java가 Hash를 그렇게 광범위하게 쓰는가 ⭐⭐

### 4.1 핵심 질문

> "TreeMap도 있고 List도 있는데 왜 거의 모든 자리에 HashMap이 박혀 있나?"

### 4.2 본질적 이유 3가지

#### 4.2.1 O(1) 조회 — 정렬 자료구조보다 빠름

```
                  get      put     iterate
HashMap           O(1)*    O(1)*   O(N+capacity)  ← capacity까지 스캔
TreeMap           O(logN)  O(logN) O(N)            (sorted)
LinkedHashMap     O(1)*    O(1)*   O(N)            (insertion order)
ArrayList         O(N)     O(1)*   O(N)            (위치 모르면 contains는 O(N))
* amortized
```

→ key로 찾는 게 압도적 일반 패턴이고, 정렬이 필요한 경우는 드물다. 자연스러운 default가 HashMap.

#### 4.2.2 Key가 Comparable이 아니어도 됨

```java
// TreeMap: Comparable 또는 Comparator 필수
Map<Order, Integer> counts = new TreeMap<>();  // Order는 Comparable 아니면 컴파일 OK 런타임 ClassCastException

// HashMap: hashCode + equals만 있으면 됨 (Object 기본 구현으로도 동작)
Map<Order, Integer> counts = new HashMap<>();  // 그냥 OK
```

→ 임의 객체를 key로 쓰는 데 진입장벽이 낮다.

#### 4.2.3 표준 라이브러리 차원의 기본 선택

| API | 내부 자료구조 |
|---|---|
| `Map.of(...)` | immutable hash map (small N은 array-backed, large는 hash) |
| `Collectors.toMap(...)` | HashMap 기본 |
| `Set.of(...)` | hash set |
| `Collectors.groupingBy(...)` | HashMap 기본 |
| `HashSet`, `LinkedHashSet` | 내부적으로 HashMap |

→ 사용자는 hash임을 의식 안 하고도 매일 hash를 쓴다.

### 4.3 JDK 내부 자체가 hash에 의존

표준 라이브러리 사용자 API뿐 아니라 **JVM과 JDK 내부 구현도 hash 위에 서 있다**:

| JDK 내부 | hash 용도 |
|---|---|
| **String intern pool** (StringTable, HotSpot 내부) | String literal과 `intern()` 호출의 중복 제거. JDK 7부터 Heap 영역. |
| **ClassFile constant pool** | UTF-8 entry, name lookup |
| **ClassLoader cache** | `loadClass(name)` → 이미 로드된 Class 찾기 |
| **JIT inline cache** | virtual call site의 type → target method 매핑 (megamorphic 처리) |
| **Pattern compile cache** | `Pattern.compile(regex)`의 내부 caching |
| **MethodHandle cache** | 자주 쓰는 invocation의 lookup 가속 |
| **Reflection cache** | `Class.getMethod(name, ...)` lookup table |

→ JVM은 자체적으로 거대한 hash 시스템이다. 이걸 모르면 ClassLoader leak이나 intern pool overflow 진단이 안 된다.

자세히는 `jvm/02-runtime-data-areas/02-metaspace-and-class-space.md` 의 String intern pool 섹션 참고.

### 4.4 운영 환경 어디든 hash

```
                  사용자 코드
                       │
                       ▼
   ┌──────────────────────────────────────────────┐
   │  HashMap / ConcurrentHashMap (in-process)    │
   └──────────────────────────────────────────────┘
                       │
                       ▼
   ┌──────────────────────────────────────────────┐
   │  Caffeine / Guava Cache (TinyLFU + hash)     │
   └──────────────────────────────────────────────┘
                       │
                       ▼
   ┌──────────────────────────────────────────────┐
   │  Redis (CRC16 cluster slot, hash data type)  │
   └──────────────────────────────────────────────┘
                       │
                       ▼
   ┌──────────────────────────────────────────────┐
   │  Kafka (murmur2(key) % partitions)           │
   └──────────────────────────────────────────────┘
                       │
                       ▼
   ┌──────────────────────────────────────────────┐
   │  CDN / Load Balancer (consistent hashing)    │
   └──────────────────────────────────────────────┘
                       │
                       ▼
   ┌──────────────────────────────────────────────┐
   │  DB (hash partition, hash join, hash index)  │
   └──────────────────────────────────────────────┘
```

→ Java 사용자 코드 한 줄 위에 hash, 아래에 hash, 옆에 hash. 시니어는 이 stack 전체를 본다.

---

## 5. 가지 ③: Object.hashCode / equals 계약 ⭐

### 5.1 핵심 질문

> "왜 `equals`만 override하면 `HashSet`이 깨지나? hashCode/equals의 5가지 계약이 뭔가?"

### 5.2 5가지 계약 — Effective Java Item 11

#### 5.2.1 equals 계약 (Item 10)

```
1. Reflexive   — x.equals(x) == true
2. Symmetric   — x.equals(y) ⇔ y.equals(x)
3. Transitive  — x.equals(y) ∧ y.equals(z) ⇒ x.equals(z)
4. Consistent  — 변경 없는 한 결과 동일
5. null-safe   — x.equals(null) == false
```

#### 5.2.2 hashCode 계약 (Item 11)

```
1. Consistent       — 같은 객체는 (변경 없으면) 같은 hash
2. equals → hash    — x.equals(y) ⇒ x.hashCode() == y.hashCode()
3. hash equal는 OK  — x.hashCode() == y.hashCode()여도 x.equals(y) 아닐 수 있음
                      (충돌 허용 — 비둘기집 원리)
```

### 5.3 왜 비대칭인가 — 가장 중요한 디테일

```
equals == true   ⇒   hashCode 같아야 함   (필수)
hashCode 같음    ⇒   equals == true        (X — 충돌 허용)
```

이유:
- HashMap이 key를 찾을 때 흐름:
  ```
  1. bucket = hashCode % capacity
  2. bucket의 chain을 돌면서 equals로 매치 확인
  3. 매치되면 return
  ```
- 만약 `equals == true`인데 hashCode가 다르면 → bucket이 달라 영원히 못 찾음.
- 만약 hashCode가 같은데 equals가 다르면 → 같은 bucket 안에서 chain의 다른 entry로 분류되므로 OK.

→ **hashCode는 "같은 bucket으로 모아주는 좌표"고, equals는 "그 안에서 일치 여부 결정"** — 역할 분담.

### 5.4 위반 시 결과

#### 5.4.1 hashCode 미구현 (equals만 override)

```java
class Order {
    String id;
    
    @Override
    public boolean equals(Object o) {
        return o instanceof Order && ((Order)o).id.equals(this.id);
    }
    // hashCode() 미구현 → Object.hashCode() = identity hash
}

Set<Order> set = new HashSet<>();
set.add(new Order("A"));
set.contains(new Order("A"));   // ★ false! 다른 bucket이라 못 찾음
```

→ 인텔리J/IDE의 "Generate hashCode/equals together" 권고가 이래서 있다.

#### 5.4.2 Mutable field 포함한 hashCode

```java
class User {
    String name;
    // Lombok @Data → equals/hashCode가 모든 field 포함
}

Set<User> set = new HashSet<>();
User u = new User();
u.name = "A";
set.add(u);

u.name = "B";    // ★ hash 변경됨
set.contains(u); // ★ false! 옛 bucket에 있지만 새 hash로 다른 bucket 봄
```

→ Lombok `@Data` 사용 시 mutable field 함정. 권장:
```java
@EqualsAndHashCode(of = {"id"})   // 불변 식별자만 포함
class User { ... }
```

### 5.5 hashCode 작성의 표준 패턴

#### 5.5.1 옛날 방식 (Effective Java Item 11 정통)

```java
@Override
public int hashCode() {
    int result = 17;
    result = 31 * result + (name == null ? 0 : name.hashCode());
    result = 31 * result + age;
    return result;
}
```

#### 5.5.2 JDK 7+ `Objects.hash`

```java
@Override
public int hashCode() {
    return Objects.hash(name, age);   // 내부적으로 위와 동일
}
```

내부 구현:
```java
public static int hash(Object... values) {
    return Arrays.hashCode(values);
}
// Arrays.hashCode는 result = 31*result + element.hashCode() 누적
```

단점: `Object... values` 배열 alloc → 성능 민감 hot path에선 손으로 작성하는 게 빠를 수 있음. 보통 무시할 수준.

### 5.6 핵심 인사이트 — "key는 immutable이다"

production hash 코드의 한 줄 권고:

> **HashMap/HashSet의 key는 immutable이어야 한다.**

- 표준 타입 `String`, `Long`, `Integer`, `UUID`, `java.time.*` 등은 모두 immutable.
- custom value object를 key로 쓰면 — final field만, setter 없음, hashCode/equals는 final field만 사용.
- mutable이면 → 위 5.4.2 사례로 데이터 분실.

---

## 6. HashMap 내부 (JDK 8+) — 코드 레벨 ⭐⭐⭐

### 6.1 핵심 질문

> "JDK 8 HashMap이 어떤 hash spread function을 쓰고, treeify 임계 8이 어떻게 결정됐고, resize에서 어떻게 high-bit split을 하나?"

### 6.2 핵심 필드 (OpenJDK 21, `HashMap.java`)

```java
public class HashMap<K,V> extends AbstractMap<K,V> {
    static final int DEFAULT_INITIAL_CAPACITY = 1 << 4;     // 16
    static final int MAXIMUM_CAPACITY = 1 << 30;
    static final float DEFAULT_LOAD_FACTOR = 0.75f;
    static final int TREEIFY_THRESHOLD = 8;
    static final int UNTREEIFY_THRESHOLD = 6;
    static final int MIN_TREEIFY_CAPACITY = 64;

    transient Node<K,V>[] table;       // ★ bucket 배열
    transient int size;
    int threshold;                      // capacity * loadFactor
    final float loadFactor;
    
    static class Node<K,V> {
        final int hash;
        final K key;
        V value;
        Node<K,V> next;     // ★ chain
    }
}
```

### 6.3 hash spread function

```java
static final int hash(Object key) {
    int h;
    return (key == null) ? 0 : (h = key.hashCode()) ^ (h >>> 16);
}
```

**왜 이렇게?**
- table size가 `2^n`이고 bucket index는 `hash & (n-1)` — lower n bit만 사용.
- 좋은 hashCode라도 upper bit가 lower로 안 흘러가면 충돌. (예: `Integer.hashCode() = value` → 0, 16, 32, 48 모두 lower 4 bit 같음 → 같은 bucket)
- `h ^ (h >>> 16)` 한 줄로 upper 16 bit를 lower 16 bit로 XOR redistribution → 작은 table에서도 upper bit 영향력 확보.

```
input  hash: aaaa bbbb cccc dddd eeee ffff gggg hhhh
       >>>16: 0000 0000 0000 0000 aaaa bbbb cccc dddd
       XOR  : aaaa bbbb cccc dddd (eeee^aaaa) (ffff^bbbb) (gggg^cccc) (hhhh^dddd)
                                  ↑↑↑↑ lower 16 bit에 upper의 정보가 섞임
```

### 6.4 putVal — 핵심 흐름 (JDK 21 발췌)

```java
final V putVal(int hash, K key, V value, boolean onlyIfAbsent, boolean evict) {
    Node<K,V>[] tab; Node<K,V> p; int n, i;
    if ((tab = table) == null || (n = tab.length) == 0)
        n = (tab = resize()).length;                          // ① 첫 put → 초기화
    if ((p = tab[i = (n - 1) & hash]) == null)
        tab[i] = newNode(hash, key, value, null);             // ② empty bucket → 그냥 set
    else {
        Node<K,V> e; K k;
        if (p.hash == hash &&
            ((k = p.key) == key || (key != null && key.equals(k))))
            e = p;                                            // ③ 첫 node가 매치
        else if (p instanceof TreeNode)
            e = ((TreeNode<K,V>)p).putTreeVal(...);            // ④ 이미 tree
        else {
            for (int binCount = 0; ; ++binCount) {            // ⑤ chain 탐색
                if ((e = p.next) == null) {
                    p.next = newNode(hash, key, value, null);
                    if (binCount >= TREEIFY_THRESHOLD - 1)    // ★ 8개 이상 → tree
                        treeifyBin(tab, hash);
                    break;
                }
                if (e.hash == hash &&
                    ((k = e.key) == key || (key != null && key.equals(k))))
                    break;
                p = e;
            }
        }
        if (e != null) {                                       // ⑥ key 존재 → value 갱신
            V oldValue = e.value;
            if (!onlyIfAbsent || oldValue == null) e.value = value;
            return oldValue;
        }
    }
    if (++size > threshold) resize();                          // ⑦ threshold 초과 → resize
    return null;
}
```

요약:
1. 비어있으면 그냥 set
2. 첫 node가 같은 key면 갱신
3. tree면 tree에 put
4. list면 끝까지 가서 추가 (도중에 같은 key 있으면 갱신)
5. chain 길이 ≥ 8 → treeifyBin
6. size > threshold → resize

### 6.5 treeifyBin — 8이라는 숫자의 정체

```java
final void treeifyBin(Node<K,V>[] tab, int hash) {
    int n;
    if (tab == null || (n = tab.length) < MIN_TREEIFY_CAPACITY)
        resize();                                  // ★ table이 너무 작으면 treeify 대신 resize
    else if ((/* index 계산 */) /* ... */)
        /* ... linked list를 TreeNode로 변환, RB-tree 구성 ... */
}
```

**왜 8?**

JDK 소스 javadoc 인용 (의역):
> 좋은 hash function (uniform random) 하에서 chain 길이는 Poisson 분포(λ = 0.5)를 따른다.
> 길이별 확률:
> - 길이 0: ~60.6%
> - 길이 1: ~30.3%
> - 길이 2: ~7.6%
> - 길이 3: ~1.3%
> - 길이 4: ~0.15%
> - 길이 5: ~0.013%
> - 길이 6: ~0.0009%
> - 길이 7: ~0.00005%
> - 길이 8: ~0.000003%  ← 백만분의 1보다 적음

→ uniform hash라면 chain 길이 8 이상은 **사실상 발생하지 않는다**. 길이 8에 도달했다면 hash 분포가 비정상 (= adversarial하거나 poor hashCode). 이때만 tree로 변환해서 worst case O(log N) 보장.

**왜 6에서 untreeify?** — hysteresis. 7-8 사이에서 oscillate하면 tree↔list 변환 비용 폭증. 6/8로 gap을 둔다.

**MIN_TREEIFY_CAPACITY = 64**: table이 너무 작으면 (예: 16) chain 길이 ≥ 8은 통계적 변동일 뿐 — 차라리 resize로 해결.

### 6.6 resize — 2배 확장 + high-bit split

```java
final Node<K,V>[] resize() {
    Node<K,V>[] oldTab = table;
    int oldCap = (oldTab == null) ? 0 : oldTab.length;
    int newCap = oldCap << 1;     // ★ 2배
    /* ... */
    Node<K,V>[] newTab = (Node<K,V>[])new Node[newCap];
    table = newTab;
    
    if (oldTab != null) {
        for (int j = 0; j < oldCap; ++j) {
            Node<K,V> e;
            if ((e = oldTab[j]) != null) {
                oldTab[j] = null;
                if (e.next == null)
                    newTab[e.hash & (newCap - 1)] = e;
                else if (e instanceof TreeNode)
                    /* tree split */;
                else {
                    Node<K,V> loHead = null, loTail = null;
                    Node<K,V> hiHead = null, hiTail = null;
                    Node<K,V> next;
                    do {
                        next = e.next;
                        if ((e.hash & oldCap) == 0) {        // ★ high bit가 0이면 low group
                            if (loTail == null) loHead = e;
                            else loTail.next = e;
                            loTail = e;
                        } else {                              // ★ high bit가 1이면 high group
                            if (hiTail == null) hiHead = e;
                            else hiTail.next = e;
                            hiTail = e;
                        }
                    } while ((e = next) != null);
                    if (loTail != null) { loTail.next = null; newTab[j] = loHead; }
                    if (hiTail != null) { hiTail.next = null; newTab[j + oldCap] = hiHead; }
                }
            }
        }
    }
    return newTab;
}
```

핵심: `(e.hash & oldCap) == 0` 한 번의 비트 AND로 entry를 두 그룹으로 가른다. 재해시 함수 호출 zero — capacity가 power of 2이기 때문에 가능한 트릭.

### 6.7 왜 capacity는 power of 2인가

```
일반 modulo: index = hash % n
power of 2 : index = hash & (n - 1)   ← AND 한 번 (수십 배 빠름)

resize 시 분리:
  power of 2: index 또는 index+oldCap의 두 곳뿐 (high bit 검사 1번)
  임의 n     : 모든 entry 재해시 필요
```

→ power of 2는 hash의 modulo를 bit 연산으로 대체하고 resize 비용을 절감하기 위한 결정.

trade-off: capacity가 항상 2의 거듭제곱 — 사용자가 `new HashMap<>(100)`이라 해도 실제는 128. 메모리 손실은 있지만 무시할 수준.

---

## 7. HashMap 진화 역사 — 한 그림에 30년

### 7.1 타임라인

```
JDK 1.0 (1996)
   │
   │   Hashtable + Vector — synchronized, 일찍 도입된 동기화 컬렉션
   │
JDK 1.2 (1998)  ── Collections Framework
   │
   │   HashMap (Hashtable의 unsync 버전)
   │   HashSet, TreeMap, LinkedList, ArrayList 표준화
   │
JDK 1.4 (2002)
   │
   │   LinkedHashMap (insertion/access order)
   │   IdentityHashMap (open addressing)
   │
JDK 5 (2004)  ── 동시성 + Generics
   │
   │   ConcurrentHashMap (Doug Lea, segment lock)
   │   Generics 도입 — HashMap<K,V>
   │
JDK 7 (2011)
   │
   │   String.hashCode 결과 캐싱 (lazy)
   │   Alternative hashing (hash flooding 대응 시도 — 일부 해제)
   │   diamond operator: new HashMap<>()
   │
JDK 8 (2014)  ── HashMap 대수술
   │
   │   ★ chain → tree 변환 (TREEIFY_THRESHOLD = 8)
   │   ★ ConcurrentHashMap 완전 재설계: segment → per-bucket CAS + synchronized
   │   compute / computeIfAbsent / merge atomic API
   │   Spliterator
   │
JDK 9 (2017)
   │
   │   Map.of, Set.of, List.of — immutable + salted hashing (per-process random seed)
   │   Map.copyOf, Set.copyOf
   │
JDK 11+
   │
   │   사소한 마이크로 최적화, Collection API 다듬기
   │
JDK 21 (2023)
   │
   │   Sequenced Collections (interface) — 변경 사항은 미미
```

### 7.2 각 진화의 트리거

| 진화 | 트리거 |
|---|---|
| JDK 5 ConcurrentHashMap | 멀티코어 시대, Hashtable의 global lock이 scalability 병목 |
| JDK 7 hashCode 캐싱 | String이 너무 자주 hash 계산 (HashMap key, intern pool, JSP cache) |
| JDK 7 alternative hashing | 2011년 28C3 hash flooding 발표 직격 (→ 12.1) |
| JDK 8 treeify | 충돌 worst case O(N) → O(log N), hash flooding 부분 완화 |
| JDK 8 ConcurrentHashMap 재설계 | segment의 메모리 오버헤드 + 동시성 한계 (16 segment) |
| JDK 9 Map.of salted hash | hash flooding 완전 방어 (immutable map만) |

### 7.3 JDK 7 → 8 ConcurrentHashMap의 진짜 의미

```
JDK 7 segment lock
   ├─ 16 segments × 각각 mini-HashMap
   ├─ segment 단위 lock — 동시성 = 16
   ├─ 각 segment는 ReentrantLock 객체 → 메모리 오버헤드
   └─ resize는 segment별 → 부분 resize 처리 복잡

JDK 8 per-bucket
   ├─ table[] 한 덩어리 (HashMap과 동일 구조)
   ├─ bucket 단위 lock — 동시성 = N (bucket 수)
   ├─ empty bucket은 CAS로 set (lock 없음)
   ├─ non-empty는 synchronized(firstNode) — 객체 헤더의 monitor 활용
   └─ resize는 multi-thread cooperative (helpTransfer)
```

→ "segment를 폐기"가 아니라 **lock의 granularity를 segment에서 bucket으로 더 잘게 쪼갰다**. Doug Lea의 design — CAS + synchronized 조합으로 메모리는 줄이고 동시성은 늘림.

---

## 8. ConcurrentHashMap 풀버전 ⭐⭐

### 8.1 핵심 질문

> "ConcurrentHashMap이 어떻게 lock-free에 가까운 동시성을 달성하나? null을 왜 금지하나? size()가 부정확한 이유는?"

### 8.2 JDK 8 put — 코드 흐름

```java
final V putVal(K key, V value, boolean onlyIfAbsent) {
    if (key == null || value == null) throw new NullPointerException();  // ★ null 금지
    int hash = spread(key.hashCode());
    int binCount = 0;
    for (Node<K,V>[] tab = table;;) {
        Node<K,V> f; int n, i, fh;
        if (tab == null || (n = tab.length) == 0)
            tab = initTable();
        else if ((f = tabAt(tab, i = (n - 1) & hash)) == null) {
            if (casTabAt(tab, i, null, new Node<K,V>(hash, key, value, null)))
                break;                          // ★ CAS 성공 → 끝 (lock-free)
        }
        else if ((fh = f.hash) == MOVED)
            tab = helpTransfer(tab, f);         // ★ resize 중이면 도와줌
        else {
            V oldVal = null;
            synchronized (f) {                  // ★ 첫 node를 monitor lock
                if (tabAt(tab, i) == f) {
                    if (fh >= 0) {
                        binCount = 1;
                        for (Node<K,V> e = f;; ++binCount) {
                            // chain traversal + put or update
                        }
                    }
                    else if (f instanceof TreeBin) {
                        // tree put
                    }
                }
            }
            if (binCount >= TREEIFY_THRESHOLD) treeifyBin(tab, i);
            break;
        }
    }
    addCount(1L, binCount);                     // ★ size 증가 (counterCells)
    return null;
}
```

흐름 정리:
1. **null 검사**: key/value 어느 것도 null 안 됨.
2. **CAS empty set**: bucket이 비어있으면 CAS로 set — 성공하면 lock 한 번도 안 잡고 끝.
3. **resize 중이면 helpTransfer**: 다른 thread가 resize 중일 때 현재 thread가 도와줌. multi-thread cooperative resize.
4. **synchronized(firstNode)**: bucket이 차있으면 그 bucket의 첫 node를 monitor로 lock. **lock 단위 = bucket 1개**.
5. **counterCells로 size 증가**: 정확한 카운터 대신 LongAdder 패턴 (striped counter).

### 8.3 왜 segment를 버렸나

| segment (JDK 7) | per-bucket (JDK 8) |
|---|---|
| 16 segments × 각자 Entry[] | 1개 table[] (HashMap과 동일) |
| segment 16개 lock 객체 | bucket별 synchronized (객체 헤더 활용) |
| 동시성 한계: 16 | 동시성 한계: bucket 수 (수천~수만) |
| 메모리 오버헤드: 16 lock + 16 metadata | bucket 자체 = 1 reference (cheaper) |
| resize: segment 단위 | resize: helpTransfer (전역 + cooperative) |

→ 더 작고, 더 빠르고, scalability 한계가 사라짐.

### 8.4 size() — 정확하지 않은 카운터

```java
public int size() {
    long n = sumCount();
    return ((n < 0L) ? 0 :
            (n > (long)Integer.MAX_VALUE) ? Integer.MAX_VALUE :
            (int)n);
}

final long sumCount() {
    CounterCell[] cs = counterCells;
    long sum = baseCount;
    if (cs != null) {
        for (CounterCell c : cs)
            if (c != null) sum += c.value;
    }
    return sum;
}
```

**counterCells = striped counter** (`LongAdder`의 원형):
- 단일 atomic counter는 contention이 심함 (모든 thread가 같은 cache line에 CAS).
- 대신 N개 cell로 쪼개서 각 thread가 자기 cell에 add → contention 분산.
- 정확한 sum이 필요할 땐 모든 cell 더함.

trade-off:
- **장점**: high contention에서도 add는 cheap (자기 cell에 CAS).
- **단점**: 다른 thread의 add가 진행 중이면 `size()`가 stale. → "weakly consistent size".

production 함의: `chm.size()`로 정확한 count 의존하지 말 것. 통계 용도로만.

### 8.5 compute / computeIfAbsent — atomic key-level

```java
map.computeIfAbsent("key", k -> expensiveCompute(k));
```

- 같은 key로 두 thread가 동시에 호출해도 `expensiveCompute(k)`는 한 번만 실행.
- 다른 key는 병렬 가능.

내부적으로 그 bucket을 synchronized로 잡고 함수를 실행 → 함수가 길면 그 bucket이 잠긴 시간만큼 다른 op 대기.

**함정**: compute 함수 안에서 같은 map의 다른 key를 건드리면 (recursive update) → JDK 8에서는 정의되지 않은 동작 (deadlock-like). JDK 9+에서는 `IllegalStateException` throw. 안전 패턴: compute 함수는 짧고 self-contained 하게.

### 8.6 왜 null 금지인가 — Doug Lea의 답

```java
if (key == null || value == null) throw new NullPointerException();
```

Doug Lea의 public 답 (concurrency-interest mailing list):
> "ConcurrentMap은 `get(k)`가 null을 돌려줄 때 두 가지 의미가 있다. (1) key가 없거나 (2) value가 null. single-thread에서는 `containsKey`로 구분할 수 있지만, concurrent에서는 두 호출 사이에 다른 thread가 put할 수 있어 구분 자체가 race condition을 만든다. 그래서 null을 아예 금지하는 게 깔끔하다."

HashMap은 null을 허용 — 단일 thread 환경에선 `containsKey + get` 2-step이 동작하기 때문.

### 8.7 iterator의 weak consistency

```java
Map<K,V> chm = new ConcurrentHashMap<>();
for (var e : chm.entrySet()) { ... }   // ★ 도중에 다른 thread가 put 해도 OK
```

- HashMap iterator는 **fail-fast** — 도중 수정 감지하면 `ConcurrentModificationException`.
- ConcurrentHashMap iterator는 **weakly consistent** — snapshot 비슷한 뷰, 예외 안 던짐. 도중 추가된 entry가 보일 수도, 안 보일 수도.

→ 정확한 snapshot 필요하면 `new HashMap<>(chm)` 으로 copy 후 iterate.

자세히는 `java-deep-dive/03-threads.md` 의 weak consistency 섹션 참조.

---

## 9. String hashCode — JVM에서 가장 많이 호출되는 hash 함수

### 9.1 핵심 질문

> "왜 String hash 식에 31을 곱하나? hashCode 캐싱은 어떻게?"

### 9.2 식

```java
public int hashCode() {
    int h = hash;
    if (h == 0 && value.length > 0) {
        char val[] = value;
        for (int i = 0; i < value.length; i++)
            h = 31 * h + val[i];
        hash = h;
    }
    return h;
}
```

수식으로:
```
h(s) = s[0]·31^(n-1) + s[1]·31^(n-2) + ... + s[n-1]·31^0
```

### 9.3 왜 31인가

3가지 이유:

#### 9.3.1 Odd prime
- 짝수면 곱셈에서 lower bit가 항상 0 → 분포 나빠짐.
- 소수면 인수분해가 안 됨 → 패턴 형성 어려움.

#### 9.3.2 Shift + subtract 최적화
- `31 * h == (h << 5) - h` — 5 bit shift + subtract 한 번.
- 곱셈 명령보다 빠른 시대(1990s)에 의미 있었음. 현대 CPU에선 곱셈도 1 cycle — 큰 의미 X.

#### 9.3.3 통계적으로 분포 좋음
- Joshua Bloch *Effective Java*: 다양한 prime을 실험했고 31이 collision이 적었다고 함.
- 다른 후보: 37, 41 등. 31이 사실상의 관습.

### 9.4 32-bit overflow는 의도된 사용

`int` 곱셈은 wrap-around — `Integer.MAX_VALUE`를 넘어가면 음수가 됨. 이것이 우연히 hash로 좋은 분포를 만듦. (modular arithmetic in 2^32).

→ "overflow는 정의되지 않은 동작"이라는 C 시대 사고방식에서 벗어남. Java는 wrap을 spec으로 정의.

### 9.5 hashCode 캐싱

```java
public final class String {
    private final byte[] value;
    private int hash;            // ★ default 0 — final 아님
    private boolean hashIsZero;  // ★ JDK 12+
}
```

- 처음 `hashCode()` 호출 → 계산 후 `hash` 필드에 저장 (lazy init).
- 다음 호출부터 cached 값 반환.
- **`hash`가 final이 아닌 이유**: lazy init 위해 mutable 필요. 그러나 `String`은 effectively immutable — 외부에서 안 보임.

#### 9.5.1 Empty String의 함정 (JDK 11 이전)

`""`의 hashCode = 0 (수식 결과).
캐싱 조건이 `if (h == 0)` — empty string은 계산 후에도 0 → 매번 재계산.

```java
String empty = "";
empty.hashCode();   // ★ 계산: 0
empty.hashCode();   // ★ 또 계산: 0 (cache 작동 안 함)
```

JDK 12부터 `hashIsZero` boolean으로 해결 — "계산했고 결과가 0이다"를 별도 표시.

production 영향: log4j/logback에서 빈 MDC key를 자주 hash → CPU 낭비. JDK 11 → 17 업그레이드 시 사라지는 미세 최적화.

### 9.6 Compact String (JDK 9+) 와의 호환성

JDK 9부터 `String`은 내부적으로 `byte[]` + coder (LATIN1 or UTF16) — Latin-1만 쓰면 메모리 절반.

hash 계산도 byte로:
```java
// LATIN1
for (byte b : value)
    h = 31 * h + (b & 0xff);

// UTF16
for (int i = 0; i < value.length; i += 2)
    h = 31 * h + ((value[i+1] & 0xff) << 8 | (value[i] & 0xff));
```

**중요**: hashCode 결과 자체는 변경 없음 (호환성). `"hello".hashCode()`는 JDK 8과 17이 동일. 내부 계산 경로만 다름.

### 9.7 hash 충돌 만들기 — 학습용 예시

```
"Aa".hashCode() == "BB".hashCode()       // 'A'*31 + 'a' vs 'B'*31 + 'B'
                                         //  65*31 + 97 vs 66*31 + 66
                                         //  2112      vs 2112
"AaAa".hashCode() == "AaBB".hashCode() == "BBAa".hashCode() == "BBBB".hashCode()
```

→ String hashCode에서 충돌을 만드는 것은 **수학적으로 쉽다**. 이게 hash flooding (→ 12.1)의 기반. crypto hash가 아니라 단순 multiplicative hash라서 어쩔 수 없음.

---

## 10. JVM 내부의 해시 활용

### 10.1 String intern pool (StringTable)

```
[String literal과 String.intern()이 모이는 곳]

   Source: String s = "hello";
            │
            ▼
   ClassFile constant pool에 UTF-8 "hello" 저장
            │
            ▼ (class load 시)
   JVM이 StringTable에서 "hello" 찾기
            │
       ┌────┴────┐
       │         │
   존재        없음
       │         │
       ▼         ▼
   같은 String  새 String 만들어 StringTable에 등록
   ref 반환
```

- **자료구조**: hash table (HotSpot 내부 C++ `StringTable`).
- **위치**: JDK 6까지 PermGen, JDK 7부터 Heap, JDK 8 PermGen 제거 후 그대로 Heap.
- **크기 옵션**: `-XX:StringTableSize=...` (default 60013 — prime 근처).
- **함정**: `String.intern()` 남용 → table size 부족 → chain 길어짐 → intern 자체가 느려짐. 옛날엔 PermGen OOM 원인이었음.

자세히는 `jvm/02-runtime-data-areas/02-metaspace-and-class-space.md` 의 String Pool 섹션 참조.

### 10.2 ClassFile constant pool

```
[.class 파일 안의 hash 가속 lookup table]

   ClassFile {
     u4 magic;                 // 0xCAFEBABE
     ...
     u2 constant_pool_count;
     cp_info constant_pool[]; // ★ UTF-8, NameAndType, MethodRef 등
   }
```

- bytecode `invokevirtual #5` — 5번째 entry를 lookup.
- VM이 메모리에 로드한 후 `name → entry` 매핑을 hash table로 가속.

### 10.3 ClassLoader cache

```java
// ClassLoader.java
private final ConcurrentHashMap<String, Object> parallelLockMap;
```

- `loadClass(name)` 호출 시 이미 로드된 클래스인지 hash로 lookup.
- WebAppClassLoader, OSGi 등 변형에서도 동일 패턴.
- **누수**: ClassLoader 인스턴스가 살아있으면 그 안의 모든 Class가 살아있음 → Metaspace 누수의 원천.

### 10.4 JIT inline cache

```
[virtual call의 dispatch 가속]

   call site: obj.method()
                │
                ▼
       ┌────────────────────┐
       │ Inline Cache (IC)  │
       │ ──────────────     │
       │ if obj.klass == K1 │ → method1 직접 호출 (inlining 가능)
       │ else if    == K2   │ → method2
       │ else               │ → 일반 vtable lookup
       └────────────────────┘
   
   K1, K2 매핑은 hash 기반 lookup table (megamorphic 시).
```

- monomorphic (1 receiver type) → 직접 inlining.
- bimorphic (2 type) → 2-way branch.
- megamorphic (3+ type) → hash table dispatch (느림).

자세히는 추후 `jvm/03-execution-engine/` 챕터.

### 10.5 Pattern compile cache

```java
Pattern.compile("^abc.*")
```

- Java regex는 NFA → DFA 변환 비용 큼.
- 일부 라이브러리 (Spring, Apache Commons)는 `ConcurrentHashMap<String, Pattern>`으로 캐싱.
- key는 regex string. 사용자 input regex를 캐싱하면 DoS (사용자가 다양한 regex로 cache 폭주).

### 10.6 Reflection cache

- `Class.getMethod(name, paramTypes)` 호출 시 method table lookup.
- HotSpot 내부에 `name → Method` hash map.
- 자세히는 `java-deep-dive/02-reflection.md` 참조.

---

## 11. Java의 다른 해시 컬렉션 친척들

### 11.1 LinkedHashMap — insertion / access order

```
[HashMap에 doubly-linked list 추가]

   HashMap bucket structure        +    doubly-linked list (across buckets)
   ┌────┐                                    
   │ 0  │ → A                          A ⇄ B ⇄ C ⇄ D ⇄ ...
   ├────┤                              ↑                ↑
   │ 1  │ → B → D                     head             tail
   ├────┤
   │ 2  │ → C
   └────┘
```

- 각 Entry가 `before`/`after` pointer 추가 → iteration이 insertion order (또는 access order).
- access order mode (`accessOrder = true`): `get/put`마다 노드를 tail로 이동 → **LRU cache 구현**.

#### 11.1.1 LRU cache 구현 패턴

```java
public class LRUCache<K, V> extends LinkedHashMap<K, V> {
    private final int capacity;
    
    public LRUCache(int capacity) {
        super(capacity, 0.75f, true);   // access order
        this.capacity = capacity;
    }
    
    @Override
    protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        return size() > capacity;
    }
}
```

- 가장 안 쓰인 entry가 head — 자동 제거.
- 단일 thread 전용. concurrent하려면 Caffeine 등.

### 11.2 WeakHashMap — key를 GC가 청소

```
[Key가 WeakReference로 wrap됨]

   HashMap entry: key(strong) → value
   WeakHashMap entry: WeakReference(key) → value
                          │
                          ▼
   key 객체에 다른 strong reference가 없으면
        → GC가 key를 수거
        → next get/put 시 expungeStaleEntries()가 entry 제거
```

- **목적**: 사용처가 key에 대한 strong reference를 잃으면 자동으로 메모리 회수.
- **함정**: value가 key를 다시 가리키면 (`Map<K, K>` 류) cyclic strong ref → 수거 안 됨.
- **활용**: `ClassValue` 내부 캐시 (class별 메타데이터). class unload 시 자동 청소.

cleanup 시점은 **lazy** — `ReferenceQueue.poll()`을 `get`/`put`/`size`에서 호출. 안 건드리면 청소 안 됨.

### 11.3 IdentityHashMap — equals 대신 ==

```java
IdentityHashMap<String, Integer> m = new IdentityHashMap<>();
String a = new String("X");
String b = new String("X");
m.put(a, 1);
m.get(a);    // 1
m.get(b);    // null  ← 내용 같아도 다른 객체면 다른 key
```

- key 비교가 `==` (참조 동일성). hashCode도 `System.identityHashCode()`.
- **자료구조**: open addressing (linear probing) — 표준 컬렉션 중 유일.
- **이유**: hash가 단순 identity → 분포 균일 → open addressing이 효율적.
- **사용처**: 객체 그래프 traversal (visited set), serialization (cycle 감지), JVM 내부 자료구조.

### 11.4 EnumMap — 사실은 hash 아님

```java
EnumMap<DayOfWeek, String> m = new EnumMap<>(DayOfWeek.class);
m.put(MONDAY, "월");
```

- 내부적으로 `Object[]` 하나. index = `enumValue.ordinal()`.
- hash 함수 호출 zero — enum의 고정된 위치 정보 활용.
- 가장 빠른 Map 구현 — O(1) 보장, 충돌 없음, 메모리 작음.

→ enum이 key라면 무조건 EnumMap.

### 11.5 HashSet vs LinkedHashSet vs TreeSet

| | 내부 자료구조 | 순서 | 비고 |
|---|---|---|---|
| HashSet | HashMap (value = dummy) | 없음 | 일반 set |
| LinkedHashSet | LinkedHashMap | insertion | 순서 보존 |
| TreeSet | TreeMap (Red-Black) | sorted | Comparable 필수 |

HashSet의 본질은 "value를 안 쓰는 HashMap" — 메모리 약간 낭비 (dummy value). 별 신경 안 써도 됨.

### 11.6 ConcurrentSkipListMap — hash 아닌 동시성 Map

- TreeMap의 concurrent 대응. **sorted** + thread-safe.
- 내부적으로 **Skip List** (확률적 자료구조). hash 아님.
- sorted iteration이 필요한 concurrent 환경에서만 사용.

### 11.7 어떻게 고르나 — 결정 트리

```
key가 enum?
   YES → EnumMap
   NO  ↓
   
순서가 필요?
   ├─ insertion order → LinkedHashMap
   ├─ sorted          → TreeMap (single) / ConcurrentSkipListMap (concurrent)
   └─ 순서 X         ↓
   
key의 lifecycle 관리?
   ├─ key GC되면 자동 청소 → WeakHashMap
   └─ identity 비교 (==)    → IdentityHashMap
   
동시성?
   ├─ YES → ConcurrentHashMap
   └─ NO  → HashMap (기본)
```

---

## 12. 외부 생태계의 hash 활용 ⭐

> Java 표준 라이브러리 너머. 시니어가 운영하는 시스템은 hash로 둘러싸여 있다.

### 12.1 분산 시스템

#### 12.1.1 Consistent Hashing

- **Cassandra**: token ring. `partitioner = Murmur3Partitioner`가 표준. 각 node가 ring의 한 token range를 소유.
- **DynamoDB**: 마찬가지로 consistent hash. partition key의 hash로 storage node 결정.
- **Memcached client (libketama)**: client-side consistent hash. server 추가/제거 시 영향 받는 key 1/N.
- **Maglev (Google L4 LB)**: consistent hash의 변형. lookup table을 미리 빌드, 균형 더 좋음.

#### 12.1.2 Rendezvous Hashing (HRW — Highest Random Weight)

```
key k와 각 노드 n의 weight: w(k, n) = hash(k, n)
선택: argmax_n w(k, n)
```

- ring 안 만들고 매번 모든 노드와 weight 비교 → 노드 적을 땐 빠름.
- 노드 추가/제거 시 영향 = 1/N (consistent hash와 동등).
- CDN, distributed cache에서 사용.

#### 12.1.3 Kafka partitioning

```java
// DefaultPartitioner (Kafka 2.4+)
int partition = Utils.toPositive(Utils.murmur2(keyBytes)) % numPartitions;
```

- key가 있으면 `murmur2(key) % N`.
- key가 없으면 round-robin (KIP-480부터 sticky partitioner).
- **운영 함정**: partition 추가하면 같은 key가 다른 partition으로 → 순서 보장 깨짐. partition count는 처음에 신중히.

#### 12.1.4 Sharding by user_id hash

```
shard = hash(user_id) % shard_count
```

- 단순. shard 추가 시 거의 모든 데이터 이동 (naive).
- → consistent hashing 또는 직접 매핑 테이블로 진화.

### 12.2 캐시

#### 12.2.1 Redis Cluster — CRC16 slot

```
slot = CRC16(key) & 16383   // 0 ~ 16383 (총 16384 slot)
node = slot_to_node_map[slot]
```

- 16384개 slot을 노드들이 분할 소유.
- hash tag: `{user:123}:profile` 처럼 `{...}` 안만 hash → 같은 user의 키들을 같은 slot에.
- **운영 사고**: key 설계 잘못으로 slot 분포 비대칭 → 한 노드만 hot → CPU 100%. `CLUSTER COUNTKEYSINSLOT`로 진단.

#### 12.2.2 CDN cache key

```
cache_key = hash(URL + Vary headers + Cookie subset)
```

- CloudFront, Akamai, Cloudflare 모두 hash 기반 key.
- Vary 설정 잘못하면 같은 컨텐츠가 여러 key로 → cache hit rate 폭락.
- ETag도 사실상 hash (content hash 또는 timestamp hash).

#### 12.2.3 HTTP ETag

```
ETag: "5d8c72a5edda" — 보통 content hash (MD5/SHA의 prefix)
```

- 클라이언트가 다음 요청에 `If-None-Match: "5d8c72a5edda"` → 서버가 동일하면 304 Not Modified.
- 변경 감지의 표준 hash 활용.

#### 12.2.4 Java in-process cache — Caffeine

- Window TinyLFU 알고리즘. 내부적으로 frequency sketch (Count-Min Sketch — 확률적 자료구조, hash 다수 사용) + LRU window.
- 자세히는 추후 cache deep dive 챕터.

### 12.3 보안 — 일반 hash vs MAC vs KDF

이 3가지를 헷갈리는 게 시니어 보안 사고의 단골.

```
                  목적              alg 예시              핵심 차이
─────────────────────────────────────────────────────────────────
hash             무결성             SHA-256, BLAKE3      key 없음, deterministic
                                                          누구나 같은 결과
─────────────────────────────────────────────────────────────────
MAC              인증 + 무결성      HMAC-SHA256          key 필요. key 모르면
                                                          MAC 생성 불가
─────────────────────────────────────────────────────────────────
KDF              password 저장      bcrypt, scrypt,      slow + salt + work
                                   argon2, PBKDF2        factor → brute force
                                                          저항
```

#### 12.3.1 Password hash

```
저장: hash = bcrypt(password, salt, cost)
       DB에 salt + hash 저장
검증: bcrypt(input, salt, cost) == stored_hash
```

- bcrypt/scrypt/argon2 = slow hash. cost factor로 brute-force 비용 ↑.
- **절대 SHA로 password 저장 X** — GPU rainbow table에 즉시 깨짐.
- salt: 같은 password도 다른 hash. rainbow table 무력화.

#### 12.3.2 HMAC — JWT signature

```
JWT = header.payload.signature
signature = HMAC-SHA256(header.payload, secret_key)
```

- 서버가 secret으로 signature 생성. 클라이언트는 변조 불가 (secret 모름).
- HS256 = HMAC-SHA256. RS256 = RSA signature (asymmetric).
- **함정**: alg=none 공격, weak secret, key 회전 미흡.

#### 12.3.3 Merkle Tree — Git, Blockchain

```
       root_hash
       /        \
     h(AB)     h(CD)
     /  \      /  \
   h(A) h(B) h(C) h(D)
    │    │    │    │
    A    B    C    D    (file content)
```

- 어떤 leaf가 바뀌면 root까지 다 바뀜 → 무결성 검증 cheap (root만 비교).
- Git의 commit hash, blockchain의 block hash 모두 Merkle.
- Docker layer digest도 같은 패턴.

### 12.4 데이터 무결성

```
file checksum: sha256sum file.tar.gz
  → "a3f9..."
  
Git commit:    "commit a3f9..." = SHA-1(tree + parent + author + message)
Docker layer:  "sha256:a3f9..." = SHA-256(layer content)
ZFS / Btrfs:   block checksum   = Fletcher 또는 SHA
TLS:           certificate fingerprint = SHA-256(cert DER)
```

→ "동일한가?"를 묻는 모든 분산 시스템이 hash로 답한다.

### 12.5 확률적 자료구조

| 자료구조 | 답하는 질문 | 정확도 | 사용처 |
|---|---|---|---|
| **Bloom filter** | "이 element 들어있을 가능성?" | false positive O, false negative X | Cassandra row filter, CDN cache |
| **Cuckoo filter** | 위 + delete 가능 | 비슷 | Bloom의 후속 |
| **HyperLogLog** | "unique 개수 추정" | 표준오차 ~2% | BigQuery `APPROX_COUNT_DISTINCT`, Redis `PFCOUNT` |
| **Count-Min Sketch** | "frequency 추정" | 과대 추정 | Caffeine TinyLFU, traffic spike 감지 |

공통: **다수의 hash function 사용** + 작은 메모리로 큰 집합 근사.

#### 12.5.1 Bloom filter 예시

```
[k개 hash function, bit array]

   put("A"):   h1("A")=3, h2("A")=8, h3("A")=12  → bit[3]=bit[8]=bit[12]=1
   put("B"):   h1("B")=1, h2("B")=5, h3("B")=12  → bit[1]=bit[5]=1, bit[12] 그대로

   contains("A")? bit[3]&bit[8]&bit[12] = 1&1&1 → maybe yes
   contains("X")? hash 후 한 bit이라도 0 → definitely no
```

→ "확실히 없다"는 보장, "있다"는 추측. RAM 작게 쓰고 disk 접근 회피.

### 12.6 DB

#### 12.6.1 Hash index vs B-tree index

| | Hash index | B-tree index |
|---|---|---|
| 동일성 조회 (=) | O(1) | O(log N) |
| 범위 조회 (<, >, BETWEEN) | 불가 (스캔 필요) | O(log N) |
| 정렬 (ORDER BY) | 불가 | 자연 정렬됨 |
| 중복 처리 | 좋음 | 좋음 |
| 디스크 fragmentation | 나쁨 (random write) | 좋음 (sequential write) |

→ PostgreSQL은 hash index를 지원하지만 거의 안 씀. WHERE x=... 만 있고 정렬도 범위도 안 쓰는 경우만.

#### 12.6.2 Hash join

```
SQL: SELECT * FROM A JOIN B ON A.id = B.a_id;

planner의 hash join:
  1. 작은 테이블 (예: A)을 메모리에 hash map으로 빌드. key = A.id.
  2. 큰 테이블 (B)을 스캔하면서 각 row에 대해 hash map lookup.
  3. 매치되는 쌍을 emit.
  
cost: O(|A| + |B|)  (vs nested loop join O(|A| × |B|))
```

- equi-join에 최적. 범위 조건엔 무력 → merge join 또는 nested loop.
- 메모리에 hash table이 안 들어가면 disk-based hash join (성능 저하).

#### 12.6.3 Partition by hash

```sql
CREATE TABLE orders (...)
PARTITION BY HASH (user_id) PARTITIONS 16;
```

- DB 엔진이 user_id의 hash로 row를 16개 partition에 분배.
- 시간 기반 partition보다 균등하지만 archival에는 불리.

---

## 13. Hash로 인한 production 사고 ⭐⭐ (시니어 핵심)

### 13.1 Hash Flooding / Hash Collision DoS

#### 13.1.1 공격 원리

```
공격자는 같은 hashCode를 가지는 N개의 key를 미리 계산
  (String의 multiplicative hash는 충돌을 수학적으로 쉽게 만들 수 있음)

1 HTTP request에 form param 10000개 (모두 같은 hashCode)
  → 서버: HashMap<String, String> params = ...
  → 10000번 put → 같은 bucket에 chain 10000개
  → put N번째의 비용 = O(N) (chain 검색) → 총 O(N²) = 10^8
  → CPU 100%, response 못 함
```

#### 13.1.2 역사

- **2003** — Crosby/Wallach 논문 *Denial of Service via Algorithmic Complexity Attacks*.
- **2011 28C3** — Alexander Klink, Julian Wälde가 PHP/Python/Ruby/Java/ASP.NET 모두 영향 받음을 공개 발표.
- 즉시 모든 언어가 패치 시도:
  - PHP 5.3.9: `max_input_vars` 제한.
  - Python 3.3: per-process random seed.
  - Java 7u40: alternative hashing (특정 임계 이상이면 다른 hash 사용) → 호환성 문제로 부분 해제.
  - Java 8: tree 변환으로 worst case O(log N) — **사실상의 정답**.

#### 13.1.3 JDK 8 tree가 완전한 해법인가?

거의 그렇지만 완전하지 않다.

```java
// Comparable 안 구현한 custom key
class BadKey {
    @Override public int hashCode() { return 1; }  // 모두 같은 hash
    @Override public boolean equals(Object o) { return ...; }
    // Comparable 미구현
}

HashMap<BadKey, String> m = new HashMap<>();
// chain ≥ 8 도달 시 treeify 시도 — 그러나 Comparable 없으면 tree에서도 비교 불가
// → 결국 list로 처리 → O(N) 충돌 잔존
```

→ **사용자 정의 key의 hashCode가 poor + Comparable 미구현이면 여전히 취약**.

권고:
- public API에서 들어오는 input을 직접 hashMap key로 쓰지 말 것.
- 외부 input은 sanitize / canonicalize 후 key로.
- 또는 Map.of (immutable, salted hashing) 사용 — JDK 9+.

#### 13.1.4 실제 사고 사례

- **Servlet form param** — Tomcat이 form param을 `Map<String, String[]>`에 저장. 공격자가 모든 param에 collision key 보내면 서버 CPU 폭주. Java 8 이전엔 Tomcat에서 `maxParameterCount` 제한 도입.
- **JSON parser** — Jackson/Gson이 JSON object를 `LinkedHashMap`에 저장. 공격자가 nested JSON에 collision key 만들면 동일 패턴.
- **HTTP header 파싱** — header name을 case-insensitive map에 저장. lowercase key에 collision 만들면 공격 가능.

운영 시그널:
```
- 특정 endpoint 호출 시 CPU 100%
- thread dump에서 다수 thread가 HashMap.putVal / getNode에 머무름
- input size에 비해 처리 시간 비선형 증가
```

### 13.2 Mutable Key 함정

```java
class MutableKey {
    String name;
    public MutableKey(String n) { this.name = n; }
    @Override public int hashCode() { return name.hashCode(); }
    @Override public boolean equals(Object o) {
        return o instanceof MutableKey && ((MutableKey)o).name.equals(name);
    }
}

MutableKey k = new MutableKey("A");
Set<MutableKey> set = new HashSet<>();
set.add(k);
k.name = "B";          // ★ 변경

set.contains(k);       // ★ false! 새 hash로 다른 bucket
set.remove(k);         // ★ false! 못 찾음 → leak
```

- **사라진 entry**: set에 분명히 있는데 못 찾음. memory leak.
- **JPA / Hibernate에서 ID가 null인 entity를 set에 넣은 후 ID 할당** — 동일 함정.

권장:
- key는 immutable. final field만.
- 변경 가능한 객체는 key 말고 value로.
- Lombok 사용 시 `@EqualsAndHashCode(of = {"id"})` 로 immutable identifier만.

### 13.3 Poor hashCode 분포

#### 13.3.1 Long.hashCode 함정

```java
public static int hashCode(long value) {
    return (int)(value ^ (value >>> 32));
}

// 작은 양수 long의 hash
0L.hashCode()       == 0
1L.hashCode()       == 1
2L.hashCode()       == 2
...
1000000L.hashCode() == 1000000
```

→ 작은 양수 Long은 자기 자신과 같은 hash. table size 16에서:
- 1, 17, 33, 49 모두 같은 bucket (lower 4 bit 같음).
- spread function `h ^ (h >>> 16)` 덕에 large value는 OK. 작은 값들은 여전히 lower bit 패턴 노출.

production 영향: `HashMap<Long, ...>` with 작은 양수 ID들 → 미세하지만 측정 가능한 cluster.

#### 13.3.2 BigInteger.hashCode 비용

```java
public int hashCode() {
    int hashCode = 0;
    for (int i = 0; i < mag.length; i++)
        hashCode = (31 * hashCode + (mag[i] & LONG_MASK));
    return hashCode * signum;
}
```

- 큰 BigInteger는 hash 계산이 O(digits) — 매 호출마다.
- caching 없음.
- 자주 hash 호출되는 hot path에 BigInteger key 쓰면 CPU 폭증.

대안: 외부에서 hash 계산해서 cache, 또는 String으로 변환 (String은 hash cache).

#### 13.3.3 큰 객체의 hashCode 매번 계산

```java
class Order {
    List<OrderItem> items;     // 100개 item
    @Override public int hashCode() {
        return Objects.hash(items);   // List.hashCode = sum of element.hashCode
    }
}
```

- `Order`를 HashMap key로 → 매 put/get마다 100개 item.hashCode 호출 → CPU.

대안:
- 식별자(`id`)만 hashCode에.
- 또는 Lombok `@EqualsAndHashCode(cacheStrategy = LAZY)` — 한 번 계산 후 캐싱.

### 13.4 HashMap 동시성 사고 — JDK 7의 무한 루프

```
JDK 7 HashMap.transfer (resize 시):
  - linked list를 새 table로 이동하면서 head insertion 사용
  - 두 thread가 동시에 resize → list가 cyclic
  - 다음 get에서 영원히 list 순회 → CPU 100%, response 못 함
```

- **실제 사고**: 2014년 LinkedIn engineering blog에 보고된 사례 등 다수.
- JDK 8: tail insertion + high-bit split → cyclic list는 사라짐. 그러나 **size 정합성**은 여전히 깨짐 (size++가 atomic이 아님).

결론: **HashMap은 단 한 줄도 concurrent write 안 됨**. 동시성 필요하면 ConcurrentHashMap.

### 13.5 ConcurrentHashMap 함정

#### 13.5.1 size()는 weakly consistent

```java
ConcurrentHashMap<K, V> chm = new ConcurrentHashMap<>();
// 다른 thread가 put 중
int s = chm.size();   // ★ 정확한 값 보장 X (snapshot of counterCells)
```

- 통계용 OK. 정확한 카운트 필요한 비즈니스 로직엔 부적합.

#### 13.5.2 iterator weakly consistent

- iterate 중 추가/삭제된 entry는 보일 수도, 안 보일 수도.
- HashMap의 fail-fast `ConcurrentModificationException`은 안 던짐.
- 정확한 snapshot이 필요하면 `new HashMap<>(chm)` 으로 copy.

#### 13.5.3 computeIfAbsent 안에서 같은 key 재귀

```java
chm.computeIfAbsent("A", k -> {
    chm.computeIfAbsent("A", k2 -> "value");   // ★ 같은 key 재귀
    return "outer";
});
```

- JDK 8: 무한 wait (deadlock-like).
- JDK 9+: `IllegalStateException` throw.

핵심: compute 함수는 짧고, 같은 map의 같은 bucket을 건드리지 말 것.

### 13.6 Autoboxing in HashMap<Long, ...>

```java
HashMap<Long, Value> map = new HashMap<>();
long id = 123L;
map.put(id, v);     // ★ long → Long boxing → Long.valueOf(123L) → 매번 new Long
map.get(id);        // ★ 또 boxing
```

- boxing 비용: small (Long cache -128~127) 외엔 new 객체 alloc.
- hashCode 비용: `Long.hashCode()` (위 13.3.1 분포 문제).
- GC 압박: boxing 객체들이 Young gen에 쌓임.

production 영향: 수백만 op/s 환경에서 measurable. JFR allocation profiling에서 `java.lang.Long` top 5 안에 등장.

대안: primitive map.
- **Eclipse Collections**: `LongObjectHashMap<V>`
- **Koloboke**: `HashLongObjMap<V>`
- **fastutil**: `Long2ObjectOpenHashMap<V>`

이들은 내부적으로 `long[]` + `Object[]` 두 배열로 entry 저장 (open addressing). boxing 없음, cache locality 우수, hashCode 직접 mix.

### 13.7 메모리 관점 — HashMap의 retained size

```
HashMap with N entries:
  - table[] = (N / 0.75) reference slots
  - Node[N] = 각 32 bytes 정도 (hash + key ref + value ref + next ref + object header)
  - + key, value 자체

shallow size (HashMap 객체만): ~48 bytes
shallow size (table[]): capacity × 4 bytes (compressed oops)
retained size (모든 entry 포함): N × (32 + key.shallow + value.shallow) + table

대략:
  HashMap<Long, String> 100만 entry
  = 1M × (32 + 24 + ~50)  ≈  100 MB
                 ↑    ↑
                Long  String shallow size
```

운영 시 heap dump 분석에서 `HashMap`이 retained size 1위 → 보통 cache가 자라거나 cleanup 안 되는 패턴.

### 13.8 WeakHashMap cleanup 지연

- cleanup이 lazy — `get/put/size` 호출 시에만 stale entry 청소.
- 안 건드리면 dead key entry가 계속 누적.
- 사용 패턴이 "한 번 넣고 다시 안 봄"이면 메모리 누수.

대안:
- 명시적 cleanup 호출 (예: scheduled).
- 또는 Caffeine의 `weakKeys()` — backend가 더 적극적 cleanup.

### 13.9 운영 시나리오 종합

#### 시나리오 A: "특정 사용자만 응답이 느려요"

진단:
1. APM (Datadog/NewRelic) — 그 사용자의 endpoint latency만 spike.
2. thread dump — 그 request의 thread가 HashMap.getNode에 머무름.
3. 원인 — 그 user_id의 hash가 우연히 cluster를 만듦 (rare).

해결:
- key 분포 측정: `keys.stream().collect(groupingBy(k -> k.hashCode() & 15, counting()))` 로 bucket 분포 확인.
- bucket이 비대칭이면 key의 hashCode 재설계.
- 또는 사용자 분류를 hash 기반에서 다른 partitioning으로.

#### 시나리오 B: "Redis Cluster의 한 node CPU만 100%"

진단:
1. `redis-cli -h <node> --hotkeys` — hot key 확인.
2. `CLUSTER COUNTKEYSINSLOT <slot>` — slot별 key 분포.
3. 원인 — hash tag `{user_id}` 사용 시 한 사용자에 모든 데이터 몰림.

해결:
- hash tag를 더 세분화 (`{user_id:type}`).
- 또는 hot data를 multiple key로 분산.

#### 시나리오 C: "Heap dump에서 ConcurrentHashMap이 retained 1위"

진단:
1. MAT으로 incoming reference 추적.
2. 어떤 cache인지 확인. eviction 정책 있는지.
3. key가 살아있는 이유 — strong reference chain.

해결:
- Caffeine으로 교체 (eviction + size limit + expire).
- 또는 명시적 cleanup 도입.
- key가 ClassLoader 관련이면 WeakHashMap 또는 ClassValue로.

#### 시나리오 D: "form param 파싱에서 CPU 폭주"

진단:
1. async-profiler — `HashMap.putVal` 또는 `Hashtable.put` top.
2. request body 확인 — form param 수가 비정상적으로 많은가.
3. param key들이 collision 패턴인가 (같은 hashCode).

해결:
- Tomcat `maxParameterCount` 설정 (default 10000 in 9+).
- WAF 또는 reverse proxy에서 큰 form 차단.
- input validation strengthen.

#### 시나리오 E: "Kafka consumer lag이 특정 partition만 누적"

진단:
1. consumer group의 partition별 lag 확인.
2. 그 partition에 message 분포 확인.
3. producer의 key 분포 확인 — `murmur2(key) % N` 결과.

해결:
- producer key를 더 균등 분포로.
- 또는 partition 수 증가 (변경의 cost는 큼).
- 또는 partition별 consumer 추가.

---

## 14. 측정·진단 도구

### 14.1 jcmd <pid> GC.class_histogram

```bash
jcmd <pid> GC.class_histogram | grep -E "HashMap|Node"

  #instances    #bytes  class name
  -------------------------
  3,245,879   103 MB    java.util.HashMap$Node
    876,234    21 MB    java.util.HashMap
    456,789    11 MB    java.util.concurrent.ConcurrentHashMap$Node
```

→ HashMap.Node가 비정상적으로 많으면 어딘가 map이 자라고 있음.

### 14.2 Heap dump + Eclipse MAT

```bash
jcmd <pid> GC.heap_dump /tmp/heap.hprof

# MAT에서 열기
# Histogram → java.util.HashMap → Group by class loader
# Path to GC roots → cache 객체 추적
# Dominator Tree → retained size 큰 객체 확인
```

전형적 패턴:
- 하나의 `static HashMap` 또는 `Spring bean의 instance HashMap`이 1위.
- key가 `String` 또는 `Class` 인스턴스 → ClassLoader leak (→ Metaspace 누수 가능).

### 14.3 async-profiler

```bash
# CPU profiling
./profiler.sh -d 30 -f profile.html <pid>

# Allocation profiling
./profiler.sh -d 30 -e alloc -f alloc.html <pid>

# wallclock (blocking 포함)
./profiler.sh -d 30 -e wall -f wall.html <pid>
```

볼 것:
- `HashMap.hash` 또는 `HashMap.putVal`이 top → hash 비용 큼.
- `Object.hashCode` 비중이 큼 → 비싼 hashCode (BigInteger 류).
- allocation에서 `HashMap$Node` 또는 `Long`/`Integer` 큼 → autoboxing 또는 map 빈번 생성.

### 14.4 Caffeine cache stats

```java
CaffeineCache<K, V> cache = Caffeine.newBuilder()
    .recordStats()
    .build();

// 운영 중
CacheStats s = cache.stats();
s.hitRate();        // hit ratio
s.evictionCount();  // 얼마나 자주 쫓아냈나
s.loadCount();      // 새로 load한 횟수
```

hit rate < 50% → cache 효과 부족, 크기/expire 조정 필요.
eviction count 폭주 → working set이 cache 크기 초과.

### 14.5 Redis 진단

```bash
# slot 분포
redis-cli -c CLUSTER COUNTKEYSINSLOT 0
redis-cli -c CLUSTER COUNTKEYSINSLOT 1
...

# 또는 한 번에
for i in {0..16383}; do
  echo "$i $(redis-cli CLUSTER COUNTKEYSINSLOT $i)"
done | sort -k2 -n -r | head

# hot key
redis-cli --hotkeys
```

분포가 비대칭 → key 설계 재검토.

### 14.6 hash 충돌률 직접 측정

```java
// 어떤 key set의 hash 분포 확인
List<String> keys = ...;
int capacity = 16;
Map<Integer, Long> bucketDist = keys.stream()
    .collect(Collectors.groupingBy(
        k -> (k.hashCode() ^ (k.hashCode() >>> 16)) & (capacity - 1),
        Collectors.counting()
    ));
System.out.println(bucketDist);
// 균등하면 모두 비슷한 count. 비대칭이면 hash 분포 나쁨.
```

부하 테스트 전 input set의 hash 분포 점검은 좋은 습관.

---

## 15. 운영 best practice 정리

### 15.1 일반 룰

1. **Map key는 immutable** — String, Long, UUID, java.time, custom value object (final fields).
2. **hashCode는 stable identifier 기반** — Lombok `@EqualsAndHashCode(of = {"id"})`.
3. **큰 Map은 initial capacity 지정** — `new HashMap<>((int)(expectedSize / 0.75) + 1)`.
4. **동시성에는 ConcurrentHashMap** — HashMap을 동기화 wrap (Collections.synchronizedMap)은 throughput 한계.
5. **외부 input을 직접 key로 쓰지 말 것** — hash flooding 방어.
6. **primitive map은 fastutil/Eclipse Collections** — autoboxing 비용이 측정 가능할 때.

### 15.2 cache 설계

7. **반드시 size limit + expire** — unbounded cache는 시한폭탄.
8. **Caffeine 기본 — Guava Cache는 deprecated 권고**.
9. **hit rate 50% 미만이면 재검토** — cache는 hit rate가 가치.
10. **WeakHashMap은 lifecycle 명확할 때만** — cleanup 보장 안 됨.

### 15.3 분산 환경

11. **partition key 설계 시 hash 분포 먼저 측정** — Kafka, Redis slot, DB partition.
12. **consistent hashing 사용 시 virtual node 활용** — 분포 균형.
13. **password는 무조건 bcrypt/scrypt/argon2** — SHA로 저장하면 보안 사고.
14. **JWT secret은 강력하고 회전** — HMAC은 secret 길이가 보안 강도.

### 15.4 진단 루틴

15. **JFR + async-profiler를 평소에 운영** — 사고 후가 아니라 평소에 baseline.
16. **heap dump 분석을 능숙히** — MAT incoming reference / dominator tree.
17. **GC log에 allocation rate 추적** — boxing 패턴 발견.
18. **Caffeine `recordStats` + Prometheus 노출** — cache 효과 가시화.

---

## 16. 면접 단골 질문 + 운영 시나리오

### 16.1 개념 — "왜?"에 답하기

#### Q1. HashMap이 어떻게 O(1)인가?
> 평균적으로 hash가 uniform 분포라는 가정 하에 chain 길이가 작은 상수(평균 α ≈ 0.75). amortized O(1) — 가끔의 resize 비용이 N개 op에 분산됨. worst case는 O(N), JDK 8에서 chain 길이 ≥ 8 + table ≥ 64이면 tree로 변환해 worst case O(log N) 완화.

#### Q2. 동시 환경에서 HashMap이 안전한가?
> No. JDK 7에서는 동시 resize가 cyclic linked list를 만들어 100% CPU 무한 루프 발생 (실제 사고 다수). JDK 8에서 알고리즘이 바뀌어 cyclic은 사라졌지만 size 정합성은 여전히 깨짐. 동시성에는 ConcurrentHashMap (per-bucket CAS + synchronized) 또는 외부 동기화 필수.

#### Q3. Load factor 0.75인 이유?
> 시간 vs 공간 trade-off의 sweet spot. Knuth의 분석에서 영감. 더 작으면(0.5) 메모리 낭비, 더 크면(1.0) 충돌 폭증. 0.75는 평균 chain 길이가 작고 resize 빈도가 합리적인 균형점. JDK 도입 이후 산업 표준으로 굳어짐.

#### Q4. Tree 변환 임계 8인 이유?
> uniform random hash에서 chain 길이가 8 이상일 확률이 Poisson(λ=0.5)로 약 백만분의 일. 즉 정상 분포에서는 사실상 발생 안 함. 8에 도달했다는 건 분포가 adversarial (= hash flooding) 또는 hashCode가 매우 poor — 그때만 tree로 변환해 worst case O(log N) 보장. untreeify 임계 6은 oscillation 방지 hysteresis.

#### Q5. 31을 곱하는 이유?
> Odd prime이라 lower bit 0 패턴 방지 + 인수분해 어려움. `31 * h == (h << 5) - h` 비트 shift 최적화. Joshua Bloch의 실험에서 통계적 분포가 좋았던 prime. 37, 41 등 다른 후보도 가능하지만 31이 관습.

### 16.2 깊이 — 코드 레벨

#### Q6. JDK 8 HashMap이 hash spread function을 쓰는 이유?
> table size가 2^n이고 index가 `hash & (n-1)`이므로 lower n bit만 사용됨. 좋은 hashCode라도 upper bit가 lower로 안 흘러가면 충돌 발생. `(h ^ (h >>> 16))`는 한 줄로 upper 16 bit를 lower 16 bit로 XOR redistribute → 작은 table에서도 upper bit 영향력 확보.

#### Q7. JDK 8 HashMap resize에서 entry를 어떻게 분리하나?
> capacity가 2배 (예: 16→32) 늘어나면 새 index는 lower bit가 하나 더 의미를 가짐 (bit 4). 각 entry의 `hash & oldCap` (=16)이 0이면 같은 index, 1이면 (index + oldCap)으로 — 한 번의 비트 AND로 두 그룹 분리. 재해시 함수 호출 zero. 이게 power of 2 capacity의 장점.

#### Q8. ConcurrentHashMap이 null을 금지하는 이유?
> Doug Lea의 답: `get(k)`가 null을 돌려줄 때 두 가지 의미가 있다 — key 없음 vs value가 null. 단일 thread에선 `containsKey`로 구분 가능. concurrent에선 두 호출 사이에 다른 thread가 put할 수 있어 구분 자체가 race condition. 그래서 null 금지로 명확화. HashMap은 단일 thread 가정이라 null 허용.

#### Q9. ConcurrentHashMap의 size()가 정확하지 않은 이유?
> 내부에 counterCells (LongAdder 패턴의 striped counter)로 size를 관리. high contention 환경에서 단일 atomic counter 대신 cell별로 add → contention 분산. 그러나 sumCount는 모든 cell을 더하는 동안 다른 thread가 계속 add → snapshot이 stale. weakly consistent. 통계용 OK, 비즈니스 critical count로는 부적합.

### 16.3 운영 — production 시나리오

#### Q10. Production에서 HashMap.put이 hot path top에 잡힌다. 어떻게 진단하나?
> 1) async-profiler로 정확히 어느 호출 path인지 (어떤 비즈니스 로직의 put인지). 2) 그 map의 key 타입과 hashCode 구현 확인 — poor hashCode 또는 비싼 hashCode (BigInteger 류) 여부. 3) map의 size 추이 — 무한 증가면 leak 가능성. 4) initial capacity 미지정으로 resize가 잦지 않은가. 5) autoboxing 발생 여부 (allocation profiling). 보통은 (a) 자주 호출되는 hot loop에서 매번 new HashMap, (b) 비싼 hashCode, (c) resize 폭주 — 셋 중 하나.

#### Q11. "특정 user만 응답 느림" — hash collision 의심. 어떻게 확인하나?
> 1) 그 user의 ID들과 다른 user들의 ID들을 모아서 hashCode 분포 측정. 2) `(h ^ h>>>16) & (capacity-1)`로 실제 bucket index 계산해서 그룹화. 3) 특정 user의 ID들이 한 bucket으로 몰리면 hash collision. 4) 해결: user ID 생성 방식 재검토 또는 key를 다른 식별자로 (그러면 hashCode 분포 달라짐). 실무에서 이런 경우는 드물고, 대부분은 cache 누수 또는 DB 인덱스 문제.

#### Q12. JDK 7에서 8로 업그레이드 후 ConcurrentHashMap 동작 차이?
> 1) lock granularity가 segment → bucket으로 변경 → 동시성 ↑. 2) size()가 segment 합 → counterCells 합으로 변경 (둘 다 weakly consistent). 3) computeIfAbsent 등 atomic API 추가. 4) JDK 8부터 resize는 multi-thread cooperative (helpTransfer). 5) JDK 9+에서 compute 안 recursive update가 명확히 IllegalStateException. 대부분은 호환되지만 size 정확성이나 reflection으로 내부 segment 접근하던 코드는 영향.

---

## 17. 꼬리질문 (3단)

### 17.1 1단 — 개념

**Q1. `equals == true`이면 `hashCode`가 같아야 한다는 계약은 왜 비대칭인가?**
> HashMap이 key를 찾을 때 먼저 hashCode로 bucket 찾고, 그 bucket의 chain에서 equals로 매치. 따라서 equals true인데 hashCode가 다르면 다른 bucket이라 영원히 못 찾음. 반대로 hashCode 같고 equals false는 같은 bucket의 다른 entry로 처리되므로 OK. hashCode는 좌표, equals는 일치 — 역할 분담의 결과.

**Q2. `HashSet`이 내부적으로 `HashMap`을 쓴다는 게 무슨 의미?**
> `HashSet<E>`는 `HashMap<E, Object>`를 wrap. element를 key로, value는 dummy `PRESENT` static 객체로 저장. add/remove/contains 모두 HashMap 메서드 호출. 메모리 약간 낭비(dummy value reference 1개) 외엔 동일.

**Q3. `LinkedHashMap`이 access order mode면 어떻게 동작?**
> 내부 doubly-linked list에서 각 get/put 호출 시 해당 노드를 list의 tail로 이동. head 쪽이 "가장 오래 안 쓰임", tail 쪽이 "최근 사용". `removeEldestEntry(eldest)` override로 size 한도 넘으면 head 자동 제거 → LRU cache 구현.

### 17.2 2단 — 운영/진단

**Q4. Production heap dump를 분석해보니 `ConcurrentHashMap` retained size가 1위(2GB)다. 어떻게 진단할까?**
> 1) Eclipse MAT 'Dominator Tree' → 그 chm의 incoming reference 추적. 어느 static 또는 bean이 들고 있는지. 2) Histogram에서 그 chm 안의 key/value 타입 확인. 3) 만약 key가 `Class` 또는 ClassLoader 객체면 ClassLoader leak (자세히는 jvm/02-runtime-data-areas/01-heap-and-tlab.md 참조). 4) 일반적으론 cache가 unbounded — size limit, expire, eviction 정책 부재. 5) 해결: Caffeine으로 교체 (`maximumSize`, `expireAfterWrite`), 또는 cleanup 로직 추가, 또는 WeakReference 활용. 6) JFR로 추가 add 패턴 확인 (allocation rate 측정).

**Q5. Tomcat이 `Map<String, String[]> parameterMap`을 만들 때 hash flooding 공격이 가능하다. 어떻게 방어?**
> 1) `maxParameterCount` (Tomcat 9+ default 10000) — 한 request의 param 수 제한. 2) `maxPostSize`로 request body 자체 제한. 3) WAF/reverse proxy(nginx) 단계에서 비정상 큰 form 차단. 4) JDK 8 tree 변환으로 worst case O(N log N) — 완전 방어는 아님 (Comparable 미구현 key는 list로 잔존, String은 Comparable이라 OK). 5) 평소 input validation 강화 — 사용자가 임의 key 이름 만드는 endpoint는 위험.

**Q6. `HashMap<Long, V>`에서 hash 분포가 나쁘다고 가정. 어떻게 측정하고 어떻게 해결?**
> 1) 측정: 실제 key set의 hashCode를 spread function 적용 후 `& (capacity-1)`로 bucket index 계산. groupingBy + counting으로 분포 확인. 정상이면 비슷한 count, 비대칭이면 cluster. 2) Long.hashCode는 `(int)(value ^ (value >>> 32))` — 작은 양수 값은 자기 자신과 같음. 작은 양수 ID들이 lower bit 충돌 가능. 3) 해결 1: spread function이 이미 upper bit를 lower로 mix하므로 대부분 OK. 4) 해결 2: 정 분포가 나쁘면 ID 생성 방식 변경 (UUID 또는 hash) 또는 primitive map (fastutil) 사용.

### 17.3 3단 — 심화

**Q7. HashMap의 `(h ^ (h >>> 16)) & (n-1)`에서 만약 `n-1`이 0xFFFF (capacity 65536)이라면 spread function의 효과가 어떻게 달라지나?**
> capacity = 2^16 = 65536이면 mask가 `0xFFFF` — lower 16 bit 전체 사용. spread function `h ^ (h >>> 16)`이 만든 lower 16 bit는 (original lower) XOR (original upper). 결과적으로 모든 32 bit가 영향을 미친 lower 16 bit를 사용 → 분포 매우 좋음. capacity가 작을수록 (예: 16, mask 0x0F) 더 적은 bit만 보지만 spread가 mix해놨으므로 좋은 hashCode면 OK. spread function은 작은 capacity 보호용.

**Q8. ConcurrentHashMap이 `synchronized(firstNode)`로 lock을 잡는다. 만약 두 thread가 다른 key를 put하는데 hash가 같은 bucket이면 어떻게 되나?**
> 같은 bucket이라 같은 firstNode를 monitor lock으로 잡으려 함 → 한 thread가 lock 잡고 chain 탐색/put 진행, 다른 thread는 BLOCKED. bucket 단위 lock의 한계 — 같은 bucket의 다른 key는 동시 처리 불가. 그러나 capacity가 충분히 크면 (수천 bucket) 다른 key가 같은 bucket일 확률 낮음 → 사실상 lock-free에 가까운 throughput. resize로 capacity가 늘어나면 lock contention 완화.

**Q9. JDK 9 `Map.of(...)`가 salted hashing을 쓴다는 게 어떤 의미? hash flooding 방어가 어떻게 동작?**
> JVM 시작 시 process-wide random salt 생성. `Map.of`로 만든 immutable map의 hash는 `key.hashCode() ^ salt` 같은 식으로 변형. 결과: 같은 key set이라도 process마다 다른 bucket 분포. 공격자가 미리 collision key 계산해도 server마다 다른 salt라 무력화. 단점: 그 map의 hashCode는 process마다 다름 → 외부 저장/직렬화 시 변동. immutable이라 GC 이전에 단명한 map에 적합. HashMap은 salt 없음 (mutable + 호환성).

**Q10. `ConcurrentSkipListMap`이 hash 안 쓰는데도 concurrent로 동작하는 원리는?**
> Skip list = probabilistic balanced search tree (확률적으로 BST의 효과를 내는 multi-level linked list). 각 노드가 여러 level의 next pointer를 가져 search/insert가 평균 O(log N). 노드 추가/제거가 모두 CAS로 가능 — 노드 간 next pointer를 atomically 갱신. lock-free. trade-off: sorted (TreeMap 같은 API), hash 안 써서 worst case도 O(log N), 메모리 약간 큼 (multi-level pointer). ConcurrentHashMap이 unordered에 hash기반인데 비해 ConcurrentSkipListMap은 ordered에 CAS 기반.

---

## 18. 마무리 — 백지 마스터 체크리스트

이 문서를 닫고 백지에 다음을 그릴 수 있는가?

- [ ] Hash 함수의 4가지 성질 (deterministic / uniform / avalanche / one-way) + crypto vs non-crypto 차이
- [ ] HashTable의 separate chaining vs open addressing 그림 + Java가 chaining을 택한 이유
- [ ] Load factor 0.75 + amortized O(1)의 정확한 의미 (resize 비용 분산)
- [ ] Object.hashCode/equals 5계약 + 비대칭 이유 (equals→hashCode 동일 필수, 역은 X)
- [ ] HashMap (JDK 8) bucket index 계산: `(h ^ h>>>16) & (n-1)` + 왜 spread function 필요한지
- [ ] Treeify 임계 8의 통계적 근거 (Poisson 분포, 백만분의 일)
- [ ] Resize의 high-bit split — `e.hash & oldCap` 한 비트로 low/high 그룹 분리
- [ ] ConcurrentHashMap (JDK 8): per-bucket CAS empty set + synchronized(firstNode) + helpTransfer + counterCells
- [ ] JDK 7 → 8 ConcurrentHashMap의 변화 이유 (segment의 한계)
- [ ] null 금지의 Doug Lea 논리 (containsKey vs get 모호성)
- [ ] String hashCode `31 * h + c` + 31 선택의 3가지 이유 + lazy caching + empty string 함정
- [ ] LinkedHashMap의 access order = LRU 구현 패턴
- [ ] WeakHashMap의 lazy cleanup + ClassValue 활용
- [ ] IdentityHashMap이 open addressing인 이유
- [ ] EnumMap이 hash 아닌 ordinal 기반인 이유
- [ ] Consistent hashing ring 그림 + virtual node + 1/N 영향
- [ ] Kafka murmur2, Redis CRC16, Cassandra Murmur3 — 각각 어떤 hash 어디 쓰는지
- [ ] Bloom filter 그림 + multiple hash + false positive only
- [ ] Hash flooding 공격 시나리오 (form param 10K collision) + 28C3 + Java 7/8 대응
- [ ] Mutable key 함정 + JDK 7 ConcurrentHashMap cycle 사고
- [ ] Long.hashCode poor 분포 + autoboxing 비용 + primitive map 대안
- [ ] ConcurrentHashMap weakly consistent (size, iterator) + computeIfAbsent recursive 함정
- [ ] 진단: jcmd GC.class_histogram / MAT incoming reference / async-profiler / Caffeine stats / Redis CLUSTER COUNTKEYSINSLOT
- [ ] best practice 18가지 (immutable key / initial capacity / ConcurrentHashMap / bounded cache / partition key 분포 측정 / password bcrypt / ...)

이 항목들이 모두 술술 나오면 hash 마스터다. 막힘이 있으면 그 장으로 돌아간다.

---

## 19. 관련 자료 / 다음 단계

### 19.1 외부 챕터 연결

| 외부 챕터 | 어떻게 이어지나 |
|---|---|
| `jvm/02-runtime-data-areas/02-metaspace-and-class-space.md` | String intern pool, ClassLoader cache가 hash 기반 — `-XX:StringTableSize` 함정 |
| `jvm/03-execution-engine/` (예정) | JIT inline cache, megamorphic call site dispatch |
| `jvm/04-gc/` (예정) | WeakHashMap의 cleanup이 GC 동작과 연동 |
| `java-deep-dive/03-threads.md` | ConcurrentHashMap의 weak iterator, compute atomic 보장 |
| `java-deep-dive/02-reflection.md` | reflection cache (Method/Constructor lookup table) |
| `network-request-lifecycle/` 류 | LB consistent hashing, CDN cache key, Redis cluster slot |

### 19.2 깊이 더 들어가려면

- OpenJDK source: `src/java.base/share/classes/java/util/HashMap.java`, `ConcurrentHashMap.java`
- Doug Lea의 `concurrency-interest` 메일링 리스트 archive — ConcurrentHashMap 설계 의도
- *Effective Java* (Joshua Bloch) Item 10, 11 — equals/hashCode 계약
- *Java Concurrency in Practice* (Brian Goetz) — ConcurrentHashMap 챕터
- *The Art of Computer Programming* Vol. 3 (Knuth) — sorting and searching, hash 수학
- 28C3 발표: "Effective Denial of Service attacks against web application platforms" (Alexander Klink, Julian Wälde, 2011)
- Cliff Click 블로그 — non-blocking HashMap의 lock-free 구현

### 19.3 다음 학습 후보

- **06. Generics + Hashing 교차** — `Map<? extends K, ? extends V>` 와 wildcard hash 동작
- **07. Annotation processing + Map** — 컴파일 시점 hash 활용 (registered processors)
- **08. Caffeine 깊이** — Window TinyLFU 알고리즘, frequency sketch, segmented LRU
- **09. Distributed Hash Tables 깊이** — Chord, Kademlia, DHT 프로토콜

---

> 이 문서를 다 읽었다면, 이제 hash라는 단어를 들었을 때 머릿속에 자동으로 떠올라야 한다:
> "bucket array + chain (또는 tree) + load factor 0.75 + hashCode 5계약 + production 사고 패턴 + 분산/캐시/보안 생태계 전체."
>
> 이게 시니어가 hash를 "안다"는 의미다.
