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

```
ZGC의 한 물리 메모리 페이지 (예: 4KB):
                                        가상 주소 공간
                                        ━━━━━━━━━━━
                                        marked0 view  ← 4KB의 가상 주소 #1
[Physical: 4KB] ───┬─── mapping 1 ──── marked1 view  ← 4KB의 가상 주소 #2
                   ├─── mapping 2 ──── remapped view ← 4KB의 가상 주소 #3
                   └─── mapping 3 ────

객체 포인터의 고위 비트로 어느 view인지 인코딩 (colored pointer)
물리 메모리는 1번이지만 RSS 측정 도구에 따라 3번 보일 수 있음
```

**ZGC vs G1 비교**:
| | G1 | ZGC |
|---|---|---|
| 적정 Heap | ~수십 GB | TB까지 |
| STW 목표 | ~수십 ms | < 10ms |
| 영역 간 참조 추적 | region당 RSet (폭증 위험) | colored pointer (자동) |
| Write barrier | 무거움 (SATB + Card + Cross-region) | 가벼움, read barrier 사용 |
| 메모리 footprint | Heap × 1.05~1.2 | Heap × 1.05 (가상은 3배) |

**ZGC pmap 함정**: pmap이 가상 주소 합산해서 3배로 보고. Container의 RSS 메트릭은 정확히 1배. **pmap 기준 알람은 ZGC에서 잘못 동작** — RSS 기준으로 측정.

**ZGC Forwarding Table**:
- 한 region의 살아있는 객체들을 다른 region으로 이동 시, 옛 주소 → 새 주소 매핑을 보관.
- 다른 스레드가 옛 주소로 접근 시 read barrier가 잡아서 새 주소로 forward.
- 메모리: 매우 작음. 한 region당 작은 hash table.

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
