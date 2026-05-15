# 02-06. GC Bookkeeping & 기타 JVM 내부 — 보이지 않는 메모리

> Heap이 100GB라면 GC를 위한 부속 자료구조는 얼마를 차지하는가?
> 답: Card Table은 Heap의 약 **0.2%**, Mark Bitmap은 **1.5%**, G1의 Remembered Set은 워크로드 따라 **5~20%까지 폭증**. 100GB Heap이면 RSet만 5~20GB를 native에 더 쓴다.
> "왜 100GB Heap을 잡았는데 RSS가 120GB?" 같은 질문의 답은 이 챕터에 있다.
> 그리고 GC 자료구조의 크기는 옵션(region 크기, marking bitmap density)에 직접 좌우된다 — 옵션 한 줄이 수 GB를 좌우.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 모두 답할 수 있다.

1. **Card Table**이 무엇이고 왜 필요한지 — Generational GC의 "Old → Young 참조" 추적.
2. Card Table의 메모리 footprint 공식 — `Heap / 512` (한 카드당 512바이트).
3. **Remembered Set (RSet)** 이 G1에서 무엇을 하는지 — region 간 참조 추적.
4. RSet의 메모리 footprint가 워크로드에 따라 **수십 배 변동**하는 이유 (cross-region 참조 밀도).
5. **Mark Bitmap** — concurrent marking이 객체별 mark bit를 native에 저장하는 메커니즘. footprint 공식 `Heap / 64`.
6. **SATB queue / Card queue** — Write barrier가 비동기로 정보를 모으는 큐 구조.
7. **ZGC의 Forwarding Table** — colored pointer를 위한 보조 자료구조.
8. JIT scratch, Symbol Table, String Table, ClassLoaderDataGraph 등 **JVM 내부 잡다한 영역**들이 차지하는 메모리.
9. 큰 Heap 환경에서 RSet 비대화로 STW 길어지는 운영 시나리오와 진단 방법.
10. `jcmd VM.native_memory summary` 의 GC 항목과 Other 항목을 분해 해석하는 능력.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: Heap과 그 부속 자료구조의 관계

- 좌측에 큰 박스 [Java Heap (예: 100GB)].
- 우측에 작은 박스들 — GC 부속 자료구조들. 모두 native 메모리.

### Step 2: 각 자료구조와 Heap의 매핑

```
[Java Heap, 100GB]              [GC Bookkeeping (native)]

  ┌─────────────────┐           ┌────────────────────────┐
  │ Young Gen        │ ◄────────│ Card Table (200MB)     │
  │ ├ Eden           │           │ 한 카드 = 512B Heap    │
  │ ├ S0 / S1        │           └────────────────────────┘
  │                  │
  │ Old Gen          │           ┌────────────────────────┐
  │                  │ ◄────────│ Remembered Set (variable)│
  │ Region들 (G1)    │           │ 한 region당 RSet 1개    │
  │                  │           │ cross-ref 따라 0~∞     │
  │                  │           └────────────────────────┘
  │                  │
  │                  │           ┌────────────────────────┐
  │                  │ ◄────────│ Mark Bitmap (~1.5GB)    │
  │                  │           │ 객체당 1 bit (8B 단위)   │
  └─────────────────┘           └────────────────────────┘
```

### Step 3: Write Barrier가 채우는 queue들

```
[사용자 코드]
obj.field = otherObj;
        │
        ▼
  Write Barrier (JIT가 자동 삽입)
        ├─ pre-barrier: SATB queue에 옛 값 enqueue (concurrent marking용)
        └─ post-barrier: Card Table 표시 + Card queue (G1의 cross-region ref)
                │                       │
                ▼                       ▼
        ┌──────────┐            ┌────────────────┐
        │ SATB Q   │            │ Card Q         │
        │ (스레드별) │            │ (스레드별)      │
        └──────────┘            └────────────────┘
              │                          │
              │ 가득 차면                  │ 가득 차면
              ▼                          ▼
        Concurrent Marking         Refinement thread가
        thread가 처리              RSet 갱신
```

### 정답 그림 (ASCII)

```
JVM Process Memory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Java Heap, -Xmx 100GB]                [Native: GC 부속 자료구조]
                                       
   ┌───────────────┐                   ┌──────────────────────────────┐
   │ Young + Old   │                   │ Card Table  ~200MB           │
   │  + Humongous  │ ◄─── 가리킴 ──────│  (Heap/512)                  │
   │                │                   ├──────────────────────────────┤
   │  region들      │ ◄─── 가리킴 ──────│ Remembered Set ~1~20GB        │
   │                │                   │  (per-region, dense ↑)       │
   │                │                   ├──────────────────────────────┤
   │                │ ◄─── 표시 ────────│ Mark Bitmap ~1.5GB             │
   └───────────────┘                   │  (Heap/64)                   │
                                       ├──────────────────────────────┤
                                       │ SATB Queue / Card Queue       │
                                       │  (스레드별, 임시 버퍼)         │
                                       ├──────────────────────────────┤
                                       │ Symbol/String Table 등        │
                                       │  (수십~수백 MB)               │
                                       └──────────────────────────────┘

총 GC bookkeeping footprint:
  - G1 + 100GB Heap + 평균 워크로드: 약 3~5GB
  - G1 + cross-region 참조 많음: 10~20GB까지
  - ZGC + 100GB Heap: 약 5~7GB (colored pointer + mark bitmap × 2)
```

