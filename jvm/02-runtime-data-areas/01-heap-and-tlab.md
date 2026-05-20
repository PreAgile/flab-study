# 02-01. Heap & TLAB — 객체가 살고 죽는 곳

> JVM에서 `new`를 호출하면 객체가 **어디에, 어떤 알고리즘으로** 할당되는가?
> 답: **Eden 안의 TLAB에서 bump-the-pointer로 3 instruction**. lock 한 번 없이.
> 이게 Java가 C++ `new`보다 빠른 이유 — 그리고 GC가 일을 더 해야 하는 이유.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Heap은 모든 스레드가 공유하는 객체 메모리이고, Weak Generational Hypothesis에 따라 Young/Old로 나뉘며, Young Eden에서 TLAB을 통해 lock-free bump-the-pointer 할당을 한다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: Heap = 공유 객체 메모리, 세대로 나뉨]
                                    │
       ┌─────────┬──────────────┬───┴───┬──────────────┬─────────┐
       │         │              │       │              │         │
      ① WHY    ② WHAT         ③ HOW   ④ 객체         ⑤ 운영    ⑥ 진화
   세대 가설   세대 구조       TLAB    Header       (시니어)   (역사)
       │         │              │       │              │         │
       │    ┌────┼────┐     ┌───┼───┐  ┌─┼─┐      ┌────┼────┐    │
    80~98%  Young Old     bump  refill  Mark Klass  -Xmx  jstat  PermGen→
    일찍죽음 Eden/S0/S1   3instr filler  Word Ptr   NewR   NMT   Metaspace
    Copying  Mark-Sweep   lock-  retire  age  Comp  Surv   JFR   G1→ZGC
    vs M-S   Promotion    free          lock  Oops  Ratio        Gen-ZGC
                          Humongous
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 세대 가설** | Weak Generational Hypothesis | Copying vs Mark-Sweep | 죽은 객체 비용 0 |
| **② WHAT 세대 구조** | Young(Eden/S0/S1) | Old(Tenured) | Promotion/Tenuring |
| **③ HOW TLAB 할당** | bump-the-pointer 3 instr | retire & refill + filler | Humongous (G1) |
| **④ 객체 Header** | Mark Word (state별) | Klass Pointer | Compressed Oops 32GB |
| **⑤ 운영** | -Xmx/NewRatio/SurvivorRatio | jstat / heap dump / NMT | OutsideTLAB 진단 |
| **⑥ 진화** | PermGen → Metaspace | G1 → ZGC | Generational ZGC (JDK 21) |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — 왜 세대로 나누는가

### 1.1 핵심 질문

> "JVM은 왜 Heap을 Young/Old로 나누고, 알고리즘도 다르게 쓸까요?"

### 1.2 키워드 1 — Weak Generational Hypothesis

> **"대부분의 객체는 일찍 죽는다."**

실측 데이터: Java 앱 객체의 **80~98%가 첫 GC를 못 넘긴다**. (HTTP request scope의 임시 객체, 임시 String, 박싱된 Integer 등)

이 한 줄짜리 가설이 generational GC 전체의 기반:
- 짧게 사는 다수 → 자주 청소 (작업량 적음, 살아있는 객체가 적으니 처리 비용 작음)
- 오래 사는 소수 → 가끔 청소 (대부분 살아있어 효율 낮으니 모아서 처리)

### 1.3 키워드 2 — Copying vs Mark-Sweep (영역별 알고리즘 선택)

> **이사 비유**:
> - **Mark-Sweep (Old)**: 방 안에서 쓰레기를 **하나하나 찾아 버린다**. 비용 ∝ 쓰레기 수.
> - **Copying (Young)**: 살릴 물건 몇 개만 **새 방으로 들고 나간다**. 원래 방? **통째로 폭파**. 비용 ∝ 살릴 물건 수.

| | Young (살아있는 게 1~20%) | Old (살아있는 게 80~95%) |
|---|---|---|
| 죽은 객체 비율 | 매우 높음 (80~99%) | 낮음 (5~20%) |
| Copying 쓰면? | 죽은 다수를 **아예 안 만짐** → 압도적 효율 | 살아있는 다수를 거의 다 복사 → 비효율 |
| Mark-Sweep 쓰면? | 죽은 다수를 일일이 free list 등록 → 낭비 | 살아있는 건 그대로, 죽은 것만 처리 → 효율 |
| 선택 | **Copying** | **Mark-Sweep (+Compact)** |

