# 02-06. GC Bookkeeping & 기타 JVM 내부 — 보이지 않는 메모리

> Heap이 100GB라면 GC를 위한 부속 자료구조는 얼마를 차지하는가?
> 답: Card Table은 Heap의 약 **0.2%**, Mark Bitmap은 **1.5%**, G1의 Remembered Set은 워크로드 따라 **5~20%까지 폭증**. 100GB Heap이면 RSet만 5~20GB를 native에 더 쓴다.
> "왜 100GB Heap을 잡았는데 RSS가 120GB?" 같은 질문의 답은 이 챕터에 있다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증**.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"GC Bookkeeping은 'Old→Young 참조'와 'concurrent marking 정확성'을 효율적으로 추적하기 위한 native 자료구조 모음이다. GC 시간을 메모리와 교환한다."**

이 한 문장에서 모든 답변이 출발한다.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: GC bookkeeping = 시간↔메모리 교환]
                                    │
       ┌─────────┬──────────────┬───┴───┬──────────────┬─────────┐
       │         │              │       │              │         │
      ① WHY    ② Card Table   ③ RSet  ④ Mark Bitmap  ⑤ Write   ⑥ 운영/
   Generational                 (G1)   + SATB         Barrier   ZGC
   가설 vs                                                       특수
   Old 100GB
       │         │              │       │              │         │
       │    ┌────┼────┐     ┌───┼───┐  ┌─┼─┐      ┌────┼────┐    │
    Old→Young Heap/512 region당 3-tier Heap/64  pre/post  Colored Symbol
    문제     dirty bit  sparse/   prev/  SATB     barrier  Pointer Table
    Card vs  precision  fine/    next   queue     5~15%   Forward  String
    RSet     vs cost    coarse   bitmap Floating  overhead Table   Table
                       워크로드  G1 2개 garbage          Multi-map ZGC
                       1~20%
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY** | Generational GC의 Old→Young 참조 추적 문제 | Card Table vs RSet 보완 관계 | "시간을 메모리와 교환" |
| **② Card Table** | 512B 단위 카드, 1바이트 표시 | Heap/512 (~0.2%) | dirty card만 스캔 |
| **③ RSet (G1)** | region별 "어디서 가리키나" 목록 | 3-tier: Sparse/Fine/Coarse | 워크로드 따라 1~20% 변동 |
| **④ Mark Bitmap + SATB** | Heap/64 (~1.5%), G1은 2개 (prev/next) | SATB pre-write barrier | Floating garbage |
| **⑤ Write Barrier** | pre/post barrier 자동 삽입 | Card Queue, Refinement thread | mutator 5~15% overhead |
| **⑥ 운영/ZGC 특수** | Symbol/String Table, CLDGraph | ZGC colored pointer + multi-mapping | pmap 3배 함정 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — 왜 부속 자료구조가 필요한가

### 1.1 핵심 질문

> "Generational GC가 왜 Card Table, RSet 같은 부속 자료구조를 필요로 하나요?"

### 1.2 키워드 1 — Old → Young 참조 추적 문제

```
Generational GC의 가정:
  Young Gen은 자주 청소, Old Gen은 가끔 청소

Young GC 시 reachability를 정확히 계산하려면:
  GC Roots (Stack/Static)에서 따라가는 객체
  + ★ Old → Young 참조도 살아있어야

문제:
  Old gen이 100GB라면 매번 100GB 전부 스캔?
  → Young GC가 Major GC만큼 비싸짐 → 의미 없음
```

→ **핵심 통찰**: 정확한 GC를 하려면 영역 간 참조를 알아야 하는데, 그 정보를 GC 시점에 처음부터 모으면 GC가 너무 비싸진다. **미리 모아두자**가 답.

### 1.3 키워드 2 — Card Table vs RSet (두 가지 접근법)

```
방법 1: Card Table
  - Heap을 512B 단위 카드로 나눠 "이 카드에 변경 있었나" 표시
  - Young GC 시 dirty card만 스캔 → 빠름
  - 단순, 작은 메모리 (Heap의 0.2%)
  - precision 한계: dirty card 안의 ref를 다 확인해야

방법 2: Remembered Set (G1)
  - region별로 "어디서 나를 가리키나" 정확한 목록
  - region 단위 evacuation의 핵심
  - precision 높음, 단 메모리 변동 큼 (1~20%)
```

→ **Card Table은 generational GC의 기본**, **RSet은 region 기반 GC(G1)의 추가 정밀도**.

### 1.4 키워드 3 — "시간을 메모리와 교환" 사상

Bookkeeping은 GC 시간을 메모리와 교환하는 trade-off. 항상 **메모리 ↑ + GC 시간 ↓**.

| 영역 | 메모리 비용 | GC 시간 절감 효과 |
|---|---|---|
| Card Table | Heap의 0.2% | Old gen 전체 스캔 → dirty card만 |
| RSet | Heap의 1~20% | region evacuation 시 precise 추적 |
| Mark Bitmap | Heap의 1.5% | Concurrent marking 가능 |
| SATB queue | 스레드별 임시 buffer | Marking 정확성 + STW ↓ |
| ZGC Forwarding Table | 매우 작음 | 객체 이동을 read barrier로 lazy 처리 |

### 1.5 도서관 색인 비유

> - **Java Heap** = 모든 책의 본문.
> - **Card Table** = "이 책장(512페이지 단위)에 변경 표시 있나" 작은 sticker. 큰 책장 통째 확인 안 하고 sticker만.
> - **Remembered Set** = "이 책장에 다른 책장의 어떤 책이 인용된 페이지 목록". 인용 많을수록 목록도 비대.
> - **Mark Bitmap** = "이 책이 살아있나 죽었나" 표시판. 책 한 권당 1비트.
> - **SATB Queue** = 책 수정 작업장에서 변경 전 원본을 잠시 보관하는 임시 폴더 (concurrent marking 정확성).

---

## 2. 가지 ②: Card Table — generational GC의 기본

### 2.1 핵심 질문

> "Card Table을 설명해보세요. 어떻게 동작하고 얼마나 메모리를 쓰나요?"

### 2.2 키워드 1 — 구조 (512B 카드, 1바이트 표시)

```
Heap (예: 1GB)
한 카드 = 512바이트
카드 수 = 1GB / 512 = 2,097,152개
각 카드당 1바이트 표시

Card Table (메모리):
  2,097,152 bytes = 2MB
  → Heap의 0.195% (1/512)

각 byte의 값:
  0x00 = clean (변경 없음)
  0xFF = dirty (변경 발생)
```

### 2.3 키워드 2 — 동작 (post-write barrier가 채우고, Young GC가 읽음)

```
1. obj.field = something;
        │
        ▼
2. JIT가 삽입한 post-write barrier:
   card_addr = (obj.field_addr >> 9);  // 512 = 2^9
   card_table[card_addr] = 0xFF;       // dirty 표시

3. Young GC 발생:
   for (i = 0 to card_count) {
     if (card_table[i] == 0xFF) {
       scan_old_gen_region(i * 512, (i+1) * 512);
     }
   }
   // dirty card만 스캔 — Old gen 100GB 중 0.1%만
```

**JDK 8+ 최적화**: 조건부 write
```
if (card_table[card_addr] != dirty) {
    card_table[card_addr] = dirty;
}
```
→ 이미 dirty면 store 안 함. cache line 무효화 회피. 처리량 5% 개선.

### 2.4 키워드 3 — 한계 (G1 도입 동기)

```
시나리오: Old gen 100GB, sparse cross-ref
  - 100GB / 512 = 200M card
  - 그 중 1%만 dirty → 2M card 스캔
  - 2M card × 512B = 1GB 영역을 매번 Young GC가 스캔 → 여전히 느림

G1의 해결: Remembered Set
  - card 단위 표시 대신 region별 "어디서 가리키나" 정확한 목록
  - precision 높음 → 스캔 영역 ↓
```

---

## 3. 가지 ③: Remembered Set (RSet) — G1의 핵심

### 3.1 핵심 질문

> "G1의 RSet이 무엇이고 왜 메모리 사용량이 워크로드에 따라 크게 변하나요?"

### 3.2 키워드 1 — region별 자료구조

```
G1 Heap: 2048개 region (한 region = 1~32MB)

각 region마다 자기만의 RSet:
  region_R의 RSet = "R을 가리키는 ref가 어느 region의 어느 card에 있나"

핵심: card에서 region으로 precision 상향. dirty card 안의 ref가 어느 region 향하는지 미리 인덱싱.
```

### 3.3 키워드 2 — 3-tier 자료구조 (Sparse → Fine → Coarse)

```
자료구조 진화 (entry 수에 따라):
  - 적음 (~256):   Sparse RSet — 작은 hash table
  - 중간 (~수천):  Fine-grained — region 단위 bitmap
  - 많음:         Coarse — "이 region 전체가 나를 가리킨다" 단일 비트로 압축
```

`fine→coarse transitions`가 빈발 = cross-region 참조 폭증 신호. 진단:
```bash
-Xlog:gc+remset=info
# RSet fine->coarse transitions: 5678
```

### 3.4 키워드 3 — 워크로드 따라 1~20% 변동