---

## 🧠 2단계: 직관

### 핵심 비유

> **도서관 색인 비유**:
> - **Java Heap** = 모든 책의 본문.
> - **Card Table** = "이 책장(예: 512페이지 단위)에 변경된 표시가 있나" 라는 작은 sticker. 큰 책장 통째 확인 안 하고 sticker만 본다.
> - **Remembered Set** = "이 책장에 다른 책장의 어떤 책이 인용된 페이지 목록". 인용이 많을수록 목록도 비대.
> - **Mark Bitmap** = "이 책이 살아있나 죽었나" 표시판. 책 한 권당 1비트.
> - **SATB Queue** = 책 수정 작업장에서 변경 전 원본을 잠시 보관하는 임시 폴더 (concurrent marking이 정확성 보장 위해).

### 정확한 정의 (비유와 분리)

| 용어 | 정의 |
|---|---|
| **Card Table** | Heap을 512바이트 단위 "카드"로 나눈 1바이트짜리 표시판 배열. 한 카드에 변경이 일어나면 그 카드의 byte를 dirty로 표시. Young GC가 Old gen 전체 스캔 안 하고 dirty card만 확인. |
| **Remembered Set (RSet)** | G1의 region별 자료구조. "이 region을 가리키는 ref가 어느 다른 region 어디에 있나"의 목록. Young GC + Mixed GC 시 사용. |
| **Mark Bitmap** | concurrent GC(G1/ZGC/Shenandoah)가 사용. 각 객체 위치에 대응하는 1 bit로 mark 상태 추적. Heap의 1/64 (객체 align 8B 기준). |
| **SATB (Snapshot-At-The-Beginning) Queue** | concurrent marking 중 발생한 mutator의 ref 변경을 GC에 알리는 큐. pre-write barrier가 옛 값을 enqueue. |
| **Card Queue / DCQ (Dirty Card Queue)** | G1의 post-write barrier가 dirty card 정보를 모으는 큐. Refinement thread가 비동기로 RSet에 반영. |
| **Forwarding Table** | ZGC/Shenandoah가 객체 이동(evacuation) 시 옛 주소 → 새 주소 매핑 보관. |
| **Symbol Table** | JVM이 클래스/메서드 이름 등 internalized 문자열을 보관. Hash table. native 메모리. |
| **String Table** | Java 코드의 interned String을 보관. JDK 7부터 Heap의 hashtable. |
| **Write Barrier** | mutator의 ref 쓰기 시 JIT/Interpreter가 자동 삽입하는 추가 코드. GC에 변경 알림. |

### 왜 이런 부속 자료구조가 필요한가 — Generational GC의 본질적 문제

```
Generational GC의 가정:
  Young Gen은 자주 청소, Old Gen은 가끔 청소

Young GC 시 reachability를 정확히 계산하려면:
  GC Roots (Stack/Static)에서 따라가는 객체 + ★ Old → Young 참조도 살아있어야

문제:
  Old gen이 100GB라면 매번 100GB 전부 스캔? → Young GC가 Major GC만큼 비싸짐 → 의미 없음

해결:
  ★ 정보를 미리 모아두자 ★

  방법 1: Card Table
    - Heap을 카드 단위로 나누고 "이 카드에 변경 있었나" 표시
    - Young GC 시 dirty card만 스캔 → 빠름
    
  방법 2: Remembered Set (G1)
    - region별로 "어디서 나를 가리키나" 목록
    - region 단위 수집에서 핵심
```

→ Bookkeeping은 **GC 시간을 메모리와 교환**하는 trade-off. 항상 메모리 ↑ + GC 시간 ↓.

### 왜 Write Barrier가 자동 삽입되나

```java
// 사용자 코드
obj.field = newObj;
```

JIT/Interpreter는 이 라인을 컴파일할 때 다음을 추가:

```
// 사용자가 작성한 본문
store obj.field, newObj;

// JIT가 자동 삽입 (G1 GC 기준)
if (G1Marking_in_progress) {       // pre-barrier
    old_value = load obj.field;
    enqueue_SATB(old_value);        // 옛 값을 marking queue에
}
mark_card_dirty(obj.field_addr);    // post-barrier
if (different_region(obj, newObj)) {
    enqueue_card(card_addr);         // RSet 갱신용 큐
}
```

→ 사용자 입장에선 보이지 않지만 **모든 ref 쓰기마다 추가 명령 ~3~10개**. 이게 GC가 정확한 정보를 유지하는 비용.

**Write Barrier 비용** (워크로드 영향):
- 메서드 호출당 ref 쓰기 비율이 높은 코드 (예: 리스트 구축)에서 5~15% 처리량 저하.
- ZGC의 read barrier는 read마다 → 더 비싸지만 STW 거의 없음.
- 트레이드오프: barrier 비용 vs STW 시간.

---

## 🔬 3단계: 구조

### Card Table 동작 원리