### 1.4 키워드 3 — Copying GC는 죽은 객체를 "지우지" 않는다

**가장 흔한 오해**: "GC가 죽은 객체를 메모리에서 지운다." 틀림.

```
Copying GC의 실제 동작:
  1. 살아있는 소수를 다른 영역(S0↔S1)으로 옮긴다
  2. 원래 영역(Eden)은 "없는 셈" 친다 — top 포인터를 start로 되돌림
  3. 죽은 객체의 비트는 그대로 남아있음
  4. 다음 new 호출 시 그 위에 덮어써질 뿐

→ 죽은 객체에 대해 GC가 한 일 = 0. 만지지도 않음.
```

> "청소를 잘하는 것"이 아니라 "**청소 안 해도 되게 만드는 것**"이 Copying의 본질.

**대신 단점**: 메모리를 2배 써야 함 (복사 대상 공간 S0/S1 필요). 그래서 Survivor는 Young의 10%씩만.

### 1.5 비유로 굳히기

> **호텔 비유**:
> - **Eden** = 로비. 신규 투숙객 다 들어옴. 회전율 매우 높음.
> - **Survivor (S0/S1)** = 임시 객실. 며칠 더 머물 사람들. 정기적 청소.
> - **Tenured (Old)** = 장기 투숙. 충분히 머물러 옮긴 사람. 청소 드물지만 큰 일.
> - **TLAB** = 각 직원이 미리 받아둔 객실 키 묶음. 본부 요청 없이 자기 묶음에서 바로 줌.
> - **Humongous** = 단체 짐 — 한 객실에 못 들어가는 큰 짐. 별도 객실 통째.

---

## 2. 가지 ②: WHAT — Heap의 세대 구조

### 2.1 핵심 질문

> "Heap을 그려보세요. 각 영역의 비율과 객체 흐름은?"

### 2.2 키워드 1 — Young Generation (Eden / S0 / S1)

```
Young Generation 100%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│←──────────  80%  ──────────→│←─ 10% ─→│←─ 10% ─→│
│             Eden              │   S0    │   S1    │
│  (신규 할당, TLAB들이 여기)    │ (active)│ (empty) │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                  ↑          ↑
                                  Minor GC마다 active 토글
                                  (S0 → S1 또는 S1 → S0)
```

**비율 제어**:
- `-XX:NewRatio=2` → Old : Young = 2 : 1 (Young은 전체의 1/3)
- `-XX:SurvivorRatio=8` → Eden : S0 : S1 = 8 : 1 : 1

### 2.3 키워드 2 — Old Generation (Tenured)

- Young에서 충분히 살아남은 객체가 이동.
- Major/Full GC 대상.
- 알고리즘: Mark-Sweep + Compact (또는 GC별 변형).
- G1의 경우 region 단위 (1~32MB).
- Humongous Object (G1, region 크기 ≥ 50%) → Old gen에 직접 할당.

### 2.4 키워드 3 — Minor GC 흐름 (Promotion / Tenuring)

```
[GC 직전]
Eden:  [A][B][C][D][E][F][G][H]      ← B, E만 살아있음
S0:    [X][Y]                         ← 이전 GC에서 옮겨온 살아있는 애들 (active)
S1:    [              ]               ← 비어있음 (대기조)
Old:   ████████                       ← 일부 사용

       │ Minor GC 시작 (STW)
       ▼

[Step 1] Root에서 reachable 추적 (Mark)
         - B, E, X, Y 살아있다고 판정
         - 죽은 객체(A,C,D,F,G,H)는 추적조차 안 함 ★ 비용 0

[Step 2] 살아있는 애들을 S1에 복사 (Copy)
         - 새 주소에 복사본 생성, 모든 참조도 새 주소로 갱신
         - age 카운터 +1
         - age > MaxTenuringThreshold (기본 15) 면 S1 대신 Old로 promote
S1:    [B'][E'][X'][Y']

[Step 3] Eden과 S0를 통째로 "버림" (Reclaim)
         - 죽은 객체를 명시적으로 지우지 않음 ★
         - top 포인터를 start로 되돌리기만

       │ STW 끝
       ▼

[GC 직후]
Eden:  [                      ]       ← 즉시 재사용 가능
S0:    [                      ]
S1:    [B'][E'][X'][Y']               ← active 토글됨
Old:   ████████◇◇                     ← promote된 객체 추가
```