```
RSet 크기 = cross-region 참조 수에 비례:
  - 가벼운 워크로드 (cache 위주, sparse 참조): Heap의 1~3%
  - 일반 (mixed):                                Heap의 3~5%
  - 무거운 (graph-heavy, dense 참조):            10~20%
  - 극단 (잘못 튜닝):                            50% 가까이 → 운영 사고
```

**RSet 비대화 운영 시나리오**:
- 증상: Young GC pause가 점점 길어짐 (50ms → 500ms), Heap은 그대로인데 RSS 증가.
- 원인: Cross-region 참조 폭증 (큰 cache + 매번 새 Young 객체 참조), 또는 region 크기가 작아 region 수 폭증 (RSet 수 ↑).
- 진단: `-Xlog:gc+phases=debug`의 `Scan RS (ms)`가 길어짐.
- 조치:
  - `-XX:G1HeapRegionSize=32m` (region 크기 ↑ → region 수 ↓ → RSet 수 ↓).
  - 캐시 크기 제한 (LRU eviction).
  - ZGC로 마이그레이션 (RSet 메커니즘 자체가 다름).

---

## 4. 가지 ④: Mark Bitmap + SATB — concurrent marking 인프라

### 4.1 핵심 질문

> "Concurrent Mark는 정확성을 어떻게 보장하나요? Mark Bitmap과 SATB의 관계는?"

### 4.2 키워드 1 — Mark Bitmap (Heap/64)

```
객체 정렬: 8바이트
Bitmap: 객체당 1 bit

Mark Bitmap 크기:
  Heap 크기 / 64 (8B 정렬 가정)
  예: 100GB Heap → 1.5GB bitmap

G1은 ★ Mark Bitmap을 2개 ★ 유지:
  - prev bitmap: 지난 marking cycle 결과
  - next bitmap: 현재 marking cycle 작업 중
  → 총 3GB

ZGC는 mark bit를 객체 헤더의 colored pointer에 저장 → 별도 bitmap 작음
```

**Concurrent Marking 4단계** (G1):
1. **Initial Mark (STW, very short)** — GC Roots에서 직접 가리키는 객체들을 next bitmap에 mark.
2. **Concurrent Mark** — 마킹된 객체에서 reachable한 것들을 재귀 마킹, mutator는 동시에 ref 변경.
3. **Remark (STW, short)** — SATB queue 처리, prev↔next bitmap swap.
4. **Cleanup (STW + concurrent)** — 죽은 객체 회수, 빈 region을 free.

### 4.3 키워드 2 — SATB (Snapshot-At-The-Beginning)

**왜 SATB인가**:
- Concurrent marking 중 mutator가 ref를 변경하면: "이미 마킹된 객체가 사실 도달 불가" 또는 "안 마킹된 객체가 사실 도달 가능"일 수 있음.
- SATB는 **marking 시작 시점의 객체 그래프 snapshot**을 유지 — 그 시점에 살아있던 객체는 죽었어도 이번 cycle은 살아있다고 본다 (다음 cycle에 회수).

**Pre-write barrier**:
```java
obj.field = newObj;
        │ JIT 삽입
        ▼
old_value = obj.field;
if (concurrent_marking_active && old_value != null) {
    SATB_queue.enqueue(old_value);   // "이 값이 곧 lost되니 마킹해 두라"
}
obj.field = newObj;
```

→ 옛 값(`old_value`)이 이후 다른 곳에서 더 이상 reachable이 아니어도 이번 marking cycle은 살아있는 것으로 간주.

### 4.4 키워드 3 — SATB vs Incremental Update + Floating Garbage

두 가지 concurrent marking 정확성 보장 전략:

| | SATB (G1, Shenandoah) | Incremental Update (CMS, 제거됨) |
|---|---|---|
| 시점 | Marking 시작 시 snapshot 유지 | Mutator 변경을 incremental 반영 |
| Barrier | Pre-write (옛 값 보존) | Post-write (새 값 알림) |
| 정확성 | 강함 | 다시 marking pass 필요할 수 있음 |
| 단점 | Floating garbage (일부 dead 객체가 이번 cycle 못 회수, 다음 cycle로) | STW 길어질 위험 |

→ 현대 GC는 SATB로 수렴. Floating garbage는 다음 cycle에 회수되므로 누적 안 됨.

---

## 5. 가지 ⑤: Write Barrier — mutator가 GC에 알리는 방법

### 5.1 핵심 질문

> "Write Barrier가 자동 삽입된다는데, 어떤 코드가 추가되고 비용은 얼마인가요?"

### 5.2 키워드 1 — pre/post barrier 자동 삽입

```java
// 사용자 코드
obj.field = newObj;
```

JIT/Interpreter가 컴파일 시 자동 추가 (G1 기준):

```
// 사용자가 작성한 본문
store obj.field, newObj;

// JIT가 자동 삽입
if (G1Marking_in_progress) {       // pre-barrier (SATB)
    old_value = load obj.field;
    enqueue_SATB(old_value);        // 옛 값을 marking queue
}
mark_card_dirty(obj.field_addr);    // post-barrier (Card Table)
if (different_region(obj, newObj)) {
    enqueue_card(card_addr);         // RSet 갱신용 큐
}
```

→ 사용자 입장에선 보이지 않지만 **모든 ref 쓰기마다 추가 명령 ~3~10개**.

### 5.3 키워드 2 — Card Queue + Refinement Thread (비동기)

```
[Application Thread]                  [Refinement Thread]
obj.field = ref;                       
   ↓ post-barrier                       
   card_queue.push(card)  ─────────►  card_queue.pop()
   (가벼움, 비동기 enqueue)               ↓ scan card for refs
                                          ↓ RSet add_reference

Application thread는 큐 push만, refinement thread가 비동기 처리.
매번 RSet 직접 갱신하면 비용 큼 → 비동기로 분산.
```

→ Application 영향 최소화. `-XX:G1ConcRefinementThreads`로 thread 수 조정.

### 5.4 키워드 3 — mutator 5~15% overhead (워크로드 의존)

**Write barrier 비용**:
- Ref 쓰기 많은 코드 (예: 리스트 구축): **5~15% 처리량 ↓**.
- 산술 위주 코드: 거의 0%.
- ZGC의 read barrier는 read마다 → 더 비싸지만 STW 거의 없음.

**측정 방법**:
- JMH 벤치마크로 GC 옵션별 비교.
- JFR `jdk.ThreadCPULoad` 이벤트.
- async-profiler로 native code의 write barrier 분포 확인.

**트레이드오프**:

| | Barrier 가벼움 (예: card table만) | Barrier 무거움 (SATB + RSet + colored) |
|---|---|---|
| Mutator | 빠름 | 5~15% 느림 |
| Concurrent 정확도 | ↓ → STW 길어질 가능성 | 거의 완전 |
| 적합 GC | Serial/Parallel | G1, ZGC, Shenandoah |

→ Latency-sensitive 시스템 (P99 < 10ms)은 무거운 barrier 감수하고 ZGC/Shenandoah 선택.

---

## 6. 가지 ⑥: 운영 + ZGC 특수성 + 기타 영역

### 6.1 핵심 질문

> "큰 Heap 환경에서 RSS가 Heap보다 훨씬 큰 이유는? ZGC는 왜 pmap에서 3배로 보이나요?"

### 6.2 키워드 1 — 전체 footprint 추정 + 운영 진단

**100GB Heap 환경의 native footprint 예측 (G1)**:
```
Card Table       = 100GB / 512    = 200MB
Mark Bitmap × 2  = 100GB / 64 × 2 = 3GB
RSet (평균 5%)    = 100GB × 5%     = 5GB         (워크로드 따라 1~20GB)
Symbol Table     = ~50MB
JVM Internal     = ~500MB
Direct Memory    = 명시
Code Cache       = 240MB
Metaspace        = ~500MB
Thread Stacks    = 500 × 1MB      = 500MB
──────────────────────────────────────
총합 (Heap 외):  약 10~30GB
→ RSS = 100GB (Heap) + 10~30GB ≈ 110~130GB
```

**진단 명령**:
```bash
jcmd <pid> VM.native_memory summary
# - GC 항목 (Card Table + RSet + Mark Bitmap 합)
# - Symbol, Internal, Other

-Xlog:gc+remset=info,gc+phases=debug
# Scan RS, RSet transitions

# JFR
jcmd <pid> JFR.start name=gc duration=300s settings=profile filename=gc.jfr
# 핵심: jdk.G1HeapRegionInformation, jdk.G1AdaptiveIHOP, jdk.GarbageCollection
```

**Killer 시나리오 — 100GB Heap RSS 130GB**:
1. NMT GC 항목 ≥ 정상 예상(8~10GB)이면 RSet 폭증 의심.
2. `-Xlog:gc+phases=debug`의 `Scan RS (ms)`가 길면 확정.
3. `-Xlog:gc+remset=info`의 fine→coarse transitions 빈발 확인.
4. 조치: region 크기 ↑, 캐시 크기 제한, ZGC 검토.

### 6.3 키워드 2 — ZGC의 colored pointer + multi-mapping (pmap 함정)