```
Heap (예: 1GB)
━━━━━━━━━━━
한 카드 = 512바이트
카드 수 = 1GB / 512 = 2,097,152개
각 카드당 1바이트 표시

Card Table (메모리 점유):
  2,097,152 bytes = 2MB
  → Heap의 0.195% (1/512)

각 byte의 값:
  0x00 = clean (변경 없음)
  0xFF = dirty (변경 발생)
  기타 = G1의 경우 transition 상태 (young/dirty/etc.)
```

#### Card Table 동작 예시

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
       // 이 512B 영역 안의 Old gen 객체들의 ref를 모두 확인
       scan_old_gen_region(i * 512, (i+1) * 512);
     }
   }
   // dirty card만 스캔 — Old gen 100GB 중 0.1%만
```

#### Card Table의 한계 (G1 도입 동기)

```
시나리오: Old gen 100GB, 매우 sparse한 cross-ref
  - 100GB / 512 = 200M card
  - 그 중 1%만 dirty → 2M card 스캔
  - 2M card × 512B = 1GB 영역을 매번 Young GC가 스캔 → 여전히 느림

G1의 해결: Remembered Set
  - card 단위 표시 대신 region별 "어디서 가리키나" 정확한 목록
  - precision 높음 → 스캔 영역 ↓
```

### Remembered Set (RSet) — G1의 핵심

```
G1 Heap: 2048개 region (한 region = 1~32MB)

각 region마다 자기만의 RSet:
  region_R의 RSet = "R을 가리키는 ref가 어느 region의 어느 card에 있나"

자료구조 진화 (entry 수에 따라):
  - 적음 (~256): Sparse RSet — 작은 hash table
  - 중간 (~수천): Fine-grained — region 단위 bitmap
  - 많음: Coarse — "이 region 전체가 나를 가리킨다" 단일 비트로 압축
```

#### RSet의 크기 변동

```
한 region이 다른 region 100개에 의해 가리킴
  → 각 referencing region마다 card 목록 (보통 수십 ~ 수백)
  → 총 RSet 크기: 수십 KB ~ 수 MB

전체 Heap의 RSet 합:
  - 가벼운 워크로드 (cache 위주, 참조 sparse): Heap의 1~3%
  - 일반 (mixed): Heap의 3~5%
  - 무거운 (graph-heavy, 참조 dense): 10~20% 이상
  - 극단 (잘못 튜닝): 50% 가까이 → 운영 사고
```

#### RSet 비대화의 운영 시나리오

```
증상:
  - Young GC pause가 점점 길어짐 (50ms → 500ms)
  - Heap은 그대로인데 RSS가 증가

원인:
  - Cross-region 참조 폭증 (예: 큰 cache + 매번 새 Young 객체 참조)
  - 또는 region 크기가 작아 region 수 폭증 (RSet 수 ↑)

진단:
  jcmd <pid> GC.heap_info
  # 또는 JFR jdk.G1HeapRegionInformation
  
  -Xlog:gc+remset=info
  # output:
  # [gc,remset] Concurrent refinement: 145ms total
  # [gc,remset] RSet sparse->fine transitions: 1234
  # [gc,remset] Coarse RSet: 5678

조치:
  - -XX:G1HeapRegionSize=32m (region 크기 ↑ → region 수 ↓ → RSet 수 ↓)
  - -XX:+UseStringDeduplication (중복 String 줄여 cross-ref 감소)
  - 애플리케이션 코드 audit (cache 크기 제한)
```

### Mark Bitmap (concurrent marking용)

```
객체 정렬: 8바이트
Bitmap: 객체당 1 bit

Mark Bitmap 크기:
  Heap 크기 / 64 (8B 정렬 가정)
  
  예: 100GB Heap → 1.5GB bitmap

G1은 사실 ★ Mark Bitmap을 2개 ★ 유지:
  - prev bitmap: 지난 marking cycle 결과
  - next bitmap: 현재 marking cycle 작업 중
  → 총 3GB

ZGC는 mark bit를 객체 헤더의 colored pointer에 저장 → 별도 bitmap 작음
```

#### Concurrent Marking 진행

```
1. Initial Mark (STW, very short)
   GC Roots에서 직접 가리키는 객체들을 next bitmap에 mark
        │
        ▼
2. Concurrent Mark (사용자 코드와 동시)
   - 마킹된 객체에서 reachable한 것들을 재귀 마킹
   - 동시에 mutator는 ref 변경
   - 그 변경을 SATB queue로 모음
        │
        ▼
3. Remark (STW, short)
   - SATB queue 처리 - mutator 변경분도 반영
   - prev ↔ next bitmap swap
        │
        ▼
4. Cleanup (STW + concurrent)
   - 죽은 객체 회수, 빈 region을 free
```

### SATB Queue — Snapshot-At-The-Beginning

**왜 SATB인가**:
- Concurrent marking 중 mutator가 ref를 변경하면 "이미 마킹된 객체가 사실 도달 불가능"이 될 수도, "아직 안 마킹된 객체가 사실 도달 가능"이 될 수도.
- SATB는 **marking 시작 시점의 객체 그래프 snapshot**을 유지 — 그 시점에 살아있던 객체는 죽었어도 이번 cycle은 살아있다고 본다 (다음 cycle에 회수).

**Pre-write barrier**:
```java
obj.field = newObj;
        │
        ▼ JIT 삽입