**동적 Tenuring Threshold**:
- Object Header의 age 필드(4비트)에 카운터.
- Survivor가 자주 차면 threshold 자동 하향 (premature promotion 위험)
- 너무 자주 promote하면 Old 압박 → Full GC 위험.

---

## 3. 가지 ③: HOW — TLAB을 통한 lock-free 할당

### 3.1 핵심 질문

> "`new Foo()`를 호출하면 정확히 어떤 일이 일어나나요?"

### 3.2 키워드 1 — bump-the-pointer 3 instruction

```
TLAB (스레드별, Eden 안에 위치)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  start                                              end
   ▼                                                  ▼
   ┌─────────────────────┬───────────────────────────┐
   │ 이미 할당된 객체들    │      미사용 (free)         │
   └─────────────────────┴───────────────────────────┘
                          ▲
                          top (bump pointer)
```

HotSpot 코드 (`threadLocalAllocBuffer.hpp`):
```cpp
HeapWord* allocate(size_t size) {
  HeapWord* obj = _top;
  HeapWord* new_top = _top + size;
  if (new_top <= _end) {
    _top = new_top;     // ★ 단 한 줄로 할당 완료
    return obj;          // ★ lock 없음
  }
  return NULL;          // TLAB full, slow path로
}
```

→ **3 instruction (load, add, compare-and-branch)**. lock 없음, 99% 케이스.

**왜 TLAB이 필요한가**: TLAB 없으면 모든 스레드가 `Eden.top`을 동시에 갱신하려고 CAS 경합 → 함수 호출만큼 빈번한 객체 할당이 직렬화됨.

### 3.3 키워드 2 — TLAB이 가득 찼을 때 (retire & refill + filler)

```
TLAB.allocate(size) 실패 (new_top > _end)
                │
        ┌───────┴───────┐
        ▼               ▼
  남은 공간 크면        남은 공간 작으면
        │               │
        ▼               ▼
  [경로 A]              [경로 B]
  Eden 직접 할당        TLAB Retire & 새 TLAB
  (Slow Path, CAS)     (Refill)
                       │
                  남은 공간을 filler object로 채움
                  (Heap walking 일관성)
                  → 새 TLAB을 Eden에서 받아옴 (CAS)
```

**filler object의 정체**: TLAB의 남은 자투리를 그냥 두면 GC가 Heap walking할 때 "여기 무슨 객체가 있나" 혼란. 더미 `int[]`로 채워 명시적 dead 처리. (`CollectedHeap::fill_with_object`)

**Eden 전체가 가득 차면** → Minor GC 트리거 (STW 10~50ms).

### 3.4 키워드 3 — Humongous Object (G1 전용 함정)

G1은 Heap을 region(1~32MB)으로 나눔. **region 크기의 50% 이상**인 객체는 Humongous로 분류:

```
Region 크기 = 4MB
   일반 객체: ≤ 2MB           Humongous: > 2MB
   ┌─────────────────┐         ┌─────────────────┐
   │ Region 안에      │         │ Region 통째     │
   │ 여러 개 들어감    │         │ 차지            │
   └─────────────────┘         └─────────────────┘
                               + 연속된 추가 region도 점유
```

**문제점 3가지**:
1. **Old gen 직접 할당** — Young GC 건너뜀, 일찍 죽어도 회수 늦음.
2. **연속 region 점유** — 4MB region에 5MB 객체면 region 2개, 1개는 일부만 사용 (낭비).
3. **Fragmentation** — 큰 Humongous region 분포가 흩어지면 연속 공간 부족.

**진단**: `-Xlog:gc+humongous=debug`, JFR `jdk.G1HeapRegionTypeChange`
**회피**: startup에 큰 배열 미리 할당하고 재사용, `-XX:G1HeapRegionSize` 조정.

### 3.5 bump-the-pointer가 malloc보다 빠른 본질적 이유

```
malloc / free                         TLAB bump-the-pointer
━━━━━━━━━━━━━━━━━                   ━━━━━━━━━━━━━━━━━━━━━━
- free list에서 빈 공간 찾기          - GC가 통째 청소 → free list 불필요
- best-fit / first-fit 탐색            - 단순 포인터 증가
- 인접 chunk merge (frag 방지)         - fragmentation 신경 안 씀 (Copying이 압축)
- 헤더에 size, status 기록
→ 수십~수백 instruction               → 3 instruction
```