> 이 절은 면접관이 "ZGC가 뭐예요?"부터 "왜 pmap이 거짓말해요?"까지 한 호흡으로 물어볼 때를 위한 완전판이다.
> **읽는 순서**: pmap → G1GC → ZGC → colored pointer → multi-mapping → pmap 함정 → Forwarding Table.

---

#### 6.3.0 사전 개념: pmap이 뭔가

**한 줄 본질**: 리눅스 명령어. 프로세스 하나의 **가상 주소 공간 지도**를 보여준다.

```
$ pmap -x <jvm-pid>
Address           Kbytes   RSS   Dirty  Mode  Mapping
00007f8000000000  104857600 ...  rw---  [anon]            ← Heap (익명 mmap)
00007f8800000000  2097152   ...  rw---  [anon]            ← Metaspace
00007f8900000000  524288    ...  rwx--  [anon]            ← Code Cache
00007f8a00000000  10240     ...  r----  libjvm.so         ← 공유 라이브러리
```

- 각 줄 = **mmap 한 번의 결과 (= VMA, Virtual Memory Area)**
- `Kbytes` = **가상 주소 공간**에서 차지한 크기 (= reserved)
- `RSS` = 그 중 실제 물리 메모리에 올라온 크기 (= 진짜 쓰는 메모리)

**왜 운영에서 쓰나**:
- Heap 외 어떤 mmap 영역들이 있는지 한눈에 봄
- NMT가 못 잡는 DirectByteBuffer, JNI malloc 영역도 보임
- 공유 라이브러리 vs 익명 영역 구분 가능

**pmap의 함정 (핵심)**: pmap은 기본적으로 **가상 주소 크기**를 합산해서 보여준다. **물리 메모리가 아니다**. 한 물리 페이지가 여러 가상 주소에 매핑되면 (= multi-mapping) **중복 카운트**된다. ZGC가 정확히 이 패턴이라 pmap이 거짓말하는 것처럼 보인다.

---

#### 6.3.1 G1GC가 뭔가 + 4개 자료구조의 진화 스토리

> 표 한 줄로 끝낼 수 없는 주제다. 각 자료구조가 **어떤 문제를 풀려고 태어났고, 어떻게 동작하고, 어떤 새 문제를 낳아서 다음 자료구조/다음 GC로 이어졌는지**를 시간 순서로 따라가야 머리에 박힌다.

##### G1의 한 줄 본질

Heap을 수천 개의 **고정 크기 region**으로 잘라놓고, 그 중 **회수 가치가 큰 region만 골라 evacuation**하는 GC. JDK 9부터 기본.

```
Heap (예: 100GB)을 2048개 region으로 분할 (각 region ~50MB)
   │
   ├── 각 region은 동적으로 역할 부여: Eden / Survivor / Old / Humongous
   │
   ├── Young GC:
   │     Eden + Survivor region 전체를 evacuate
   │     ★ "Old gen 안에 Young을 가리키는 참조가 어디 있는지" 알아야 됨
   │
   └── Mixed GC:
         Old region 중 "쓰레기 비율 높은 것"만 골라 evacuate
         ★ "다른 Old region이 이 region을 가리키는지" 알아야 됨
```

→ G1의 모든 자료구조는 **"region 단위 evacuation을 효율적으로 하기 위한 인덱스"**다.

---

##### 출발점: 모든 문제의 근원 (Generational 가설의 부작용)

```
Generational GC의 가정:
  "대부분의 객체는 일찍 죽는다 → Young만 자주 청소하면 효율적"

  Eden (자주 청소)  ──생존자──►  Old (가끔 청소)

문제: Young GC에서 "이 Young 객체 살아있나?" 판정하려면 Roots만으론 부족.
      ★ Old gen의 어떤 객체가 Young을 가리키고 있을 수도 있다 ★

예시:
  static Cache CACHE = new Cache();   ← Root에서 도달 가능 (Old)
  CACHE.put("key", new User());        ← User는 Young, CACHE는 Old
       ↑
   Old → Young 참조

이 참조를 모르면 Young GC가 User를 죽임 → CACHE에 댕글링 참조 → SIGSEGV
```

**우직한 해법**: Young GC마다 Old 전체(100GB)를 스캔해서 cross-gen 참조 찾기.
**결과**: Young GC가 Major GC만큼 느려짐 → **generational 가설의 이점 박살**.

**필요한 것**: Old → Young 참조를 **미리 어딘가 기록해두기**. → **Card Table의 탄생**.

---

##### 1단계 — Card Table: 가장 단순한 해법 (Serial/Parallel/CMS/G1 공통)

**핵심 아이디어**: Heap을 작은 카드 단위로 잘라놓고, **카드 안에서 ref 쓰기가 발생하면 카드를 "더럽혔다"고 표시**. Young GC 시 더러운 카드만 스캔.

```
Heap (Old gen 부분)을 카드로 분할:
  카드 0: [0 ~ 512 byte]
  카드 1: [512 ~ 1024 byte]
  카드 2: [1024 ~ 1536 byte]
  ...
  카드 N: ...

Card Table = 카드 수만큼의 1바이트 배열 (별도 native 메모리):
  card_table[0] = clean
  card_table[1] = clean
  card_table[2] = clean
  ...
```

###### Card Table은 어떻게 채워지나 — Write Barrier가 자동 채움

```java
// 사용자 코드 (Old에 있는 cache)
cache.users[i] = newUser;   // newUser는 Young 객체

// JIT가 자동 삽입한 코드 (post-write barrier)
card_idx = (address_of(cache.users[i]) >> 9);   // 512로 나눔
card_table[card_idx] = DIRTY;
```

→ **사용자는 평범한 대입문 하나를 썼는데, JIT가 카드를 더럽히는 코드를 몰래 추가**. 이게 write barrier.

###### Card Table은 어떻게 쓰이나 — Young GC가 읽음

```
Young GC 시작:
  1. Roots에서 도달 가능한 Young 객체 마킹
  2. ★ Old gen의 모든 카드를 스캔 ★
     for card in old_gen:
       if card_table[card] == DIRTY:
         scan_512_bytes(card)               ← 이 512B 안의 모든 참조 검사
         for each ref in this 512B:
           if ref points to Young:
             mark ref as live root          ← Old → Young 참조 발견
  3. Young 영역 evacuation
  4. Card Table 모두 clean으로 리셋
```

**중요한 비대칭**:
- Card Table은 **"writer 중심"**: 변경된 위치를 기록 (어디가 더럽혀졌나)
- 카드 안 어디서 → 어디로 가는 참조인지는 **모름**
- 그래서 dirty 카드 발견하면 **512B 통째 스캔**해서 참조를 찾음 ★

###### Card Table의 강점

```
✅ 메모리: Heap의 0.2% (512배 압축). 100GB Heap → 200MB
✅ Write barrier 비용: 명령어 ~3개. 매우 가벼움
✅ 구현 단순: 1바이트 배열 + post-write barrier만
✅ Generational GC 전체가 이걸로 충분 (Young, Old 두 영역만 있을 때)
```

###### Card Table의 한계 — G1을 부른 원인

```
G1은 Heap을 2048개 region으로 잘라놓음.

문제 1: precision 부족
  Mixed GC 시 "Old region A를 가리키는 다른 Old region B의 참조"가 필요
  Card Table은 "B의 어느 카드가 더러운지"만 알려줌
  → A를 evacuate 하려는데 B의 어느 카드가 A를 가리키는지 찾으려면
     B의 모든 dirty card를 스캔해야 됨

문제 2: 선택적 evacuation에 부적합
  Card Table은 "Old 전체 → Young 전체" 추적용
  G1은 "Old region X만 evacuate" 같은 ★선택적★ 청소를 원함
  → "X를 가리키는 곳"을 X 기준으로 알고 싶음

→ Card Table은 "출발지(writer) 기준" 인덱스
→ G1이 원하는 건 "도착지(target region) 기준" 인덱스
```

**필요한 것**: 각 region마다 **"이 region을 가리키는 외부 참조의 위치 목록"**. → **Remembered Set의 탄생**.

---

##### 2단계 — Remembered Set: G1을 위한 역방향 인덱스

**핵심 아이디어**: **region마다 자기만의 RSet을 가짐**. RSet에는 **"내 region을 가리키는 참조가 어느 region의 어느 카드에 있는지"** 기록.

###### Card Table vs RSet 방향 비교

```
Card Table (writer 중심):
  "어디서 변경이 일어났나"
  ┌────────┐     write
  │ Region │─────────► card_table[idx] = DIRTY
  │   A    │
  └────────┘
  사용 시: "Old 전체 dirty 카드 다 훑어야" 어디로 가는지 모름

RSet (target 중심):
  "나는 어디서 가리키고 있나"
  ┌────────┐                 ┌────────┐
  │ Region │── write to ─────►│ Region │
  │   A    │                  │   B    │
  └────────┘                  └────────┘
                                  │
                                  ▼
                          RSet of B = {
                            "A의 카드 15에 B를 가리키는 참조 있음",
                            "C의 카드 7에 B를 가리키는 참조 있음",
                            ...
                          }
  사용 시: B를 evacuate 하려면 RSet(B)만 보면 끝
```