old_value = obj.field;
if (concurrent_marking_active && old_value != null) {
    SATB_queue.enqueue(old_value);   // "이 값이 곧 lost되므로 마킹해 두라"
}
obj.field = newObj;
```

→ 옛 값(`old_value`)이 이후 다른 곳에서 더 이상 reachable이 아니어도 이번 marking cycle은 살아있는 것으로 간주.

**Card Queue (DCQ)** — G1 전용 post-write barrier:
- ref 변경 시 dirty card 정보를 큐에 push.
- **Refinement thread**가 비동기로 큐 처리 → RSet 갱신.
- 이렇게 비동기로 처리하지 않으면 매번 RSet 직접 갱신 = 비용 큼.

### ZGC의 Forwarding Table

```
ZGC의 evacuation:
  - 한 region의 살아있는 객체들을 다른 region으로 이동
  - 이동 시 옛 주소 → 새 주소 매핑을 Forwarding Table에 기록
  - 다른 스레드/메서드가 옛 주소로 접근 시 read barrier가 잡아서 새 주소로 forward
```

**메모리**: 매우 작음. 한 region당 작은 hash table.

**Multi-mapping**:
- ZGC는 colored pointer를 위해 한 region을 가상 메모리에 3번 mapping (mark0, mark1, remapped).
- 실제 물리 메모리는 1번이지만 가상 주소는 3개 — RSS에는 1번만 카운트.

### 기타 JVM 내부 메모리 영역

```
Symbol Table:
  - 모든 internalized symbol (클래스 이름, 메서드 이름, descriptor)
  - native hash table
  - 일반 앱: 수 MB ~ 수십 MB
  - 클래스 수 많은 앱 (Spring Boot 거대): 100~200MB

String Table:
  - String.intern() 결과 보관
  - JDK 7+부터 Heap의 일반 영역
  - 크기 제한: -XX:StringTableSize (해시 버킷 수)
  - 거대 String pool 시 collision 증가 → 성능 저하

ClassLoaderDataGraph:
  - 모든 CLD의 linked list
  - CLD당 작은 메모리 (수 KB)
  - CLD 수 폭증 시 (ClassLoader 누수) 수 GB

JIT Scratch:
  - C1/C2가 컴파일 중 임시 사용
  - 컴파일 끝나면 free
  - 수십 MB

JVMTI/JFR Buffers:
  - 모니터링 도구가 사용
  - JFR: 기본 ~50MB 버퍼

Reserved JVM Internal:
  - 디버그 정보, perf data 등
  - 수십 ~ 수백 MB
```

### 전체 footprint 추정 공식 (G1 기준)

```
100GB Heap 환경의 native footprint 예측:

Card Table     = 100GB / 512   = 200MB
Mark Bitmap × 2 = 100GB / 64 × 2 = 3GB
RSet (평균)    = 100GB × 5%    = 5GB         (워크로드 따라 1~20GB)
Symbol Table   = ~50MB
Internal       = ~500MB
Direct Memory  = 명시 (예: 4GB)
Code Cache     = 240MB
Metaspace      = ~500MB
Thread Stacks  = 500 × 1MB     = 500MB

총합 (Heap 외): 약 13~14GB

→ RSS = 100GB (Heap) + 14GB ≈ 114GB
```

---

## 🧬 4단계: 내부 구현 — HotSpot

### Card Table 구현

위치: `src/hotspot/share/gc/shared/cardTable.cpp`

```cpp
class CardTable : public CHeapObj<mtGC> {
private:
  CardValue* _byte_map;        // 카드 배열의 base
  size_t     _byte_map_size;   // 카드 수
  HeapWord*  _whole_heap_base; // Heap 시작 주소

  static const int card_shift = 9;  // 2^9 = 512

public:
  // Heap 주소 → 카드 인덱스
  CardValue* byte_for(const void* p) const {
    return _byte_map + (((uintptr_t)p - (uintptr_t)_whole_heap_base) >> card_shift);
  }

  // 카드를 dirty로 표시
  void dirty_card(CardValue* card) {
    *card = dirty_card_val();
  }

  // 모든 dirty 카드 순회
  void process_dirty_cards(...);
};
```

→ HeapWord 주소를 9 bit shift해서 카드 인덱스로 변환. 한 카드 = 512B.

### Remembered Set 구현 (G1)

위치: `src/hotspot/share/gc/g1/g1RemSet.cpp`, `g1RemSet.hpp`

```cpp
class HeapRegionRemSet {
private:
  // 자료구조 진화 단계
  SparsePRT   _sparse_table;       // 적은 entry
  FinePRT     _fine_grain_table;   // 중간
  CoarseRSet  _coarse_table;       // 많은 entry → bitmap으로 압축

  // 외부에서 호출하는 add 메서드
public:
  void add_reference(OopOrNarrowOopStar from, uint tid) {
    if (_sparse_table.add_card(from)) return;
    // sparse 가득 차면 fine으로 promote
    if (_fine_grain_table.add(from)) return;
    // fine도 가득 차면 coarse로
    _coarse_table.add(from);
  }