→ **GC가 정리를 책임지니까 할당이 무지 단순해질 수 있다.** Java/Go/C# 같은 GC 언어가 C/C++보다 할당이 빠른 이유. 대신 그 비용을 GC가 묶어서 한 번에 지불.

---

## 4. 가지 ④: 객체 Header — 객체의 신분증

### 4.1 핵심 질문

> "Java 객체 하나가 메모리에서 정확히 어떤 모양인가요? lock 상태는 어디에 저장되나요?"

### 4.2 키워드 1 — Mark Word (상태 기계)

```
객체 메모리 레이아웃 (64-bit, Compressed Oops):
┌──────────────────┬──────────────┬──────────────────┐
│ Mark Word (8B)    │ Klass Ptr(4B)│ Fields ...       │
└──────────────────┴──────────────┴──────────────────┘
   ↓ Mark Word는 객체 상태에 따라 의미가 달라짐:

Unlocked:    hash code + age + lock bits
Biased:      소유 thread id + epoch (JDK 15 이전)
Lightweight: lock record 포인터
Heavyweight: monitor 포인터
GC marked:   forwarding pointer (Copy 후 새 주소)
```

→ 하나의 8바이트가 **lock 상태, hash, GC age, forwarding** 모두를 시점별로 담는 다중 용도. Java 동기화부터 GC까지 전부 여기서 출발.

### 4.3 키워드 2 — Klass Pointer

- 객체의 클래스 메타데이터(`InstanceKlass*`)를 가리킴.
- Metaspace의 Compressed Class Space에 위치.
- 이걸 따라가야 method dispatch, type check, reflection 모두 가능.
- 4B (compressed) / 8B (uncompressed).

### 4.4 키워드 3 — Compressed Oops & 32GB의 벽

```
일반 64-bit oop:    [────────── 8 bytes ──────────]
Compressed oop:     [── 4 bytes ──]
                    실제 주소 = base + (compressed_oop << 3)
                                                ↑ shift 3 = 8바이트 정렬
```

- **활성 조건**: Heap < 32GB. (4GB × 8바이트 정렬 = 32GB 표현 가능)
- **자동 결정**: `-XX:+UseCompressedOops` (기본 on, JDK 6u23+)
- **장점**: 메모리 ~30% 절감, 캐시 효율 ↑
- **단점**: 32GB 이상 Heap에서 자동 비활성 → 갑자기 메모리 사용 증가

> **"32GB의 벽"** — Heap을 32GB 넘기면 갑자기 footprint가 커진다. 31GB가 32GB 이상보다 더 효율적인 역설.

**Compressed Class Pointer**도 같은 사상. Metaspace의 별도 영역 Compressed Class Space (기본 1GB). Spring Boot처럼 Class 수 많은 앱에서 1GB 한계가 OOM:Metaspace 원인이 되기도.

---

## 5. 가지 ⑤: 운영 — 시니어 진단

### 5.1 핵심 질문

> "실무에서 Heap/GC 관련 문제를 어떻게 진단하고 해결하나요?"

### 5.2 키워드 1 — 핵심 옵션 트레이드오프

**`-Xmx` (최대 Heap 크기)**:

| 작게 | 크게 |
|---|---|
| Footprint 작음, 컨테이너 친화 | Footprint 큼, container limit 압박 |
| Full GC 자주, OOM 위험 | Full GC 드물게, burst 견딤 |

**경험칙**: container limit의 50~70%. **32GB는 절대 안 넘김**. `-Xms = -Xmx` (동적 resize는 hiccup 유발).

**`-XX:NewRatio` (Young vs Old 비율)**:

| Young 크게 | Young 작게 |
|---|---|
| Minor GC 드물게, 한 번에 길게 | Minor GC 자주, 짧게 |
| Premature promotion 위험 적음 | Survivor 충분 |

**`-XX:SurvivorRatio` (Eden vs Survivor)**: 기본 8 (`E:S0:S1 = 8:1:1`). `-XX:ResizeTLAB` (기본 on)이 동적 조정.

### 5.3 키워드 2 — 진단 도구 4단계

**① jstat — 실시간 모니터링**:
```bash
jstat -gc <pid> 1s
# S0C S1C S0U S1U  EC EU  OC OU  MC MU  YGC YGCT FGC FGCT
```
판독: `EC/EU` = Eden Capacity/Used, `YGC` = Young GC 횟수, `YGCT` = 누적 시간.