###### RSet은 어떻게 채워지나 — Card Table + Refinement Thread 협업

**중요한 사실**: G1도 **Card Table을 여전히 씀**. RSet은 Card Table 위에 쌓은 추가 레이어.

```
[Application Thread]
  obj.field = ref;                    ← 사용자 코드 (obj는 region A, ref는 region B)
       │
       │ JIT 삽입 post-write barrier
       ▼
  ① card_table[card_idx] = DIRTY      ← Card Table 표시 (예전과 동일)
  ② if (region_of(obj) != region_of(ref)):
        dirty_card_queue.enqueue(card_idx)   ← cross-region이면 큐에 넣음
       │
       │ (큐가 차면 백그라운드 스레드가 처리)
       ▼
[Refinement Thread] ★ 비동기 ★
  while dirty_card_queue not empty:
    card = dequeue()
    for each ref in card's 512B:
      target_region = region_of(ref)
      if target_region != source_region:
        RSet[target_region].add(card_idx)   ★ 여기서 RSet 갱신 ★
```

**핵심**:
- Application thread는 **카드 더럽히기 + 큐에 넣기**만 (가벼움)
- 실제 RSet 갱신은 **refinement thread가 비동기로**
- 이렇게 안 하면 mutator가 매번 RSet 자료구조를 직접 수정해야 됨 → 락 + 비대화

###### Young/Old 안에 어떻게 기록되나

```
Heap 구조:
┌─────────────────────────────────────────────────────────────┐
│  Region A (Eden)   Region B (Survivor)   Region C (Old)    │
│  ┌────────────┐    ┌────────────┐         ┌────────────┐  │
│  │ 객체들      │    │ 객체들      │         │ 객체들      │  │
│  └────────────┘    └────────────┘         └────────────┘  │
└─────────────────────────────────────────────────────────────┘

RSet은 region 안에 ★있지 않다★. 별도 native 메모리에 region별로 보관:
┌─────────────────────────────────────────────────────────────┐
│  Native 영역 (NMT의 GC 카테고리)                              │
│                                                              │
│  RSet(A) = { "C의 카드 8에 A를 가리키는 참조 있음", ... }     │
│  RSet(B) = { "C의 카드 12에 B를 가리키는 참조 있음", ... }    │
│  RSet(C) = { }   ← Old는 evacuation 자주 안 되므로 보통 작음  │
│  ...                                                         │
└─────────────────────────────────────────────────────────────┘

★ Young GC 시:
  → RSet(Young region 전부)만 보면 Old → Young 참조 다 찾음
  → Old 전체 스캔 불필요

★ Mixed GC 시:
  → RSet(CSet에 포함된 Old region)만 보면 외부 참조 다 찾음
```

###### RSet의 3-tier 자료구조 — 왜 진화했나

```
초기: 단순 hash table — entry 적을 때 빠르지만, 많아지면 메모리 폭발

진화: entry 수에 따라 자동 변신

Sparse RSet (entry 0~수십개):
  작은 hash table. region 대부분이 이 상태.
  메모리 비용 작음.

Fine-grained (entry 수백~수천):
  Sparse가 꽉 차면 변환.
  카드 단위 bitmap (어느 region의 어느 카드가 나를 가리키는지).
  메모리 중간.

Coarse-grained (entry 너무 많음):
  Fine-grained도 꽉 차면 변환.
  "region X 전체가 나를 가리킨다" 단일 비트로 압축.
  메모리 작지만 ★precision 손실★
  evacuation 시 region X 전체를 스캔해야 됨.

→ 메모리와 precision의 trade-off를 동적으로 조정.
→ fine→coarse 전환 빈발 = cross-region 참조 폭증 신호 (운영 알람!)
```

###### RSet이 G1의 약점이 된 이유

```
워크로드별 RSet 크기:
  - 가벼운 (캐시 위주): Heap × 1~3%
  - 일반 (mixed): Heap × 3~5%
  - 무거운 (graph-heavy): Heap × 10~20%
  - 극단 (튜닝 실패): Heap × 50% 까지

100GB Heap에서 ★RSet만 10~20GB★ → RSS가 Heap의 1.2~1.3배

추가 문제:
  1. region 수 ↑ → RSet 개수 ↑ → 전체 메모리 폭증
  2. cross-region 참조 ↑ → 각 RSet 크기 ↑ → 폭증 가속
  3. refinement thread CPU 소모 (백그라운드 인덱싱)
  4. fine→coarse 전환 시 evacuation pause 길어짐

→ "G1의 메모리 풋프린트가 너무 크다"가 ZGC 동기 중 하나.
```

---

##### 3단계 — Mark Bitmap: Concurrent Marking을 위한 살아있음 표시판

지금까지(Card Table, RSet)는 **"cross-gen/cross-region 참조 추적"** 문제. 이번에는 다른 축의 문제다: **"객체가 살아있나 죽었나를 어디에 기록하나"**.

###### 왜 별도 비트맵이 필요한가

```
선택지 1: 객체 헤더에 mark 비트 두기
  → 옛날 GC 방식 (Serial, Parallel)
  → 문제: STW 시에만 가능. mutator가 헤더를 같이 쓰니까.
  → Concurrent marking 불가.

선택지 2: 객체와 ★분리된★ 비트맵에 mark 비트 두기
  → 비트맵 = "주소별로 1비트"인 native 배열
  → mutator는 객체 헤더 만지고, GC는 비트맵 만짐 → 충돌 없음
  → ★Concurrent marking 가능★
```

###### Mark Bitmap의 구조

```
객체 정렬: 8바이트 단위 (모든 객체 주소는 8의 배수)

Heap:
[obj1: 32B] [obj2: 16B] [obj3: 64B] ...

Bitmap (Heap의 1/64 메모리):
  bit 0 = obj1 살아있나
  bit 4 = obj2 살아있나 (obj1이 32B = 4 슬롯)
  bit 6 = obj3 살아있나 (obj2가 16B = 2 슬롯)
  ...

★ 객체 주소 → bitmap 인덱스 변환: (obj_addr - heap_start) >> 3

  비트 1 = 살아있음 (concurrent marking이 다녀감)
  비트 0 = 미확인 또는 죽음
```

###### G1은 왜 비트맵이 2개인가 — prev/next

```
시간 흐름:
  t=0: marking cycle N 시작
       next_bitmap 초기화, marking thread가 채워나감
       prev_bitmap = cycle N-1의 결과 (★사용 가능한 살아있음 정보★)

  t=1~T: concurrent marking 진행
       next_bitmap을 채우는 중
       Young GC가 동시에 일어나면 "살아있나?" 질문해야 됨
       → 아직 미완성인 next 못 씀
       → ★prev_bitmap(지난 cycle 결과)을 사용★

  t=T: marking cycle 끝
       next_bitmap 완성됨
       prev ↔ next swap
       이제 prev_bitmap = cycle N의 결과 (가장 최신)
       next_bitmap은 다음 cycle용으로 비움
```

→ **"한 비트맵을 채우는 동안 다른 비트맵으로 질의"** 패턴. 100GB Heap이면 비트맵 1.5GB × 2 = 3GB.

###### Mark Bitmap이 푸는 본질적 문제

```
GC의 마킹은 본질적으로 그래프 순회 (BFS/DFS)
  Roots → 객체 → 참조 → 객체 → ...

순회 도중 mutator가 그래프를 ★바꾸면★:
  - 이미 방문한 노드의 참조가 사라짐 → 별 문제 없음
  - 아직 방문 안 한 노드에 새 참조 생김 → ★놓침 (lost object)★

해결책 2가지:
  방법 A: Snapshot 유지 (SATB)  ← G1, Shenandoah
  방법 B: 변경을 추적 (Incremental Update)  ← 옛 CMS

둘 다 ★어딘가에 마킹 상태★를 보관해야 됨 → Mark Bitmap 필요.
```

→ 다음 문제: **mutator가 마킹 도중 참조를 바꾸면 놓치는 객체**. → **SATB Queue의 탄생**.

---

##### 4단계 — SATB Queue: Concurrent Marking 정확성의 마지막 퍼즐

**핵심 아이디어**: marking 시작 시점의 객체 그래프 **snapshot**을 유지. 이후 mutator가 참조를 바꿔도, **바뀌기 전 옛 값**을 기록해서 marking thread에게 넘김.

###### 왜 필요한가 — 놓치는 객체(Lost Object) 시나리오

```
marking 시작 시점의 그래프:
  Root → A → B → C
              │
              └→ D

  marking thread가 BFS 진행 중: Root, A, B는 마킹함. C, D는 아직.

이때 mutator가:
  B.ref = null;     // B → C, B → D 참조 끊김
  Root.new_ref = D; // Root에 D 직접 매다는 건 안 함 (예시)

marking thread가 다음 단계 진행:
  B의 자식 = 없음 (mutator가 끊었으니까)
  → C, D 영영 발견 못 함
  → C, D 죽었다고 판정 → 회수
  
★ 그런데 mutator가:
  some_var = was_B_ref_to_D;  // 끊기 전에 D를 어딘가에 백업했을 수 있음
  → D는 살아있어야 했음
  → ★살아있는 D를 죽임★ → 메모리 안전성 박살
```