  // GC 시 RSet 스캔
  void iterate(...) {
    _sparse_table.iterate(...);
    _fine_grain_table.iterate(...);
    _coarse_table.iterate(...);
  }
};
```

→ 3-tier 자료구조. entry 수 증가에 따라 자동 promote.

### Refinement Thread (G1의 비동기 RSet 갱신)

위치: `src/hotspot/share/gc/g1/g1ConcurrentRefine.cpp`

```cpp
class G1ConcurrentRefineThread : public ConcurrentGCThread {
public:
  void run_service() {
    while (!should_terminate()) {
      // Card Queue에서 dirty card를 꺼냄
      DirtyCardQueue* dcq = ...;
      if (dcq->is_empty()) {
        wait_for_notify();
        continue;
      }
      DirtyCardEntry* entry = dcq->pop();

      // 이 card 안의 ref를 스캔
      scan_card_for_refs(entry, [&](Oop* ref) {
        // ref가 가리키는 region의 RSet에 add
        ref->target_region()->rem_set()->add_reference(ref);
      });
    }
  }
};
```

→ Application thread는 card queue에 push만, refinement thread가 비동기 처리. mutator 영향 최소화.

### Mark Bitmap (G1)

위치: `src/hotspot/share/gc/g1/g1ConcurrentMark.cpp`

```cpp
class G1CMBitMap : public CHeapObj<mtGC> {
private:
  HeapWord*  _covered_start;
  HeapWord*  _covered_end;
  size_t     _size_in_words;
  BitMapView _bm;

public:
  // 객체 마킹
  bool mark(HeapWord* addr) {
    size_t bit = addr_to_bit(addr);
    return _bm.par_at_put(bit, true);   // CAS 기반
  }

  bool is_marked(HeapWord* addr) const {
    return _bm.at(addr_to_bit(addr));
  }
};
```

→ Heap의 1/64 크기 bitmap. CAS로 thread-safe 마킹.

### SATB Pre-Write Barrier

위치: `src/hotspot/share/gc/shared/satbMarkQueue.cpp`

```cpp
// JIT가 인라인하는 코드의 의사 표현
void g1_pre_write_barrier(oop* field) {
    if (g1_marking_active()) {
        oop old_val = *field;
        if (old_val != nullptr) {
            // SATB queue에 enqueue
            JavaThread* thread = JavaThread::current();
            thread->satb_mark_queue().enqueue(old_val);
        }
    }
}
```

### Symbol Table

위치: `src/hotspot/share/classfile/symbolTable.cpp`

```cpp
class SymbolTable : public CHeapObj<mtSymbol> {
private:
  static SymbolTable*  _the_table;
  ConcurrentHashTable<...> _local_table;
  size_t               _items_count;
  size_t               _uncleaned_items_count;

public:
  static Symbol* lookup(const char* name, int len);
  static Symbol* new_symbol(const char* name, int len);
  static void unlink();  // 사용 안 되는 symbol 정리
};
```

→ Concurrent hash table 기반. CLD unload 시 그 CLD에서만 쓰던 symbol들 정리.

---

## 📜 5단계: 역사

| 연도 | 릴리스 | 변화 | 이유 |
|---|---|---|---|
| 1996 | JDK 1.0 | Mark-Sweep, 단순 마킹 | 초기 |
| 1999 | JDK 1.2 | Card Table 도입 (Serial/Parallel) | Young GC 가속 |
| 2002 | JDK 1.4 | CMS, concurrent marking + bitmap | low pause |
| 2009 | JDK 7u4+ | G1 + Remembered Set | region 기반 GC |
| 2014 | JDK 8 | Card Table 개선 (G1 fast write barrier) | mutator overhead ↓ |
| 2018 | JDK 11 | **ZGC + colored pointer + multi-mapping** | sub-ms pause |
| 2019 | JDK 12 | Shenandoah (Brooks pointer → LRB) | low pause 대안 |
| 2023 | JDK 21 | **Generational ZGC** | weak generational hypothesis 활용 |
| 2024+ | JDK 22+ | Project Lilliput (compact object header) | Heap footprint ↓ |

### Card Table 진화 — barrier 비용 최소화

JDK 8 이전: post-write barrier가 `card_table[card_addr] = dirty;` 단순 write.

JDK 8+: 조건부 write:
```
if (card_table[card_addr] != dirty) {
    card_table[card_addr] = dirty;
}
```

→ 이미 dirty면 store 안 함. cache line 무효화 회피. 처리량 5% 개선.

### G1의 RSet 비대화 문제와 해결

JDK 9까지 G1: RSet refinement thread가 mutator와 경합.
JDK 10+: refinement throughput 개선, RSet entry 수 한계 (`G1RSetUpdatingPauseTimePercent`).
JDK 17+: RSet의 메모리 효율 개선 (sparse table 압축).

### ZGC의 메모리 모델 — Multi-Mapping

```
한 물리 메모리 페이지 (예: 4KB):
                                        가상 주소 공간
                                        ━━━━━━━━━━━
                                        marked0 view  ← 4KB의 가상 주소 #1