**② Heap dump — 사후 분석**:
```bash
jcmd <pid> GC.heap_dump /tmp/heap.hprof
# 또는 OOM 시 자동 dump
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/ -jar app.jar
# 분석: Eclipse MAT, VisualVM
```

**③ NMT — Heap 밖 영역까지**:
```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <pid> VM.native_memory summary
```
영역별 reserved/committed 비교. RSS 큰데 Heap 정상일 때 핵심.

**④ JFR — 할당 패턴**:
```bash
jcmd <pid> JFR.start name=alloc settings=profile duration=60s filename=alloc.jfr
```
핵심 이벤트:
- `jdk.ObjectAllocationInNewTLAB` — TLAB 가득 차서 새 TLAB
- `jdk.ObjectAllocationOutsideTLAB` — TLAB 우회, Eden 직접 (★ 많으면 문제)
- `jdk.G1HeapRegionTypeChange` — Humongous 추적

### 5.4 키워드 3 — 운영 시나리오 매트릭스

| 증상 | 진단 명령 | 가능한 원인 |
|---|---|---|
| `OutOfMemoryError: Java heap space` | heap dump + MAT | 메모리 누수, Heap 부족 |
| Full GC 매분 발생 | `jstat -gc 1s`, GC log | Old gen 압박, premature promotion |
| Young GC가 너무 길다 | `-Xlog:gc+phases=debug` | Heap 너무 큼, Survivor 부족 |
| P99 latency 튐 | JFR `jdk.GarbageCollection` | STW 길이 vs 목표 |
| RSS는 큰데 Heap은 작음 | `jcmd VM.native_memory` | Metaspace/Direct Memory/Code Cache |
| `OutsideTLAB` 폭증 | JFR allocation profile | 큰 객체 빈번 할당 |
| Container OOM-killed | NMT + container limit | Heap 외 영역 폭증 |

### 5.5 Killer 시나리오 — "OutsideTLAB이 많이 나옵니다"

**원인 후보**:
1. 큰 객체 빈번 할당 — `byte[]`, `String.toCharArray()`, JSON 파싱 임시 객체
2. TLAB 크기가 allocation rate를 못 따라감

**진단 절차**:
```bash
asprof -e alloc -d 30 -f alloc.html <pid>
# alloc.html flame graph로 hot allocation path 식별
```

**조치**:
- 큰 배열을 startup에 미리 할당 + 재사용 (object pool 패턴)
- `-XX:MinTLABSize`, `-XX:TLABSize` 미세 조정
- 박싱 제거 (`int[]` 대신 `List<Integer>` 안 쓰기)

### 5.6 안티패턴

```java
// ❌ 1. 핫 루프에서 거대한 임시 배열
byte[] tmp = new byte[10_000_000];  // 10MB
// → TLAB 우회, Eden 직접 (CAS 경합)
// → Pretenuring (Old 직행) → Full GC 위험

// ❌ 2. 핫 루프에서 박싱
for (int i = 0; i < 1_000_000; i++) {
    list.add(i);  // int → Integer
    // → 100만 개 작은 객체 → TLAB refill 잦음
}

// ❌ 3. 객체 풀 (요즘은 거의 안티패턴)
// TLAB가 너무 빨라서 풀 큐의 동기화 비용이 더 큼.
// Escape Analysis가 stack allocation 못 함.
// 예외: DB connection처럼 자원 자체가 비싼 경우만 OK.
```

---

## 6. 가지 ⑥: 진화 — Heap의 역사

### 6.1 핵심 질문

> "JDK 8에서 PermGen이 왜 죽었고, ZGC는 왜 처음엔 generational이 아니었나요?"

### 6.2 키워드 1 — PermGen → Metaspace (JDK 8)

**옛 PermGen의 문제**:
1. **크기 고정** — `-XX:MaxPermSize=256m` 미리 잡아야 함. 동적 클래스 생성 많은 앱(Spring AOP, Hibernate proxy, Mockito)에서 `OutOfMemoryError: PermGen space` 빈발.
2. **GC 비효율** — Heap 안의 generation이라 GC 정책에 끼어들고, ClassLoader unload가 비효율.
3. **Compressed Oops 충돌** — Klass 포인터 압축에 PermGen 위치가 제약.

**JDK 8 해결**:
- **Metaspace**: Heap 밖 native 메모리, 기본 무제한
- **String Pool**: Heap의 일반 영역으로 이동 → 일반 GC가 처리
- **Compressed Class Space**: Klass 포인터 압축용 별도 영역