→ **marking 도중 참조 변경이 있을 수 있음**을 가정해야 안전.

###### SATB의 해법 — 변경 직전 옛 값을 큐에 넣기

```java
// 사용자 코드
obj.field = newValue;

// JIT가 자동 삽입한 코드 (pre-write barrier)
if (concurrent_marking_active) {
    old_value = obj.field;             // ★ 덮어쓰기 ★전★ 값 ★
    if (old_value != null) {
        satb_queue.enqueue(old_value); // 큐에 보관
    }
}
obj.field = newValue;                  // 실제 쓰기
```

###### SATB Queue는 어떻게 처리되나

```
[Application Thread]                      [Marking Thread]
obj.field = newValue;                     
  ↓ pre-barrier                           
  satb_queue.enqueue(old_value)  ──────►  drain satb_queue
                                            ↓
                                          for each captured old_value:
                                            mark old_value alive       
                                            traverse from old_value     
                                            (BFS 계속)

★ "끊기기 전에 가리키고 있던 값"을 빠짐없이 살림
★ 결과: marking 시작 시점의 스냅샷을 유지하는 효과
```

###### SATB의 트레이드오프 — Floating Garbage

```
SATB의 보수성:
  "marking 시작 시점에 살아있던 객체는, 이번 cycle은 일단 살린다"
  → marking 도중 실제로 죽은 객체도 이번엔 회수 못 함
  → ★Floating Garbage★

비용:
  - 한 cycle 분의 floating garbage = 메모리 일부 낭비
  - 다음 cycle엔 다 회수됨 → 누적 안 됨
  - "정확성 vs 회수 효율"의 trade-off에서 정확성 선택
```

###### SATB Queue의 메모리 비용이 작은 이유

```
Card Table, RSet, Mark Bitmap = "Heap의 N%" 영구 자료구조

SATB Queue:
  - 스레드별 작은 버퍼 (~1KB)
  - marking 끝나면 비움
  - 동시 실행 중인 스레드 수만큼만 존재
  - 전체 합쳐도 수 MB 수준

→ "임시 큐"라 비대화 위험 없음.
```

---

##### 5단계 — 4개 자료구조의 협업 도식

이제 4개가 모두 등장했다. **G1 동작 한 사이클에서 어떻게 함께 일하는지**:

```
[Young GC 한 사이클]

1. Mutator가 평소대로 동작 중
   obj.field = ref;
        ↓ JIT가 삽입한 barriers
   ├─ pre-write barrier:
   │    if (marking_active) satb_queue.push(old_value)   ← SATB
   │
   ├─ post-write barrier:
   │    card_table[idx] = DIRTY                          ← Card Table
   │    if (cross-region) dirty_card_queue.push(card)    ← RSet 준비
   │
   └─ 실제 쓰기 수행

2. Refinement Thread (백그라운드)
   dirty_card_queue 비우면서 RSet 갱신                    ← RSet
   "card N에 region B 가리키는 참조 있다" → RSet(B).add(card N)

3. Young GC 발생 (STW)
   a. Roots 스캔
   b. RSet(모든 Young region) 조회                       ← RSet 활용
      → Old → Young 참조 위치 즉시 획득
      → 해당 카드만 스캔 (Old 전체 X)
   c. 살아있는 Young 객체 evacuation
   d. (concurrent marking 중이면) Mark Bitmap 갱신       ← Mark Bitmap
   e. Card Table 리셋 (다음 cycle 준비)

[Concurrent Marking 한 사이클] (병행)

1. Initial Mark (STW, 매우 짧음)
   Roots에서 직접 가리키는 객체를 next_bitmap에 마킹

2. Concurrent Mark (mutator와 동시)
   next_bitmap 채우며 BFS 진행
   동시에 SATB queue로 옛 참조 보존                       ← SATB
   동시에 prev_bitmap으로 "살아있나?" 질의 답함            ← Mark Bitmap

3. Remark (STW, 짧음)
   SATB queue 마지막까지 drain
   prev ↔ next bitmap swap

4. Cleanup
   완전히 비어버린 region 즉시 회수
   다음 Mixed GC를 위한 CSet 후보 선정
```

→ **4개 자료구조 + 2종류 barrier가 한 사이클에서 끊임없이 협주**.

---

##### 6단계 — G1의 한계가 ZGC를 부른 이유

위 협주의 비용을 합산하면:

```
G1 동작 비용 누적:
  - Card Table: Heap × 0.2%                            (작음)
  - RSet: Heap × 1~20% ★변동성, 폭증 위험★              (큼)
  - Mark Bitmap × 2: Heap × 3%                         (중간)
  - SATB Queue: 작음                                    (작음)
  - Pre + Post barrier: mutator throughput 5~15% 손실  (큼)
  - Refinement thread: CPU 추가 소모                    (중간)
  - Evacuation pause: 살아있는 객체 수에 비례 STW       (★ 한계 ★)

100GB Heap의 native footprint:
  10~25GB 추가 → RSS = 110~125GB

★★ 결정적 한계 ★★:
  Evacuation pause(객체 복사)는 ★ 본질적으로 STW ★
  → Heap 크기 ↑, 살아남은 객체 수 ↑ → STW 길어짐
  → 100GB+ 환경에서 STW가 수백 ms로 늘어남
  → P99 latency SLA(<10ms) 못 지킴
```

###### ZGC의 "전면 재설계"

```
G1의 4개 자료구조 + 2 barrier를 ★전부 재검토★:

1. Card Table → 폐기
   - 사용 이유: writer 기준 cross-gen 참조 추적
   - 대안: 객체 접근 시 load barrier가 ★매번 체크★ → 별도 인덱스 불필요

2. RSet → 폐기
   - 사용 이유: target 기준 cross-region 참조 인덱스
   - 대안: relocation 시 forwarding table에 옛↔새 주소만 기록
            객체 자체에 접근하는 mutator가 load barrier로 자가 치유

3. Mark Bitmap → 포인터 비트로 흡수
   - 사용 이유: 객체 살아있음 표시
   - 대안: ★colored pointer★ — 포인터 상위 비트가 곧 mark 상태
   - 별도 비트맵 거의 필요 없음

4. SATB Queue → 다른 방식의 marking
   - ZGC도 concurrent marking을 위한 barrier는 있음
   - 하지만 read barrier 기반이라 메커니즘이 다름
   - SATB 형태의 큐는 사실상 필요 없음

5. Write barrier → Load barrier로 전환
   - "쓸 때 알리기" → "읽을 때 확인하기"
   - 모든 검사가 read 경로로 통합
   - mutator 오버헤드 비슷하지만 ★concurrent 처리가 훨씬 자연스러움★

결과:
  - native footprint: Heap × 1.05 (G1의 1.2~1.3에서 ↓)
  - STW: < 1ms (객체 수와 무관)
  - 단점: 가상 주소 공간 3배 (multi-mapping) → pmap 함정
```

---

##### 진화 순서 한 줄 요약

> **Generational GC는 Old→Young 참조를 위해 Card Table을 만들었다 → G1은 region 단위 evacuation을 위해 Card Table 위에 RSet을 쌓았다 → Concurrent marking을 위해 Mark Bitmap × 2와 SATB Queue를 추가했다 → 이 4개 자료구조의 메모리/STW 비용이 한계에 부딪혀, ZGC는 colored pointer + multi-mapping + forwarding table로 거의 전부 재설계했다.**

---

#### 6.3.2 ZGC가 뭔가 — 본질부터

**한 줄 본질**: **모든 GC 작업(marking, relocation, reference updating)을 동시(concurrent)로 수행**해서 **STW를 객체 수와 무관한 sub-ms 수준**으로 만드는 GC. JDK 15 production-ready, JDK 21에서 Generational ZGC.

##### 설계 철학의 차이

```
G1의 접근:
  "STW를 짧게 — 하지만 어쩔 수 없이 객체 수에 비례해 길어짐"

ZGC의 접근:
  "STW를 객체 수와 분리 — Root scanning만 STW로, 나머지는 전부 concurrent"
  → STW 시간이 Heap 크기와 무관 (16GB든 16TB든 비슷)
```

##### ZGC의 핵심 트릭 4개

```
1. Colored Pointer
   객체의 살아있음/이동중/마킹상태를 ★포인터의 비트에 직접 인코딩★
   → 객체 헤더에 마크 비트 안 둠, Card Table도 RSet도 없음

2. Load Barrier (read barrier)
   객체를 ★읽을 때마다★ 포인터 색깔 확인
   → 잘못된 색이면 즉시 교정 (relocation, remap)
   → G1의 write barrier 대신 read barrier 사용

3. Multi-mapping
   한 물리 메모리 페이지를 ★여러 가상 주소에 매핑★
   → colored pointer가 가리키는 색깔별로 다른 가상 주소로 접근
   → MMU(하드웨어)가 색 해석을 도와줌

4. Region-based + Forwarding Table
   G1처럼 region 단위 evacuation, 하지만 forwarding table로 lazy 갱신
   → STW 없이 객체 이동 가능
```

##### ZGC의 사이클