[Physical: 4KB] ───┬─── mapping 1 ──── marked1 view  ← 4KB의 가상 주소 #2
                   ├─── mapping 2 ──── remapped view ← 4KB의 가상 주소 #3
                   └─── mapping 3 ────

객체 포인터의 고위 비트로 어느 view인지 인코딩 (colored pointer)
물리 메모리는 1번이지만 RSS 측정 도구에 따라 3번 보일 수 있음
```

→ `pmap` 같은 OS 도구가 ZGC의 메모리를 3배로 보고하는 함정. 실제 물리는 1번.

---

## ⚖️ 6단계: 트레이드오프

### Card Table 크기 vs Granularity

| Card 작게 (예: 128B) | Card 크게 (예: 4KB) |
|---|---|
| ✅ Precision 높음 (스캔 영역 ↓) | ❌ Precision 낮음 |
| ❌ Card Table 메모리 ↑ | ✅ Card Table 작음 |
| ❌ Cache line 충돌 가능 | ✅ |

JVM 기본: 512B — 균형점. 사용자 변경 거의 안 함.

### G1 Region 크기 트레이드오프

| Region 작게 (1MB) | Region 크게 (32MB) |
|---|---|
| ❌ Region 수 많음 (32K~) → RSet 수 많음 → 메모리 ↑ | ✅ Region 수 적음 (2K~) |
| ❌ 작은 객체도 humongous 될 가능성 | ✅ Humongous 거의 없음 |
| ✅ 세밀한 evacuation | ❌ 한 region 비우는 비용 ↑ |

**경험칙**: `Heap / 2048`이 일반 가이드. 1MB ~ 32MB 사이 자동 선택. 명시: `-XX:G1HeapRegionSize=Nm`.

### Mark Bitmap 정밀도 vs 메모리

- 객체 정렬 8B 기준 → bitmap이 Heap의 1/64.
- 옵션 변경 거의 안 함 (HotSpot 내부 결정).

### Write Barrier 비용 vs Concurrent 정확도

| Barrier 가벼움 (예: card table만) | Barrier 무거움 (SATB + RSet + colored) |
|---|---|
| ✅ Mutator 빠름 | ❌ Mutator 5~15% 느림 |
| ❌ Concurrent 정확도 ↓ → STW 길어질 가능성 | ✅ Concurrent 거의 완전 |
| 적합 GC: Serial/Parallel | 적합 GC: G1, ZGC, Shenandoah |

→ Latency-sensitive 시스템 (P99 < 10ms 목표)은 무거운 barrier 감수하고 ZGC/Shenandoah 선택.

---

## 📊 7단계: 측정·진단

### `jcmd VM.native_memory summary` 의 GC 항목

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <pid> VM.native_memory summary
```

```
-                        GC (reserved=5234MB, committed=5234MB)
                            (malloc=128MB #1234)
                            (mmap: reserved=5106MB, committed=5106MB)
```

→ GC 항목 = Card Table + RSet + Mark Bitmap + 기타 GC 자료구조 합. 100GB Heap이면 보통 3~7GB.

### G1 RSet 추세 모니터링

```bash
java -Xlog:gc+remset=debug -jar app.jar
# 출력 예:
# [gc,remset] Updating Remembered Set: ... 145.2ms
# [gc,remset] Concurrent refinement: 89.1ms
# [gc,remset] RSet sparse->fine transitions: 1234
# [gc,remset] RSet fine->coarse transitions: 56
```

`fine->coarse transitions`가 빈발하면 cross-region 참조 폭증 신호.

### JFR 이벤트 — GC 자료구조

```bash
jcmd <pid> JFR.start name=gc duration=300s settings=profile filename=gc.jfr
jfr summary gc.jfr | grep -iE 'G1HeapRegion|RemSet|MarkStack'
```

**핵심 이벤트**:
- `jdk.G1HeapRegionInformation` — region별 RSet 크기.
- `jdk.G1HeapRegionTypeChange` — Humongous 생성/소멸.
- `jdk.G1AdaptiveIHOP` — concurrent marking 트리거 결정.
- `jdk.GarbageCollection` — 각 GC 단계 시간 분해.

### Card Table 효율 측정 (G1)

```bash
-Xlog:gc+phases=debug

# 출력 일부:
# [gc,phases]    Scan Heap Roots (ms):  Min:  2.3, Max: 12.1, Avg:  5.4
# [gc,phases]    Update RS (ms):        Min:  0.8, Max:  3.2, Avg:  1.5
# [gc,phases]    Scan RS (ms):          Min:  1.2, Max:  8.7, Avg:  3.1
```

`Scan RS` 시간이 길어지면 RSet 비대 확인.

### `-XX:+PrintAdaptiveSizePolicy` (Parallel GC) / `-Xlog:gc+ergo` (G1)

GC 자동 튜닝 결정 추적 — heap 영역 크기 조정, marking 트리거 등.

### 운영 시나리오 진단 매트릭스