→ 자세한 건 [02. Metaspace & Class Space](./02-metaspace-and-class-space.md).

### 6.3 키워드 2 — GC의 진화 (Serial → G1 → ZGC)

| 연도 | 릴리스 | 변화 |
|---|---|---|
| 1996 | JDK 1.0 | Serial GC, generational Heap |
| 2002 | JDK 1.4 | Parallel GC (Young Gen 병렬) + CMS (응답 시간) |
| 2009 | JDK 6u14 | Compressed Oops |
| 2012 | JDK 7u4 | G1 GC (실험) — region 기반 |
| 2014 | JDK 8 | **PermGen 제거 → Metaspace**, String Pool → Heap |
| 2017 | JDK 9 | **G1을 default GC**로 (Parallel 대체) |
| 2018 | JDK 11 | ZGC 실험 (Heap 16TB, sub-ms pause) |
| 2020 | JDK 14 | **CMS 제거** (Concurrent Mode Failure + G1 완성) |
| 2020 | JDK 15 | ZGC production-ready |
| 2023 | JDK 21 | **Generational ZGC** |

### 6.4 키워드 3 — Generational ZGC (JDK 21)의 의미

처음 ZGC는 single-gen이었음 — 모든 시나리오 균등하게 다루려고. 그러나:

| 워크로드 | Generational GC | Single-gen ZGC |
|---|---|---|
| 일반 웹 (객체 짧게 산다) | ★ 매우 효율 | △ 비효율 |
| 분석 작업 (대용량 오래 산다) | △ Old 압박 | ★ 효율 |
| 캐시 서버 (객체 절반 영구) | △ Survivor 빨리 가득 | ★ 효율 |

→ JDK 21 Generational ZGC: weak generational hypothesis를 ZGC도 활용. 양쪽 다 노림. **결국 "대부분의 객체는 일찍 죽는다"가 모든 모던 GC의 기반이 됨**.

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Heap 구조 설명해보세요" | ② WHAT | ① WHY (세대 이유) |
| "Young/Old 알고리즘 차이?" | ① WHY | ② WHAT (구조) |
| "TLAB이 뭐고 왜 필요한가요?" | ③ HOW | ⑤ 운영 (OutsideTLAB 진단) |
| "객체 Header에 뭐가 있나요?" | ④ Header | ① Mark Word의 lock 진화 |
| "Compressed Oops 왜 32GB?" | ④ Header | ⑤ 운영 (Heap 크기 결정) |
| "PermGen이 왜 죽었나요?" | ⑥ 진화 | 02 문서로 |
| "Humongous Object 문제?" | ③ HOW (G1) | ⑤ 운영 (회피) |
| "RSS는 큰데 Heap 정상" | ⑤ 운영 (NMT) | 03 문서 (Thread) |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 → 듣는 사람 표정 보고 인접 가지로**

예: "TLAB이 뭐고 왜 필요한가요?"

> "Heap은 모든 스레드 공유라 lock 경합이 문제인데, JVM은 Eden 안을 스레드별로 잘라 TLAB을 줍니다. (← 루트)
> 첫째, **bump-the-pointer**로 3 instruction (load, add, branch)에 할당 끝, lock 없음.
> 둘째, TLAB이 가득 차면 **retire & refill** — 남은 자투리를 filler object(`int[]`)로 채워 GC walking 일관성 유지하고 새 TLAB CAS로 받아옴.
> 셋째, **Humongous Object**처럼 TLAB 우회 케이스도 있음 — G1에서 region 50% 이상 객체는 Old 직행.
> 그래서 `OutsideTLAB` 이벤트가 JFR에서 많이 나오면 큰 객체 빈번 할당이 hot path인지 점검합니다."

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. Heap의 구조를 설명하세요.

> Young Generation + Old Generation. Young = Eden + S0 + S1 (기본 8:1:1). 새 객체는 Eden 할당, Minor GC에서 살아남으면 Survivor → 충분히 살면 Old로 promote. G1에서는 region 단위, region 크기 50% 이상은 Humongous로 Old 직행. JDK 8부터 PermGen은 Metaspace(native)로 이동.

**🪝 Q1-1: Eden:S0:S1 = 8:1:1인 이유는?**
> Survivor를 너무 크게 잡으면 Eden이 작아져 Minor GC가 잦아짐. 너무 작으면 살아남은 객체를 다 못 담아 premature promotion. 8:1:1이 generational hypothesis(80% 이상 일찍 죽음)와 실측 분포 사이의 균형점.