```
1. Pause Mark Start (STW, sub-ms)
   GC Roots 스캔 — 스택의 root만, Heap은 안 봄
        │
        ▼
2. Concurrent Mark (concurrent)
   load barrier 도움 받으며 mutator와 동시에 도달성 분석
        │
        ▼
3. Pause Mark End (STW, sub-ms)
   동기화 지점
        │
        ▼
4. Concurrent Relocate (concurrent)
   대상 region의 객체를 다른 region으로 복사
   forwarding table에 옛 주소 → 새 주소 기록
   mutator가 옛 주소로 접근하면 load barrier가 새 주소로 redirect
        │
        ▼
5. (다음 cycle 시작 시) Pointer remap
   살아있는 모든 포인터를 새 주소로 lazy하게 교체
```

**핵심**: STW는 1, 3번뿐 — Root 스캔만. **Heap이 16TB여도 1ms 안에 끝남.**

---

#### 6.3.3 Colored Pointer가 뭔가 — 포인터에 색칠하기

**한 줄 본질**: 64비트 객체 포인터의 **상위 비트 일부를 주소가 아닌 "상태 플래그"로 사용**하는 기법. 객체의 살아있음/이동중/마킹상태를 포인터 자체가 들고 다닌다.

##### 일반 포인터 vs Colored Pointer

```
일반 포인터 (64비트):
┌──────────────────────────────────────────────┐
│  64bit: 전부 가상 주소                          │
└──────────────────────────────────────────────┘
실제로는 x86-64에서 하위 48비트만 사용, 상위는 부호 확장으로 낭비.

Colored Pointer (ZGC):
┌──────────┬──────────────────────────────────┐
│ 색깔 비트  │  실제 가상 주소 (하위 N비트)        │
│ (몇 비트) │                                  │
└──────────┴──────────────────────────────────┘
   ↑
   marked0 / marked1 / remapped 같은 "GC 상태"를 인코딩
```

(표면 디테일인 정확한 비트 위치는 JDK 버전마다 다름 — 본질은 "상위 비트 = 상태")

##### 색깔이 뜻하는 것 (개념적으로)

| 색깔 | 의미 | 언제 쓰이나 |
|------|------|----------|
| **marked0** | "지난 marking cycle에서 살아있다고 마킹됨" | cycle N |
| **marked1** | "이번 marking cycle에서 마킹됨" | cycle N+1 (cycle마다 교차 사용) |
| **remapped** | "이미 새 주소로 갱신된 포인터" | relocation 끝난 후 |
| **(finalizable 등 더 있음)** | | |

##### Colored Pointer가 푸는 문제

**문제**: G1은 객체의 살아있음/마킹 상태를 별도 **bitmap**에 저장 → Heap의 1.5% × 2 메모리, bitmap 접근 추가.

**ZGC의 해결**: 포인터 자체에 상태 인코딩 → 객체를 가리키는 순간 상태가 따라옴 → bitmap 불필요, Card Table 불필요, RSet 불필요.

```
G1:  객체 접근 → bitmap[obj_addr] 확인 → 마킹 여부 알 수 있음
ZGC: 객체 접근 → 포인터 자체의 색깔 확인 → 상태 즉시 판별
```

##### Load Barrier와의 결합

```java
// 사용자 코드
Order o = user.order;
        ↓ JIT가 load barrier 자동 삽입
ptr = load(user.order);
if (ptr.color != current_good_color) {  // 색깔이 안 맞으면
    ptr = slow_path(ptr);                // 새 주소로 교정 (relocation 반영)
    user.order = ptr;                    // self-healing — 다음엔 빠른 경로
}
```

→ **객체를 읽을 때마다 색을 확인**해서 자가 치유. 이래서 ZGC는 read barrier 기반.

---

#### 6.3.4 Multi-mapping이 뭔가 — 한 물리 페이지를 여러 가상 주소에서

**한 줄 본질**: **한 물리 메모리 페이지를 동일한 프로세스의 여러 가상 주소에 동시 매핑**하는 OS 기능. ZGC가 색깔별 view를 만드는 데 사용.

##### mmap으로 한 페이지를 세 번 매핑하기

```
[물리 메모리]
   4KB 페이지 (PFN = 0x1234)
        ▲
        │ 같은 물리 페이지를 가리키는 세 개의 가상 주소
        │
   ┌────┴─────┬──────────┐
   │          │          │
가상 주소 A  가상 주소 B  가상 주소 C
0x000...  0x100...  0x200...
(marked0)  (marked1)  (remapped)

★ 같은 데이터, 다른 가상 주소.
★ 어느 주소로 접근해도 같은 4KB 페이지가 보임.
★ MMU가 페이지 테이블을 통해 가상 → 물리 변환.
```

##### 왜 이게 ZGC에 필요한가

```
Colored pointer가 객체를 가리킬 때:
   포인터 = 색깔 비트 + 가상 주소

★ 트릭: 색깔 비트가 ★가상 주소의 상위 비트★를 결정하도록 설계

  색이 marked0이면 → 0x000... 영역의 가상 주소로 접근
  색이 marked1이면 → 0x100... 영역의 가상 주소로 접근
  색이 remapped면 → 0x200... 영역의 가상 주소로 접근

  세 영역 모두 ★같은 물리 메모리★를 가리킴 (multi-mapping)
```

##### 무엇이 좋아지나

```
일반 GC:
  포인터 색깔 확인 → if/else 분기 → 다른 처리
  → CPU branch + 추가 명령 비용

ZGC + multi-mapping:
  포인터를 그냥 dereference → MMU가 가상 주소의 상위 비트 보고 알아서 처리
  → 색깔 확인이 ★하드웨어 차원에서 자동★
```

→ load barrier가 super-fast. read마다 거는데도 mutator 영향이 작은 이유.

##### 도식 — 1개 물리 페이지 = 3개 가상 view

```
ZGC의 한 물리 메모리 페이지 (예: 4KB):

                                            가상 주소 공간
                                            ━━━━━━━━━━━━━

                                  ┌──────► marked0 view  (0x000... 영역)
                                  │
[Physical RAM: 4KB, PFN 0x1234]───┼──────► marked1 view  (0x100... 영역)
                                  │
                                  └──────► remapped view (0x200... 영역)

  ★ 물리 메모리: 4KB 한 장
  ★ 가상 주소 공간: 12KB 차지 (4KB × 3 view)
  ★ 어느 view로 읽어도 같은 데이터
  ★ MMU가 자동으로 색→view 라우팅
```

---

#### 6.3.5 pmap 함정 — 왜 ZGC가 RSS의 3배로 보이나

##### 함정의 원리

```
pmap의 동작:
  각 VMA(mmap된 영역)의 크기를 ★단순 합산★
  같은 물리 페이지가 여러 가상 주소에 매핑된 것을 ★구분 못 함★

ZGC의 매핑:
  100GB Heap → 3개 view로 multi-mapping
  → pmap 합산 결과: 100GB × 3 = 300GB ★거짓★
  → 실제 물리 메모리: 100GB ★진짜★
```

##### 실제로 어떻게 보이나

```
$ pmap -x <zgc-pid>
Address           Kbytes      RSS    Mode  Mapping
0x000200000000   104857600  104857600 rw--  [anon]  ← marked0 view, 100GB
0x000400000000   104857600  104857600 rw--  [anon]  ← marked1 view, 100GB
0x000800000000   104857600  104857600 rw--  [anon]  ← remapped view, 100GB
                ─────────  ─────────
                 300 GB    300 GB    ← pmap이 보고하는 가상 합계 ★거짓말★

실제 물리 메모리는 100GB ★단 한 번★ 사용됨
```

`/proc/<pid>/status`의 `VmRSS`나 cgroup의 `memory.usage_in_bytes`는 OS 커널이 페이지 단위로 카운팅 → 100GB로 정확히 보고.

##### 측정 도구별 진실/거짓 표

| 도구 | ZGC 100GB Heap을 어떻게 보고? | 신뢰 가능? |
|------|---------------------------|----------|
| **pmap (Kbytes 합)** | ~300GB | ❌ 거짓 (가상 주소 합) |
| **pmap (RSS 합)** | ~300GB | ❌ 거짓 (같은 페이지 중복 카운트) |
| **top RSS** | ~100GB | ✅ 진짜 (커널이 페이지 단위) |
| **/proc/pid/status VmRSS** | ~100GB | ✅ 진짜 |
| **cgroup memory.usage** | ~100GB | ✅ 진짜 (컨테이너 메트릭) |
| **smaps의 PSS (Proportional)** | ~100GB | ✅ 진짜 (공유 페이지를 나눠 카운팅) |
| **NMT** | ~100GB Heap | ✅ JVM 시점에서 정확 |

##### 운영 사고 시나리오

```
1. 알람 규칙: "pmap 출력이 -Xmx의 2배 넘으면 메모리 누수"
2. 누군가 G1 → ZGC로 GC 바꿈
3. 다음날 알람 전부 빨강
4. 새벽에 호출됨
5. 실제로는 멀쩡함, ZGC multi-mapping 때문

→ 교훈: ★알람은 cgroup/RSS 기준으로★ — pmap 가상 합계 기준 알람은 즉시 폐기
```