| 증상 | 진단 명령 | 가능 원인 |
|---|---|---|
| Young GC pause 갑자기 ↑ | `-Xlog:gc+phases` Scan RS 시간 | RSet 비대 |
| RSS가 Heap보다 1.2배 이상 | NMT GC 항목 + Direct Memory | RSet 폭증 + Direct 누수 복합 |
| Concurrent Mark 시간 ↑ | JFR `jdk.G1ConcurrentMark` | Heap 큰데 marking thread 적음 |
| Symbol Table 누수 | `jcmd VM.symbols` | 동적 symbol 생성 (예: dynamic proxy 폭주) |
| ZGC pmap 사용량이 Heap × 3 | ZGC multi-mapping 정상 | 가상 메모리 정상, RSS 1× |

### 시나리오 1: 큰 Heap + RSet 비대

```
환경: -Xmx 64GB, G1 GC, Spring Boot + 큰 캐시
증상: Young GC pause 50ms → 800ms (수일 지나면서)

진단:
1. -Xlog:gc+phases=debug
   "Scan RS (ms): Avg: 250" ← RSet 스캔이 대부분
2. -Xlog:gc+remset=info
   "RSet fine->coarse transitions: 12345 / hour" ← 폭증
3. jcmd <pid> VM.native_memory summary
   GC 항목: 8GB (정상 예상 3GB)

원인: 캐시(Old gen) → 새 Young 객체 참조가 매우 dense
       cross-region 참조 폭증으로 RSet 비대

조치:
- -XX:G1HeapRegionSize=32m (옛 1MB → 32MB)
  → region 수 64K → 2K로 축소 → RSet 수 ↓
- 캐시 크기 제한 (LRU eviction)
- 또는 ZGC로 마이그레이션 (RSet 메커니즘 다름)
```

### 시나리오 2: ZGC pmap 함정

```
환경: -Xmx 32GB, ZGC
증상: pmap이 96GB 사용으로 보고됨
       반면 container에서는 RSS 35GB 정도

원인: ZGC multi-mapping — 한 물리 페이지를 3번 가상 매핑
       pmap의 가상 주소 합산은 3배로 보임
       RSS (실제 물리) 는 1배

조치: 정상. 잘못된 메트릭 알람 무시. RSS 메트릭 기준으로 모니터링.
```

### 시나리오 3: Symbol Table 폭주

```
환경: 동적 클래스 생성 많은 앱 (Mockito, ASM)
증상: NMT의 Symbol 항목이 시간 지나면서 ↑

진단:
jcmd <pid> VM.symbols | head -20
# 자주 등장하는 symbol 패턴 확인

원인: dynamic proxy/lambda가 매번 새 symbol 생성
       ClassLoader unload 안 되면 symbol도 정리 안 됨

조치:
- 클래스 unload가 정상인지 확인 (-Xlog:class+unload)
- ClassLoader 누수 패턴 점검 (이전 챕터 02-metaspace 참조)
```

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. Card Table이 무엇이고 왜 필요한가요?

**예상 답변**:
> Heap을 512B 단위 "카드"로 나눈 1바이트 표시판 배열.
> Young GC 시 Old → Young 참조를 효율적으로 찾기 위해 — Old gen 전체 스캔 대신 dirty card만 스캔.
> 
> 동작:
> 1. mutator가 `obj.field = ref` 실행.
> 2. JIT가 자동 삽입한 post-write barrier가 그 주소를 카드 인덱스로 변환.
> 3. `card_table[idx] = dirty` 표시.
> 4. Young GC 시 dirty 카드 안의 ref들만 확인.
> 
> 메모리 비용: Heap의 약 0.2% (1/512).

#### 🪝 Q1-1: Card Table의 한계는 무엇이고 G1은 어떻게 보완했나요?

> Card Table은 region 단위가 아닌 Heap 전체 단위 — Old gen이 100GB면 카드 200M개. Dirty 비율 1%여도 2M 카드 스캔.
> G1의 Remembered Set: region별로 "어디서 가리키나" 정확한 목록 유지. precision 훨씬 높음.
> 단, RSet은 메모리 사용량이 워크로드 따라 크게 변동 (Heap의 1~20%).

### Q2. Remembered Set이 워크로드에 따라 메모리 사용이 크게 변하는 이유는?

**예상 답변**:
> RSet 크기 = cross-region 참조 수에 비례.
> - Sparse 워크로드 (캐시 위주, 참조 적음): Heap의 1~3%.
> - Dense 워크로드 (graph 구조, 참조 많음): 10~20%.
> 
> G1의 RSet은 3-tier:
> 1. Sparse table (적은 entry).
> 2. Fine-grained (중간).
> 3. Coarse (많은 entry → bitmap으로 압축).
> 
> 진단:
> - `-Xlog:gc+remset=info` 로 transition 횟수 확인.
> - fine→coarse transition 빈발 시 cross-region 폭증 신호.
> 
> 조치:
> - region 크기 ↑ (`-XX:G1HeapRegionSize=32m`) → region 수 ↓ → RSet 수 ↓.
> - 코드 audit (캐시 크기 제한).

### Q3. SATB queue가 무엇이고 왜 필요한가요?