**🪝🪝 Q1-1-1: Survivor 비율 조정이 의미 있나요?**
> 워크로드 의존. 단명 객체 많으면 Survivor 작아도 됨. 중기 객체 많으면 키워야 함. 진단: `-XX:+PrintTenuringDistribution` 또는 JFR `jdk.GCSurvivorAge`. JVM 동적 조정이 대부분 잘 되므로 측정 후에만 튜닝.

### Q2 [가지 ③]. TLAB이 무엇이고 왜 필요한가요?

> Thread-Local Allocation Buffer. Eden 안에서 각 스레드가 미리 확보한 작은 영역. lock 없이 bump-the-pointer 3 instruction에 할당. 없으면 모든 스레드가 Eden.top을 동시 갱신 → CAS 경합으로 할당 직렬화. 기본 크기는 JVM 자동 조정 (수십 KB ~ 수 MB).

**🪝 Q2-1: TLAB이 가득 차면 어떻게 되나요?**
> 두 경로: ① **Retire & Refill** — 자투리를 filler object로 채우고 새 TLAB을 Eden에서 CAS로 받음. ② **Slow Path** — 객체 하나만 Eden에 직접 할당. 남은 공간 비율과 객체 크기 휴리스틱으로 결정.

**🪝🪝 Q2-1-1: filler object가 왜 필요하나요?**
> GC가 Heap walking할 때 일관된 객체 경계를 가정. TLAB 남은 공간을 그냥 두면 메모리 내용을 모름. `int[size]` dummy로 채우면 "여긴 dead int 배열" 로 인식하고 건너뜀. HotSpot `CollectedHeap::fill_with_object`.

### Q3 [가지 ③]. Humongous Object가 뭐고 왜 운영 함정인가요?

> G1에서 region 크기의 50% 이상인 큰 객체. 일반 객체와 달리 **Old gen 직접 할당** → Young GC 안 거침. 문제: ① 일찍 죽어도 회수 늦음, ② 연속 region 점유로 낭비(4MB region에 5MB 객체면 region 2개), ③ Fragmentation. 진단: `-Xlog:gc+humongous=debug`. 회피: startup에 미리 할당 + 재사용, `-XX:G1HeapRegionSize` 조정.

**🪝 Q3-1: ZGC에서도 Humongous 개념이 있나요?**
> ZGC는 region이 아닌 **page** 단위 (Small 2MB / Medium 32MB / Large 동적). Large page는 한 페이지에 한 객체 — G1 Humongous와 비슷한 처리. 큰 객체 fragmentation 위험은 유사.

### Q4 [가지 ④]. Object Header에는 무엇이 들어있나요?

> Mark Word (8B) + Klass Pointer (4B/8B). Mark Word는 객체 상태에 따라 의미가 달라짐: Unlocked는 hash+age+lock bits, Biased는 thread id+epoch, Lightweight Lock은 lock record 포인터, Heavyweight Lock은 monitor 포인터, GC marked는 forwarding pointer. Klass Pointer는 객체의 클래스 메타데이터(InstanceKlass) 위치.

**🪝 Q4-1: Compressed Oops가 뭐고 왜 Heap 32GB까지만?**
> 64-bit JVM에서 객체 참조를 32-bit로 압축. 실제 주소 = base + (oop << 3). shift 3은 8바이트 정렬. 4GB × 8 = 32GB까지 표현. 그 이상이면 자동 비활성 → 갑자기 footprint 증가 ("32GB의 벽"). 31GB에서 안 죽으면 31GB가 32GB 이상보다 효율.

**🪝🪝 Q4-1-1: Klass Pointer도 압축되나요?**
> Yes. **Compressed Class Pointer**. Metaspace 안에 별도 **Compressed Class Space** (기본 1GB). `-XX:CompressedClassSpaceSize`로 조정. Spring Boot처럼 Class 수 많은 앱에서 1GB 한계가 OOM:Metaspace 원인이 되기도.

### Q5 [가지 ⑥]. PermGen이 왜 죽고 Metaspace가 도입됐나요?

> PermGen 문제: ① 크기 고정 → 동적 클래스 생성 많은 앱에서 OOM 빈발, ② Heap 안의 generation이라 ClassLoader unload 비효율, ③ Compressed Oops와 충돌. Metaspace 해결: Heap 밖 native, 기본 무제한, ClassLoaderData 단위 chunk 할당 → CL unload 시 통째 free, String Pool은 Heap으로.