##### smaps로 진실 보기 (참고)

```bash
$ cat /proc/<pid>/smaps | grep -E "Size|Rss|Pss"
Size:           104857600 kB   ← 이 VMA의 가상 크기
Rss:            104857600 kB   ← 매핑된 물리 (중복 포함)
Pss:             34952533 kB   ← 비례 분할 (3 view면 1/3)
```

**PSS(Proportional Set Size)**가 multi-mapping을 정확히 처리 — 공유된 페이지를 view 수로 나눠 카운팅. ZGC 측정 시 RSS 대신 PSS 보는 것도 한 방법.

---

#### 6.3.6 ZGC Forwarding Table — 객체 이동을 STW 없이

**한 줄 본질**: ZGC가 객체를 옛 region에서 새 region으로 복사할 때, **옛 주소 → 새 주소 매핑을 region별 작은 hash table에 보관**. mutator가 옛 주소로 접근하면 load barrier가 forwarding table을 보고 새 주소로 redirect.

##### 왜 필요한가

```
G1의 Evacuation:
  STW로 멈춤 → 살아있는 객체를 다른 region에 복사 → 모든 포인터 갱신 → STW 해제
  ★문제: 살아있는 객체가 많으면 STW가 길어짐 (수십~수백 ms)

ZGC의 Relocation:
  ★STW 없이★ 객체를 새 region에 복사 (concurrent)
  포인터 갱신은? → 다 안 갱신해도 됨. forwarding table이 다리 역할
  나중에 lazy하게 (다음 cycle에) 진짜 포인터 갱신
```

##### 동작

```
1. region A의 객체 X를 region B로 복사
   - A의 forwarding table에 기록: "X의 옛 주소 → X의 새 주소(B 안)"
   - 복사 자체는 concurrent (mutator 안 멈춤)

2. mutator가 옛 주소(A 안)로 X에 접근하려 함
        ↓
   load barrier가 포인터 색깔 확인
        ↓ 색이 "remapped 아님"
   forwarding table 조회 → 새 주소 획득
        ↓
   self-healing: 들고 있던 포인터를 새 주소로 교체 (다음엔 빠른 경로)
        ↓
   X에 접근 성공

3. 모든 mutator가 새 주소로 갱신 완료되면 forwarding table 폐기
```

##### 메모리 비용

```
forwarding table:
  - region당 1개
  - 이동된 객체 수에 비례하는 작은 hash table
  - 전체 Heap 대비 < 0.1% 수준

G1의 RSet(1~20%)과 비교하면 ★압도적으로 작음★
→ ZGC가 "Heap × 1.05 메모리만" 쓰는 이유
```

---

#### 6.3.7 G1 vs ZGC 종합 비교표

| 항목 | G1 | ZGC |
|------|----|----|
| **STW 목표** | ~수십 ms | < 1 ms (객체 수 무관) |
| **적정 Heap 크기** | ~수십 GB (100GB부터 부담) | 8GB ~ 16TB |
| **영역 간 참조 추적** | Card Table + Region RSet | Colored Pointer (자동) |
| **참조 추적 메모리** | Heap × 1~20% (워크로드 의존, 폭증 위험) | < Heap × 0.1% |
| **Mark Bit 위치** | 별도 Mark Bitmap × 2 (Heap × 3%) | 포인터 비트 자체 |
| **Barrier 종류** | Write barrier (SATB pre + Card post) | Load barrier (read 시) |
| **Mutator 오버헤드** | 5~15% (write-heavy) | 비슷하거나 약간 낮음 (read-heavy에 비례) |
| **Evacuation** | STW pause | 100% Concurrent (forwarding table) |
| **물리 메모리 footprint** | Heap × 1.05 ~ 1.2 | Heap × 1.05 |
| **가상 주소 footprint** | Heap × 1.05 ~ 1.2 | **Heap × 3 ~ 4** (multi-mapping) |
| **pmap이 거짓 보고?** | 아니오 | **예** (위 함정) |
| **Generational 지원** | 처음부터 | JDK 21+ (Generational ZGC) |

---

#### 6.3.8 운영 관점 — 언제 ZGC를 선택하나

##### ZGC가 답인 상황

```
✅ Heap > 100GB
✅ P99 latency가 비즈니스 SLA (예: 광고 입찰, 트레이딩, 실시간 게임)
✅ G1에서 RSet 폭증 시나리오 발생 (RSS가 Heap의 1.3배 이상)
✅ 컨테이너 환경 + RSS 기반 알람으로 모니터링 가능
```

##### G1이 여전히 나은 상황

```
✅ Heap < 32GB, throughput 중심 (배치, 데이터 파이프라인)
✅ 워크로드가 sparse cross-region (RSet 작음)
✅ 운영 도구 체인이 pmap/proc 가상 주소 기반 → ZGC로 가면 알람 다 깨짐
✅ JDK 버전이 ZGC 안정화 이전 (< JDK 15) — 더 이상 거의 해당 없음
```

##### 마이그레이션 체크리스트 (G1 → ZGC)

```
1. JDK 21+ 확인 (Generational ZGC 권장)
2. -XX:+UseZGC 옵션
3. ★알람/모니터링 도구 점검★
   - pmap 가상 합계 기준 알람 → RSS/PSS 기반으로 교체
   - cgroup memory.usage 기반 알람은 그대로 유효
4. 컨테이너 메모리 limit는 -Xmx의 1.1배 정도면 충분 (G1처럼 1.3배 잡을 필요 X)
5. -Xlog:gc로 STW 시간 검증 (< 1ms 확인)
6. JFR로 read barrier 비용 측정 (mutator 영향 비교)
```

---

#### 6.3.9 핵심 한 줄 정리

> **ZGC는 colored pointer + multi-mapping + forwarding table 조합으로 "객체 수와 무관한 sub-ms STW"를 달성한다. 한 물리 페이지를 색깔별로 여러 가상 주소에 매핑하기 때문에 pmap의 가상 주소 합계는 실제 메모리의 3~4배로 부풀려 보이지만, RSS/PSS/cgroup 메트릭은 정확하다. 운영에서는 알람을 반드시 RSS 기반으로 두고, G1 → ZGC 전환 시 모니터링 도구의 가상/물리 구분을 먼저 점검해야 한다.**

### 6.4 키워드 3 — 기타 JVM 내부 영역 (Symbol/String/CLD)

| 영역 | 용도 | 메모리 |
|---|---|---|
| **Symbol Table** | 클래스/메서드 이름 등 internalized symbol, native hash table | 수 MB~200MB |
| **String Table** | `String.intern()` 결과 (JDK 7+ Heap의 hashtable) | `-XX:StringTableSize`로 버킷 수 조정 |
| **ClassLoaderDataGraph** | 모든 CLD의 linked list, CLD당 수 KB | CLD 누수 시 GB |
| **JIT Scratch** | C1/C2 컴파일 중 임시 사용, 컴파일 끝나면 free | 수십 MB |
| **JVMTI/JFR Buffers** | 모니터링 도구, JFR 기본 ~50MB | |
| **Reserved JVM Internal** | 디버그 정보, perf data 등 | 수십~수백 MB |

**Symbol Table 폭주 시나리오**:
- 환경: 동적 클래스 생성 많은 앱 (Mockito, ASM).
- 증상: NMT의 Symbol 항목이 시간 지나면서 ↑.
- 진단: `jcmd VM.symbols | head -20`.
- 원인: dynamic proxy/lambda가 매번 새 symbol 생성, ClassLoader unload 안 되면 symbol도 정리 안 됨.
- 조치: `-Xlog:class+unload`로 unload 확인, ClassLoader 누수 패턴 점검 (→ 02-metaspace 참조).

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Card Table이 뭔가요?" | ② Card Table | ① WHY (왜 필요) |
| "RSet 메모리 변동 이유?" | ③ RSet | ⑤ Write barrier (Card Queue) |
| "Concurrent Mark 정확성은?" | ④ Mark Bitmap + SATB | ⑤ Write barrier (pre-barrier) |
| "Write barrier가 뭐? 비용?" | ⑤ Write Barrier | ③ RSet (Card Queue) |
| "ZGC의 colored pointer?" | ⑥ ZGC 특수 | ⑤ Write barrier (가벼움) |
| "100GB Heap RSS 130GB 진단?" | ⑥ 운영 (Killer) | ③ RSet |
| "Symbol Table 누수?" | ⑥ 기타 | 02-metaspace |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 → 듣는 사람 표정 보고 인접 가지로**

예: "RSet 메모리가 워크로드에 따라 왜 크게 변하나요?"

> "GC bookkeeping은 GC 시간을 메모리와 교환하는데, 그 중 RSet은 G1의 region별 'cross-region 참조 추적' 자료구조입니다. (← 루트)
> 첫째, 한 region마다 'R을 가리키는 ref가 어느 region 어느 card에 있나' 목록을 유지합니다.
> 둘째, **3-tier 자료구조**로 entry 수에 따라 Sparse(작은 hash table) → Fine(region bitmap) → Coarse(단일 비트 압축)로 promote됩니다.
> 셋째, cross-region 참조 밀도에 직접 비례 — 가벼운 워크로드는 Heap의 1~3%, dense graph 워크로드는 **10~20%, 극단은 50% 가까이**.
> `-Xlog:gc+remset=info`로 fine→coarse transition 빈발 확인하고, 조치는 region 크기 ↑(`-XX:G1HeapRegionSize=32m`)나 캐시 크기 제한, 100GB 이상이면 ZGC 마이그레이션."

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. Card Table이 무엇이고 왜 필요한가요?