**예상 답변**:
> Snapshot-At-The-Beginning — concurrent marking이 정확성을 보장하기 위한 메커니즘.
> 
> 문제: concurrent marking 중 mutator가 ref를 변경하면 marking 결과가 잘못될 수 있음.
> 
> 해결:
> - Pre-write barrier가 변경 직전의 옛 값을 SATB queue에 enqueue.
> - Marking thread가 queue를 처리 — 옛 값이 가리키던 객체도 살아있다고 간주 (이번 cycle만).
> - 즉 marking 시작 시점의 snapshot을 유지.
> 
> 트레이드오프:
> - 정확성 ↑ (concurrent도 정확).
> - 일부 dead 객체가 이번 cycle엔 못 회수 (다음 cycle로 미뤄짐) — "floating garbage".

#### 🪝 Q3-1: SATB와 Incremental Update의 차이는?

> 두 가지 concurrent marking 정확성 보장 전략:
> 
> **SATB (G1, Shenandoah)**:
> - Marking 시작 시 snapshot 유지.
> - Pre-write barrier로 옛 값 보존.
> - 정확성 강함, floating garbage 있음.
> 
> **Incremental Update (CMS — 제거됨)**:
> - Mutator의 변경을 incremental하게 marking에 반영.
> - Post-write barrier로 새 값 알림.
> - 다시 marking pass 필요할 수 있음 — STW 길어질 위험.
> 
> 현대 GC는 SATB로 수렴.

### Q4. ZGC의 multi-mapping이 무엇이고 pmap이 왜 3배 보고하나요?

**예상 답변**:
> ZGC는 colored pointer를 위해 한 물리 메모리 페이지를 3개 가상 주소에 매핑 (marked0, marked1, remapped).
> 
> 객체 포인터의 고위 비트에 색(state)을 인코딩 — 어느 매핑을 통해 접근할지 결정.
> 
> 결과:
> - 물리 메모리: 1배 (실제 RSS).
> - 가상 주소 공간: 3배.
> - `pmap` 같은 가상 주소 합산 도구는 3배로 보고.
> - Container의 RSS 메트릭은 정확히 1배.
> 
> 운영: pmap 기준의 알람은 ZGC에서 잘못 동작 — RSS 기준으로 측정해야 함.

### Q5. Write Barrier 비용이 어느 정도이고, 어떻게 측정하나요?

**예상 답변**:
> Write barrier는 매 ref 쓰기에 추가되는 명령 (~3~10개):
> - Card Table 표시 (post-barrier).
> - SATB queue enqueue (pre-barrier, G1).
> - Cross-region 체크 + Card Queue (G1).
> - Read barrier (ZGC, Shenandoah).
> 
> 비용:
> - Ref 쓰기 많은 코드 (예: list 구축): 5~15% 처리량 ↓.
> - 산술 위주 코드: 거의 0%.
> 
> 측정:
> - JMH 벤치마크로 GC 옵션별 비교.
> - JFR `jdk.ThreadCPULoad` 이벤트.
> - async-profiler로 native code의 write barrier 분포 확인.

### Q6. (Killer) -Xmx 100GB로 시작한 JVM의 RSS가 130GB입니다. Heap 외 30GB가 어디서 오는지 어떻게 진단하시겠어요?

**예상 답변**:
> 100GB Heap이면 native 부속이 큼:
> 
> 1. **GC 부속 자료구조** (NMT GC 항목):
>    - Card Table: 200MB.
>    - Mark Bitmap × 2: 3GB.
>    - RSet (G1): 5~20GB ← 가장 큰 변동.
>    - 합: 8~24GB.
> 
> 2. **기타 영역**:
>    - Metaspace: 200MB ~ 2GB.
>    - Code Cache: 240MB.
>    - Thread Stacks: 500MB.
>    - Direct Memory: 명시한 값.
>    - JVM Internal: 500MB.
> 
> 진단:
> ```
> jcmd <pid> VM.native_memory summary
> # 각 항목 합산 확인
> 
> -Xlog:gc+remset=info,gc+phases=debug
> # RSet 추세 확인
> ```
> 
> 30GB 중:
> - 정상 예상: 10~15GB (GC + Direct + 기타).
> - 비정상 (RSet 폭증 의심): 15GB 이상.
> 
> 조치:
> - RSet 폭증 시: region 크기 ↑, 캐시 크기 제한, ZGC 검토.
> - 100GB Heap 자체가 G1에 부담 — ZGC/Generational ZGC가 더 적합.

#### 🪝 Q6-1: 100GB 이상 Heap에서 G1 vs ZGC 선택 기준은?

> | | G1 | ZGC |
> |---|---|---|
> | 적정 Heap | ~수십 GB | TB까지 |
> | STW 목표 | ~수십 ms | < 10ms |
> | RSet 메커니즘 | region당 RSet (cross-ref 폭증 위험) | colored pointer (region 사이 추적 자동) |
> | Write barrier | 무거움 (SATB + Card + Cross-region) | 가벼움, read barrier 사용 |
> | 메모리 footprint | Heap × 1.05~1.2 | Heap × 1.05 (multi-mapping은 가상만) |
> 
> 100GB 이상 + low latency 목표: ZGC.
> 100GB 이하 + 처리량 중요: G1.

---

## 🔗 다음 단계

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

## 📚 참고

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