### Q6 (Killer) [가지 ⑤]. -Xmx2g인데 RSS 4GB. 진단 절차?

> 단계:
> 1. **NMT 활성화**: `java -XX:NativeMemoryTracking=summary`, `jcmd VM.native_memory summary`
> 2. **영역별 committed 확인**: Java Heap / Class (Metaspace + CCS) / Thread (스레드 × 1MB) / Code Cache / GC / Internal
> 3. **일반 분포**: Heap 2GB + Metaspace 200MB + Code Cache 240MB + Threads 500MB (500스레드) + Direct Memory + GC bookkeeping ≈ 3.5~4GB
> 4. **비정상이면**: Metaspace 비대 → ClassLoader 누수 / Direct Memory 비대 → DirectBuffer 누수 / Thread 비대 → 스레드 수 폭증
> 5. 컨테이너 환경이면 limit의 50~70%로 `-Xmx` 설정.

**🪝 Q6-1: NMT의 reserved vs committed 차이?**
> reserved = JVM이 OS에 "이 가상 주소 공간 우리 거" 표시, 실제 메모리 사용 아님. committed = 실제 물리 메모리 매핑, RSS에 잡힘. Heap `-Xmx4g`면 reserve 4GB, committed는 -Xms ~ 현재 사용량. `top`의 VSZ ≈ reserved, RSS ≈ committed.

### Q7 (패턴 통찰) [가지 ③]. TLAB 사상이 다른 어디서 반복되나요?

> "비싼 동기화 영역화" — 자원을 N개로 나눠 lock-free 빠른 길을 깔고, 가끔만 묶어 동기화. **HW (cache line, NUMA) → OS (per-CPU 카운터, slab magazine) → JVM (TLAB) → 라이브러리 (LongAdder, ThreadLocalRandom) → DB (InnoDB partition) → MQ (routing key) → 분산 (consistent hashing)**. 이게 **mechanical sympathy** (Martin Thompson) — HW 동시성 한계를 이해하고 그 결을 따라 SW를 짜는 사고방식.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: Weak Generational Hypothesis와 Copying vs Mark-Sweep 선택 이유를 설명
- [ ] 가지 ① WHY: "Copying GC는 죽은 객체를 만지지 않는다"를 그림과 함께 설명
- [ ] 가지 ② WHAT: Young/Old 비율(NewRatio=2)과 Eden:S0:S1(8:1:1)을 그린다
- [ ] 가지 ② WHAT: Minor GC 흐름 (Mark → Copy → Reclaim) 단계별로 추적
- [ ] 가지 ③ HOW: bump-the-pointer 3 instruction과 TLAB retire/refill을 코드 수준으로 설명
- [ ] 가지 ③ HOW: Humongous Object의 3가지 문제와 진단 명령
- [ ] 가지 ④ Header: Mark Word의 상태별 의미와 Compressed Oops 32GB 벽
- [ ] 가지 ⑤ 운영: jstat / heap dump / NMT / JFR 4단계 진단 도구 매핑
- [ ] 가지 ⑤ 운영: -Xmx 2g인데 RSS 4GB 진단 5단계
- [ ] 가지 ⑥ 진화: PermGen → Metaspace 전환 이유 3가지, Generational ZGC의 의미
- [ ] 8장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [02. Metaspace & Class Space](./02-metaspace-and-class-space.md): PermGen 죽음의 풀버전, ClassLoaderData
- → [03. Stack & PC & Native](./03-stack-pc-native.md): Per-thread 영역
- → [04. Code Cache](./04-code-cache.md): JIT 결과 저장소
- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO
- → [06. GC Bookkeeping](./06-gc-bookkeeping-and-others.md): Card Table, RSet, Mark Bitmap

## 참고

- **JVMS §2.5 (Run-Time Data Areas)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5
- **HotSpot Glossary - Heap**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
- **JEP 122 (Remove PermGen)**: https://openjdk.org/jeps/122
- **G1 GC Tuning Guide**: https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html
- **HotSpot `threadLocalAllocBuffer.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/threadLocalAllocBuffer.hpp
- **HotSpot `g1CollectedHeap.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1CollectedHeap.cpp
- **async-profiler**: https://github.com/async-profiler/async-profiler
- **Eclipse MAT**: https://www.eclipse.org/mat/