> Heap을 512B 단위 카드로 나눈 1바이트 표시판 배열. Young GC 시 Old→Young 참조를 효율적으로 찾기 위해 — Old gen 전체 스캔 대신 dirty card만 스캔.
> 동작: ① mutator가 `obj.field = ref`. ② JIT가 자동 삽입한 post-write barrier가 주소를 카드 인덱스로 변환. ③ `card_table[idx] = dirty`. ④ Young GC 시 dirty 카드 안의 ref만 확인.
> 메모리: Heap의 약 0.2% (1/512).

**🪝 Q1-1: Card Table의 한계는 무엇이고 G1은 어떻게 보완했나요?**
> Card Table은 Heap 전체 단위 — Old gen 100GB면 카드 200M개. Dirty 비율 1%여도 2M 카드 스캔. G1의 RSet: region별 "어디서 가리키나" 정확한 목록 유지, precision 훨씬 높음. 단 RSet은 메모리 사용량이 워크로드 따라 크게 변동 (1~20%).

### Q2 [가지 ③]. Remembered Set이 워크로드에 따라 메모리가 크게 변하는 이유는?

> RSet 크기 = cross-region 참조 수에 비례. Sparse 워크로드(캐시 위주): 1~3%. Dense(graph): 10~20%. 극단: 50%까지.
> G1의 RSet은 3-tier: Sparse table → Fine-grained → Coarse(bitmap 압축). entry 수 증가에 따라 자동 promote.
> 진단: `-Xlog:gc+remset=info`의 fine→coarse transition 빈발이 cross-region 폭증 신호.
> 조치: region 크기 ↑(`-XX:G1HeapRegionSize=32m`) → region 수 ↓ → RSet 수 ↓, 캐시 크기 제한.

### Q3 [가지 ④]. SATB queue가 무엇이고 왜 필요한가요?

> Snapshot-At-The-Beginning — concurrent marking이 정확성을 보장하기 위한 메커니즘. 문제: marking 중 mutator가 ref를 변경하면 결과가 잘못될 수 있음. 해결: pre-write barrier가 변경 직전의 옛 값을 SATB queue에 enqueue → marking thread가 처리. 즉 marking 시작 시점의 snapshot 유지. 트레이드오프: 정확성 ↑, 일부 dead 객체가 이번 cycle엔 못 회수(다음 cycle로) — **floating garbage**.

**🪝 Q3-1: SATB와 Incremental Update의 차이는?**
> SATB (G1, Shenandoah): Marking 시작 시 snapshot 유지, pre-write barrier로 옛 값 보존. 정확성 강함, floating garbage 있음.
> Incremental Update (CMS, 제거됨): Mutator 변경을 incremental하게 반영, post-write barrier로 새 값 알림. 다시 marking pass 필요할 수 있음 — STW 길어질 위험. 현대 GC는 SATB로 수렴.

### Q4 [가지 ⑥]. ZGC의 multi-mapping이 무엇이고 pmap이 왜 3배 보고하나요?

> ZGC는 colored pointer를 위해 한 물리 메모리 페이지를 3개 가상 주소에 매핑 (marked0, marked1, remapped). 객체 포인터의 고위 비트에 색(state)을 인코딩 — 어느 매핑을 통해 접근할지 결정.
> 결과: 물리 메모리 1배(실제 RSS), 가상 주소 공간 3배. `pmap` 같은 가상 주소 합산 도구는 3배로 보고. Container의 RSS 메트릭은 정확히 1배.
> 운영: pmap 기준 알람은 ZGC에서 잘못 동작 — RSS 기준으로 측정.

### Q5 [가지 ⑤]. Write Barrier 비용이 어느 정도이고 어떻게 측정하나요?

> Write barrier는 매 ref 쓰기에 추가되는 명령(~3~10개): Card Table 표시(post), SATB queue enqueue(pre, G1), Cross-region 체크 + Card Queue(G1), Read barrier(ZGC, Shenandoah).
> 비용: Ref 쓰기 많은 코드(list 구축)는 5~15% 처리량 ↓. 산술 위주 코드는 거의 0%.
> 측정: JMH 벤치마크, JFR `jdk.ThreadCPULoad`, async-profiler로 native code 분포 확인.

### Q6 (Killer) [가지 ⑥]. -Xmx 100GB JVM의 RSS가 130GB. Heap 외 30GB가 어디서?

> 100GB Heap이면 native 부속이 큼:
> 1. **GC 부속 자료구조**:
>    - Card Table: 200MB.
>    - Mark Bitmap × 2: 3GB.
>    - **RSet: 5~20GB ← 가장 큰 변동**.
>    - 합: 8~24GB.
> 2. **기타**: Metaspace 200MB~2GB, Code Cache 240MB, Thread Stacks 500MB, Direct, Internal 500MB.
> 진단: `jcmd VM.native_memory summary` 각 항목 합산. `-Xlog:gc+remset=info`로 RSet 추세.
> 30GB 중 정상 예상은 10~15GB. 15GB 이상이면 RSet 폭증 의심. 조치: region 크기 ↑, 캐시 크기 제한, **ZGC/Generational ZGC 검토** (100GB는 G1에 부담).

**🪝 Q6-1: 100GB 이상 Heap에서 G1 vs ZGC 선택 기준?**
> G1: ~수십 GB Heap, STW 수십 ms, RSet 메커니즘이 cross-region 폭증 시 비대화 위험, write barrier 무거움. ZGC: TB까지, STW <10ms, colored pointer로 region 사이 추적 자동, read barrier 사용. **100GB 이상 + low latency = ZGC**. 100GB 이하 + 처리량 중심 = G1.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: Generational GC의 Old→Young 추적 문제, "시간을 메모리와 교환" 사상
- [ ] 가지 ② Card Table: 512B 카드, Heap/512, dirty card만 스캔, JDK 8+ 조건부 write
- [ ] 가지 ③ RSet: 3-tier (Sparse/Fine/Coarse), 워크로드 따라 1~20% 변동, region 크기 조정
- [ ] 가지 ④ Mark Bitmap: Heap/64, G1은 prev/next 2개, ZGC는 colored pointer로 대체
- [ ] 가지 ④ SATB: pre-write barrier, floating garbage, vs Incremental Update
- [ ] 가지 ⑤ Write Barrier: pre/post barrier 자동 삽입 + Card Queue 비동기
- [ ] 가지 ⑤ Write Barrier: mutator 5~15% overhead, GC별 무거움 차이
- [ ] 가지 ⑥ ZGC multi-mapping + colored pointer + pmap 3배 함정
- [ ] 가지 ⑥ 100GB Heap RSS 130GB 진단 절차
- [ ] 8장 꼬리질문 6개에 막힘없이 답한다

---

## 다음 단계

본 챕터(02-runtime-data-areas)의 모든 sub-chapter 완료. 다음은 다른 챕터로:

- → 03-execution-engine: 인터프리터 + JIT 컴파일러 깊이 (C1/C2, Sea-of-Nodes, Escape Analysis, Inline Cache, Speculative Optimization, Loop Unrolling, Lock Coarsening 등)
- → 04-gc: GC 알고리즘 풀버전 (Serial → Parallel → CMS → G1 → ZGC → Shenandoah → Generational ZGC, SATB vs Incremental Update, Brooks vs LRB, Colored Pointer, Multi-mapping Memory)
- → 05-threading: JMM, happens-before 13규칙, Memory Barriers, synchronized Mark Word 승격, Park/Unpark native, Virtual Thread Continuation

본 챕터 다른 sub-chapter:
- ← [01. Heap & TLAB](./01-heap-and-tlab.md)
- ← [02. Metaspace & Class Space](./02-metaspace-and-class-space.md)
- ← [03. Stack & PC & Native](./03-stack-pc-native.md)
- ← [04. Code Cache](./04-code-cache.md)
- ← [05. Direct Memory](./05-direct-memory.md)

## 참고

- **JVMS §2.5 (Run-Time Data Areas)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5
- **HotSpot `cardTable.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/cardTable.cpp
- **HotSpot `g1RemSet.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1RemSet.cpp
- **HotSpot `g1ConcurrentMark.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1ConcurrentMark.cpp
- **HotSpot `satbMarkQueue.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/satbMarkQueue.cpp
- **G1 Tuning Guide (Oracle)**: https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html
- **ZGC: A Scalable Low-Latency Garbage Collector**: Per Liden, JavaOne 발표
- **Shenandoah GC Paper**: Christine Flood et al. 2016
- **JEP 333 ZGC**: https://openjdk.org/jeps/333
- **Aleksey Shipilëv — GC Internals Deep Dives**: https://shipilev.net/jvm/anatomy-quarks/
